#!/usr/bin/env python3
"""Workspace mode — the DEFAULT mode — could add a FIRST project but never
a second one.

test_new_project_creates_folder.py already pins the fix for the `!project`
empty state: its "Create your first project" button calls
`setShowAdd(true)` in place, instead of flipping to Classic. That fix only
ever covered the empty state, because the button living there is the ONLY
thing in WorkspaceView that ever called `setShowAdd(true)` for a NEW
project. The instant `project` is truthy — i.e. the moment a boss has
exactly one project, which is nearly always — that branch unmounts for
good, and nothing replaces it.

Measured live 2026-08-30: built the bundle, opened Projects (lands on
Workspace by default), added one project, and confirmed there. From there
the topbar only ever offered the mode toggle, the project `<select>`
(switches between EXISTING projects, doesn't add one), the path label, the
Follow-along checkbox and the status pip. No button. `⌨ Shortcuts` lists
nothing for it either (H hire, S settings, M memory, N sticky note, U
stand-up, F 1:1, D day/night, / focus chat). The only surviving door was
Classic's own always-present "+ ADD" (views/projects.jsx's ProjectsView,
both the desktop sidebar header and the mobile list header render it
unconditionally, `projects.length` or not) — undiscoverable from the
default mode, the exact "Classic means nothing to a four-minute-old boss"
problem the empty-state CTA was rewritten to avoid.

Fix: a "+ Add" button in the topbar's `mode === 'workspace' && project`
branch, next to the project selector, calling the same `setShowAdd(true)`
the empty state uses — WorkspaceView already renders its own
<AddProjectModal> unconditionally at the end of the component, so no new
plumbing is needed, only the missing door.

Verified live: rebuilt the bundle, clicked the new button with a project
already selected, filled in the modal, and the second project appeared
selected in the (now two-option) dropdown — same commitProject() flow the
empty state already used.

Run: python3 scripts/test_a_second_project_had_no_door_in_workspace.py
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

ws_start = src.find('function WorkspaceView')
cls_start = src.find('function ProjectsView')
check(ws_start != -1 and cls_start != -1 and ws_start < cls_start,
      "views/projects.jsx: could not locate WorkspaceView and ProjectsView.")
ws = src[ws_start:cls_start] if (ws_start != -1 and cls_start != -1) else ''

# The topbar branch that renders once a project exists — the ONLY place a
# second-project door can live without also being visible on the (already
# separately covered) empty state.
topbar = re.search(
    r"\{mode === 'workspace' && project && \(\s*<>([\s\S]*?)</>\s*\)\}", ws)
check(bool(topbar),
      "WorkspaceView: could not find the `mode === 'workspace' && project` "
      "topbar branch that renders the project selector.")
block = topbar.group(1) if topbar else ''

check(
    bool(re.search(r'onClick=\{\(\) => setShowAdd\(true\)\}', block)),
    "WorkspaceView's topbar must open Add Project even when a project "
    "ALREADY exists. The only such button lives in the `!project` empty "
    "state today (see test_new_project_creates_folder.py), which unmounts "
    "for good the moment the first project is added — from then on this "
    "mode has no button, no menu, and no shortcut that opens Add Project, "
    "and the only surviving door is Classic's undiscoverable '+ ADD'.",
)

check(
    block.find('<select') != -1
    and 0 <= block.find('<select') < block.find('setShowAdd(true)')
    if 'setShowAdd(true)' in block else False,
    "the new Add-project control must sit in the SAME branch as the "
    "project `<select>` (i.e. only rendered once a project exists) — a "
    "copy left only in the empty state doesn't fix anything, since that "
    "branch already had its own door.",
)

# WorkspaceView must still own the modal that setShowAdd(true) opens — this
# doesn't change with the fix, but a regression that dropped the shared
# <AddProjectModal> render site would make the new button open nothing.
check(
    '<AddProjectModal' in ws,
    "WorkspaceView must render its own <AddProjectModal> — without it, "
    "setShowAdd(true) from the new topbar button opens nothing.",
)

# Styling: an unstyled button in a tightly-packed topbar ships invisible or
# unclickable, same risk test_workspace_crew.py already flags for the crew
# strip.
css = (ROOT / 'styles.css').read_text()
check(
    '.ws-addproj' in css,
    "styles.css must style the new Add-project topbar button (e.g. via a "
    "`.ws-addproj` rule) — an unstyled control risks shipping invisible or "
    "with no clickable affordance.",
)

if failures:
    print("FAIL:")
    for f in failures:
        print(f" - {f}")
    raise SystemExit(1)

print("ALL PASS")
