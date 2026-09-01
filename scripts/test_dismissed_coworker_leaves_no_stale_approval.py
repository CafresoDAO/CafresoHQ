#!/usr/bin/env python3
"""Firing a coworker used to leave their pending approval cards (hire-agent,
hire-assistant, grant-elevation, awaiting-stamp) sitting in the tray, along
with the `pendingHiresRef`/`pendingAssistantHiresRef`/`pendingElevationRef`
guards that mark them "already has one outstanding".

Concretely: an agent requests file/shell elevation, its card appears in the
tray, the boss fires that agent (onDismiss) before acting on the card. The
card survives — onDismiss never touched `approvals` or the ref sets, despite
a code comment on pendingElevationRef claiming otherwise ("released ... also
when the agent is dismissed (handled in onDismiss)"). The boss later clicks
Approve on the stale card: the shared "✓ APPROVED — ..." chat line always
fires (onApprove, line ~5579), but the kind-specific branch (grant-elevation,
hire-agent, hire-assistant) does `agents.find(a => a.id === requestedBy)`,
finds nothing, and silently skips the actual grant/hire with no error shown.
The boss is told it worked; nothing happened.

Fix: onDismiss now filters `approvals` for any card whose `agentId` (or
`fromAgent`, for workflow-step cards) is in the `leaving` set, and releases
the three pending-ref guards for every leaving id.

Found by a background hunt agent scanning previously-uncovered areas
(Roster/hiring, Approvals, Search, mobile layout, Workflows).

Run: python3 scripts/test_dismissed_coworker_leaves_no_stale_approval.py
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
    print('Dismissing a coworker purges their pending approvals + ref guards')

    src = APP.read_text(encoding='utf-8')

    m = re.search(r"const onDismiss = async \(id\) => \{(.*?)\n  \};", src, re.S)
    check('onDismiss is still present and this test is looking at the right function',
          m is not None)
    body = m.group(1) if m else ''

    m2 = re.search(
        r"const leaving = new Set\(\[.*?\]\);(.*?)setTasks\(prev => prev\.map",
        body, re.S)
    check('the `leaving` set is computed before the tasks hand-back (anchor point)',
          m2 is not None)

    check('onDismiss filters approvals for cards raised by a leaving agent',
          re.search(
              r"setApprovals\(prev => prev\.filter\(p => "
              r"!leaving\.has\(p\.agentId\) && !leaving\.has\(p\.fromAgent\)\)\);",
              body) is not None,
          'expected setApprovals(...leaving.has(p.agentId)...leaving.has(p.fromAgent)...) in onDismiss')

    check('...and releases pendingHiresRef for every leaving id',
          re.search(r"leaving\.forEach\([^)]*=>\s*\{[^}]*pendingHiresRef\.current\.delete",
                     body, re.S) is not None)
    check('...and releases pendingAssistantHiresRef for every leaving id',
          re.search(r"leaving\.forEach\([^)]*=>\s*\{[^}]*pendingAssistantHiresRef\.current\.delete",
                     body, re.S) is not None)
    check('...and releases pendingElevationRef for every leaving id',
          re.search(r"leaving\.forEach\([^)]*=>\s*\{[^}]*pendingElevationRef\.current\.delete",
                     body, re.S) is not None)

    check('every hire/elevation approval card is keyed by agentId '
          '(the field the new filter reads) — hire-agent',
          re.search(r"kind:\s*'hire-agent',\s*\n\s*agentId:\s*agent\.id", src) is not None)
    check('...hire-assistant',
          re.search(r"kind:\s*'hire-assistant',\s*\n\s*agentId:\s*agent\.id", src) is not None)
    check('...grant-elevation',
          re.search(r"kind:\s*'grant-elevation',\s*\n\s*agentId:\s*agent\.id", src) is not None)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
