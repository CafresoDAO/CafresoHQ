#!/usr/bin/env python3
"""Rejecting a workflow chain-step approval left the next task silently
stuck in the inbox with no explanation.

When a workflow chain step isn't `autoDispatch`, finishing the prior
step raises a `kind: 'workflow-step'` approval (app.jsx, inside the
task-finish handler) carrying `taskId` (the next task) and `fromAgent`
— but no `agentId`. `onApprove` has an explicit branch for this kind
that calls `triggerChainStep`. `onReject` had explicit branches for
`hire-agent`, `hire-assistant`, and `grant-elevation` rejections — each
releasing a pending slot and posting an explanatory team-thread note —
but none at all for `workflow-step`. Since the approval object has no
`agentId`, the generic tail (`ap.external && ap.externalId` /
`ap.agentId`) never fires either: rejecting did nothing beyond the
"✕ REJECTED" chat line. `nextTask` stayed in `status: 'inbox'` forever
with no `stalledNote` — indistinguishable on the board from a task
nobody had ever gotten to. The boss has to remember their own decision,
because nothing on the card says they declined it.

Found by a background hunt agent sweeping previously-unswept areas
(Night Shift, search, hire/onboarding, export/publish, workflow error
paths, chat delegate/handoff, calendar recurrence, vault graph, other
wallet flows).

Fix: added a `workflow-step` branch to `onReject`, mirroring the
existing hire/elevation branches — sets `stalledNote` on the next task
(via `ap.taskId`) explaining the boss declined it, and posts a
team-thread note naming the agent (`ap.fromAgent`) who proposed the
chain step.

Run: python3 scripts/test_workflow_step_rejection_leaves_a_note.py
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
    print("Rejecting a workflow-step approval leaves the next task explained, not stuck")

    src = APP.read_text(encoding='utf-8')

    m = re.search(r"const onReject = \(id\) => \{(.*?)\n  \};", src, re.S)
    check('onReject is still present', m is not None)
    body = m.group(1) if m else ''

    check("onApprove's workflow-step branch (the 'yes' half of this same "
          "fork) is still present, so this fix's 'no' half has something "
          "to mirror",
          "if (ap.kind === 'workflow-step') {" in src
          and "triggerChainStep(nextTask, ap.priorResult" in src)

    wf_m = re.search(
        r"if \(ap\.kind === 'workflow-step'\) \{(.*?)\n        return;\n      \}",
        body, re.S)
    check("onReject now has its own workflow-step branch", wf_m is not None)
    wf_body = wf_m.group(1) if wf_m else ''

    check("it sets stalledNote on the next task via ap.taskId, so the "
          "board explains why the task is sitting in the inbox instead "
          "of leaving it looking untouched",
          "t.id === ap.taskId" in wf_body and 'stalledNote:' in wf_body)

    check("it looks up the proposing agent via ap.fromAgent (the field "
          "this approval kind actually carries — it has no agentId) "
          "and posts a team-thread note naming them",
          "agents.find(a => a.id === ap.fromAgent)" in wf_body
          and "thread: 'team'" in wf_body)

    check("the branch returns early, same as every sibling "
          "kind-specific rejection branch (hire-agent, hire-assistant, "
          "grant-elevation) — so it can't also fall into the generic "
          "agentId tail below",
          bool(wf_m))

    # Ordering: the new branch must run BEFORE the generic tail that checks
    # ap.external/ap.agentId, or it would never be reached in practice.
    wf_pos = body.find("if (ap.kind === 'workflow-step') {")
    tail_pos = body.find("if (ap.external && ap.externalId)")
    check("the workflow-step branch sits before the generic external/"
          "agentId tail (which never matches this approval kind anyway, "
          "since it carries fromAgent, not agentId)",
          wf_pos != -1 and tail_pos != -1 and wf_pos < tail_pos)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
