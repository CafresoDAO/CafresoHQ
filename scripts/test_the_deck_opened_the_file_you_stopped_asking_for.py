#!/usr/bin/env python3
"""#409 — the stale-observation class, carried into the OTHER editor.

#398/#400 swept 85 suspend points across app.jsx and hq-runtime.jsx for the
class #394 opened: an observation made BEFORE an `await`, acted upon AFTER it,
when the observed thing can change during the wait. #404 carried it into
views/ and fixed three doors in views/vault.jsx — and named
`views/projects.jsx` `openPath` as its strongest unfixed lead, without driving
it. This is that lead, driven.

WorkspaceView keeps ONE editor buffer (`openFile` / `openFileRef`), and the
office writes to it from three directions: the boss's tree clicks, the boss's
typing, and the coworker runtime's `cafresohq:agentTool` window event — which
is not a DOM click, so no modal backdrop is anywhere in its path.

1. openPath. `const cur = openFileRef.current` (is it dirty?), then `await
   window.hqConfirm` on the user arm, then `await C.fsReadText(path)` on both
   arms, then an unconditional `setOpenFile({ path, content: r.content,
   dirty: false })`. Both halves of that observation expire in the gap:

   — a LATER open supersedes this one. `busy` is wired to exactly ONE thing in
     this pane (`disabled={busy}` on the Save button), so the tree is never
     disabled during a read. Measured pre-fix through
     scripts/harness_projects_openpath_race.mjs, which lifts the REAL
     openPath / save / reloadOpen / switchProject out of the committed source:
     `bufferAfterBothLanded: "/p/slow.js"` for a boss whose last click was
     /p/fast.js, and `errShown: "Not a file: /p/gone.js"` painted over the
     file that DID open.
   — a KEYSTROKE lands during the read. The IDEEditor textarea stays live
     through it — the same fact `save` twenty lines below states about its own
     three round trips. Measured pre-fix: `typedTextStillInBuffer: false,
     typedTextOnDisk: false, said: []`, from Follow along
     (`openPath(arg, {auto:true})`, no gesture from the boss at all) as well
     as from the boss's own click. "Never silently drop unsaved edits" is that
     door's own comment.

2. reloadOpen. The agent bus picks between the conflict BANNER and a silent
   reload on one observation — `cur.dirty` — made before the read starts, and
   the write on the far side tested only the path. Type during the read and
   you land in the branch you were never routed to. Measured pre-fix:
   `bufferContentAfter: "COWORKER BODY", typedTextStillInBuffer: false,
   conflictBannerRaised: false` — a coworker's file on top of a paragraph that
   was never saved anywhere.

3. switchProject (and the add-project commit beside it) clears the deck, which
   SEEDS the same buffer. A read started in the OLD project used to land after
   the switch: `bufferAfterSwitch: "/old/slow.js"` in the new project, its
   absolute path wired to Save, under a toolbar and tree that said otherwise.

The fix is this file's OWN shape twice over: `save`, twenty lines below
openPath, already re-derives and stamps clean only what it actually wrote
(driven here, so that claim is a measurement); and `openSeqRef` is the ref
#404 added to views/vault.jsx for exactly this, in exactly this shape.

Run: python3 scripts/test_the_deck_opened_the_file_you_stopped_asking_for.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / 'views' / 'projects.jsx'
VAULT = ROOT / 'views' / 'vault.jsx'
HARNESS = ROOT / 'scripts' / 'harness_projects_openpath_race.mjs'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def brace_lift(src, header):
    """The body of the function `header` introduces, or None when the header is
    gone — a missing marker must FAIL a check, never crash the run over the
    other forty (#404's fire test is what found that out)."""
    i = src.find(header)
    if i < 0:
        return None
    j = src.find('{', i + len(header) - 1)
    if j < 0:
        return None
    d = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                return src[j + 1:k]
    return None


def between(src, a, b):
    """The slice from `a` to `b`, or None when either marker is absent."""
    if src is None:
        return None
    i = src.find(a)
    j = src.find(b)
    if i < 0 or j < 0 or j < i:
        return None
    return src[i:j]


def no_await_between(src, a, b):
    seg = between(src, a, b)
    return seg is not None and 'await' not in seg


def has(src, needle):
    return src is not None and needle in src


def rx(src, pattern):
    return src is not None and re.search(pattern, src) is not None


projects_raw = PROJECTS.read_text()
projects = strip_comments(projects_raw)

print('\n#409 · the deck opened the file you stopped asking for')

# ── 1. openPath ───────────────────────────────────────────────────────────
print('\nstructural — 📂 openPath, re-derived on the far side of the read')
open_path = brace_lift(projects, 'const openPath = async (path, opts) =>')
check('openPath is still there to fix', open_path is not None)

check('a number is claimed before the first suspend',
      rx(open_path, r'const seq = \+\+openSeqRef\.current;')
      and no_await_between(open_path, 'const seq = ++openSeqRef.current;',
                           'await window.hqConfirm'),
      'claimed after a suspend is claimed too late')

check('the claim is the FIRST thing a proceeding open does to the seq ref',
      open_path is not None
      and open_path.find('++openSeqRef.current') < open_path.find('hqConfirm'),
      'the confirm is a suspend point like any other')

check('a Follow-along bail happens BEFORE the claim',
      rx(open_path, r'if \(mustAsk && opts && opts\.auto\) return;')
      and open_path.find('opts.auto) return;') < open_path.find('++openSeqRef'),
      'an auto open that declines to run has superseded nothing — claiming on '
      "the way out cancels the boss's own open instead")

check('the dialog gap is re-checked before anything is written',
      rx(open_path, r'if \(openSeqRef\.current !== seq\) return;')
      and no_await_between(open_path, 'hqConfirm', 'openSeqRef.current !== seq'),
      'the discard confirm is a suspend point')

check('the read gap is re-checked before the buffer is replaced',
      between(open_path, 'await C.fsReadText(path)',
              'setOpenFile({ path, content: r.content') is not None
      and 'openSeqRef.current !== seq' in
      between(open_path, 'await C.fsReadText(path)',
              'setOpenFile({ path, content: r.content'),
      'last read to LAND is not last file clicked')

check('the LIVE buffer is read from the ref on the far side, not from `cur`',
      rx(open_path, r'const live = openFileRef\.current;')
      and open_path.find('const live =') > open_path.find('await C.fsReadText'),
      'the pre-read observation is exactly what expired')

check('typing that landed during the read is FILED, not dropped',
      rx(open_path, r'if \(saveRef\.current\) await saveRef\.current\(false\);'),
      "'Never silently drop unsaved edits' is this door's own contract")

check('the flush re-checks the number, because the flush is itself a suspend',
      between(open_path, 'await saveRef.current(false);', 'const still =')
      is not None
      and 'openSeqRef.current !== seq' in
      between(open_path, 'await saveRef.current(false);', 'const still ='),
      'a flush is three round trips')

check('a flush that did NOT land keeps the boss where their typing is',
      rx(open_path, r'const still = openFileRef\.current;')
      and rx(open_path, r"toast\('warn', `Still on \$\{baseName\(still\.path\)\}"),
      'opening the other file over unfiled typing is the bug, not the fix')

check('a displacement is reported exactly once, naming both files',
      open_path is not None
      and open_path.count("Filed your changes to ${baseName(live.path)}") == 1,
      'the office says what it did rather than doing it silently')

check("an accepted Discard is still honoured — the far side does not save "
      "what the boss just threw away",
      rx(open_path, r'discarded = cur\.path;')
      and rx(open_path, r'live\.path !== discarded'),
      'the boss said discard, about that file, seconds ago')

check('an `auto` open never saves on the boss\'s behalf on the far side',
      rx(open_path, r'if \(opts && opts\.auto\) \{ setBusy\(false\); return; \}'),
      'Follow along is the office\'s gesture, not the boss\'s')

check("a superseded read's FAILURE does not blot the file that did open",
      between(open_path, 'catch (e) {', "m.indexOf('ALLOWED_DIRS')") is not None
      and 'openSeqRef.current !== seq' in
      between(open_path, 'catch (e) {', "m.indexOf('ALLOWED_DIRS')"),
      'a refusal belongs to the open it came from')

check('LOAD-BEARING NEGATIVE: nothing awaitable between the last re-check and '
      'the write it guards',
      no_await_between(open_path, 'const still = openFileRef.current;',
                       'setOpenFile({ path, content: r.content'),
      'an await there re-opens the very window this closes')

check('every early return on the far side clears busy',
      open_path is not None
      and open_path.count('{ setBusy(false); return; }') >= 4,
      'a return inside the try must not leave the pane spinning')

check('the read itself is untouched — the boss still gets the file',
      has(open_path, 'const r = await C.fsReadText(path);')
      and has(open_path, 'setOpenFile({ path, content: r.content, mtime: r.mtime, '
                         'hash: r.hash, dirty: false, binary: false });'))

check('the sandbox refusal sentence is untouched',
      has(open_path, "m.indexOf('ALLOWED_DIRS') !== -1"),
      'pinned by test_add_project_speaks_plainly')

# ── 2. reloadOpen ─────────────────────────────────────────────────────────
print('\nstructural — 🔄 the silent reload, routed by what is true when it lands')
reload_open = brace_lift(projects, 'const reloadOpen = async (path) =>')
check('reloadOpen is still there to fix', reload_open is not None)

check('the buffer is re-derived after the read',
      rx(reload_open, r'const live = openFileRef\.current;')
      and reload_open.find('const live =') > reload_open.find('await C.fsReadText'))

check('a buffer that went dirty gets the BANNER, which is its own branch',
      rx(reload_open, r'if \(live && live\.path === path && live\.dirty\) \{ setConflict\(true\); return; \}'),
      'the agent bus offers exactly two outcomes; this picks the true one')

check('the write itself also refuses a dirty buffer',
      rx(reload_open, r'setOpenFile\(o => \(o && o\.path === path && !o\.dirty\) \?'),
      'belt and braces on the one line that can destroy typing')

check('LOAD-BEARING NEGATIVE: nothing awaitable between that re-read and the write',
      no_await_between(reload_open, 'const live = openFileRef.current;',
                       'setPreviewNonce'))

check('the agent bus still routes a clean buffer here and a dirty one to the banner',
      'if (cur.dirty) setConflict(true);' in projects
      and 'else reloadOpen(arg);' in projects,
      'the pre-read choice is fine; it is the far side that had to re-derive')

# ── 3. the seeds ──────────────────────────────────────────────────────────
print('\nstructural — 🗂 the doors that SEED the buffer claim a number too')
switch = brace_lift(projects, 'const switchProject = async (id) =>')
check('switchProject claims before it clears the deck',
      switch is not None and 'openSeqRef.current++;' in switch
      and switch.find('openSeqRef.current++;') < switch.find('setOpenFile(null)'))

check('the add-project commit — the second path to the same clear — claims too',
      projects.count('openSeqRef.current++;') == 2,
      projects.count('openSeqRef.current++;'))

check('the ref is declared beside the other refs of this pane',
      rx(projects, r'const openSeqRef = React\.useRef\(0\);')
      and rx(projects, r'const saveRef = React\.useRef\(null\);'))

check('saveRef is wired every render, the way vault.jsx wires saveNoteRef',
      rx(projects, r'^\s*saveRef\.current = save;', ) or 'saveRef.current = save;' in projects)

# ── 3b. Classic (ProjectsView), which has no ref at all ───────────────────
print('\nstructural — 🗄 Classic, where the render value was spread back whole')
classic_rename = brace_lift(projects[projects.find('const readFile = async (path) =>'):],
                            'const renameEntry = async (entry) =>')
classic_delete = brace_lift(projects[projects.find('const readFile = async (path) =>'):],
                            'const deleteEntry = async (entry) =>')
check("Classic's rename rebases inside the updater, on the buffer as it stands",
      rx(classic_rename, r'setOpenFile\(o => \(o && o\.path && isUnder\(o\.path, entry\.path\)\)'),
      'a `{ ...openFile }` spread restores the render snapshot over whatever '
      'opened during the prompt and the rename')

check("Classic's rename no longer spreads the render value",
      classic_rename is not None and '{ ...openFile,' not in classic_rename)

check("Classic's delete decides on the buffer as it stands",
      rx(classic_delete, r'setOpenFile\(o => \(o && o\.path && isUnder\(o\.path, entry\.path\)\) \? null : o\);'))

check('LOAD-BEARING NEGATIVE: neither Classic door awaits between its rename/'
      'delete landing and the write it drives',
      no_await_between(classic_rename, 'setTreeNonce(n => n + 1);',
                       "toast('success'")
      and no_await_between(classic_delete, 'setTreeNonce(n => n + 1);',
                           "toast('success'"))

# ── 4. the conventions this copies, pinned as properties ──────────────────
print('\nmechanism — the facts that make all of this reachable')

check('`busy` reaches the Save button, and neither the tree nor the editor',
      'onClick={() => save(false)} disabled={busy}' in projects
      and '<IDEEditor value={openFile.content} onChange={onEdit} '
          'path={openFile.path} />' in projects
      and 'disabled' not in (between(projects, '<LocalTree path={project.path}',
                                     'pulsePaths={pulse} />') or 'disabled'),
      'if the tree or the textarea were disabled during a read, half of this '
      'would be unreachable — and they are not')

check('the textarea is live during a read: onEdit writes straight to the buffer',
      'const onEdit = (val) => setOpenFile(f => f ? { ...f, content: val, '
      'dirty: true } : f);' in projects,
      'the harness copies this line verbatim; a change here must break this '
      'check rather than leave the model describing something else')

check('the coworker runtime reaches this pane through a WINDOW EVENT, which no '
      'backdrop covers',
      "window.addEventListener('cafresohq:agentTool', onAgentTool)" in projects)

check('Follow along still opens whatever they write, code included',
      "openPath(arg, { auto: true });" in projects)

check('save still re-derives and stamps clean only what it wrote',
      'setOpenFile(o => (o && o.path === f.path) ? { ...o, hash: nh, mtime: nm, '
      'dirty: o.content !== f.content } : o);' in projects,
      'the convention openPath now copies — pinned so it cannot quietly go')

check('vault.jsx still carries the openSeqRef this is modelled on (#404)',
      'openSeqRef' in strip_comments(VAULT.read_text()),
      'the shape is this codebase\'s own, not an invention')

# ── 5. behaviour, through the real lifted source ──────────────────────────
print('\nbehavioural — the real openPath / reloadOpen / switchProject, driven')
proc = subprocess.run([str(sys.executable and 'node'), str(HARNESS), str(ROOT)],
                      capture_output=True, text=True)
S = {}
for line in proc.stdout.splitlines():
    line = line.strip()
    if not line.startswith('{'):
        continue
    try:
        row = json.loads(line)
    except ValueError:
        continue
    S[row.get('scenario')] = row
check('the harness ran every scenario', len(S) == 14 and proc.returncode == 0,
      (len(S), proc.returncode, proc.stderr[-400:]))


def sc(name):
    return S.get(name) or {}


r = sc('follow-along-lands-on-your-typing')
check('Follow along does not land on a paragraph typed during its read',
      r.get('typedTextStillInBuffer') is True
      and r.get('bufferPathAfter') == '/p/notes.md', r)

r = sc('typing-during-your-own-open')
check("the boss's own open still happens — and their typing is FILED first",
      r.get('gestureHonoured') is True and r.get('typedTextOnDisk') is True, r)
check('and the office says so, once',
      len([s for s in r.get('said', []) if s.startswith('Filed your changes')]) == 1, r)

r = sc('two-clicks-last-read-to-land-wins')
check('the file the boss clicked LAST is the file they end up on',
      r.get('endedOnTheFileTheyClickedLast') is True
      and r.get('busyCleared') is True, r)

r = sc('superseded-failure-blots-the-open-file')
check('a superseded read that failed says nothing about the file on screen',
      r.get('errAboutTheFileOnScreen') is True
      and r.get('bufferAfter') == '/p/fast.js', r)

r = sc('silent-reload-lands-on-your-typing')
check("a coworker's write during your typing raises the banner instead of "
      'overwriting you',
      r.get('conflictBannerRaised') is True
      and r.get('typedTextStillInBuffer') is True
      and r.get('bufferStillDirty') is True, r)

r = sc('read-lands-after-a-project-switch')
check('a read from the old project does not land in the new one',
      r.get('clearedAtSwitch') is True and r.get('deckStayedClear') is True, r)

r = sc('coworker-writes-under-the-discard-confirm')
check('a coworker writing under the discard dialog does not steal the open',
      r.get('endedWhereTheBossAsked') is True
      and r.get('followAlongBailedOnTheDirtyBuffer') is True, r)

r = sc('accepted-discard')
check('negative — an accepted Discard is honoured, not quietly saved',
      r.get('discardWasHonoured') is True
      and r.get('bufferPathAfter') == '/p/index.js', r)

r = sc('declined-discard')
check('negative — a declined Discard keeps the file and its edits',
      r.get('bufferPathAfter') == '/p/notes.md'
      and r.get('bufferContentAfter') == 'NOTES BODY EDITED'
      and r.get('reads') == [], r)

r = sc('ordinary-open')
check('negative — an ordinary open with nothing racing it still works',
      r.get('bufferPathAfter') == '/p/index.js'
      and r.get('bufferContentAfter') == 'INDEX BODY'
      and r.get('dirty') is False and r.get('busyCleared') is True
      and r.get('err') is None, r)

r = sc('classic-rename-restores-the-file-you-left')
check('Classic: a rename does not restore the file you had left over the one '
      'you opened',
      r.get('theFileTheyOpenedSurvived') is True and r.get('renamedOnDisk') is True, r)

r = sc('classic-delete-clears-the-wrong-buffer')
check('Classic: a delete clears the deck only when the deck holds what was '
      'deleted',
      r.get('theFileTheyOpenedSurvived') is True and r.get('deletedOnDisk') is True, r)

r = sc('classic-rename-and-delete-alone')
check('negative — Classic still follows a folder rename and still closes a '
      'deleted file when nothing is racing',
      r.get('followedTheFolderRename') is True
      and r.get('deckClearedByTheDelete') is True, r)

r = sc('save-already-re-derives')
check('negative — save, driven: it files what it captured and leaves newer '
      'keystrokes dirty',
      r.get('wroteToDisk') == 'INDEX BODY ONE'
      and r.get('bufferContentAfter') == 'INDEX BODY ONE TWO'
      and r.get('stillDirtyBecauseNewerKeystrokes') is True, r)

print()
if FAILS:
    print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
    sys.exit(1)
print('all good — the deck opens the file you last asked for, and files what '
      'you typed while it was fetching it.')
