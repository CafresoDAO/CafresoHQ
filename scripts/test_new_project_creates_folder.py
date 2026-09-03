#!/usr/bin/env python3
""""Create your first project" dead-ended on "Not a directory" for anyone
who actually followed the onboarding copy.

The Projects "Local folder" tab's Add form only ever did
`onCommit({name, path, source: 'local'})` -- it never created `path`. The
GitHub-clone tab's path always exists (cloneRepo creates it server-side),
so this only ever bit the local tab. But that tab is exactly where the
onboarding checklist's "Create your first Project" step and the empty-
state's "Create your first project" button both funnel a brand-new boss,
and a brand-new boss doesn't have a pre-existing empty projects folder to
point at -- they type a path for something that doesn't exist yet. Result:
the Files pane's first-ever render read "Not a directory: /tmp/…", with no
visible way out (the fix was the unrelated "+ Folder" button already doing
`mkdir(parents=True)` as a side effect of creating a subfolder -- not
something a first-timer staring at a raw filesystem error would guess).

Fix: `commitProject` in views/projects.jsx now best-effort creates the
path via the same `CafresoHQClient.fsMkdir` call "+ Folder" already used,
for the 'local' source only. An existing path (the "point me at my real
repo" case this tab's own copy also describes) round-trips through
fs_routes.py's `_fs_mkdir`, which already returns `{ok: True, existed:
True}` for a path that's already a directory -- so this changes nothing
for that case and only helps the empty-path one.

Verified live: rebuilt the bundle, added a project pointed at a path that
did not exist on disk, and confirmed via `ls` that the directory was
created and the Files pane showed its normal empty state instead of the
error.

Run: python3 scripts/test_new_project_creates_folder.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / 'views' / 'projects.jsx'

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


src = PROJECTS.read_text()

# There are now TWO commitProject functions: ProjectsView's (Classic) and
# WorkspaceView's (the workspace empty state commits without leaving the
# view). Every copy must carry the mkdir guarantee — a regression in either
# one re-opens the "Not a directory" dead end on that path.
matches = list(re.finditer(r'const commitProject = (async )?\(\{[^}]*\}\) => \{', src))
check(
    len(matches) >= 2,
    "views/projects.jsx: expected commitProject in BOTH WorkspaceView and "
    f"ProjectsView (found {len(matches)}) — if one was consolidated into a "
    "shared helper, update this test to point at the helper instead.",
)
# The mkdir was consolidated into the shared `_addProjectMkdir` helper (#149,
# which also made the create audible in the toast). This file said in the
# message above what to do if that ever happened — "update this test to point
# at the helper instead" — so the three guarantees below moved with it rather
# than being deleted. What each commitProject still owes is that it CALLS the
# helper and waits for it; the guarantees themselves are now the helper's.
helper = re.search(r'const _addProjectMkdir = [\s\S]*?\n\};', src)
check(
    bool(helper),
    "views/projects.jsx: the shared `_addProjectMkdir` helper is gone — if "
    "the mkdir moved again, point these checks at wherever it lives now, or "
    "the 'Not a directory' dead end comes back unnoticed.",
)
hbody = helper.group(0) if helper else ''
check(
    "source !== 'local'" in hbody or "source === 'local'" in hbody,
    "_addProjectMkdir must gate the mkdir on the local-folder source — "
    "GitHub-clone paths already exist (cloneRepo creates them server-side), "
    "so this must not run for that tab.",
)
check(
    'fsMkdir' in hbody,
    "_addProjectMkdir must call fsMkdir(path) — the same call the '+ Folder' "
    "button already made, run automatically so a brand-new project path is "
    "guaranteed to exist before the Files pane ever tries to list it.",
)
check(
    re.search(r'try\s*\{[\s\S]*?fsMkdir', hbody) and 'catch' in hbody,
    "the fsMkdir call in _addProjectMkdir must be try/caught — a failure here "
    "(e.g. no permission) must fall back to today's existing 'not a "
    "directory' state, not break project creation outright.",
)
for i, m in enumerate(matches):
    who = f"commitProject #{i + 1}"
    check(
        m.group(1) == 'async ',
        f"{who} must be `async` — it awaits the mkdir before adding the "
        "project.",
    )
    tail = src[m.end():]
    end = tail.index('\n  };')
    body = tail[:end]
    check(
        re.search(r'await\s+_addProjectMkdir\(', body),
        f"{who} must await _addProjectMkdir(...) — a commit step that skips "
        "it re-opens the 'Not a directory' dead end on that path, and one "
        "that does not await it files the project before the folder exists.",
    )

# The Workspace empty state's "Create your first project" button must open
# the Add-Project dialog IN PLACE — not flip to Classic. The first rewrite
# renamed the CTA but kept `flipMode('classic')`, so a brand-new boss at
# onboarding step 5 clicked a button named after the thing they wanted and
# got a second empty state ("Click + ADD") in a mode they never asked for.
# Watched live on a fresh office 2026-08-13.
noproj = re.search(r'className="ws-noproj">(.*?)</div>\s*\)', src, re.S)
check(noproj, "views/projects.jsx: could not find the ws-noproj empty state.")
if noproj:
    block = noproj.group(1)
    check(
        'setShowAdd(true)' in block,
        "the ws-noproj 'Create your first project' button must open the "
        "Add-Project modal (setShowAdd(true)) — a button does the thing it "
        "is named after.",
    )
    check(
        "flipMode('classic')" not in block,
        "the ws-noproj empty state must NOT flip to Classic — that lands a "
        "first-time boss on a second empty state instead of the dialog.",
    )
check(
    src.count('<AddProjectModal') >= 3,
    "WorkspaceView must render its own <AddProjectModal> (expected the two "
    "ProjectsView render sites plus WorkspaceView's) — without it, "
    "setShowAdd(true) in the workspace empty state opens nothing.",
)

if failures:
    print("FAIL:")
    for f in failures:
        print(f" - {f}")
    raise SystemExit(1)

print("ALL PASS")
