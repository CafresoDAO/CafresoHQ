#!/usr/bin/env python3
"""Firing a coworker who was assigned to a project (or a chat "meeting"
room) left them on that project's/meeting's `agentIds` roster forever —
`onDismiss` cascaded `tasks`, `approvals`, and the three pending-request
ref guards, but never touched `projects` or `meetings`.

Concretely: assign a coworker to a project (views/projects.jsx's
coworker checklist pushes their id into `project.agentIds`), then fire
them from Team/Roster. `agents` drops them correctly, but
`project.agentIds` still contains their id, with visible, contradictory
consequences:

  - views/projects.jsx's "👥 ASSIGNED · N" badge (both the workspace
    header and the project card) reads the raw, unfiltered
    `agentIds.length` — it keeps counting someone who no longer works
    here.
  - `deleteProject`'s confirm dialog computes the same raw count and
    tells the boss "N agent(s) currently assigned" about someone
    already gone.
  - ui/chat.jsx gates a project's entire dynamic chat-room tab on
    `p.agentIds.length > 0` and prints `${p.agentIds.length} assigned`
    in its description — so the tab (and its fake headcount) never
    disappears, even though opening that room shows "No participants
    yet" (it separately filters participants against live `agents`),
    a direct on-screen contradiction between the tab list and the room
    itself.

The exact same shape applies to `meetings[].agentIds` (ui/chat.jsx's
"Meeting: ... · N attendees" tab).

Found by a background hunt agent sweeping previously-unswept areas
(delete/cascade logic — dangling references left in sibling state after
a dismissal).

Fix: `onDismiss` now also drops every leaving id from both
`projects[].agentIds` and `meetings[].agentIds`, in the same place every
other trace of a dismissed coworker is purged.

Run: python3 scripts/test_dismissed_coworker_leaves_no_stale_project_roster.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
PROJECTS_JSX = ROOT / 'views' / 'projects.jsx'
CHAT_JSX = ROOT / 'ui' / 'chat.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("Dismissing a coworker purges them from every project/meeting's agentIds roster")

    app_src = APP.read_text(encoding='utf-8')
    proj_src = PROJECTS_JSX.read_text(encoding='utf-8')
    chat_src = CHAT_JSX.read_text(encoding='utf-8')

    m = re.search(r"const onDismiss = async \(id\) => \{(.*?)\n  \};", app_src, re.S)
    check('onDismiss is still present and this test is looking at the '
          'right function', m is not None)
    body = m.group(1) if m else ''

    check('onDismiss drops every leaving id from projects[].agentIds',
          re.search(
              r"setProjects\(prev => prev\.map\(p => "
              r"\(p\.agentIds \|\| \[\]\)\.some\(pid => leaving\.has\(pid\)\)\s*\n\s*"
              r"\? \{ \.\.\.p, agentIds: p\.agentIds\.filter\(pid => !leaving\.has\(pid\)\) \} : p\)\);",
              body) is not None,
          'expected a setProjects(...) cascade filtering agentIds against `leaving`')

    check('onDismiss drops every leaving id from meetings[].agentIds too '
          '(same dangling-reference shape, same fix)',
          re.search(
              r"setMeetings\(prev => prev\.map\(m => "
              r"\(m\.agentIds \|\| \[\]\)\.some\(mid => leaving\.has\(mid\)\)\s*\n\s*"
              r"\? \{ \.\.\.m, agentIds: m\.agentIds\.filter\(mid => !leaving\.has\(mid\)\) \} : m\)\);",
              body) is not None,
          'expected a setMeetings(...) cascade filtering agentIds against `leaving`')

    # Confirm the cascade actually runs on the SAME `leaving` set used by the
    # tasks/approvals cascades above it, not a re-derived id — a stray
    # `leaving2`/`[id]`-only set would silently miss cascaded assistants.
    check("the project/meeting cascades come after the `leaving` set is "
          "computed (reuse the same set the tasks/approvals cascades use, "
          "so a cascaded-dismiss of assistants is covered too)",
          bool(re.search(r"const leaving = new Set\(.*?setProjects\(prev => prev\.map\(p =>",
                          body, re.S)))

    # Confirm the read sites this fix is protecting against are real, so the
    # test doesn't just check the fix's own shape in a vacuum.
    check('views/projects.jsx\'s ASSIGNED badge reads the raw agentIds '
          'length (the stale count this fix prevents)',
          "👥 ASSIGNED · {(project.agentIds || []).length}" in proj_src)
    check("deleteProject's confirm dialog computes the same raw count",
          re.search(r"const assignees = \(p\.agentIds \|\| \[\]\)\.length", proj_src)
          is not None)
    check("ui/chat.jsx gates the project chat-room tab on the same raw "
          "agentIds length (the stale tab this fix prevents from "
          "outliving every real assignee)",
          "p.agentIds.length > 0" in chat_src and "assigned`" in chat_src)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
