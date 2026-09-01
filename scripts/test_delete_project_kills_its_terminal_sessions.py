#!/usr/bin/env python3
"""Deleting a project used to leave its terminal PTY sessions running
server-side forever (up to _PTY_SESSION_TTL, but with no client left to
ever reconnect or kill them) and their localStorage entries orphaned for
good.

`deleteProject` (views/projects.jsx) only filtered the project out of
`projects` and dropped its id from `openedTerminals` — the comment right
above that second line even said the intent was "or the PTY stays
connected to a project that no longer exists," but removing the id from
`openedTerminals` only unmounts the React <ProjectTerminal> component; it
never called /terminal/kill for any of that project's sessionIds. The
only place that ever hit /terminal/kill was `closeSession` inside
ProjectTerminal (terminal.jsx), which fires solely on an explicit tab-close
click — unmounting the component doesn't invoke it. Worse, closeSession's
localStorage cleanup (mode/msgs/model/auth per session, which can be
hundreds of KB after a long conversation) never ran either, and the
project's own `cafresohq_terminal:sessions:<id>` / `:active:<id>` keys
were never removed — so those accumulated in localStorage forever, one
orphaned set per deleted project.

Found by a background hunt agent sweeping previously-uncovered areas
(Calendar, Library/Graph, Meetings, Night Shift, Settings, notifications,
CEO 1:1, drag-and-drop task assignment).

Fix: `deleteProject` now reads the project's persisted session list from
`cafresohq_terminal:sessions:<p.id>`, fires /terminal/kill for each
sessionId (best-effort, mirroring closeSession's own kill call), removes
each session's mode/msgs/model/auth localStorage keys, and finally
removes the project's own `sessions`/`active` keys.

Run: python3 scripts/test_delete_project_kills_its_terminal_sessions.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / 'views' / 'projects.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("Deleting a project kills its open terminal PTY sessions and clears their storage")

    src = PROJECTS.read_text(encoding='utf-8')

    m = re.search(r"const deleteProject = async \(p\) => \{(.*?)\n  \};", src, re.S)
    check('deleteProject is still present', m is not None)
    body = m.group(1) if m else ''

    check("it still drops the project's keep-alive terminal mount "
          "(the pre-existing behavior this fix must not regress)",
          "setOpenedTerminals(prev => prev.filter(id => id !== p.id));" in body)

    check("it reads the project's persisted terminal session list from "
          "localStorage (cafresohq_terminal:sessions:<id>)",
          "`cafresohq_terminal:sessions:${p.id}`" in body)

    check("it calls /terminal/kill for every session that has a sessionId "
          "(best-effort, matching closeSession's own kill call)",
          re.search(r"/terminal/kill\?session_id=\$\{encodeURIComponent\(s\.sessionId\)\}",
                     body) is not None)

    check("it clears each session's mode/msgs/model/auth localStorage keys "
          "(the same four suffixes closeSession clears per-tab)",
          "['mode', 'msgs', 'model', 'auth'].forEach(suffix =>" in body
          and "`cafresohq_terminal:${suffix}:${p.id}:${s.sessionId}`" in body)

    check("it removes the project's own sessions and active keys once "
          "every session under them has been handled",
          "localStorage.removeItem(sessKey);" in body
          and "localStorage.removeItem(`cafresohq_terminal:active:${p.id}`);" in body)

    check("the cleanup is wrapped so a localStorage/JSON failure can never "
          "block the delete itself",
          re.search(r"try \{.*?localStorage\.removeItem\(sessKey\);.*?\} catch",
                     body, re.S) is not None)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
