#!/usr/bin/env python3
"""A task dragged straight to DONE on the Task Board must say WHEN, even
though nobody credits an agent for it.

f01359b ("Stamp completedAt/completedBy on every task completion") taught
the three sites that finish a task via an agent's own run to stamp
`completedAt`/`completedBy`, so a DONE card can read "✓ Llama finished this
· just now" instead of a bare "✓ finished". Its own wiring check greps
app.jsx/features.jsx for the literal text `applyStatus(...,'done'` — and
that regex is exactly why a fourth site was missed: the Task Board's column
drag, `onMoveTask` in app.jsx —

    const onMoveTask = (id, status) =>
      setTasks(prev => prev.map(t => t.id === id ? applyStatus(t, status) : t));

— calls `applyStatus(t, status)` with `status` a variable, which never
matches a literal `'done'` and was never counted among "the three sites
that put a task into done".

Measured against the code as it stood before this fix: drag a parked task
(one whose run came back without a deliverable -- `result` holds the reply
text, `completedAt`/`completedBy` both correctly null per f01359b's own
not-produced branch) straight from DOING onto the DONE column. TaskBoard's
result block (features.jsx) computes `finished = t.status === 'done'` from
status alone, so the card flips to "✓ finished" -- and with nothing
stamping `completedAt` on that path, stays timeless forever: the exact bare
line f01359b was written to stop, on the one path it didn't reach.

The fix teaches `applyStatus` itself to own the invariant, symmetrically
with the `startedAt` invariant it already owns: stamp `completedAt` (only
when absent) on the way into `done`, clear `completedAt` AND `completedBy`
on the way out. Every explicit call site that sets its own `completedAt`/
`completedBy` right after calling `applyStatus` (object-spread order) still
wins -- this only fills the gap where nothing else does.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKLOG = ROOT / 'app' / 'worklog.jsx'
APP = ROOT / 'app.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def run_js(cases_js):
    text = WORKLOG.read_text(encoding='utf-8')
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
    print('a dragged DONE card says when')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    if not WORKLOG.is_file():
        print(f'  FAIL  missing {WORKLOG}')
        return 1

    out = run_js(r'''
const R = {};
const T0 = 1000000;

// ── The bug, reproduced exactly: a parked run's own state ──────────────
// This is precisely the shape f01359b's not-produced branch leaves behind:
// doing, a result already on file, completedAt/completedBy explicitly null.
const parked = { id: 'a', status: 'doing', result: 'here is what I have so far',
                  completedAt: null, completedBy: null };

// The Task Board's column drop calls exactly this: onMoveTask(id, 'done')
// -> applyStatus(t, 'done'). No agent, no explicit stamp alongside it.
const draggedToDone = applyStatus(parked, 'done', T0);
R.stampsOnDrag   = draggedToDone.completedAt;
R.noFabricatedBy = 'completedBy' in draggedToDone ? draggedToDone.completedBy : null;
// The on-screen payoff: finishedLabel must now produce a real label instead
// of staying silent, which is what "✓ finished" with no time really means.
R.rendersATime   = finishedLabel(draggedToDone, T0 + 30000);

// ── Symmetric with startedAt's own invariant ────────────────────────────
R.keepsClock = applyStatus({ id: 'a', status: 'done', completedAt: T0, completedBy: 'agentX' },
                            'done', T0 + 3600000).completedAt;

const reopened = applyStatus(
  { id: 'a', status: 'done', completedAt: T0, completedBy: 'agentX', result: 'r' },
  'doing', T0 + 3600000);
R.clearsAtOnReopen = 'completedAt' in reopened;
R.clearsByOnReopen  = 'completedBy' in reopened;

const backToInbox = applyStatus(
  { id: 'a', status: 'done', completedAt: T0, completedBy: 'agentX' }, 'inbox', T0);
R.clearsOnBackToInbox = 'completedAt' in backToInbox || 'completedBy' in backToInbox;

R.noStampNonDoneMove = 'completedAt' in applyStatus({ id: 'a', status: 'inbox' }, 'inbox', T0);

// Explicit stamps at the call site still win over the default (object-spread
// order in app.jsx puts them AFTER the applyStatus(...) call).
const explicit = { ...applyStatus({ id: 'a', status: 'doing' }, 'done', T0),
                    completedAt: T0 + 1, completedBy: 'real-agent' };
R.explicitWins = explicit.completedAt === T0 + 1 && explicit.completedBy === 'real-agent';

// Purity, same guarantee startedAt already has.
R.pure = (() => {
  const t = { id: 'a', status: 'doing' };
  applyStatus(t, 'done', T0);
  return 'completedAt' in t;
})();

console.log(JSON.stringify(R));
''')

    check('dragging a parked card straight to DONE stamps completedAt',
          out['stampsOnDrag'] == 1000000, str(out['stampsOnDrag']))
    check('...without inventing a completedBy nobody earned',
          out['noFabricatedBy'] is None, repr(out['noFabricatedBy']))
    check('...so the card can finally say WHEN ("✓ finished · just now", not silence)',
          out['rendersATime'] == 'just now', repr(out['rendersATime']))
    check('re-dropping an already-done card on DONE does not refresh its finish time',
          out['keepsClock'] == 1000000, str(out['keepsClock']))
    check('dragging a DONE card back to DOING clears completedAt',
          out['clearsAtOnReopen'] is False)
    check('...and clears completedBy with it (a name with no time is worse than neither)',
          out['clearsByOnReopen'] is False)
    check('dragging a DONE card back to INBOX clears both stamps',
          out['clearsOnBackToInbox'] is False)
    check('a move that was never headed to/from done adds no stamp',
          out['noStampNonDoneMove'] is False)
    check('an explicit completedAt/completedBy at the call site still wins',
          out['explicitWins'] is True)
    check('the input task is not mutated', out['pure'] is False)

    # ---- wiring: onMoveTask is still the one place that owns the column
    # drop, and it still routes through applyStatus with a variable status
    # rather than re-implementing (or skipping) the invariant inline. If a
    # future edit hardcodes the status transition here instead, this fix
    # stops applying without anyone having to notice by hand.
    print('wiring: the Task Board column drop routes through applyStatus')
    app_src = APP.read_text(encoding='utf-8')
    m = re.search(r"const onMoveTask = \(id, status\) =>\s*\n\s*setTasks\(prev => prev\.map\("
                  r"t => t\.id === id \? applyStatus\(t, status\) : t\)\);", app_src)
    check('onMoveTask calls applyStatus(t, status) — the dynamic-status call '
          'this fix teaches to stamp/clear completedAt', m is not None)

    print()
    if FAILS:
        print(f'FAILED ({len(FAILS)}): ' + ', '.join(FAILS))
        return 1
    print('PASS: a task dragged straight to DONE says when, even with no one to credit')
    return 0


if __name__ == '__main__':
    sys.exit(main())
