#!/usr/bin/env python3
"""Workspace mode — the DEFAULT mode — could not put a coworker on a project.

Found 2026-08-13 while driving a real coworker in a real project. The
Workspace's third pane is titled "Coworkers · working together" and its
body copy read "Your coworkers share this folder & shell." Its only
control was a TALK button, and that button is

    disabled={(project.agentIds || []).length === 0}

so in the empty state it offered a disabled button, a sentence about
coworkers who were not there, and no way to change either. The roster of
assignment checkboxes existed only in `ProjectsView` (Classic). A boss who
never found the Workspace/Classic toggle could not staff a project at all.

That is not a missing convenience. Assignment is the gate for everything
downstream: `agentIds` is what makes the "📁 <project>" room appear in the
chat panel, what makes a message fan out to the team, and what gives this
pane anybody to report on. Until a coworker is assigned, the entire
"watch your coworkers work" surface has nothing to watch — which is the
product's north star sitting behind a control in another mode.

Fix: a crew strip in the Workspace's own coworkers pane — one toggle chip
per hired coworker, plus an honest empty state when nobody is hired and a
different one when nobody is assigned.

Run: python3 scripts/test_workspace_crew.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'views' / 'projects.jsx'

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


src = SRC.read_text()

# Everything below must live in WorkspaceView, not Classic — being present
# somewhere in the file is exactly the bug this test exists to catch.
ws_start = src.find('function WorkspaceView')
cls_start = src.find('function ProjectsView')
check(ws_start != -1 and cls_start != -1 and ws_start < cls_start,
      "views/projects.jsx: could not locate WorkspaceView and ProjectsView.")

ws = src[ws_start:cls_start] if (ws_start != -1 and cls_start != -1) else ''

check(
    re.search(r'const toggleAgent = \(agentId\) => \{', ws),
    "WorkspaceView must own a toggleAgent — the assignment control lived "
    "only in Classic, leaving the default mode unable to staff a project.",
)
check(
    re.search(r'agentIds: cur\.includes\(agentId\)\s*\?\s*cur\.filter', ws),
    "WorkspaceView's toggleAgent must toggle membership of project.agentIds "
    "(off when already on, on when not) — assignment has to be reversible "
    "from the same control that grants it.",
)
check(
    re.search(r"p\.id !== project\.id", ws),
    "toggleAgent must only rewrite the CURRENTLY selected project — mapping "
    "over every project without that guard reassigns the whole list.",
)

# The crew strip itself, in the coworkers pane.
check('ws-crew-chip' in ws,
      "the Workspace coworkers pane must render a crew chip per hired "
      "coworker — this is the assignment control the pane was missing.")
check(
    re.search(r"onClick=\{\(\) => toggleAgent\(a\.id\)\}", ws),
    "each crew chip must call toggleAgent — a chip that only looks "
    "selectable is the same dead end as the disabled TALK button.",
)
check(
    re.search(r"const on = \(project\.agentIds \|\| \[\]\)\.includes\(a\.id\)", ws),
    "each chip must reflect real assignment state from project.agentIds, "
    "not local state — the boss has to be able to see who is actually on "
    "the project.",
)

# Honest empty states: hired-nobody and assigned-nobody are different
# problems with different fixes, and the pane used to describe neither.
check(
    re.search(r"agents\.length === 0[\s\S]{0,120}visit Team", ws),
    "with nobody hired, the crew strip must say so and point at Team — "
    "otherwise the pane is an empty box with no explanation.",
)
# The inline ternary this used to match has since moved into `ledgerEmpty()`,
# which resolves agentIds into the actual coworkers (`crew`) so it can also
# tell a crew that holds file access from one that does not — see
# test_the_workspace_only_reports_its_own_folder.py. The claim being pinned
# here is unchanged: no crew, say so.
check(
    re.search(r"!crew\.length\)[\s\S]{0,80}Nobody is on this project yet", ws),
    "with nobody ASSIGNED, the ledger's empty state must say nobody is on "
    "the project — the old copy (\"Your coworkers share this folder & "
    "shell\") described a collaboration that was not happening.",
)

# The strip must sit in the coworkers pane, above the ledger it explains.
check(
    ws.find('ws-crew') != -1 and ws.find('ws-crew') < ws.find('ws-ledger'),
    "the crew strip belongs above the activity ledger in the coworkers "
    "pane — it is the thing that makes the ledger have content.",
)

# The TALK button's gate is fine; what was missing was a way to satisfy it.
check(
    re.search(r"className=\"ws-talk\" disabled=\{\(project\.agentIds \|\| \[\]\)\.length === 0\}", ws),
    "TALK stays disabled until somebody is assigned — that gate is correct "
    "and should remain; the bug was that nothing in this mode could "
    "un-disable it.",
)

# Styles for the strip must exist, or the control ships invisible.
css = (ROOT / 'styles.css').read_text()
for cls in ('.ws-crew ', '.ws-crew-chip', '.ws-crew-chip.on', '.ws-crew-empty'):
    check(cls in css,
          f"styles.css is missing `{cls}` — an unstyled crew strip is a row "
          "of unreadable buttons in the one pane that has to make "
          "collaboration legible.")

if failures:
    print("FAIL:")
    for f in failures:
        print(f" - {f}")
    raise SystemExit(1)

print("ALL PASS")
