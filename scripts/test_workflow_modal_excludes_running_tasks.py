#!/usr/bin/env python3
"""WorkflowModal's "AVAILABLE TASKS" list used to offer any task not yet
`done`, which included a task with `status === 'doing'` — one an agent is
actively running right now.

Chaining an already-running task into a new workflow (e.g. as step 2 of
A -> B -> C, where B is already `doing`) wires it up with `dependsOn:
[A.id]` in `onSave`, implying it should wait for A — but B was never
gated by A; it's already running under its own steam. Two silent breaks
followed:
  - If B finishes before A, app.jsx's chain-advance fires C immediately
    with A still unfinished, violating the sequential guarantee the whole
    workflow feature promises.
  - If A finishes first, the hand-off to B silently no-ops (the check is
    `nextTask.status === 'inbox'`, and B is `doing`), with no error and no
    sign the chain never actually took.

The modal's own status-summary panel would still render a plausible
"1/3 done - 1 in progress" for this broken chain, giving the boss no
signal anything was wrong.

Found by a background hunt agent scanning previously-uncovered areas
(Search, mobile layout, the Workflow-building modal).

Fix: `inboxTasks` in modals/collab.jsx now filters on `status === 'inbox'`
(matching the variable's own name and the "AVAILABLE TASKS" section's
intent) instead of the weaker `status !== 'done'`.

Run: python3 scripts/test_workflow_modal_excludes_running_tasks.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLLAB = ROOT / 'modals' / 'collab.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("WorkflowModal's available-tasks list excludes already-running tasks")

    src = COLLAB.read_text(encoding='utf-8')

    m = re.search(r"const inboxTasks = tasks\.filter\((.*?)\);", src)
    check('inboxTasks filter is still present in modals/collab.jsx', m is not None)
    filt = m.group(1) if m else ''

    check("the filter requires status === 'inbox' (not the weaker "
          "status !== 'done', which also let in an already-'doing' task)",
          "t.status === 'inbox'" in filt)
    check("...and no longer accepts the old, broader status !== 'done' test",
          "t.status !== 'done'" not in filt)
    check('the filter still excludes tasks already claimed by another '
          'workflow (t.workflowId) — pre-existing behavior this fix must not regress',
          '!t.workflowId' in filt)
    check('...and still excludes tasks already added as a step in the '
          'workflow being built right now',
          '!steps.includes(t.id)' in filt)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
