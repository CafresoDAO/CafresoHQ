#!/usr/bin/env python3
"""Add-project accepted folders the boss's own office can never show.

The office's reading doors (/fs/browse, /fs/file — what the FILES tree
and the Workspace editor actually open with) are sandboxed to
CAFRESOHQ_ALLOWED_DIRS in every mode, deliberately: they are keyless.
The key-gated coworker tools honor unrestricted local dev, and so does
the add flow's best-effort mkdir — so a project at an outside path was
accepted and then half-worked forever: coworkers could build in it
while every click of the boss's own tree answered a raw
"path is outside CAFRESOHQ_ALLOWED_DIRS".

Now both commit steps (WorkspaceView's and ProjectsView's) ask the
reading door first: a 403 from /fs/browse refuses the add out loud
with the way out, while the modal is still open to take a better
path. An unreachable server is not a verdict about the path. And a
project that still points outside (added before this check, or moved)
gets one honest sentence in the editor instead of the env-var leak.
Verified live in both directions: outside path refused with the modal
open, inside path added, and the editor's message names the remedy.

Run: python3 scripts/test_the_add_project_door_checks_the_reading_door.py
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    i = src.index(opener)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise SystemExit('unbalanced braces lifting ' + opener)


HARNESS = r'''
const window = { _API_BASE: '' };
const FETCH = %s;   // 403 | 200 | 'throw'
const toasts = [];
const toast = (kind, msg) => toasts.push({ kind, msg });
const fetch = async (url) => {
  if (FETCH === 'throw') throw new Error('server gone');
  return { status: FETCH, _url: url };
};
%s;
(async () => {
  const refused = await _addRefusedOutsideSandbox('/some/where', toast);
  console.log(JSON.stringify({ refused, toasts }));
})();
'''


def run(fetch_behavior):
    src = (ROOT / 'views' / 'projects.jsx').read_text(encoding='utf-8')
    fn = brace_lift(src, 'const _addRefusedOutsideSandbox = async (path, toast) => {')
    js = HARNESS % (json.dumps(fetch_behavior), fn)
    p = subprocess.run(['node', '-e', js], capture_output=True, text=True,
                       timeout=60)
    if p.returncode != 0:
        print(p.stderr[-800:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(p.stdout.strip().split('\n')[-1])


def main():
    print('the add-project door checks the reading door')
    src = (ROOT / 'views' / 'projects.jsx').read_text(encoding='utf-8')

    out = run(403)
    check('a sandboxed path refuses the add', out['refused'] is True, out)
    check('…out loud, with the way out (Browse, not an env var)',
          len(out['toasts']) == 1 and out['toasts'][0]['kind'] == 'error'
          and 'outside the ones this office can show you' in out['toasts'][0]['msg']
          and 'Browse' in out['toasts'][0]['msg']
          and 'CAFRESOHQ_ALLOWED_DIRS' not in out['toasts'][0]['msg'], out)

    out = run(200)
    check('a readable path adds silently',
          out['refused'] is False and out['toasts'] == [], out)

    out = run('throw')
    check('an unreachable server is not a verdict about the path',
          out['refused'] is False and out['toasts'] == [], out)

    check('both commit steps ask before filing the project',
          src.count('if (await _addRefusedOutsideSandbox(path, toast)) return;') == 2)

    check("the editor's leftover-project message names the remedy, not the leak",
          "m.indexOf('ALLOWED_DIRS') !== -1" in src
          and 'outside the folders this office can show you' in src)

    fs = (ROOT / 'fs_routes.py').read_text(encoding='utf-8')
    check('the server-side refusal this all keys on still stands',
          fs.count("'error': 'path is outside CAFRESOHQ_ALLOWED_DIRS'") >= 2)

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
