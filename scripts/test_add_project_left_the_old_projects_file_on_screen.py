#!/usr/bin/env python3
"""Creating a new project (the "+ ADD" flow) left the PREVIOUSLY selected
project's open file, editor tab and error banner on screen — while the
project list and its "active" highlight both correctly showed the
brand-new project as selected.

`views/projects.jsx` has TWO functions named `commitProject` — one on each
of the file's sibling top-level components — and while investigating
whether task #41's "context-switch state leak" pattern
(`WorkspaceView`'s per-project state with no reset on selection change)
recurs elsewhere, BOTH turned out to still have it, via two independent
code paths:

  - `WorkspaceView.commitProject` (line ~61) called `setSelectedId(id)`
    directly — completely bypassing `switchProject()` (line ~42), the very
    function task #41 wrote to close this exact leak for the project
    dropdown. Creating a project while a DIFFERENT project's file was open
    reintroduced the full leak `switchProject` exists to prevent: stale
    `openFile`/`ledger`/`agentStatus`/`pulse`/`err`/`conflict`, and
    (worst) `save()` still writing that stale file's absolute path with no
    re-check against the freshly created project.

  - `ProjectsView.commitProject` (the "Classic" component, line ~810)
    called `setSelected(id)` but never `setOpenFile(null)` — unlike every
    other `setSelected` call site in that same component (`deleteProject`,
    the mobile back button, and both mobile/desktop list rows all pair the
    two). The editor pane there (gated only on
    `rightTab === 'files' && openFile`, not on which project that file
    belongs to) kept rendering the OLD project's file/tab/err banner right
    under the NEW project's now-active row. `saveFile` there writes via an
    absolute `openFile.path` independent of `selected`, so this one case is
    UI-honesty-only — no cross-project data corruption — unlike
    WorkspaceView's version above.

**The fix**: `WorkspaceView.commitProject` now performs the same resets
`switchProject()` does (minus its dirty-confirm guard and
`id === selectedId` check — both irrelevant for a freshly generated id).
`ProjectsView.commitProject` gets `setOpenFile(null)` added, matching its
own component's established convention exactly (nothing else — `err`,
`previewMode` — needed resetting there, since no sibling call site resets
those either).

Run: python3 scripts/test_add_project_left_the_old_projects_file_on_screen.py
"""
import json
import re
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
    print('Adding a project no longer leaves the previous project\'s file '
          'on screen (both WorkspaceView and Classic ProjectsView)')

    src = PROJECTS.read_text(encoding='utf-8')

    # The mkdir and its sentence moved into two module-scope helpers (#149)
    # that BOTH commit steps now share. Lift the real ones rather than stub
    # them: this suite drives the real bodies, and a stub here would let the
    # bodies call a helper that no longer exists in the app.
    def lift_const(name):
        m = re.search(r'^const %s = ' % re.escape(name), src, re.M)
        if not m:
            raise SystemExit('views/projects.jsx: could not lift ' + name)
        depth, i = 0, m.end()
        while i < len(src):
            ch = src[i]
            if ch in '({[':
                depth += 1
            elif ch in ')}]':
                depth -= 1
            elif ch == ';' and depth == 0:
                return src[m.start():i + 1]
            i += 1
        raise SystemExit('views/projects.jsx: unterminated ' + name)

    MKDIR_SRC = lift_const('_addProjectMkdir')
    SAY_SRC = lift_const('_addedProjectSay')

    check('exactly one WorkspaceView.commitProject and one '
          'ProjectsView.commitProject exist',
          src.count('const commitProject = async ({ name, path, source }) => {') == 2,
          'views/projects.jsx: commitProject count changed')

    # --- WorkspaceView.commitProject -----------------------------------
    # Located by ORDINAL, not by a line from the body. This used to key off
    # `if (source === 'local' && C && C.fsMkdir)`, a mkdir detail that has
    # nothing to do with the state-reset behaviour under test — and when that
    # mkdir moved into a shared helper (#149) this file did not fail, it
    # crashed on a ValueError from `str.index`, which reads as a broken test
    # rather than a broken app. The count check above already pins that there
    # are exactly two, and WorkspaceView's is the first in the file; the
    # setSelectedId assertion below is what confirms we landed on it.
    SIG = 'const commitProject = async ({ name, path, source }) => {'
    ws_fn = extract(src, SIG, '\n  };')
    check('found WorkspaceView.commitProject, the first of the two',
          'setSelectedId' in ws_fn, 'views/projects.jsx shape changed')
    check('WorkspaceView.commitProject no longer calls setSelectedId directly '
          'without resetting state first',
          'setOpenFile(null)' in ws_fn and 'setLedger([])' in ws_fn
          and 'setErr(null)' in ws_fn and 'setConflict(false)' in ws_fn
          and 'setAgentStatus(\'idle\')' in ws_fn and 'setPulse(new Set())' in ws_fn,
          ws_fn)
    check('...and still cancels pending pulse/idle timers first',
          'pulseTimers.current' in ws_fn and 'clearTimeout(idleTimer.current)' in ws_fn,
          ws_fn)

    ws_body = ws_fn[ws_fn.index('=> {') + len('=> {'):ws_fn.rindex('\n  }')]

    def drive_workspace():
        harness = """
const C = { fsMkdir: async () => ({ ok: true, path: '/tmp/marketing' }) };
%(mkdir)s
%(say)s
// The sandbox preflight is its own tested unit (see
// test_the_add_project_door_checks_the_reading_door.py) — here it waves
// the add through so the reset behavior under test is reachable.
const _addRefusedOutsideSandbox = async () => false;
const calls = {
  setProjects: [], setSelectedId: [], setShowAdd: [], toasts: [],
  setOpenFile: [], setLedger: [], setAgentStatus: [], setPulse: [],
  setErr: [], setConflict: [], timersCleared: 0,
};
const setProjects = (fn) => calls.setProjects.push(typeof fn === 'function' ? fn([]) : fn);
const setSelectedId = (v) => calls.setSelectedId.push(v);
const setShowAdd = (v) => calls.setShowAdd.push(v);
const toast = (k, m) => calls.toasts.push([k, m]);
const setOpenFile = (v) => calls.setOpenFile.push(v);
const setLedger = (v) => calls.setLedger.push(v);
const setAgentStatus = (v) => calls.setAgentStatus.push(v);
const setPulse = (v) => calls.setPulse.push(Array.from(v));
const setErr = (v) => calls.setErr.push(v);
const setConflict = (v) => calls.setConflict.push(v);
const pulseTimers = { current: { '/a/b.txt': 1, '/a/c.txt': 2 } };
const idleTimer = { current: 3 };
/* #409 — clearing the deck SEEDS the pane's one editor buffer, so the commit
   step claims a number the way every other seed there does (a read still in
   flight from the old project must not land in the new one). Not this test's
   subject; the lift just needs the name. */
const openSeqRef = { current: 0 };
const clearTimeout = () => { calls.timersCleared++; };
const commitProject = async ({ name, path, source }) => {
%(body)s
};
(async () => {
  await commitProject({ name: 'Marketing Site', path: '/tmp/marketing', source: 'local' });
  console.log(JSON.stringify(calls));
})();
""" % {'mkdir': MKDIR_SRC, 'say': SAY_SRC, 'body': ws_body}
        return run(harness)

    ws = drive_workspace()
    check('WorkspaceView: still selects the newly created project',
          len(ws['setSelectedId']) == 1 and ws['setSelectedId'][0].startswith('p_'), ws)
    check('WorkspaceView: clears the previously open file',
          ws['setOpenFile'] == [None], ws)
    check('WorkspaceView: clears the ledger',
          ws['setLedger'] == [[]], ws)
    check('WorkspaceView: resets the coworker-status pip to idle',
          ws['setAgentStatus'] == ['idle'], ws)
    check('WorkspaceView: clears the tree-pulse set',
          ws['setPulse'] == [[]], ws)
    check('WorkspaceView: clears the stale error banner',
          ws['setErr'] == [None], ws)
    check('WorkspaceView: clears the conflict banner',
          ws['setConflict'] == [False], ws)
    check('WorkspaceView: cancels the pending pulse/idle timers (2 pulse + 1 idle)',
          ws['timersCleared'] == 3, ws)
    check('WorkspaceView: still closes the Add-Project modal and toasts success',
          ws['setShowAdd'] == [False] and len(ws['toasts']) == 1, ws)

    # --- ProjectsView (Classic).commitProject --------------------------
    # The second of the two, found by resuming the search past the first.
    classic_fn = extract(src[src.index(SIG) + len(SIG):], SIG, '\n  };')
    check('found ProjectsView.commitProject, the second of the two',
          'setSelected' in classic_fn and 'setSelectedId' not in classic_fn,
          'views/projects.jsx shape changed')
    # `## 414.` folded the six bare `setOpenFile(null)` into `clearOpenFile()`
    # (which claims openSeqRef and then clears) — the pairing is the same,
    # the spelling is not.
    check('ProjectsView.commitProject now resets openFile alongside setSelected',
          'clearOpenFile()' in classic_fn, classic_fn)

    for label, needle in [
        ('deleteProject', "if (selected === p.id) { setSelected(null); clearOpenFile(); }"),
        ('mobile-back', "setSelected(null); clearOpenFile(); setMobileStep('list');"),
        ('mobile-list-row', "setSelected(p.id); clearOpenFile(); setMobileStep('detail');"),
        ('desktop-list-row', "setSelected(p.id); clearOpenFile(); setRightTab('files');"),
    ]:
        check(f'ProjectsView.{label} still pairs setSelected with clearOpenFile()',
              needle in src, 'views/projects.jsx: sibling call site changed shape')

    classic_body = classic_fn[classic_fn.index('=> {') + len('=> {'):classic_fn.rindex('\n  }')]

    def drive_classic(toast_available=True):
        harness = """
const CafresoHQClient = { fsMkdir: async () => ({ ok: true, path: '/tmp/marketing' }) };
%(mkdir)s
%(say)s
// Preflight stubbed open — its own behavior is covered by
// test_the_add_project_door_checks_the_reading_door.py.
const _addRefusedOutsideSandbox = async () => false;
const calls = {
  setProjects: [], setSelected: [], setOpenFile: [], setShowAdd: [],
  toastMsgs: [],
};
const setProjects = (fn) => calls.setProjects.push(typeof fn === 'function' ? fn([]) : fn);
const setSelected = (v) => calls.setSelected.push(v);
const setOpenFile = (v) => calls.setOpenFile.push(v);
// The real one, verbatim from views/projects.jsx (`## 414.`): claim, then clear.
const openSeqRef = { current: 0 };
const clearOpenFile = () => { openSeqRef.current++; setOpenFile(null); };
const setShowAdd = (v) => calls.setShowAdd.push(v);
const toast = () => {};   // only the refused branch speaks through it
const window = { cafresohqToast: %(toast)s };
const commitProject = async ({ name, path, source }) => {
%(body)s
};
(async () => {
  await commitProject({ name: 'Marketing Site', path: '/tmp/marketing', source: 'local' });
  console.log(JSON.stringify(calls));
})();
""" % {
            'mkdir': MKDIR_SRC, 'say': SAY_SRC,
            'toast': ("{ success: (m) => calls.toastMsgs.push(m) }"
                      if toast_available else "undefined"),
            'body': classic_body,
        }
        return run(harness)

    result = drive_classic()
    check('ProjectsView: still selects the newly created project',
          len(result['setSelected']) == 1 and result['setSelected'][0].startswith('p_'),
          result)
    check('...and now also clears the previously open file',
          result['setOpenFile'] == [None], result)
    check('...and still closes the Add-Project modal',
          result['setShowAdd'] == [False], result)
    check('...and still adds the project to the list',
          len(result['setProjects']) == 1, result)
    check('...and still toasts success',
          len(result['toastMsgs']) == 1 and 'Marketing Site' in result['toastMsgs'][0],
          result)

    no_toast = drive_classic(toast_available=False)
    check('missing window.cafresohqToast does not crash ProjectsView.commitProject',
          no_toast['setOpenFile'] == [None] and len(no_toast['setSelected']) == 1,
          no_toast)

    print()
    if FAILS:
        print(f'add-project file leak: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:5]))
        return 1
    print('add-project file leak: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
