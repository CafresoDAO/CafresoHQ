#!/usr/bin/env python3
"""The Workspace's live-presence feed watched the wrong paths, then skipped code.

Two defects, both in WorkspaceView's `cafresohq:agentTool` handler in
views/projects.jsx, both found by driving a real coworker in a real project
on 2026-08-13. Together they meant the "watch them work" pitch — the whole
reason the Workspace exists — did nothing for the ordinary case.

1. PATH IDENTITY. The runtime emits the marker argument verbatim, so a
   coworker working inside a project writes `index.html`, not
   `/abs/path/site/index.html`. The pane's tree, `openFile.path` and
   `fsReadText` are all absolute. Nothing ever matched:

     · the tree pulse highlighted a path not in the tree,
     · Follow along called fsReadText('index.html'), which fails, and the
       error renders only inside the editor pane — with no file open the
       failure was completely invisible,
     · `cur.path === arg` (reload the file you are LOOKING AT, or raise the
       conflict banner over your unsaved edits) could never be true, so a
       coworker could silently overwrite the file under your cursor.

   Measured live: the runtime's own relative-arg event left the editor
   showing stale content with no banner; the identical event carrying the
   absolute path reloaded it instantly.

2. THE CODE GATE. Follow along was guarded by `previewKind(arg) !== 'code'`,
   so it opened .md/.html/.svg/.csv and skipped .js, .py, .css, .json — i.e.
   nearly everything a coworker writes in a code workspace — while the
   checkbox beside it promised "Auto-open whatever file they are writing".
   Measured live: a .md write followed, the very next .js write did not, and
   the stage silently kept showing the stale file. The gate was not
   protecting unsaved work either — openPath's own `auto` branch does that,
   by returning early on a dirty buffer.

Run: python3 scripts/test_workspace_follow.py
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

# ── 1. path identity ────────────────────────────────────────────────────────
check(
    re.search(r'const projectRef = React\.useRef\(', src),
    "views/projects.jsx: `projectRef` is gone — the agentTool listener is "
    "mounted once with [] deps, so it can only see the selected project "
    "through a ref. Reading `project` directly there captures the value from "
    "first mount and silently resolves against a stale (or absent) root.",
)
check(
    re.search(r'projectRef\.current = project;', src),
    "projectRef must be kept in sync with the selected project — a ref that "
    "is never assigned resolves every relative path against `undefined`.",
)

# Second parameter since the "only report your own folder" pass: a relative
# path is resolved against the directory the coworker was actually standing
# in, not against whichever project happens to be selected.
m = re.search(r'const resolveInProject = \(p, cwd\) => \{(.*?)\n  \};', src, re.S)
check(m, "views/projects.jsx: `resolveInProject` is gone. Marker args arrive "
         "project-relative and every consumer in this pane is absolute; "
         "without this one conversion the tree pulse, Follow along and the "
         "open-file reload/conflict branch all go dead again.")

if m:
    body = m.group(1)
    check(
        "startsWith('/')" in body,
        "resolveInProject must pass POSIX absolute paths through untouched — "
        "tools that already emit an absolute path (and every non-project "
        "caller) must not get the project root glued on front.",
    )
    check(
        re.search(r'[A-Za-z]:\[\\\\/\]', body) or 'A-Za-z' in body,
        "resolveInProject must pass Windows absolute paths (C:\\...) through "
        "untouched too — same reason as POSIX.",
    )
    check(
        'projectRef.current' in body and 'joinPath' in body,
        "resolveInProject must join against the CURRENT project's path via "
        "projectRef — that is the whole point of the conversion.",
    )
    # This used to require the arg BACK unchanged when there was no project.
    # Passing it through is what let an unresolvable path travel on and get
    # filed anyway; '' is the honest answer and every caller reads it as
    # "not mine". See test_the_workspace_only_reports_its_own_folder.py.
    check(
        re.search(r"if \(!s \|\| !base\) return '';", body),
        "with no project selected there is no root to resolve against; "
        "resolveInProject must say it cannot place the path rather than "
        "handing back something that reads like one.",
    )

# The conversion has to happen for FILE_* only: vault and export args are
# vault-relative and have nothing to do with this project tree.
handler = re.search(
    r"const onAgentTool = \(e\) => \{(.*?)\n    \};", src, re.S)
check(handler, "the `onAgentTool` handler is gone from views/projects.jsx — "
               "it is the Workspace's entire live-presence feed.")

if handler:
    h = handler.group(1)
    check(
        re.search(
            r"name === 'FILE_WRITE' \|\| name === 'FILE_READ';[\s\S]{0,200}"
            r"\?\s*resolveInProject\(d\.arg, d\.cwd\)",
            h,
        ),
        "onAgentTool must run FILE_WRITE/FILE_READ args through "
        "resolveInProject before using them — using `d.arg` raw is exactly "
        "the bug: a relative arg matches nothing in this pane.",
    )
    check(
        re.search(r"resolveInProject\(d\.arg, d\.cwd\)\s*\n?\s*:\s*String\(d\.arg \|\| ''\)\.trim\(\)", h),
        "the ternary's OTHER branch must still take d.arg raw — only the "
        "FILE_* tools may be resolved against the project root, because "
        "vault and export args are vault-relative and gluing the project "
        "path onto them would point at files that do not exist.",
    )

    # ── 2. the code gate ────────────────────────────────────────────────────
    follow = re.search(r'\} else if \(isWrite && followRef\.current([^)]*)\)', h)
    check(follow, "the Follow-along branch is gone — the checkbox would be "
                  "inert.")
    if follow:
        check(
            "previewKind" not in follow.group(1),
            "Follow along must NOT be gated on previewKind — that gate "
            "skipped every code file (.js, .py, .css, .json) while the "
            "checkbox promised \"Auto-open whatever file they are writing\", "
            "and an editor whose main job is showing code following "
            "everything EXCEPT code is the least defensible version of this "
            "feature. Unsaved edits are protected by openPath's `auto` "
            "branch, not by this check.",
        )

# The dirty-buffer guard that the removed gate was NOT providing must exist,
# or dropping the gate really would start clobbering unsaved work.
op = re.search(r'const openPath = async \(path, opts\) => \{(.*?)\n  \};', src, re.S)
check(op, "openPath is gone from views/projects.jsx.")
if op:
    body = op.group(1)
    check(
        re.search(r'const mustAsk = !!\(cur && cur\.dirty && cur\.path !== path\);', body)
        and re.search(r'if \(mustAsk && opts && opts\.auto\) return;', body),
        "openPath must still bail out of an AUTO open when the current "
        "buffer is dirty — this is the guard that makes ungated Follow along "
        "safe. Lose it and a coworker's write yanks the boss off their own "
        "unsaved edits.",
    )
    # #409 — that guard is made BEFORE the read, and the read is a round trip
    # the boss can type through. The far side has to bail the same way, or the
    # guard above only covers typing that had already happened.
    check(
        re.search(r'if \(opts && opts\.auto\) \{ setBusy\(false\); return; \}', body),
        "an AUTO open must also bail when the buffer went dirty DURING its "
        "read — measured in #409: Follow along landed on a paragraph that was "
        "never saved anywhere.",
    )

# The label the code has to live up to.
check(
    'Auto-open whatever file they are writing' in src,
    "the Follow-along label/title changed — if the promise is reworded, this "
    "test's expectations about what the checkbox must do need rewording too.",
)

if failures:
    print("FAIL:")
    for f in failures:
        print(f" - {f}")
    raise SystemExit(1)

print("ALL PASS")
