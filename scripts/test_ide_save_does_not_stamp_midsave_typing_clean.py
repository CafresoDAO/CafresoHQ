#!/usr/bin/env python3
"""Saving must not stamp keystrokes typed DURING the save as clean (views/projects.jsx).

Bug: both editors' save paths — WorkspaceView's save() and ProjectsView's
saveFile() — capture the open file (`f` / `openFile`) at click time, then run
three awaited round trips (fsStat conflict check, FILE_WRITE, fsStat re-stamp)
while the textarea stays enabled. Keystrokes that land during those round
trips update state via onEdit (content + dirty:true). The completion updater
then spread the CURRENT state and stamped `dirty: false` unconditionally:

    setOpenFile(o => (o && o.path === f.path)
      ? { ...o, hash: nh, mtime: nm, dirty: false } : o);

So the disk held the click-time content, the buffer held the newer typing,
and the buffer read CLEAN. The dirty dot and the Save button vanished; every
switch guard (openPath, switchProject, flipMode — all keyed on cur.dirty)
skipped its "Discard unsaved changes?" confirm; and the agent event bus's
clean-buffer branch (`cur.dirty ? setConflict(true) : reloadOpen(arg)`)
silently reloaded a coworker's write straight over the typing.

Fix: only the content that was actually written may be stamped clean —
`dirty: o.content !== f.content` (and the openFile twin in saveFile). The
hash/mtime re-stamp still applies: they describe the disk, which now holds
the captured content, so the NEXT save's conflict check has the right
baseline either way.

This lifts the REAL updater arrows out of views/projects.jsx (brace-balanced
function extraction, then paren-balanced argument extraction of the
setOpenFile(...) call that carries the re-stamped `nh`) and EXECUTES them in
node against two states: a buffer that kept typing during the save must stay
dirty; an untouched buffer must come back clean.
Run: python3 scripts/test_ide_save_does_not_stamp_midsave_typing_clean.py
"""
import json
import re
import subprocess
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


def extract_arrow_const(src, name):
    """Brace-balanced extraction of `const NAME = async (...) => { ... }`."""
    m = re.search(r'const\s+' + re.escape(name) + r'\s*=\s*async\s*\([^)]*\)\s*=>\s*\{', src)
    if not m:
        return None
    depth = 0
    j = m.end() - 1  # the opening '{'
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
        j += 1
    return None


def extract_updater(fn_body):
    """The argument of the post-write setOpenFile(...) call — the one that
    re-stamps the fresh hash (`nh`). Paren-balanced from the call's '('."""
    for m in re.finditer(r'setOpenFile\(', fn_body):
        i = m.end() - 1
        depth = 0
        j = i
        while j < len(fn_body):
            if fn_body[j] == '(':
                depth += 1
            elif fn_body[j] == ')':
                depth -= 1
                if depth == 0:
                    arg = fn_body[i + 1:j]
                    if 'nh' in arg and 'nm' in arg:
                        return arg
                    break
            j += 1
    return None


def run_updater(arrow, captured_var):
    """Execute the lifted arrow in node. `captured_var` is the click-time
    snapshot the save wrote to disk (f in Workspace, openFile in Classic)."""
    js = (
        'const %s = { path: "/p/a.js", content: "saved-content" };\n'
        'const nh = "h2", nm = 2;\n'
        'const up = (%s);\n'
        '// buffer that kept typing while the save was in flight\n'
        'const typed = up({ path: "/p/a.js", content: "saved-content-plus-typing", dirty: true, hash: "h1", mtime: 1 });\n'
        '// buffer untouched since the click\n'
        'const still = up({ path: "/p/a.js", content: "saved-content", dirty: true, hash: "h1", mtime: 1 });\n'
        '// a different file must pass through unchanged\n'
        'const other = up({ path: "/p/b.js", content: "x", dirty: true, hash: "z", mtime: 9 });\n'
        'console.log(JSON.stringify({\n'
        '  typedDirty: typed.dirty, typedContent: typed.content, typedHash: typed.hash,\n'
        '  stillDirty: still.dirty, otherUntouched: other.dirty === true && other.hash === "z",\n'
        '}));\n'
    ) % (captured_var, arrow)
    r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
    if r.returncode != 0:
        return None, (r.stderr or r.stdout).strip()
    return json.loads(r.stdout.strip()), None


def main():
    print('IDE save — keystrokes typed during the save keep their dirty dot')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    text = SRC.read_text(encoding='utf-8')

    for label, fn_name, captured in (
        ('WorkspaceView save()', 'save', 'f'),
        ('ProjectsView saveFile()', 'saveFile', 'openFile'),
    ):
        body = extract_arrow_const(text, fn_name)
        check(f'{label} extracted from views/projects.jsx', body is not None)
        if body is None:
            continue
        arrow = extract_updater(body)
        check(f'{label} post-write setOpenFile updater found', arrow is not None)
        if arrow is None:
            continue
        out, err = run_updater(arrow, captured)
        check(f'{label} updater executes in node', out is not None, err or '')
        if out is None:
            continue
        check(f'{label}: buffer typed-during-save stays DIRTY',
              out['typedDirty'] is True, f'dirty={out["typedDirty"]}')
        check(f'{label}: typed content itself is preserved',
              out['typedContent'] == 'saved-content-plus-typing')
        check(f'{label}: hash re-stamps to the disk state either way',
              out['typedHash'] == 'h2')
        check(f'{label}: untouched buffer comes back clean',
              out['stillDirty'] is False, f'dirty={out["stillDirty"]}')
        check(f'{label}: a different open file passes through unchanged',
              out['otherUntouched'] is True)

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'ide save mid-save typing: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
