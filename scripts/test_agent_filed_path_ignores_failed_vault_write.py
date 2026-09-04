#!/usr/bin/env python3
"""agentFiledPath (app/artifacts.jsx) must not credit a FAILED vault write.

hq-runtime.jsx's tool loop wraps every call in try/catch: when a VAULT_NEW
throws (cabinet unreachable, write rejected, etc.) it sets `meta.failed =
true` and still emits a `done` event carrying the path the coworker WAS
TRYING to write (`arg` is unchanged on failure — only `result` becomes the
error text). That visit lands in `toolVisits` as
`{ name: 'VAULT_NEW', arg: '<path>', failed: true }`.

agentFiledPath used to ignore `.failed` entirely and hand back that path as
"the coworker filed it themselves". Two things follow from app.jsx
(`const ownPath = agentFiledPath(toolVisits); filedPath = ownPath ||
await fileDelivery(...)`):

  1. task.artifactPath — what the out-tray's "open the latest" click uses —
     points at a cabinet entry that was never created.
  2. Because `ownPath` was truthy, the host's OWN fallback filing
     (`fileDelivery`) never even runs, so no copy of the deliverable lands
     in the cabinet at all despite the task showing as delivered.

unwrittenPaths() and the `consulted` check in buildDelivery() both already
skip `v.failed` for exactly this reason; agentFiledPath was the one path
that hadn't been taught it.

Runs the real module (minus its browser-only imports) under node, so this
fails against the unpatched source and passes once `.failed` is checked.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app' / 'artifacts.jsx'
FLOOR = ROOT / 'app' / 'floor.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def _strip_module_lines(path):
    return '\n'.join(ln for ln in path.read_text(encoding='utf-8').split('\n')
                     if not ln.startswith('import ') and not ln.startswith('export '))


def pure_source():
    src = _strip_module_lines(FLOOR) + '\n' + _strip_module_lines(SRC)
    for fn in ('function cabinetIsEncrypted', 'async function fileDelivery'):
        i = src.find(fn)
        if i == -1:
            continue
        depth, j, started = 0, i, False
        while j < len(src):
            if src[j] == '{':
                depth += 1
                started = True
            elif src[j] == '}':
                depth -= 1
                if started and depth == 0:
                    j += 1
                    break
            j += 1
        src = src[:i] + src[j:]
    return src


def run_js(cases_js):
    script = pure_source() + '\n' + cases_js
    proc = subprocess.run(['node', '--input-type=module', '-e', script],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('agentFiledPath ignores a failed VAULT_NEW')
    import shutil
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1

    out = run_js(r'''
const R = {};
// The hq-runtime shape for a call that threw: arg unchanged, failed:true.
R.afFailedVault = agentFiledPath([{ name: 'VAULT_NEW', arg: 'Research/x.md', failed: true }]);
// A later SUCCESSFUL write must still win even if an earlier one failed.
R.afFailedThenOk = agentFiledPath([
  { name: 'VAULT_NEW', arg: 'Research/bad.md', failed: true },
  { name: 'VAULT_NEW', arg: 'Research/good.md' },
]);
// An earlier success must not be shadowed by a LATER failed retry — the
// failed attempt produced nothing, so the real file stays the deliverable.
R.afOkThenFailed = agentFiledPath([
  { name: 'VAULT_NEW', arg: 'Research/good.md' },
  { name: 'VAULT_NEW', arg: 'Research/bad.md', failed: true },
]);
// A run where every cabinet write failed must report nothing filed, so the
// host's own fileDelivery fallback still runs.
R.afAllFailed = agentFiledPath([
  { name: 'VAULT_NEW', arg: 'Research/a.md', failed: true },
  { name: 'VAULT_APPEND', arg: 'Research/a.md', failed: true },
]);
// Baseline: an ordinary successful write is unaffected by the fix.
R.afOk = agentFiledPath([{ name: 'VAULT_NEW', arg: 'Research/x.md' }]);
console.log(JSON.stringify(R));
''')

    check('failed VAULT_NEW is not credited as filed',
          out['afFailedVault'] is None, repr(out['afFailedVault']))
    check('a later successful write still wins over an earlier failure',
          out['afFailedThenOk'] == 'Research/good.md', repr(out['afFailedThenOk']))
    check('an earlier success is not shadowed by a later failed retry',
          out['afOkThenFailed'] == 'Research/good.md', repr(out['afOkThenFailed']))
    check('an all-failed run reports nothing filed',
          out['afAllFailed'] is None, repr(out['afAllFailed']))
    check('an ordinary successful write is still recognised',
          out['afOk'] == 'Research/x.md', repr(out['afOk']))

    if FAILS:
        print(f'\n{len(FAILS)} check(s) failed: {", ".join(FAILS)}')
        return 1
    print('\nall checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
