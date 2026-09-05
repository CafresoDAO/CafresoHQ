#!/usr/bin/env python3
"""Switching projects in the Workspace view left the OLD project's open
file, activity ledger, coworker-status pip and error banner all showing
— while the dropdown, file tree and path label all agreed the NEW
project was now active.

Found by reading `views/projects.jsx`'s `WorkspaceView`: `openFile`,
`ledger`, `agentStatus`, `pulse` and `err` are plain component state with
no effect keyed on `project.id`/`selectedId`, and the dropdown's only
handler was `onChange={e => setSelectedId(e.target.value)}` — nothing
else. Every one of these renders unconditionally on the current state,
not on which project that state came from:

    - the editor tab shows `baseName(openFile.path)` regardless of
      whether `openFile.path` is even inside the newly-selected
      project's folder,
    - `save()` writes `openFileRef.current.path` via FILE_WRITE — the
      OLD project's absolute path — with no re-check against the
      project actually selected when Save is clicked,
    - the ledger panel lists `ledger.map(...)` with no per-project
      filter, so old activity rows keep showing under the new project,
    - `{err && ...}` renders above the file-open gate, so a stale error
      from the old project's failed read/save survives the switch even
      with no file open.

The sibling "Classic" `ProjectsView` in the same file DOES clear
`openFile` on every project-switch path (its `setSelected`/`setOpenFile`
pairs) — `WorkspaceView` never got the same treatment.

**The fix** adds `switchProject()`, reusing the exact same
never-silently-drop-edits contract `flipMode()` already uses two
functions above it in this file: confirm first if the open file has
unsaved changes, then reset every piece of per-project state (and clear
the pending pulse/idle timers so they can't mutate state for the new
project after the fact) before actually changing `selectedId`. The
dropdown now calls `switchProject`, not `setSelectedId` directly.

Run: python3 scripts/test_workspace_project_switch_clears_the_old_projects_state.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / 'views' / 'projects.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract(text, start_marker, end_marker):
    i = text.index(start_marker)
    j = text.index(end_marker, i + len(start_marker))
    return text[i:j + len(end_marker)]


def run(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the real file')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('Switching Workspace projects no longer leaks the old project\'s '
          'state into the new one')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    src = PROJECTS.read_text(encoding='utf-8')

    fn = extract(src, 'const switchProject = async (id) => {', '\n  };')
    check('extracted switchProject()', 'setSelectedId' in fn,
          'views/projects.jsx shape changed')
    check('the dropdown now calls switchProject, not setSelectedId directly',
          "onChange={e => switchProject(e.target.value)}" in src,
          'views/projects.jsx: project selector changed shape')

    body = fn[fn.index('(id) => {') + len('(id) => {'):fn.rindex('\n  }')]

    def drive(selected_id, target_id, dirty, confirmed):
        calls = {'setOpenFile': [], 'setLedger': [], 'setAgentStatus': [],
                  'setPulse': [], 'setErr': [], 'setConflict': [],
                  'setSelectedId': [], 'confirmAsked': False,
                  'timersCleared': 0}
        harness = """
const selectedId = %s;
const openFileRef = { current: %s };
const window = { hqConfirm: async () => { calls.confirmAsked = true; return %s; } };
const baseName = (p) => String(p || '').split('/').pop();
let timersCleared = 0;
const clearTimeout = () => { timersCleared++; };
const pulseTimers = { current: { '/a/b.txt': 1, '/a/c.txt': 2 } };
const idleTimer = { current: 3 };
/* #409 — clearing the deck SEEDS the pane's one editor buffer, so switchProject
   claims a number: a read still in flight from the OLD project must not land
   in the new one (measured there: `bufferAfterSwitch: "/old/slow.js"`). Not
   this test's subject; the lift just needs the name. */
const openSeqRef = { current: 0 };
const calls = {
  setOpenFile: [], setLedger: [], setAgentStatus: [], setPulse: [],
  setErr: [], setConflict: [], setSelectedId: [], confirmAsked: false,
};
const setOpenFile = (v) => calls.setOpenFile.push(v);
const setLedger = (v) => calls.setLedger.push(v);
const setAgentStatus = (v) => calls.setAgentStatus.push(v);
const setPulse = (v) => calls.setPulse.push(Array.from(v));
const setErr = (v) => calls.setErr.push(v);
const setConflict = (v) => calls.setConflict.push(v);
const setSelectedId = (v) => calls.setSelectedId.push(v);
const switchProject = async (id) => {
%s
};
(async () => {
  await switchProject(%s);
  console.log(JSON.stringify({ ...calls, timersCleared }));
})();
""" % (
            json.dumps(selected_id),
            json.dumps({'path': '/old/project/file.txt', 'dirty': dirty}),
            'true' if confirmed else 'false',
            body,
            json.dumps(target_id),
        )
        return run(harness)

    same = drive('p1', 'p1', dirty=False, confirmed=True)
    check('switching to the already-selected project is a no-op (no reset, '
          'no confirm)',
          same['setSelectedId'] == [] and same['confirmAsked'] is False, same)

    clean = drive('p1', 'p2', dirty=False, confirmed=True)
    check('a clean switch resets openFile to null',
          clean['setOpenFile'] == [None], clean)
    check('...and clears the ledger',
          clean['setLedger'] == [[]], clean)
    check('...and resets the coworker-status pip to idle',
          clean['setAgentStatus'] == ['idle'], clean)
    check('...and clears the tree-pulse set',
          clean['setPulse'] == [[]], clean)
    check('...and clears the stale error banner',
          clean['setErr'] == [None], clean)
    check('...and clears the conflict banner',
          clean['setConflict'] == [False], clean)
    check('...and actually switches to the new project',
          clean['setSelectedId'] == ['p2'], clean)
    check('...and cancels the pending pulse/idle timers (2 pulse + 1 idle) '
          'so they cannot mutate state for the new project later',
          clean['timersCleared'] == 3, clean)
    check('a clean file switch does not even ask for confirmation',
          clean['confirmAsked'] is False, clean)

    declined = drive('p1', 'p2', dirty=True, confirmed=False)
    check('a dirty file that the boss declines to discard blocks the '
          'switch entirely — no state reset, no project change',
          declined['setSelectedId'] == [] and declined['setOpenFile'] == []
          and declined['setLedger'] == [] and declined['confirmAsked'] is True,
          declined)

    confirmed_dirty = drive('p1', 'p2', dirty=True, confirmed=True)
    check('a dirty file the boss confirms discarding still resets state '
          'and switches, same as the clean path',
          confirmed_dirty['setSelectedId'] == ['p2']
          and confirmed_dirty['setOpenFile'] == [None]
          and confirmed_dirty['confirmAsked'] is True,
          confirmed_dirty)

    print()
    if FAILS:
        print(f'workspace project switch: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:5]))
        return 1
    print('workspace project switch: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
