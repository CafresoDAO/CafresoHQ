#!/usr/bin/env python3
"""The "Classic" Projects view (views/projects.jsx's ProjectsView) saved
files with zero conflict detection, unlike the default Workspace view.

WorkspaceView's `save()` (this file, ~line 188) re-stats the file before
writing and refuses to clobber a concurrent edit:

    if (!force && f.hash) {
      const st = await C.fsStat(f.path);
      if (st && st.hash && st.hash !== f.hash) { setConflict(true); ...; return; }
    }

ProjectsView — a first-class, user-visible mode (a "Classic" toggle
button whose tooltip literally says "The original Projects view", not a
deprecated/hidden path) — used to have a completely separate readFile/
saveFile pair that skipped this entirely: readFile never even captured
a hash/mtime when opening the file, and saveFile just wrote straight
through:

    const saveFile = async () => {
      if (!openFile) return;
      ...
      await CafresoHQClient.toolExec('FILE_WRITE', openFile.path, { body: openFile.content });
      ...
    };

Concrete repro: a boss opens a project, flips to Classic mode, opens a
file an agent is actively writing to, edits it, and clicks Save. If the
agent wrote to that same file in the meantime, the old saveFile
silently overwrote the agent's changes — no warning, no reload option,
no error. The agent's work vanished with no indication to either party.

Found by a background hunt agent looking for a legacy/duplicate code
path missing a safety feature its sibling path already has — both
still live and user-reachable via a visible mode toggle.

Fix: readFile now uses CafresoHQClient.fsReadText (which, as a bonus,
also fixes a second bug — FILE_READ truncates at 8000 chars, so Classic
mode used to load large files half-open) to capture mtime/hash on open,
mirroring WorkspaceView's openPath. saveFile now re-stats before writing
and sets a `conflict` flag instead of clobbering, exactly mirroring
WorkspaceView's own save() logic. Both of ProjectsView's Save-button
render sites (mobile editor and the desktop split editor) got the same
"⚠ Your coworker changed this file… [Reload] [Keep mine]" banner
WorkspaceView already shows, wired to the same handlers reused here.

A second, distinct bug turned up live-verifying the first fix: both
Save buttons were still wired as `onClick={saveFile}`, so React handed
saveFile the click SyntheticEvent as its `force` argument — an object
is truthy, so `!force` was always false and the brand-new conflict
check silently never ran, no matter how correct the check itself was.
Both buttons now call `onClick={() => saveFile()}` instead, matching
WorkspaceView's own `onClick={() => save(false)}` pattern. This is
exactly the kind of bug the source-shape regex checks below exist to
pin down — the live browser repro (edit in Classic mode, overwrite the
file on disk, click Save, watch it clobber anyway) is what caught it in
the first place, twice.

Run: python3 scripts/test_classic_projects_save_no_longer_clobbers_a_coworkers_edit.py
(skips the live-execution checks if `node` isn't on PATH — the
source-shape checks still run everywhere)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS_JSX = ROOT / 'views' / 'projects.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract_fn(src, name, params):
    m = re.search(
        r"const " + re.escape(name) + r" = async \(" + re.escape(params) + r"\) => \{\n"
        r"(.*?)\n  \};",
        src, re.S)
    return m.group(1) if m else None


def main():
    print("Classic Projects mode's save is now conflict-safe like the Workspace view")

    src = PROJECTS_JSX.read_text(encoding='utf-8')

    check('ProjectsView declares a `conflict` state slot',
          bool(re.search(r"const \[conflict, setConflict\] = useSV\(false\);", src)))

    read_body = extract_fn(src, 'readFile', 'path')
    check('found readFile', read_body is not None)
    check('readFile now captures mtime/hash via fsReadText, the same '
          'conflict-metadata contract WorkspaceView\'s openPath uses '
          '(the previous FILE_READ call captured neither)',
          read_body and 'CafresoHQClient.fsReadText(path)' in read_body
          and 'hash: r.hash' in read_body)

    save_body = extract_fn(src, 'saveFile', 'force')
    check('found saveFile', save_body is not None)
    check('saveFile re-stats the file before writing when not forced — '
          'the actual regression: this check did not exist at all before',
          save_body and "if (!force && openFile.hash)" in save_body
          and 'CafresoHQClient.fsStat(openFile.path)' in save_body)
    check('saveFile sets `conflict` instead of writing when the on-disk '
          'hash has moved',
          save_body and 'if (st && st.hash && st.hash !== openFile.hash) { setConflict(true)' in save_body)

    check('both Save buttons in ProjectsView are wired to a conflict '
          'banner (mobile editor + desktop split editor)',
          len(re.findall(r"⚠ Your coworker changed this file while you had edits\.", src)) >= 3)
    # (>=3 because WorkspaceView already had one; ProjectsView's two sites add two more)

    check('neither Save button passes the click SyntheticEvent straight '
          'into saveFile as `force` — this was a real regression caught '
          'live: `onClick={saveFile}` makes the event object into a '
          'truthy `force` arg, so `!force` is always false and the '
          'conflict check silently never runs, no matter what onClick '
          'says elsewhere in this file',
          not re.search(r"onClick=\{saveFile\}", src))
    check('both Save buttons instead wrap the call so it is invoked '
          'with no arguments (force defaults to undefined)',
          len(re.findall(r"onClick=\{\(\) => saveFile\(\)\}", src)) == 2)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted '
          'saveFile logic below)', has_node, 'skipping the live-execution check')

    if has_node and save_body:
        js = f"""
        async function run() {{
          const calls = [];
          const CafresoHQClient = {{
            async fsStat(path) {{ calls.push(['fsStat', path]); return {{ ok: true, hash: 'NEW_HASH', mtime: 't2' }}; }},
            async toolExec(kind, path, opts) {{ calls.push(['toolExec', kind, path]); return {{}}; }},
          }};
          let openFile = {{ path: '/proj/a.md', content: 'boss edit', hash: 'OLD_HASH', mtime: 't1', dirty: true }};
          let conflict = false, busy = false, err = null;
          const setConflict = (v) => {{ conflict = v; }};
          const setBusy = (v) => {{ busy = v; }};
          const setErr = (v) => {{ err = v; }};
          const setOpenFile = (v) => {{ openFile = typeof v === 'function' ? v(openFile) : v; }};

          const saveFile = async (force) => {{
            {save_body}
          }};

          // Case 1: on-disk hash moved (a coworker wrote it) — must NOT write, must flag conflict.
          await saveFile(undefined);
          const case1 = {{ conflictFlagged: conflict, wroteAnyway: calls.some(c => c[0] === 'toolExec') }};

          // Case 2: force=true ("Keep mine") — must write through despite the mismatch.
          conflict = false;
          await saveFile(true);
          const case2 = {{ wroteWithForce: calls.some(c => c[0] === 'toolExec') }};

          console.log(JSON.stringify({{ case1, case2 }}));
        }}
        run();
        """
        r = subprocess.run(['node', '-e', js], capture_output=True, text=True)
        check('the extracted saveFile ran without a Node error',
              r.returncode == 0, r.stderr.strip()[-500:])
        if r.returncode == 0:
            out = json.loads(r.stdout.strip().splitlines()[-1])
            check('a stale hash flags `conflict` instead of writing — this '
                  'is exactly the silent-clobber this fix closes',
                  out['case1']['conflictFlagged'] is True
                  and out['case1']['wroteAnyway'] is False,
                  out['case1'])
            check('"Keep mine" (force=true) still writes through the '
                  'conflict, matching WorkspaceView\'s own force-save path',
                  out['case2']['wroteWithForce'] is True, out['case2'])

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
