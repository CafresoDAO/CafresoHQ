#!/usr/bin/env python3
"""A new tester could not start the app, and the app's own advice was wrong.

Reproduced end to end on a fresh clone (`git archive HEAD | tar -x` into an
empty directory, which is exactly what a tester has):

  1. dist-ui/ and node_modules/ are both gitignored, so the clone has neither.
  2. GET /hq.html returned the stdlib 500 page: "HQ UI not built: … (run
     `npm run build`)".
  3. `npm run build` — the remedy that error itself names — died with

        Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'esbuild' imported
        from …/scripts/build_ui_bundle.mjs

     a raw Node stack that never says `npm install`, printed during MODULE
     RESOLUTION, before a single line of the builder ran.

Two dead ends before a pixel renders, and the second one is the app failing
at its own instruction. The README half was fixed in `#295`/`#296`; this is
the code half, because the failure has to explain itself to someone who
never opened the README.

Three fixes, and this test holds all three:

  * the builder loads `esbuild` behind a guard and exits with a sentence
    naming `npm install`;
  * serve.py's 500 names BOTH steps in order — on a fresh clone `npm run
    build` alone is not sufficient advice;
  * Start-CafresoHQ.sh, the script testers are actually pointed at, does the
    two steps itself instead of delegating them to a 500 page.

The builder check is behavioural, not textual: it RUNS the builder in a
temp directory with no node_modules anywhere above it and reads what a
tester would see.

Run: python3 scripts/test_a_fresh_clone_is_told_to_run_npm_install.py
"""
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILDER = ROOT / 'scripts' / 'build_ui_bundle.mjs'
SERVE = ROOT / 'serve.py'
LAUNCHER = ROOT / 'Start-CafresoHQ.sh'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_js_comments(src):
    """Drop // and /* */ comments so this file's own prose about the bad
    pattern cannot satisfy — or trip — a check on the real code."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in '"\'`':
            q, j = c, i + 1
            while j < n and src[j] != q:
                j += 2 if src[j] == '\\' else 1
            out.append(src[i:j + 1])
            i = j + 1
        elif src.startswith('//', i):
            j = src.find('\n', i)
            i = n if j < 0 else j
        elif src.startswith('/*', i):
            j = src.find('*/', i)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def strip_sh_comments(src):
    return '\n'.join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith('#'))


def serve_not_built_message():
    """The literal serve.py hands to send_error for a missing bundle.

    `## 396.` split that call in two: the reason phrase is now the bare
    'HQ UI not built' (the HTTP status line is latin-1 and cannot carry the
    em dash), and the advice moved into the `explain` argument, which is
    what the browser actually renders. There are therefore two constants
    matching here and the first one ast.walk reaches is the short one, so
    take the LONGEST — the advice is the half this test is about.
    """
    tree = ast.parse(SERVE.read_text(encoding='utf-8'))
    found = [node.value for node in ast.walk(tree)
             if isinstance(node, ast.Constant) and isinstance(node.value, str)
             and 'HQ UI not built' in node.value]
    return max(found, key=len) if found else None


def main():
    print('fresh clone: the failure paths name npm install')

    # ---- 1. the builder does not die during module resolution -------------
    code = strip_js_comments(BUILDER.read_text(encoding='utf-8'))
    check('the builder has no top-level static import of esbuild',
          not re.search(r'^\s*import[^\n]*\bfrom\s*[\'"]esbuild[\'"]', code, re.M),
          'a static import fails before any code runs, so the script cannot '
          'explain itself')
    check('the builder imports esbuild dynamically',
          re.search(r'import\s*\(\s*[\'"]esbuild[\'"]\s*\)', code) is not None)

    # ---- 2. what a tester on a fresh clone actually sees -------------------
    if shutil.which('node') is None:
        print('  SKIP  node not on PATH (builder behaviour)')
    else:
        # A temp dir OUTSIDE the repo: node walks ancestors looking for
        # node_modules, so running this inside the checkout would resolve
        # esbuild from a parent and never exercise the missing-deps path.
        tmp = tempfile.mkdtemp(prefix='hq-freshclone-')
        try:
            os.makedirs(os.path.join(tmp, 'scripts'))
            shutil.copy(BUILDER, os.path.join(tmp, 'scripts', BUILDER.name))
            shutil.copy(ROOT / 'package.json', os.path.join(tmp, 'package.json'))
            p = subprocess.run(['node', 'scripts/build_ui_bundle.mjs'],
                               cwd=tmp, capture_output=True, text=True, timeout=120)
            said = (p.stdout + p.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        check('the builder fails loudly with no dependencies installed',
              p.returncode != 0, f'exited {p.returncode}')
        check('the builder names `npm install`', 'npm install' in said,
              repr(said[:400]))
        check('the builder does not dump a raw ERR_MODULE_NOT_FOUND stack',
              'ERR_MODULE_NOT_FOUND' not in said and 'at ModuleJob' not in said,
              repr(said[:400]))

    # ---- 3. the 500 page names both steps, in order -----------------------
    msg = serve_not_built_message()
    check('serve.py still has a "HQ UI not built" message', msg is not None)
    if msg:
        check('the 500 page names `npm install`', 'npm install' in msg, repr(msg))
        check('the 500 page names `npm run build`', 'npm run build' in msg, repr(msg))
        check('it names install BEFORE build',
              msg.find('npm install') < msg.find('npm run build'),
              'build-then-install is not a sequence anyone can follow')

    # ---- 4. the launcher testers are pointed at does the work -------------
    sh = strip_sh_comments(LAUNCHER.read_text(encoding='utf-8'))
    check('the launcher checks for a built bundle',
          'dist-ui/manifest.json' in sh,
          'it started serve.py unconditionally, so a fresh clone got the 500')
    check('the launcher installs dependencies when they are absent',
          'npm install' in sh and 'node_modules' in sh)
    check('the launcher builds the bundle', 'npm run build' in sh)
    check('the launcher says what to do when npm is missing',
          re.search(r'command -v npm', sh) is not None
          and 'nodejs.org' in sh.lower(),
          'without npm it can neither install nor explain')

    print()
    if FAILS:
        print(f'fresh clone: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('fresh clone: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
