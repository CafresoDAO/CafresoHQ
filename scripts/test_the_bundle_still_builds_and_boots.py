#!/usr/bin/env python3
"""Smoke: the shipped bundle builds from source and carries its boot path.

Every other suite reads app.jsx and friends as TEXT. All 230+ of them
can be green while `npm run build` is broken — a stray TypeScript
annotation, an import of a file that moved — because nothing ever
compiled the code. The browser loads dist-ui/, not the .jsx, and the
repo's own staleness trap (a .jsx edit without a rebuild silently
serves the old app) means "the tests pass" and "the app runs" are
independent claims.

This suite makes the first claim imply the second's precondition:

  1. `npm run build` exits 0, from source, right now;
  2. the manifest and every asset it names exist and are non-trivial;
  3. the app bundle actually contains the boot path (the createRoot
     mount and the App component) and the office's load-bearing
     surfaces (the chat panel, the Library, the message registry) —
     a bundle that "built" but tree-shook the app away would pass
     steps 1–2.

Run: python3 scripts/test_the_bundle_still_builds_and_boots.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('the bundle still builds and boots')
    if not shutil.which('npm'):
        print('  SKIP  npm not on PATH — cannot build')
        return 0

    p = subprocess.run(['npm', 'run', 'build'], cwd=ROOT,
                       capture_output=True, text=True, timeout=300)
    check('npm run build exits 0', p.returncode == 0,
          (p.stderr or p.stdout).strip()[-400:])
    if p.returncode != 0:
        print('FAIL')
        return 1

    manifest_path = ROOT / 'dist-ui' / 'manifest.json'
    check('the manifest exists', manifest_path.exists())
    if not manifest_path.exists():
        print('FAIL')
        return 1
    manifest = json.loads(manifest_path.read_text())
    # Values are either a path or a list of paths, all relative to dist-ui/.
    names = []
    for v in manifest.values():
        names.extend(v if isinstance(v, list) else [v])
    missing = [n for n in names if not (ROOT / 'dist-ui' / n).exists()]
    check('every asset the manifest names exists', not missing, missing)

    app_assets = manifest.get('app') or []
    app_asset = next((a for a in app_assets if 'hq-app' in a), None)
    check('the app bundle is in the manifest', bool(app_asset), manifest)
    if app_asset:
        js = (ROOT / 'dist-ui' / app_asset).read_text(encoding='utf-8', errors='replace')
        check('the app bundle is non-trivial', len(js) > 200_000, f'{len(js)} bytes')
        # Load-bearing markers, chosen to survive minification: string
        # literals and globals, not identifier names.
        for label, marker in (
            ('the mount point', 'createRoot'),
            ('the chat threads', '"direct"'),  # esbuild normalizes quotes
            ('the Library', 'LIBRARY'),
            ('the message registry', 'CafresoHQMessages'),
        ):
            check(f'the bundle carries {label}', marker in js,
                  f'{marker!r} not found — built, but the app is not in it')

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
