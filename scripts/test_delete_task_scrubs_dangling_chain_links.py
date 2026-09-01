#!/usr/bin/env python3
"""Deleting a task used to leave other tasks' workflow-chain pointers
dangling, with no visible sign anything broke.

`task.dependsOn` is read in exactly one place in the whole codebase: the
success handler that runs right after a chain predecessor finishes
(app.jsx, just before triggerChainStep), which looks up
`tasksRef.current.find(t => t.id === task.chainTo)`. `onDeleteTask` never
scrubbed other tasks' `chainTo`/`dependsOn` references to the id it just
removed.

Two concrete failure modes this left in place:
  1. Task A --chainTo--> B. Delete B. When A finishes, the lookup for
     `task.chainTo` finds nothing — the whole chain-advance block
     (including the stalledNote/activity-row path that already handles a
     dangling *dependsOn* entry) is skipped outright. Silent, no trace.
  2. Task C depends on B (dependsOn: [B.id]). Delete B. B can never again
     become `status: 'done'`, so C's `blockedBy` filter (`!dep` — B no
     longer resolves) blocks it FOREVER, with no way for the boss to ever
     unblock it short of manually editing state.

Found by a background hunt agent scanning previously-uncovered areas
(Search, Workflow chains, mobile layout).

Fix: `onDeleteTask` now scrubs `chainTo` (nulls it) and `dependsOn`
(filters the dangling id out) on every other task when a task is deleted,
and logs one activity row if it actually broke a link — so the workflow
board can be a place the boss checks headline the words as soon as it
happens, not an invisible desync noticed only when a chain fails to
advance.

Run: python3 scripts/test_delete_task_scrubs_dangling_chain_links.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("onDeleteTask scrubs dangling chainTo/dependsOn links on other tasks")

    src = APP.read_text(encoding='utf-8')

    m = re.search(r"const onDeleteTask = async \(id\) => \{(.*?)\n  \};", src, re.S)
    check('onDeleteTask is still present and this test is looking at the right function',
          m is not None)
    body = m.group(1) if m else ''

    check('the deletion pass nulls out any other task\'s chainTo pointing at the deleted id',
          re.search(r"next\.chainTo === id.*?next = \{ \.\.\.next, chainTo: null \}", body, re.S)
          is not None)
    check('...and filters the deleted id out of any dependsOn array that references it',
          re.search(
              r"next\.dependsOn.*?includes\(id\).*?dependsOn:\s*next\.dependsOn\.filter\("
              r"d => d !== id\)", body, re.S) is not None)
    check('it still filters the deleted task itself out of the tasks array '
          '(the pre-existing behavior this fix must not regress)',
          re.search(r"\.filter\(x => x\.id !== id\)", body) is not None)
    check('it logs an activity row when a chain link actually broke, so the '
          'break has a visible trace instead of being silent',
          re.search(r"if \(brokeChain\)", body) is not None
          and re.search(r"logActivity\(\{.*?broke a workflow chain link", body, re.S)
          is not None)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
