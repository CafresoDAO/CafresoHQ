#!/usr/bin/env python3
"""A reloaded run's stale start time haunted the one it replaced.

`app/worklog.jsx`'s `applyStatus` is the office's one place that owns the
`startedAt` invariant: stamp it on the way INTO `doing` (only when absent, so
a reassignment doesn't restart the clock), clear it on the way OUT (so a
re-opened task can't inherit a stale age from a previous life). The comment
above it says outright that there are seven sites that write a task status
and an invariant enforced at six of them is not one.

`app.jsx`'s `tasksOnLoad` — the load-time scrub that sends any task still
`doing` at page-load back to `inbox` (a run that died with the last tab) —
was the seventh. It wrote `{ ...t, status: 'inbox', ... }` directly, never
calling `applyStatus`, so `startedAt` rode along on the trip back to inbox
untouched.

Reproduced end to end: start a task at T0, reload the page 3 hours later
(the run is long dead, nothing is streaming for it) — the scrub sends it to
inbox, `startedAt` still reads T0. A minute after that, the same task is
picked up again (any of the many `applyStatus(t, 'doing')` call sites in
app.jsx). `applyStatus` only stamps `startedAt` "when absent" — that is the
whole point of the invariant, so a mid-run reassignment doesn't reset the
clock — and here it is very much present, just wrong. The card that just
started ten seconds ago reads `worklogLine` as `on it · 3h 1m`, the exact
"stale age from a previous life" `applyStatus`'s own comment says a re-open
must never carry.

The fix routes the scrub through `applyStatus(t, 'inbox')` instead of the
raw spread, same as every other place that leaves `doing`.

Run: python3 scripts/test_reload_scrub_clears_started_at.py
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

T0 = 1_000_000
MIN = 60000
HOUR = 3600000


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift_first_arg(src, opener):
    """Extract the first argument of a call `opener(<arg>, <arg2>)` by
    paren/bracket/brace-matching from right after `opener`, stopping at the
    top-level comma that starts the next argument. Lifts the REAL arrow
    function passed to React.useCallback rather than pattern-matching it
    from a distance."""
    i = src.index(opener)
    start = i + len(opener)
    depth = 0
    k = start
    while k < len(src):
        c = src[k]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        elif c == ',' and depth == 0:
            return src[start:k]
        k += 1
    raise SystemExit('could not find end of first arg for ' + opener)


def run_js(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('a reloaded run must not haunt the one that replaces it')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    if not APP.is_file() or not WORKLOG.is_file():
        print('  FAIL  missing app.jsx or app/worklog.jsx')
        return 1

    wl = WORKLOG.read_text(encoding='utf-8')
    wl_body = '\n'.join(ln for ln in wl.split('\n')
                        if not ln.startswith('import ') and not ln.startswith('export '))

    app = APP.read_text(encoding='utf-8')
    idx = app.index('const tasksOnLoad = React.useCallback(')
    call_start = idx + len('const tasksOnLoad = ')
    opener = 'React.useCallback('
    arrow_src = lift_first_arg(app[call_start:], opener)

    js = wl_body + '\n' + 'const tasksOnLoad = ' + arrow_src + ';\n' + f"""
const R = {{}};

// A task that was picked up at T0 and is still 'doing' 3 hours later, when
// the boss reloads the page. No blockedReason -- this is the "run died with
// the tab" case, not a parked snag.
const dying = {{ id: 't1', status: 'doing', startedAt: {T0}, assignedTo: 'a1' }};
const scrubbed = tasksOnLoad([dying])[0];

R.scrubStatus = scrubbed.status;
R.scrubHasStartedAt = 'startedAt' in scrubbed;

// Now the task is picked up again a minute later -- the real path every
// START button and drag-to-DOING site in app.jsx uses.
const restarted = applyStatus(scrubbed, 'doing', {T0 + 3 * HOUR + MIN});
R.restartedStartedAt = restarted.startedAt;
R.freshAge = worklogLine(restarted, {{ status: 'active' }}, {T0 + 3 * HOUR + 2 * MIN});

console.log(JSON.stringify(R));
"""
    out = run_js(js)

    check('the scrub sends the card back to inbox',
          out['scrubStatus'] == 'inbox', out['scrubStatus'])
    check('the scrub clears startedAt, same as every other exit from doing',
          out['scrubHasStartedAt'] is False,
          'startedAt survived the reload scrub, so applyStatus\'s "only '
          'stamp when absent" rule sees it as already-running on the next '
          'pickup and never gives it a fresh start time')
    check('restarting the card after the scrub gets a FRESH startedAt, '
          'not the one from the run the reload killed',
          out['restartedStartedAt'] == T0 + 3 * HOUR + MIN,
          out['restartedStartedAt'])
    check('a card started ten seconds ago must not read hours old',
          out['freshAge'] == 'on it · 1m', out['freshAge'])

    print()
    if FAILS:
        print(f'reload-scrub startedAt: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('reload-scrub startedAt: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
