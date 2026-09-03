#!/usr/bin/env python3
"""WorkspaceView's <ProjectTerminal> must remount on project switch (views/projects.jsx).

Bug: WorkspaceView (views.jsx) renders a single <ProjectTerminal project={project} .../>
for both the desktop "Terminal" tab and the mobile "terminal" pane, and `project`
changes as the user picks a different project from the ws-projsel <select> —
but neither render call had a `key` tied to the project's identity, so React
reused the SAME component instance across the switch instead of unmounting it.

ProjectTerminal keeps its session-tab list (`sessions`/`activeId`) in
useStoredV, which is a plain useState seeded ONCE at mount by reading
localStorage for the CURRENT project id — it never re-reads when the id
changes later, because a prop change alone doesn't reset useState. So on an
un-keyed project switch the component kept showing the PREVIOUS project's
terminal tabs, and its debounced write-back effect (keyed on the CURRENT,
now-different, sessKey/activeKey) then persisted those stale tabs into the
NEW project's localStorage slot — silently overwriting whatever terminal
session list that project actually had. Reload (or reselect) that project
and its own tabs are gone, replaced by the other project's — including
`sessionId`s that the backend's /terminal/pty session_id reconnect path
(serve.py _terminal_pty_ws) will happily reattach to, so the browser can end
up showing project B's chrome while it's actually still talking to project
A's already-running PTY (wrong cwd).

Fix: give both ProjectTerminal call sites in WorkspaceView a
`key={project.id || project.path}` (the same technique ProjectsView's own
per-project `openedTerminals.map(pid => ...)` loop already used correctly),
forcing a full unmount/remount — and therefore a fresh localStorage read —
whenever the selected project changes.

This lifts the REAL WorkspaceView source out of views/projects.jsx
(brace-balanced extraction, like the app/*.jsx node suites) and checks the
structural invariant directly, rather than reimplementing React's
render/mount logic: every <ProjectTerminal> JSX call site inside
WorkspaceView must carry a `key=` expression that actually depends on
project.id or project.path. (ProjectsView, the OTHER function in this file
that also renders <ProjectTerminal>, already keys its per-project loop
correctly and is out of scope for this regression — WorkspaceView's
brace-balanced extraction stops at its own closing brace, well before
ProjectsView starts.)
Run: python3 scripts/test_workspace_terminal_key.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'views' / 'projects.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def extract_function(src, name):
    """Brace-balanced extraction of `function NAME(...) { ... }` — same
    technique test_artifacts.py uses to lift a span out of a bigger file."""
    m = re.search(r'function\s+' + re.escape(name) + r'\s*\([^)]*\)\s*\{', src)
    if not m:
        return None
    depth = 0
    i = m.end() - 1  # the opening '{'
    j = i
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
        j += 1
    return None


# A `key=` prop whose *expression* actually reads project.id or
# project.path — not just any `key=` (a static/unrelated key would compile
# but never force a remount when the project changes).
KEY_RE = re.compile(r'key=\{[^}]*project\.(?:id|path)[^}]*\}')


def main():
    print('WorkspaceView — <ProjectTerminal> keyed by project identity')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    text = SRC.read_text(encoding='utf-8')

    body = extract_function(text, 'WorkspaceView')
    check('WorkspaceView extracted from views/projects.jsx', body is not None)
    if body is None:
        print('\n1 failure(s)')
        return 1

    calls = re.findall(r'<ProjectTerminal\b[^>]*/>', body)
    # Two known render sites today: the mobile ws-mterm pane and the desktop
    # ws-cstage terminal tab. If this drops to 0 the extraction itself broke
    # (WorkspaceView renamed/restructured) — that's a hard fail, not a skip.
    check('found <ProjectTerminal> call sites in WorkspaceView', len(calls) >= 2,
          f'found {len(calls)}')

    for i, call in enumerate(calls):
        check(f'call site {i + 1} has key={{project.id|path}} — {call[:70]}…',
              bool(KEY_RE.search(call)), call)

    # Guard against a regression hiding behind a decoy: a project prop with no
    # key at all must never sneak back in.
    unkeyed = [c for c in calls if 'key=' not in c]
    check('no <ProjectTerminal> call site is missing key= entirely',
          len(unkeyed) == 0, str(unkeyed))

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'workspace terminal key: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
