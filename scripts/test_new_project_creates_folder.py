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

m = re.search(r'const commitProject = (async )?\(\{[^}]*\}\) => \{', src)
check(m, "views/projects.jsx: could not find the `commitProject` function.")
if m:
    check(
        m.group(1) == 'async ',
        "commitProject must be `async` — it now awaits CafresoHQClient.fsMkdir "
        "before adding the project.",
    )
    tail = src[m.end():]
    end = tail.index('\n  };')
    body = tail[:end]
    check(
        "source === 'local'" in body,
        "commitProject must gate the mkdir call on `source === 'local'` — "
        "GitHub-clone paths already exist (cloneRepo creates them), so this "
        "should only run for the local-folder tab.",
    )
    check(
        'fsMkdir' in body,
        "commitProject must call CafresoHQClient.fsMkdir(path) — the same "
        "call the '+ Folder' button already made, now run automatically so "
        "a brand-new project path is guaranteed to exist before the Files "
        "pane ever tries to list it.",
    )
    check(
        re.search(r'try\s*\{[^}]*fsMkdir', body) or 'catch' in body,
        "the fsMkdir call must be try/caught — a failure here (e.g. no "
        "permission) must fall back to today's existing 'not a directory' "
        "state, not break project creation outright.",
    )

if failures:
    print("FAIL:")
    for f in failures:
        print(f" - {f}")
    raise SystemExit(1)

print("ALL PASS")
