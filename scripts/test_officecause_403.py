#!/usr/bin/env python3
"""officeCause (app/floor.jsx) — a bare 403 must read as permission-denied.

OFFICE_CAUSES' "not found" rule used to match `\\b40[34]\\b`, catching 403
as well as 404. That rule runs BEFORE the dedicated eacces/403
permission-denied rule, so a raw error whose only marker was the bare
number "403" (e.g. an HTTP 403 file-op failure, no "eacces" or "permission
denied" words) was classified as "the office couldn't find that — it may
have been moved or renamed" — the wrong diagnosis, sending the boss to look
for a file that was there the whole time instead of telling them it's a
permissions problem. A 404 must still read as "couldn't find that".

Same pattern as test_floor.py: strip the export line and run the REAL
source under node.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app' / 'floor.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def run_js(cases_js):
    text = SRC.read_text(encoding='utf-8')
    src = '\n'.join(ln for ln in text.split('\n')
                    if not ln.startswith('import ') and not ln.startswith('export '))
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases_js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('officeCause: bare 403 is permission-denied, not "not found"')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1

    out = run_js(r'''
const R = {};
// A bare HTTP 403 with none of the eacces/"permission denied" wording —
// the only marker is the number.
R.bare403 = officeCause('Request failed with status code 403');
// A bare 404 must still read as "not found".
R.bare404 = officeCause('Request failed with status code 404');
// The worded forms must keep working too.
R.eacces  = officeCause('EACCES: permission denied, open \'/etc/shadow\'');
console.log(JSON.stringify(R));
''')

    check('a bare 403 reads as permission-denied',
          'allowed' in out['bare403'], out['bare403'])
    check('...not as "not found"',
          'moved or renamed' not in out['bare403'], out['bare403'])
    check('a bare 404 still reads as "not found"',
          'moved or renamed' in out['bare404'], out['bare404'])
    check('EACCES wording still reads as permission-denied',
          'allowed' in out['eacces'], out['eacces'])

    print()
    if FAILS:
        print(f'officeCause 403: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('officeCause 403: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
