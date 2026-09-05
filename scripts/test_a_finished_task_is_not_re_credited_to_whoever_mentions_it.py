#!/usr/bin/env python3
"""A job someone finished last week must not be re-credited to whoever
mentions it in chat today.

`applyStatus` (app/worklog.jsx) settled this rule for the whole office:
"ENTERING done, not merely being done". Its own comment spells out the
damage — an unstamped card handed `Date.now()` by an action that had
nothing to do with finishing it, "written to disk, with the true finish
time gone for good" — and
scripts/test_a_done_card_does_not_invent_a_finish_time.py pins it.

The chat marker handler in app.jsx never learned it. Its done branch
spreads its OWN stamps over applyStatus's answer:

    return { ...applyStatus(t, 'done'),
             result: upd.result || t.result || '',
             blockedReason: '', blockedAt: null,
             completedAt: Date.now(),
             completedBy: agent.id };

— unconditionally, with no check that the card was not already done. The
XP ledger beside it does check (`if (dt && dt.status !== 'done')`), and
`xpRecord`'s own comment names the exact traffic that makes this reachable:
"every double-fire path safe (an agent re-emitting [TASK_DONE:…] …)". A
coworker re-emitting a marker for a card that is already closed is not an
edge case, it is the case that guard was written for.

Reproduced in this harness against the real block lifted out of app.jsx:
a card finished by Mira at T0 and closed again by Kenji today comes back
`completedBy: 'kenji'`, `completedAt: <now>`. The DONE card then reads
"✓ Kenji finished this · just now" over a job Kenji never touched, the
real finish time overwritten and persisted — the office crediting the
wrong person on the one surface that exists to say who did the work.

The fix lets applyStatus own the timestamp (it already refuses to
re-stamp) and attaches `completedBy` only when a stamp was actually
placed, so a genuine close still names its author and a re-mention
changes nothing.

Run: python3 scripts/test_a_finished_task_is_not_re_credited_to_whoever_mentions_it.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
WORKLOG = ROOT / 'app' / 'worklog.jsx'

FAILS = []

BLOCK_START = ("setTasks(prev => prev.map(t => {\n"
               "          const upd = taskUpdates.find(u => u.id === t.id);")
BLOCK_END = "\n        }));"


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift_block():
    """The real marker-handling reducer, out of app.jsx verbatim.

    Lifted rather than restated so this test and the office run the same
    code — a paraphrase here would go on passing after the real one
    drifted."""
    src = APP.read_text(encoding='utf-8')
    i = src.find(BLOCK_START)
    if i < 0:
        return None
    j = src.find(BLOCK_END, i)
    if j < 0:
        return None
    return src[i:j + len(BLOCK_END)]


def run_js(block, cases_js):
    worklog = '\n'.join(
        ln for ln in WORKLOG.read_text(encoding='utf-8').split('\n')
        if not ln.startswith('import ') and not ln.startswith('export '))
    harness = (worklog + '\n'
               + 'function applyMarkers(prev, taskUpdates, agent, toast) {\n'
               + '  let out = null;\n'
               + '  const setTasks = (fn) => { out = fn(prev); };\n'
               + block + '\n'
               + '  return out;\n}\n')
    proc = subprocess.run(['node', '--input-type=module', '-e', harness + cases_js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('a finished task is not re-credited to whoever mentions it')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    block = lift_block()
    if block is None:
        print('  FAIL  could not find the [TASK_DONE] reducer in app.jsx')
        return 1

    out = run_js(block, r'''
const R = {};
const T0 = 1000000;
const toasts = [];
const toast = { success: (s) => toasts.push(s), warn: (s) => toasts.push(s),
                info: (s) => toasts.push(s) };
const kenji = { id: 'kenji', name: 'Kenji' };
const mira  = { id: 'mira',  name: 'Mira'  };

// ── the defect ─────────────────────────────────────────────────────────
// Mira finished this last week. Kenji's reply today re-emits the marker.
const mirasJob = { id: 't1', title: 'Ship the page', status: 'done',
                   result: 'the page', completedAt: T0, completedBy: 'mira' };
const after = applyMarkers([mirasJob],
  [{ id: 't1', action: 'done', result: '' }], kenji, toast)[0];
R.keepsWho   = after.completedBy;
R.keepsWhen  = after.completedAt;
R.keepsWhat  = after.result;
R.staysDone  = after.status;

// A card finished before anything stamped it — the record `finishedLabel`
// is built to stay silent about. A re-mention must not fill the blank in.
const legacy = { id: 't2', title: 'Old brief', status: 'done',
                 result: 'the brief' };
const afterLegacy = applyMarkers([legacy],
  [{ id: 't2', action: 'done', result: '' }], kenji, toast)[0];
R.legacyWhen = ('completedAt' in afterLegacy && afterLegacy.completedAt != null)
  ? afterLegacy.completedAt : null;
R.legacyWho  = ('completedBy' in afterLegacy && afterLegacy.completedBy != null)
  ? afterLegacy.completedBy : null;
R.legacyLabel = finishedLabel(afterLegacy, T0 + 30000);

// ── what must still happen ─────────────────────────────────────────────
// A real close stamps, and names the coworker who actually closed it.
const open = { id: 't3', title: 'Draft the memo', status: 'doing',
               assignedTo: 'mira', startedAt: T0 - 5000,
               blockedReason: 'waiting on the key', blockedAt: T0 - 4000 };
const closed = applyMarkers([open],
  [{ id: 't3', action: 'done', result: 'here is the memo' }], mira, toast)[0];
R.closeWho    = closed.completedBy;
R.closeStamps = typeof closed.completedAt === 'number' && closed.completedAt > 0;
R.closeStatus = closed.status;
R.closeResult = closed.result;
R.closeClears = closed.blockedReason === '' && closed.blockedAt === null;
R.closeAge    = 'startedAt' in closed ? closed.startedAt : null;
R.closeLabel  = finishedLabel(closed);

// A card reopened after a finish, then genuinely finished again, credits
// the coworker who did the second run.
const reopened = { id: 't4', title: 'Second pass', status: 'doing' };
const reclosed = applyMarkers([reopened],
  [{ id: 't4', action: 'done', result: 'done again' }], kenji, toast)[0];
R.reWho = reclosed.completedBy;
R.reStamps = typeof reclosed.completedAt === 'number' && reclosed.completedAt > 0;

// The other two markers are untouched by this fix.
const blocked = applyMarkers([{ id: 't5', title: 'Blocked one', status: 'doing' }],
  [{ id: 't5', action: 'blocked', note: 'no API key' }], mira, toast)[0];
R.blockedReason = blocked.blockedReason;
R.blockedStatus = blocked.status;

const progressed = applyMarkers([{ id: 't6', title: 'Moving', status: 'inbox',
                                   blockedReason: 'old snag' }],
  [{ id: 't6', action: 'progress', note: 'halfway' }], mira, toast)[0];
R.progressStatus = progressed.status;
R.progressClears = progressed.blockedReason;
R.progressLog = (progressed.progressLog || []).length;

// Cards nobody mentioned are returned untouched, by identity.
const other = { id: 't7', title: 'Untouched', status: 'inbox' };
R.identity = applyMarkers([other],
  [{ id: 'nope', action: 'done', result: 'x' }], kenji, toast)[0] === other;

// The toast never announces a completion for a card that was already done.
R.toastOnRepeat = toasts[0];
console.log(JSON.stringify(R));
''')

    print('1. a re-emitted [TASK_DONE] does not rewrite a finished record')
    check('the card still credits the coworker who finished it',
          out['keepsWho'] == 'mira', repr(out['keepsWho']))
    check('...and still carries its real finish time',
          out['keepsWhen'] == 1000000, repr(out['keepsWhen']))
    check('...and keeps the work that came back',
          out['keepsWhat'] == 'the page', repr(out['keepsWhat']))
    check('...and stays done', out['staysDone'] == 'done', repr(out['staysDone']))
    check('an unstamped finished card is not given a fabricated time',
          out['legacyWhen'] is None, repr(out['legacyWhen']))
    check('...nor a fabricated name', out['legacyWho'] is None,
          repr(out['legacyWho']))
    check('...so the card still says nothing rather than "just now"',
          out['legacyLabel'] is None, repr(out['legacyLabel']))
    check('the toast does not claim a completion that already happened',
          'completed' not in str(out['toastOnRepeat'] or ''),
          repr(out['toastOnRepeat']))

    print('2. a genuine close still records who and when')
    check('the coworker who closed it is named', out['closeWho'] == 'mira',
          repr(out['closeWho']))
    check('...with a real timestamp', out['closeStamps'] is True)
    check('...and the card reads as finished', out['closeLabel'] == 'just now',
          repr(out['closeLabel']))
    check('...in the done column', out['closeStatus'] == 'done',
          repr(out['closeStatus']))
    check('...holding the result the coworker sent',
          out['closeResult'] == 'here is the memo', repr(out['closeResult']))
    check('...with the old snag cleared', out['closeClears'] is True)
    check('...and the doing-clock cleared', out['closeAge'] is None,
          repr(out['closeAge']))
    check('a reopened card finished again credits the second run',
          out['reWho'] == 'kenji' and out['reStamps'] is True,
          repr([out['reWho'], out['reStamps']]))

    print('3. the other two markers are unchanged')
    check('[TASK_BLOCKED] still parks the card with its reason',
          out['blockedStatus'] == 'doing' and out['blockedReason'] == 'no API key',
          repr([out['blockedStatus'], out['blockedReason']]))
    check('[TASK_PROGRESS] still moves an inbox card into doing',
          out['progressStatus'] == 'doing', repr(out['progressStatus']))
    check('...clearing the old snag and logging the note',
          out['progressClears'] == '' and out['progressLog'] == 1,
          repr([out['progressClears'], out['progressLog']]))
    check('a card nobody mentioned is returned untouched',
          out['identity'] is True)

    print()
    if FAILS:
        print('a finished task is not re-credited to whoever mentions it: '
              f'{len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('a finished task is not re-credited to whoever mentions it: '
          'all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
