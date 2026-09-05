#!/usr/bin/env python3
"""The README asked for Node 18+ and nothing in the repo ever checked.

`## 405.` walked the README's own first-run sequence from a `git archive` of the
branch into an empty directory. The sequence itself works — `npm install`,
`npm run build`, `python3 serve.py`, `GET /hq.html -> 200 11071b`. What it does
not do is notice the one prerequisite it states.

WHAT WAS THERE.  `package.json` declared no `engines` at all. Two of its own
dependencies do — `esbuild@0.24.2` says `{"node": ">=18"}` and `eslint` says
`^18.18.0 || ^20.9.0 || >=21.1.0` — and npm treats every `engines` field as a
WARNING by default. So a tester on Node 16 got `npm warn EBADENGINE`, buried
under 265 packages of install chatter, and then a cheerful "added 265 packages".
The build that followed failed from somewhere inside the bundler, in a message
that never says the word "Node". The prerequisite was stated in prose and
enforced nowhere.

WHAT THIS ASSERTS, as invariants rather than as one pinned string:

  1. The floor is DECLARED once, in `package.json`'s `engines.node`.
  2. The floor is at least as high as the highest floor any installed
     dependency declares — otherwise the repo's own number is a fiction and
     npm's per-package check is the only real one. (Skipped, loudly, when
     node_modules/ is absent; it is gitignored.)
  3. The floor is ENFORCED, not warned: `.npmrc` sets `engine-strict`, so the
     refusal lands on `npm install` — the first command the README gives —
     with Required and Actual both named.
  4. `.npmrc` is committed. A fresh clone that does not get the file does not
     get the enforcement, which is the entire point.
  5. The build script refuses an under-floor Node ITSELF, for anyone who runs
     it directly or copied a node_modules in, and the refusal names Node, the
     required major, and a way to get it. Driven for real: the script is run
     with `process.version` redefined to one major below the declared floor.
  6. The same script at the declared floor and above does NOT refuse.

Checks 5 and 6 read the floor out of `package.json` at test time, so raising
the floor there does not require editing this file — and a guard that had
hardcoded its own second copy of the number would fail check 5 the moment the
two drifted.

Run: python3 scripts/test_a_fresh_clone_is_told_which_node_it_needs.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / 'package.json'
NPMRC = ROOT / '.npmrc'
BUILD = ROOT / 'scripts' / 'build_ui_bundle.mjs'
GITIGNORE = ROOT / '.gitignore'
FAILS = []


def check(name, ok, why=''):
    print(('  ok   ' if ok else '  FAIL ') + name)
    if not ok:
        if why:
            print('         ' + why)
        FAILS.append(name)


def floor_of(spec):
    """Lowest major this semver-range string will accept, or None."""
    majors = [int(m) for m in re.findall(r'>=\s*v?(\d+)', str(spec))]
    majors += [int(m) for m in re.findall(r'\^\s*v?(\d+)', str(spec))]
    return min(majors) if majors else None


def run_build_with_version(fake_version):
    """Run the real build script with process.version redefined.

    `process.version` is a plain string property, so a one-liner can put this
    machine's node into an old node's shoes without installing one. The script
    compares against `process.version` (not `process.versions.node`) precisely
    so this is drivable anywhere.
    """
    node = shutil.which('node')
    if not node:
        return None
    src = (
        "Object.defineProperty(process,'version',"
        "{value:%s,configurable:true});"
        "await import(%s);" % (json.dumps(fake_version), json.dumps(BUILD.as_uri()))
    )
    return subprocess.run(
        [node, '--input-type=module', '-e', src],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
    )


def main():
    print('node prerequisite — declared, enforced, and refused legibly')

    pkg = json.loads(PKG.read_text(encoding='utf-8'))
    declared = (pkg.get('engines') or {}).get('node')
    floor = floor_of(declared) if declared else None

    check('package.json declares a node floor',
          floor is not None,
          'engines.node is %r — the README states "Node 18+" and this is the '
          'only place a machine can read that number' % (declared,))
    if floor is None:
        print()
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1

    check('the declared floor is 18 or higher',
          floor >= 18,
          'esbuild alone requires >=18; a lower declared floor would let '
          'npm admit a Node the bundler cannot run on')

    # ── 2. our floor vs. every floor our dependencies declare ────────────────
    nm = ROOT / 'node_modules'
    if not nm.is_dir():
        print('  skip  dependency floors (node_modules/ absent — gitignored; '
              'run `npm install` to include this check)')
    else:
        worst, worst_pkg = 0, ''
        for meta in nm.glob('*/package.json'):
            try:
                d = json.loads(meta.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                continue
            f = floor_of((d.get('engines') or {}).get('node') or '')
            if f and f > worst:
                worst, worst_pkg = f, meta.parent.name
        check('the declared floor covers every installed dependency',
              worst <= floor,
              '%s requires node >=%d but package.json declares >=%d — the '
              'repo would admit a Node its own dependencies refuse'
              % (worst_pkg, worst, floor))

    # ── 3/4. enforcement, and that a fresh clone receives it ────────────────
    npmrc = NPMRC.read_text(encoding='utf-8') if NPMRC.is_file() else ''
    check('.npmrc turns the declared floor into a refusal',
          re.search(r'^\s*engine-strict\s*=\s*true\s*$', npmrc, re.M),
          'without engine-strict, npm prints EBADENGINE as a WARNING and '
          'installs anyway — measured: the warning scrolls past under 265 '
          'packages and the install reports success')

    ignored = GITIGNORE.read_text(encoding='utf-8') if GITIGNORE.is_file() else ''
    check('.npmrc is not gitignored',
          not re.search(r'^\s*\.?/?\.npmrc\s*$', ignored, re.M),
          'a fresh clone that does not receive .npmrc does not receive the '
          'enforcement, which is the only reason the file exists')

    # ── 5/6. the build script speaks for itself ─────────────────────────────
    if not shutil.which('node'):
        print('  skip  the build script guard (no node on PATH)')
    else:
        red = run_build_with_version('v%d.0.0' % (floor - 1))
        out = ((red.stdout or '') + (red.stderr or '')) if red else ''
        check('an under-floor node is refused by the build script',
              red is not None and red.returncode != 0,
              'exit=%r — the script ran the build anyway on a Node its own '
              'package.json rejects' % (red.returncode if red else None,))
        check('the refusal names Node and the version it needs',
              re.search(r'\bNode\b', out) and str(floor) in out
              and re.search(r'v%d\.' % (floor - 1), out),
              'the message must name the runtime, the required major, and '
              'the one it found; got: %r' % (out[:300],))
        check('the refusal says how to get it',
              re.search(r'nodejs\.org|nvm install', out),
              'a first-run failure a tester cannot act on is the bug — the '
              'message has to end somewhere they can go; got: %r' % (out[:300],))
        check('the required major comes from package.json, not a second copy',
              str(floor) in out and 'package.json' in BUILD.read_text(encoding='utf-8'),
              'the guard must read engines.node rather than hardcode its own '
              'number, or the two drift and the message starts lying')

        # 6 — the green side, driven in a THROWAWAY copy so nothing here
        # rebuilds the checkout's dist-ui/ out from under a parallel session.
        # The copy has package.json and the script and no node_modules, so a
        # node AT the floor must sail past the version guard and land on the
        # dependency preflight instead — which is exactly the pass-through
        # this check is asserting, with no build performed.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            sandbox = Path(td)
            (sandbox / 'scripts').mkdir()
            shutil.copy2(PKG, sandbox / 'package.json')
            shutil.copy2(BUILD, sandbox / 'scripts' / BUILD.name)
            src = (
                "Object.defineProperty(process,'version',"
                "{value:%s,configurable:true});"
                "await import(%s);"
                % (json.dumps('v%d.0.0' % floor),
                   json.dumps((sandbox / 'scripts' / BUILD.name).as_uri()))
            )
            ok_run = subprocess.run(
                [shutil.which('node'), '--input-type=module', '-e', src],
                cwd=str(sandbox), capture_output=True, text=True, timeout=300,
            )
        ok_out = (ok_run.stdout or '') + (ok_run.stderr or '')
        check('a node AT the declared floor is not refused',
              'is too old' not in ok_out,
              'the guard fired on the very version package.json admits — an '
              'off-by-one in the comparison: %r' % (ok_out[:300],))
        check('past the version guard, the older preflight still speaks',
              'npm install' in ok_out,
              'a node at the floor with no node_modules should reach the '
              'dependency preflight and be told to run npm install; got: %r'
              % (ok_out[:300],))

    print()
    if FAILS:
        print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('all good')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
