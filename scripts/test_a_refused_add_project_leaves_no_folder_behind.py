#!/usr/bin/env python3
"""A refused add-project had already made the folder it then turned down.

Both commit steps in views/projects.jsx do two things before filing a
project: a best-effort `/fs/mkdir` (#149 — so a first-run boss typing a
fresh path doesn't land on "Not a directory: …"), and a `/fs/browse`
probe that refuses paths the office's own reading doors can never show
(test_the_add_project_door_checks_the_reading_door.py).

They ran in that order — make, then ask — and the two doors disagree by
construction:

  · /fs/mkdir goes through `_safe_path`/`_validate_path`, which skips the
    whitelist entirely on an unrestricted local run (fs_routes._fs_mutate_ok
    + serve.py's `skip` branch), and creates with `parents=True`.
  · /fs/browse is sandboxed in EVERY mode, deliberately, and its 403 runs
    BEFORE `is_dir()` — so a path that does not exist yet still 403s.

So on the ordinary self-hosted install, typing an absolute path outside
the sandbox — `/tmp/site`, or a typo like `~/Documnets/site` expanded —
created that whole directory chain on the boss's disk, and THEN refused
the add. The project was never filed, so `_addedProjectSay`'s "there was
no folder at X, so the office made one" sentence never ran: the boss got
one error toast about Browse and an unrequested directory nobody
mentioned. That is exactly the silent-write failure #149 exists to
prevent, reintroduced on the refusal path.

A refused add must leave the disk untouched. Ask first, then make.

Run: python3 scripts/test_a_refused_add_project_leaves_no_folder_behind.py
"""
import json
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / 'views' / 'projects.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    """Lift `opener` plus its balanced brace body straight out of the app."""
    i = src.index(opener)
    depth = 0
    # Start counting at the opener's OWN final brace — `({ name, path,
    # source }) => {` has a balanced destructure in the middle that would
    # otherwise end the lift on the parameter list.
    for j in range(i + len(opener) - 1, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise SystemExit('unbalanced braces lifting ' + opener)


COMMIT = 'const commitProject = async ({ name, path, source }) => {'

HARNESS = r'''
const BROWSE_STATUS = %(status)s;
const calls = { mkdir: [], toasts: [], filed: [] };
const window = {
  _API_BASE: '',
  cafresohqToast: {
    success: (m) => calls.toasts.push({ kind: 'success', msg: m }),
    error:   (m) => calls.toasts.push({ kind: 'error',   msg: m }),
    info:    (m) => calls.toasts.push({ kind: 'info',    msg: m }),
  },
};
const fetch = async () => ({ status: BROWSE_STATUS });
const toast = (kind, msg) => {
  if (window.cafresohqToast && window.cafresohqToast[kind]) window.cafresohqToast[kind](msg);
};
/* The real fsMkdir CREATES. Recording the call IS the observation: on the
   unrestricted local run this test is about, /fs/mkdir does not refuse the
   outside path, so any call here means a directory on the boss's disk. */
const CafresoHQClient = { fsMkdir: async (p) => { calls.mkdir.push(p); return { ok: true, path: p }; } };
const C = CafresoHQClient;
const setProjects = (fn) => { calls.filed = fn(calls.filed); };
const pulseTimers = { current: {} };
const idleTimer = { current: null };
/* #409 — clearing the deck SEEDS the one editor buffer, so the commit step
   claims a number the way every other seed in this pane does (a read still in
   flight from the old project must not land in the new one). Nothing in THIS
   test's subject touches it; it is here because the lift needs the name. */
const openSeqRef = { current: 0 };
const setSelectedId = () => {};
const setSelected = () => {};
const setOpenFile = () => {};
const clearOpenFile = () => {};   // `## 414.`: claim-then-clear, one call
const setLedger = () => {};
const setAgentStatus = () => {};
const setPulse = () => {};
const setErr = () => {};
const setConflict = () => {};
const setShowAdd = () => {};

%(helpers)s

%(commit)s

(async () => {
  await commitProject({ name: 'My site', path: '/outside/the/sandbox/site', source: 'local' });
  console.log(JSON.stringify(calls));
})();
'''


def run(view_src, helpers, status):
    js = HARNESS % {
        'status': json.dumps(status),
        'helpers': helpers,
        'commit': brace_lift(view_src, COMMIT),
    }
    p = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr[-1200:], file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(p.stdout.strip().split('\n')[-1])


def main():
    print('a refused add-project leaves no folder behind')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    src = SRC.read_text(encoding='utf-8')
    helpers = '\n'.join([
        brace_lift(src, 'const _addRefusedOutsideSandbox = async (path, toast) => {'),
        brace_lift(src, 'const _addProjectMkdir = async (client, path, source) => {'),
        # _addedProjectSay is a parenthesised arrow, not a brace body.
        src[src.index('const _addedProjectSay = '):
            src.index('function WorkspaceView(')].rstrip(),
    ])

    split = src.index('function ProjectsView(')
    views = {'Workspace': src[:split], 'Classic': src[split:]}
    for label, half in views.items():
        check(f'{label}: the commit step is still where this test reads it',
              COMMIT in half, 'views/projects.jsx')

    for label, half in views.items():
        # ── the refusal: nothing may be written ─────────────────────────
        out = run(half, helpers, 403)
        check(f'{label}: a refused path never reaches mkdir',
              out['mkdir'] == [],
              f"created {out['mkdir']!r} on the boss's disk and then refused the add")
        check(f'{label}: the refusal still files no project',
              out['filed'] == [], out['filed'])
        check(f'{label}: the refusal is one error toast about Browse',
              len(out['toasts']) == 1
              and out['toasts'][0]['kind'] == 'error'
              and 'Browse' in out['toasts'][0]['msg'], out['toasts'])
        check(f'{label}: …and nothing claims a folder was made',
              not any('made one' in t['msg'] for t in out['toasts']), out['toasts'])

        # ── the accepted path: #149's receipt must survive ──────────────
        out = run(half, helpers, 200)
        check(f'{label}: an allowed path still gets its folder',
              out['mkdir'] == ['/outside/the/sandbox/site'], out['mkdir'])
        check(f'{label}: …is filed as a project',
              len(out['filed']) == 1 and out['filed'][0]['name'] == 'My site',
              out['filed'])
        check(f'{label}: …and the boss is told the office made it (#149)',
              len(out['toasts']) == 1
              and out['toasts'][0]['kind'] == 'success'
              and 'the office made one' in out['toasts'][0]['msg']
              and '/outside/the/sandbox/site' in out['toasts'][0]['msg'],
              out['toasts'])

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
