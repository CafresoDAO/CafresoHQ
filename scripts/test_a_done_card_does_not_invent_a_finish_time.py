#!/usr/bin/env python3
"""A DONE card must not invent a finish time it never had.

`finishedLabel` (app/worklog.jsx) refuses to guess: a task with no
`completedAt` says nothing, "for the same reason `sittingFor` refuses to
fall back to `createdAt`". Such records are real — the read side of the
feature was built long after the write side, so offices carry cards that
finished before anything stamped them.

`applyStatus`'s done branch stamped on the wrong condition. It asked "is
the stamp absent?" when the question is "is this card ENTERING done?".
Three call sites hand it the status the task already has:

    app.jsx:1706  dismissing a coworker  applyStatus(t, t.status === 'doing' ? 'inbox' : t.status)
    app.jsx:3145  a late [TASK_PROGRESS] applyStatus(t, t.status === 'inbox' ? 'doing' : t.status)
    app.jsx:6438  chat re-infers assignee  (same shape)

So dismissing a coworker walked every card they held through
`applyStatus(t, 'done')`, and each unstamped one came back claiming it had
been finished at that exact moment. The board then read "✓ finished · just
now" over a week-old job, and `setTasks` persisted the fabrication — the
real finish time was not recovered, it was overwritten with a lie.

The fix stamps only on a genuine transition into `done`. The dragged-card
case this branch was written for (a parked `doing` card dropped on the DONE
column — scripts/test_a_dragged_done_card_says_when.py) is a transition and
still stamps.

The module is import-free, so it runs verbatim under node minus its export
line.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app' / 'worklog.jsx'
APP = ROOT / 'app.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def run_js(cases_js):
    text = SRC.read_text(encoding='utf-8')
    src = '\n'.join(ln for ln in text.split('\n')
                    if not ln.startswith('import ') and not ln.startswith('export '))
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases_js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('a DONE card does not invent a finish time')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1

    out = run_js(r'''
const R = {};
const T0 = 1000000;

// A card finished long ago by a path that never stamped. `finishedLabel`
// is built to say nothing about it, and does.
const legacyDone = { id: 'a', status: 'done', title: 'Ship the page',
                     result: 'here it is', assignedTo: 'agentX' };
R.silentBefore = finishedLabel(legacyDone, T0);

// 1. Dismissing the coworker who held it: app.jsx maps EVERY card of theirs
//    through applyStatus(t, t.status) — 'done' stays 'done'.
const afterDismiss = applyStatus(legacyDone, legacyDone.status, T0);
R.dismissStamp = 'completedAt' in afterDismiss ? afterDismiss.completedAt : null;
R.dismissLabel = finishedLabel(afterDismiss, T0 + 30000);

// 2. A late [TASK_PROGRESS] on a card already in done — same shape.
const afterProgress = applyStatus(legacyDone, legacyDone.status === 'inbox' ? 'doing' : legacyDone.status, T0);
R.progressStamp = 'completedAt' in afterProgress ? afterProgress.completedAt : null;

// 3. Re-dropping an already-done card on the DONE column refreshes nothing
//    and invents nothing (the module's own stated rule for this branch).
R.redropStamp = 'completedAt' in applyStatus(legacyDone, 'done', T0) ? 'stamped' : null;

// Nothing else about the card is disturbed by the pass-through.
R.keepsResult = afterDismiss.result;
R.keepsStatus = afterDismiss.status;

// ── what must still happen ──────────────────────────────────────────────
// A real transition into done stamps: the parked card dragged from DOING to
// the DONE column, which is the case this branch exists for.
const parked = { id: 'b', status: 'doing', result: 'what I have so far',
                 completedAt: null, completedBy: null };
const dragged = applyStatus(parked, 'done', T0);
R.dragStamp  = dragged.completedAt;
R.dragLabel  = finishedLabel(dragged, T0 + 30000);
R.dragNoBy   = 'completedBy' in dragged ? dragged.completedBy : null;

// An inbox card moved to done stamps too.
R.inboxToDone = applyStatus({ id: 'c', status: 'inbox' }, 'done', T0).completedAt;

// A real stamp on an already-done card is never refreshed.
R.keepsClock = applyStatus({ id: 'd', status: 'done', completedAt: T0, completedBy: 'agentX' },
                           'done', T0 + 3600000).completedAt;

// Reopening still clears both stamps.
const reopened = applyStatus({ id: 'e', status: 'done', completedAt: T0, completedBy: 'agentX' },
                             'doing', T0 + 60000);
R.reopenClears = ('completedAt' in reopened) || ('completedBy' in reopened);

// An explicit stamp at the call site still wins (app.jsx spreads it after).
const explicit = { ...applyStatus({ id: 'f', status: 'doing' }, 'done', T0),
                   completedAt: T0 + 1, completedBy: 'real-agent' };
R.explicitWins = explicit.completedAt === T0 + 1 && explicit.completedBy === 'real-agent';

// Degenerate input must not throw.
R.nullTask = (() => { try { return applyStatus(null, 'done', T0).status; }
                      catch (e) { return 'THREW: ' + e.message; } })();

// Purity.
R.pure = (() => { const t = { id: 'g', status: 'doing' };
                  applyStatus(t, 'done', T0); return 'completedAt' in t; })();

console.log(JSON.stringify(R));
''')

    print('1. a card that is already done is never re-stamped')
    check('a legacy DONE card says nothing about when it finished',
          out['silentBefore'] is None, repr(out['silentBefore']))
    check('dismissing its coworker does NOT fabricate a finish time',
          out['dismissStamp'] is None, repr(out['dismissStamp']))
    check('...so the card still says nothing rather than "just now"',
          out['dismissLabel'] is None, repr(out['dismissLabel']))
    check('a late progress note does not fabricate one either',
          out['progressStamp'] is None, repr(out['progressStamp']))
    check('re-dropping an already-done card on DONE invents nothing',
          out['redropStamp'] is None, repr(out['redropStamp']))
    check('the rest of the card is untouched',
          out['keepsResult'] == 'here it is' and out['keepsStatus'] == 'done',
          repr([out['keepsResult'], out['keepsStatus']]))

    print('2. a real move into DONE still stamps')
    check('a parked DOING card dragged to DONE gets its stamp',
          out['dragStamp'] == 1000000, repr(out['dragStamp']))
    check('...and renders a real time', out['dragLabel'] == 'just now',
          repr(out['dragLabel']))
    check('...without inventing a name', out['dragNoBy'] is None)
    check('inbox → done stamps', out['inboxToDone'] == 1000000,
          repr(out['inboxToDone']))
    check('an existing stamp is never refreshed', out['keepsClock'] == 1000000,
          repr(out['keepsClock']))
    check('reopening still clears both stamps', out['reopenClears'] is False)
    check('an explicit call-site stamp still wins', out['explicitWins'] is True)
    check('a null task does not throw', out['nullTask'] == 'done',
          repr(out['nullTask']))
    check('the input task is not mutated', out['pure'] is False)

    print('3. the call sites that hand it a status the task already has')
    app = APP.read_text(encoding='utf-8') if APP.is_file() else ''
    check('app.jsx still routes the dismissal through applyStatus(t, t.status …)',
          "applyStatus(t, t.status === 'doing' ? 'inbox' : t.status)" in app)
    check('...and the progress / re-infer paths do the same',
          len(re.findall(r"applyStatus\(t, t\.status === 'inbox' \? 'doing' : t\.status\)", app)) >= 2,
          str(len(re.findall(r"applyStatus\(t, t\.status === 'inbox' \? 'doing' : t\.status\)", app))))

    print()
    if FAILS:
        print(f'a DONE card does not invent a finish time: {len(FAILS)} FAILED — '
              + ', '.join(FAILS))
        return 1
    print('a DONE card does not invent a finish time: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
