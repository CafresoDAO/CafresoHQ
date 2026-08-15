#!/usr/bin/env python3
"""A coworker said it was stuck. The office wrote it down and never showed it.

A coworker mid-run can emit `[TASK_BLOCKED: <id>: <reason>]`. The office
stored `blockedReason`/`blockedAt` on the task, raised a toast, and left the
card in DOING. Nothing read `blockedReason` anywhere in the product.

So a job a coworker had explicitly given up on sat on the board looking
exactly like one in flight, with the only notice of it gone from the screen
in seconds. Found by sweeping for fields written to state records and never
read back -- `blockedReason`, `blockedAt` and `progressLog` were the three
domain fields with zero readers.

Worse than looking neutral. `worklogLine` answers "is anyone on this?" from
`agent.status`, which is about the COWORKER and not the task -- so the moment
that coworker was dispatched to anything else, a blocked card read

    ⚡ on it · 45m

over a job nobody was doing anything about. The missing answer had become a
wrong one. `app/worklog.jsx` already reserved the word for this case in a
comment ("it never says stuck -- that word belongs to a coworker who tried
and snagged") and had no branch for it.

Run: python3 scripts/test_a_blocked_card_says_so.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FEATURES = ROOT / 'features.jsx'
WORKLOG = ROOT / 'app' / 'worklog.jsx'
FAILS = []

T0 = 1_000_000
MIN = 60000


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def lift_block(src, opener):
    """Brace-match the arrow body starting at `opener` so the REAL update
    handler runs here, rather than being pattern-matched from a distance."""
    i = src.index(opener)
    j = src.index('{', i + len(opener) - 1)
    depth, k = 0, j
    while k < len(src):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[j:k + 1]
        k += 1
    raise SystemExit('could not brace-match ' + opener)


def main():
    print('a card nobody is working on has to say why')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    app = APP.read_text(encoding='utf-8')
    feats = FEATURES.read_text(encoding='utf-8')
    wl = WORKLOG.read_text(encoding='utf-8')

    # ── 1. the one line on the card ─────────────────────────────────────
    body = '\n'.join(ln for ln in wl.split('\n')
                     if not ln.startswith('import ') and not ln.startswith('export '))
    out = run(body + """
const R = {};
const blocked = { status: 'doing', startedAt: %d, blockedReason: 'the sheet is locked' };
R.blockedBusyOwner = worklogLine(blocked, { status: 'active' }, %d);
R.blockedIdleOwner = worklogLine(blocked, { status: 'idle'   }, %d);
R.blockedNoStamp   = worklogLine({ status: 'doing', blockedReason: 'x' }, { status: 'idle' }, %d);
R.blockedInbox     = worklogLine({ status: 'inbox', blockedReason: 'x' }, { status: 'idle' }, %d);
R.plainOnIt        = worklogLine({ status: 'doing', startedAt: %d }, { status: 'active' }, %d);
R.plainNobody      = worklogLine({ status: 'doing', startedAt: %d }, { status: 'idle' }, %d);
R.emptyReason      = worklogLine({ status: 'doing', startedAt: %d, blockedReason: '' },
                                 { status: 'active' }, %d);
console.log(JSON.stringify(R));
""" % (T0, T0 + 45 * MIN, T0 + 45 * MIN, T0, T0,
       T0, T0 + 45 * MIN, T0, T0 + 45 * MIN, T0, T0 + 45 * MIN))

    check('a blocked job does not report someone on it',
          out['blockedBusyOwner'] == 'hit a snag · 45m',
          f"{out['blockedBusyOwner']!r} — the owner being 'active' says the "
          'COWORKER is busy, not that this job is moving; that is how a card '
          'nobody was helping read "on it · 45m"')
    check('...and reads the same when the owner is idle',
          out['blockedIdleOwner'] == out['blockedBusyOwner'],
          f"{out['blockedIdleOwner']!r} — a block is a fact about the JOB; who "
          'happens to be at a keyboard does not change it')
    check('...and still says it with no start stamp',
          out['blockedNoStamp'] == 'hit a snag', out['blockedNoStamp'])
    check('a blocked job outside DOING gets no line here',
          out['blockedInbox'] is None,
          f"{out['blockedInbox']!r} — this line only ever speaks for DOING; the "
          'reason itself is rendered separately, and is not gated that way')
    check('an ordinary job is untouched',
          out['plainOnIt'] == 'on it · 45m'
          and out['plainNobody'] == "nobody's on this · 45m",
          f"{out['plainOnIt']!r} / {out['plainNobody']!r}")
    check('an empty reason is not a block',
          out['emptyReason'] == 'on it · 45m',
          f"{out['emptyReason']!r} — the field is cleared to '' rather than "
          'deleted, so a falsy check is the only correct one')
    check('a job nobody picked up is still never called stuck (§5)',
          not re.search(r'stuck|fail|error', str(out['plainNobody']), re.I),
          out['plainNobody'])

    # ── 2. the reason reaches the card, and leaves when it should ───────
    m = re.search(r"\{t\.blockedReason && t\.status ([^&]+)&&", feats)
    check('the card renders the reason at all', bool(m),
          'features.jsx: nothing read blockedReason — that was the defect')
    if m:
        check("...gated the same way stalledNote is, not on 'doing'",
              m.group(1).strip() == "!== 'done'",
              f'{m.group(1).strip()!r} — the boss can drag a blocked card off '
              'DOING by hand (onMoveTask -> applyStatus keeps the field), so a '
              'doing-only gate hides a live reason the moment the card moves, '
              'and "start it again" is bad advice for a job that will hit the '
              'same wall — the reason must follow the card')
    # The scrub really does leave the field alone — the premise of the gate.
    scrub = re.search(r'const tasksOnLoad = React\.useCallback\([\s\S]*?\), \[\]\);', app)
    check('the reload scrub is still one statement', bool(scrub), 'app.jsx')
    if scrub:
        scrubbed = run("""
const React = { useCallback: (f) => f };
%s
console.log(JSON.stringify(tasksOnLoad([{ id:'t1', status:'doing',
  blockedReason:'the sheet is locked' }])[0]));
""" % scrub.group(0))
        # Written when the scrub moved every DOING card to inbox; since the
        # parked-snag guard it must not touch this card at all. The intent is
        # unchanged — a reload must never hide the reason — it is now served
        # by leaving the settled card exactly as the settle left it.
        check('a reload leaves a parked card exactly as the settle left it',
              scrubbed.get('blockedReason') == 'the sheet is locked'
              and scrubbed.get('status') == 'doing'
              and not scrubbed.get('stalledNote'),
              f'{scrubbed!r} — a doing card with a blockedReason is a run that '
              'ENDED (the run-end path is the field\'s only writer); moving it '
              'and stamping "the run stopped when the page reloaded" told a '
              'second, false story about a run whose true ending was already '
              'on the card')

    # ── 3. the three ways off a block, run for real ─────────────────────
    handler = lift_block(app, 'setTasks(prev => prev.map(t => {')
    R = run("""
const applyStatus = (t, s) => Object.assign({}, t, { status: s });
const toast = null;
const agent = { id: 'a1', name: 'Nova' };
const BASE = { id: 't1', title: 'Publish the Q3 summary', status: 'doing' };
const step = (t, taskUpdates) => ((t) => %s)(t);
const R = {};
R.blocked  = step(BASE, [{ id: 't1', action: 'blocked', note: 'the sheet is locked' }]);
const B = R.blocked;
R.progress = step(B, [{ id: 't1', action: 'progress', note: 'got the password' }]);
R.done     = step(B, [{ id: 't1', action: 'done', result: 'published' }]);
R.other    = step(B, [{ id: 'other', action: 'done' }]);
console.log(JSON.stringify(R));
""" % handler.replace('taskUpdates', 'taskUpdates'))

    check('a block is recorded with its reason',
          R['blocked'].get('blockedReason') == 'the sheet is locked'
          and R['blocked'].get('status') == 'doing',
          f"{R['blocked'].get('blockedReason')!r}")
    check('a progress note clears the block',
          not R['progress'].get('blockedReason'),
          f"{R['progress'].get('blockedReason')!r} — a coworker reporting "
          'progress has moved past whatever they were stuck on; leaving it '
          'puts a solved problem under a moving job')
    check('finishing clears the block',
          not R['done'].get('blockedReason') and R['done'].get('status') == 'done',
          f"{R['done'].get('blockedReason')!r} — a field that is rendered "
          'needs a lifecycle, or "waiting on the API key" ends up under a '
          'completed job')
    check('an update for another task changes nothing',
          R['other'].get('blockedReason') == 'the sheet is locked', R['other'])

    # ── 4. …and a fresh START, which is the boss's way off it ───────────
    start = re.search(r"\{ \.\.\.applyStatus\(t, 'doing'\), assignedTo: agent\.id,[\s\S]{0,140}?\}", app)
    check('starting a task clears the block too', bool(start)
          and 'blockedReason' in start.group(0),
          f'{start.group(0) if start else None!r} — app.jsx: START already '
          'cleared stalledNote for exactly this reason; a new run is not '
          'still stuck on what the last one was stuck on')

    print()
    if FAILS:
        print(f'a blocked card: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('a blocked card: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
