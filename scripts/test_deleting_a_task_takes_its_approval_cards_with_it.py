#!/usr/bin/env python3
"""Deleting a task left its approval cards standing in the tray, and
stamping one wrote an approval receipt for nothing at all.

Two card kinds in the ApprovalTray are bound to a specific task by
`taskId`: the 'awaiting stamp' a coworker raises mid-run, and the
'workflow-step' card that asks "run the next step?". `onDeleteTask`
scrubbed the task, its chain pointers, and (when running) the stream —
but never the approvals pointing at it.

The workflow-step card is the sharp end. onApprove's branch reads

    const nextTask = tasks.find(t => t.id === ap.taskId);
    if (nextTask && nextTask.status === 'inbox') { triggerChainStep(…) }
    else if (nextTask) { /* say it was already started */ }

With the task deleted, `nextTask` is undefined and BOTH arms are skipped
— while the "✓ APPROVED — …" chat line has already been written by the
common prologue. The boss stamps the card, reads a receipt saying the
step was approved, and nothing runs, nothing is said, and the card is
merely removed. An 'awaiting stamp' for a deleted task is the same lie a
step quieter: a decision solicited about work the boss already removed.

The dismissal cascade already fixed exactly this shape for a departing
coworker ("clicking Approve on a stale … card looks like it worked …
while the actual grant/hire silently no-ops"), purging their approvals
at the same place every other trace of them is purged. Task deletion had
no equivalent.

Fix: `onDeleteTask` filters approvals whose `taskId` is the deleted id,
in the same pass that scrubs the chain links. Cards with no `taskId`
(external, publish, hire, elevation) are untouched.

Run: python3 scripts/test_deleting_a_task_takes_its_approval_cards_with_it.py
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
    print("deleting a task takes its approval cards with it")

    src = APP.read_text(encoding='utf-8')

    m = re.search(r"const onDeleteTask = async \(id\) => \{(.*?)\n  \};", src, re.S)
    check('onDeleteTask is still present and this test is looking at the right function',
          m is not None)
    body = m.group(1) if m else ''

    check('onDeleteTask purges the tray of approval cards bound to the deleted task',
          re.search(r"setApprovals\(", body) is not None,
          'no setApprovals call in onDeleteTask — the tray keeps asking about a deleted task')

    check('...and it purges by taskId (the field both task-bound card kinds carry)',
          re.search(r"setApprovals\(\s*prev\s*=>\s*prev\.filter\([^)]*taskId[^)]*\)",
                    body, re.S) is not None,
          'the purge does not key on taskId')

    check('...keeping cards that carry no taskId, so external/publish/hire/'
          'elevation approvals are not collateral',
          re.search(r"setApprovals\(\s*prev\s*=>\s*prev\.filter\(\s*p\s*=>\s*"
                    r"!\(\s*p\.taskId\s*&&\s*p\.taskId === id\s*\)\s*\)\s*\)",
                    body, re.S) is not None,
          'the filter is not the guarded `p.taskId && p.taskId === id` form')

    check('the purge runs after the task itself is removed, not instead of it '
          '(pre-existing behavior this fix must not regress)',
          re.search(r"\.filter\(x => x\.id !== id\)", body) is not None
          and body.index('.filter(x => x.id !== id)') < body.index('setApprovals(')
          if ('setApprovals(' in body and '.filter(x => x.id !== id)' in body) else False)

    # The bug this guards against: onApprove's workflow-step branch does
    # nothing at all when the task is gone, after the receipt has been written.
    ap = re.search(r"if \(ap\.kind === 'workflow-step'\) \{(.*?)\n        return;",
                   src, re.S)
    check("the workflow-step stamp still acts only under a resolved task "
          "(the silent no-op this purge makes unreachable)",
          ap is not None
          and re.search(r"const nextTask = tasks\.find\(t => t\.id === ap\.taskId\)",
                        ap.group(1)) is not None
          and re.search(r"if \(nextTask && nextTask\.status === 'inbox'\)",
                        ap.group(1)) is not None)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
