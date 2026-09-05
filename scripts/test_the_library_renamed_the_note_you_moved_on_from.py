#!/usr/bin/env python3
"""#404 — the stale-observation class, carried into the view layer.

#398 swept 85 suspend points across app.jsx and hq-runtime.jsx for the class
#394 opened: an observation made BEFORE an `await`, acted upon AFTER it, when
the observed thing can change during the wait. #400 finished that file pair.
Neither sweep reached views/ or ui/ — 152 more suspend points, and the single
most important data surface in the app is in there.

views/vault.jsx keeps ONE editor buffer (`openNote` / `openNoteRef`). Three
doors read it, suspend, and then WRITE it back unconditionally:

1. renameNote. `const n = openNoteRef.current`, then `await window.hqPrompt`,
   then `await CafresoHQClient.vaultRename(n.path, to)`, then
   `setOpenNote(o => o ? { ...o, path: to.trim() } : o)` — retargeting
   WHATEVER is open now. Swap the buffer inside that gap and the note on
   screen is relabelled with the renamed note's new path; the very next
   keystroke's 2.5s quiet autosave writes THAT note's body over the file just
   renamed, and the renamed note's content leaves the Library entirely.
   Silent, permanent, zero lines said.

   Measured pre-fix via scripts/harness_vault_note_race.mjs, lifting the REAL
   renameNote / saveNote / openByPath / flushBeforeLeave:
   `renamedNoteBody: "IDEA BODY EDITED"`, `quarterlyBodySurvivesSomewhere:
   false`, `displacementReported: []`.

2. deleteNote. Same gap, pointed the other way: `n` read before the confirm
   and the DELETE, `setOpenNote(null)` + `setSaveState('')` unconditional
   after. A buffer that changed hands during the dialog is blanked with its
   unsaved typing — nothing on this path flushes — and the '⚠ Retry save' chip
   is wiped with it, which is verbatim the failure flushBeforeLeave's own
   docstring was written to close. Measured pre-fix: `bufferAfter: null`,
   `typedTextStillInBuffer: false`, `typedTextOnDisk: false`.

3. openByPath. `flushBeforeLeave()` answers "nothing to lose", then
   `await CafresoHQClient.vaultRead(path)`, then the buffer is replaced. Both
   halves of that answer expire during the read: a LATER open supersedes this
   one (last read to LAND won, which is not the last note clicked), and a
   KEYSTROKE into the buffer makes the replacement a clobber of typing that
   was never filed. Measured pre-fix: `bufferAfterBothLanded:
   "Research/slow.md"` for a boss whose last click was Inbox/fast.md, and
   `typedTextSurvived: false` / `typedTextOnDisk: false` in both scenarios.

The buffer changes underneath a modal for an ordinary reason and not a rare
one: the graph POPOUT (`?popout=graph`, app.jsx GraphPopout) is a SEPARATE
BROWSER WINDOW. A node click there posts `{type:'open-note'}` on
BroadcastChannel('cafresohq-graph'); the main window answers with goTo('vault')
plus a `cafresohq:openNote` CustomEvent, which views/vault.jsx hands straight
to openByPath. The modal `.backdrop` (ui/feedback.jsx) covers the main window
and nothing else. openByPath's own race needs no modal at all — two tree clicks
in a slow Library.

The fix is this file's OWN shape, not an invention: `moveByDrag`, thirty lines
above renameNote and calling the same vaultRename, already re-derives on the
far side (`const o0 = openNoteRef.current; if (o0 && inside(o0.path))`). That
is pinned below as a property, so a later edit cannot quietly take it away.

Run: python3 scripts/test_the_library_renamed_the_note_you_moved_on_from.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / 'views' / 'vault.jsx'
APP = ROOT / 'app.jsx'
FEEDBACK = ROOT / 'ui' / 'feedback.jsx'
HARNESS = ROOT / 'scripts' / 'harness_vault_note_race.mjs'
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
    i = src.index(header)
    j = src.index('{', i + len(header) - 1)
    d = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                return src[j + 1:k]
    raise AssertionError('unbalanced: ' + header)


def between(src, a, b):
    """The slice from `a` to `b`, or None when either marker is absent — a
    missing marker is a FAILED check, never a stack trace over the other
    forty. (The fire test for this entry is what found that out.)"""
    i = src.find(a)
    j = src.find(b)
    if i < 0 or j < 0 or j < i:
        return None
    return src[i:j]


def no_await_between(src, a, b):
    seg = between(src, a, b)
    return seg is not None and 'await' not in seg


vault_raw = VAULT.read_text()
vault = strip_comments(vault_raw)

print('\n#404 · the Library renamed the note you had moved on from')

# ── 1. renameNote ─────────────────────────────────────────────────────────
print('\nstructural — ✎ rename, re-derived on the far side of the prompt')
rename = brace_lift(vault, 'const renameNote = async () =>')

check('the retarget is keyed on the note the dialog was about',
      re.search(r"setOpenNote\(o => \(o && o\.path === n\.path\) \? \{ \.\.\.o, path: to\.trim\(\) \} : o\)",
                rename),
      'an unconditional {...o, path} relabels whichever buffer is open now')

check('the live buffer is read from the ref, not from this render',
      re.search(r'const nowOpen = openNoteRef\.current;', rename),
      'the render closure cannot have moved — only the ref can')

check('a displaced buffer is reported, once, naming both notes',
      re.search(r'if \(!nowOpen \|\| nowOpen\.path !== n\.path\)', rename)
      and rename.count('say(`Moved "${n.path}"') == 1,
      rename.count('say(`Moved "${n.path}"'))

check('LOAD-BEARING NEGATIVE: nothing awaitable between the re-read and the '
      'two acts on it',
      no_await_between(rename, 'const nowOpen =', 'sayStranded(res);'),
      'an await there re-opens the very window this closes')

check('the rename itself is unchanged — the boss still gets what they asked for',
      'const res = await CafresoHQClient.vaultRename(n.path, to.trim());' in rename)

check('the dirty flush before the rename still reads the pre-prompt note',
      'if (n.dirty) await saveNoteRef.current({ quiet: true });' in rename,
      'pinned: that one IS about the note the dialog named')

# ── 2. deleteNote ─────────────────────────────────────────────────────────
print('\nstructural — 🗑 delete, keyed to the note the confirm named')
delete = brace_lift(vault, 'const deleteNote = async () =>')

check('the close is keyed on the deleted path',
      re.search(r'if \(!nowOpen \|\| nowOpen\.path === n\.path\) \{', delete))

check("setSaveState('') is inside that gate, not above it",
      re.search(r"nowOpen\.path === n\.path\) \{\s*setSaveState\(''\);\s*setOpenNote\(null\);", delete),
      "wiping the '⚠ Retry save' chip on a note we are NOT closing is the "
      "failure flushBeforeLeave's docstring exists to prevent")

check('a buffer left standing is said out loud', "say(`Deleted \"${n.path}\"" in delete)

check('LOAD-BEARING NEGATIVE: nothing awaitable between the re-read and the close',
      no_await_between(delete, 'const nowOpen =', 'await refresh();'),
      'an await there re-opens the window')

check('the DELETE itself is unchanged',
      'await CafresoHQClient.vaultDelete(n.path);' in delete)

check('the confirm still counts inbound links from the pre-ask snapshot',
      'window.CafresoHQGraph && window.CafresoHQGraph._lastGraph' in delete
      and 0 <= delete.find('_lastGraph') < delete.find('hqConfirm'),
      'the dialog is a question about now; re-writing it after the fact would '
      'describe a moment the boss was never shown')

# ── 3. openByPath ─────────────────────────────────────────────────────────
print('\nstructural — the read that lands last')
opener = brace_lift(vault, 'const openByPath = async (path) =>')

check('the open sequence ref is declared beside openNoteRef',
      re.search(r'const openNoteRef = React\.useRef\(null\);[\s\S]{0,600}?'
               r'const openSeqRef = React\.useRef\(0\);', vault),
      'the same two lines agentsRef/tasksRef are, for the same reason')

check('openByPath claims its number BEFORE the first suspend',
      re.search(r'const seq = \+\+openSeqRef\.current;', opener)
      and 0 <= opener.find('const seq = ++openSeqRef.current;') < opener.find('await'),
      'a number claimed after the flush cannot see what the flush let through')

check('a superseded read is dropped rather than written',
      opener.count('if (openSeqRef.current !== seq) { setBusy(false); return; }') == 2,
      opener.count('if (openSeqRef.current !== seq) { setBusy(false); return; }'))

check('a buffer that went dirty during the read is flushed, not clobbered',
      re.search(r'if \(openNoteRef\.current && openNoteRef\.current\.dirty\) \{\s*'
                r'if \(!\(await flushBeforeLeave\(\)\)\) \{ setBusy\(false\); return; \}',
                opener),
      'flushBeforeLeave already answered about a buffer that has since moved')

check('and the number is re-checked AFTER that second flush',
      re.search(r'await flushBeforeLeave\(\)\)\) \{ setBusy\(false\); return; \}\s*'
                r'if \(openSeqRef\.current !== seq\) \{ setBusy\(false\); return; \}', opener),
      'the flush is itself a suspend point')

check('every early return clears busy',
      opener.count('setBusy(false); return;') == opener.count('setBusy(false)') - 1,
      'a return inside the try skips the setBusy(false) at the bottom and '
      'leaves the whole room spinning')

check('the two other buffer seeds claim a number too',
      strip_comments(vault).count('openSeqRef.current++;') == 2,
      'newNote and openWikilink replace the buffer after their own flush; a '
      'read still in flight would otherwise land on top of the seed')

# ── 4. the shape this copies, pinned ──────────────────────────────────────
print('\nstructural — the pattern this file already had')
move = brace_lift(vault, 'const moveByDrag = async (src, destFolder) =>')
check('moveByDrag still re-derives the buffer on the far side of its rename',
      re.search(r'const o0 = openNoteRef\.current;\s*if \(o0 && inside\(o0\.path\)\)', move),
      'this is where the fixes above got their shape; if it goes, they are '
      'an invention rather than a convention')

# ── 5. the mechanism, pinned as a property ────────────────────────────────
print('\nstructural — why the buffer can move while a modal is up')
app = APP.read_text()
check('the graph popout broadcasts open-note from its OWN window',
      "ch.postMessage({ type: 'open-note', path })" in app
      and 'function GraphPopout()' in app)
check('the main window turns that into a cafresohq:openNote event',
      re.search(r"if \(m\.type === 'open-note' && m\.path\)[\s\S]{0,400}?"
                r"CustomEvent\('cafresohq:openNote'", app))
check('and views/vault.jsx hands that event straight to openByPath',
      re.search(r"if \(e\.detail && e\.detail\.path\) openByPath\(e\.detail\.path\)", vault)
      and "window.addEventListener('cafresohq:openNote', handler)" in vault)
check('the modal backdrop is scoped to the window that raised it',
      'className="backdrop"' in FEEDBACK.read_text(),
      'a DOM overlay stops clicks in ITS document and no other')

# ── 6. driven ─────────────────────────────────────────────────────────────
print('\nbehavioural — the real doors, through scripts/harness_vault_note_race.mjs')
proc = subprocess.run([sys.executable and 'node', str(HARNESS), str(ROOT)],
                      capture_output=True, text=True)
if proc.returncode != 0:
    print(proc.stdout)
    print(proc.stderr)
    check('the harness runs', False, 'exit %d' % proc.returncode)
    print('\nFAILED (%d): harness' % 1)
    sys.exit(1)
S = {}
for line in proc.stdout.strip().splitlines():
    row = json.loads(line)
    S[row['scenario']] = row

r = S['rename-dialog-outlives-the-note']
check('the buffer really did change hands during the prompt',
      r['bufferSwappedDuringDialog'], r)
check('the boss still gets the rename they asked for', r['renamedOnDisk'], r)
check("the renamed note still holds ITS OWN body",
      r['renamedNoteBody'] == 'QUARTERLY BODY', r['renamedNoteBody'])
check('nothing in the Library lost its content',
      r['quarterlyBodySurvivesSomewhere'], r)
check("the note the boss moved on to keeps its own path and its own edit",
      r['bufferPathAfter'] == 'Inbox/idea.md'
      and r['ideaStillAtItsOwnPath'] == 'IDEA BODY EDITED', r)
check('the displacement is named, exactly once',
      len(r['displacementReported']) == 1
      and 'Research/quarterly.md' in r['displacementReported'][0]
      and 'Inbox/idea.md' in r['displacementReported'][0], r['displacementReported'])

r = S['rename-unchanged-buffer']
check('negative — an untouched buffer still follows its own rename',
      r['renamedOnDisk'] and r['bufferFollowedTheRename'], r)
check('and says nothing about a displacement that did not happen',
      r['said'] == [], r['said'])

r = S['rename-declined']
check('negative — a declined rename moves nothing and relabels nothing',
      r['stillAtOldPath'] and r['bufferPathAfter'] == 'Research/quarterly.md'
      and r['wrote'] == [], r)

r = S['delete-dialog-outlives-the-note']
check('the boss still gets the deletion they asked for', r['quarterlyDeleted'], r)
check('the note they had moved on to is still open',
      r['bufferAfter'] and r['bufferAfter']['path'] == 'Inbox/idea.md', r)
check('with the paragraph they typed into it still there',
      r['typedTextStillInBuffer'] and r['bufferAfter']['dirty'], r)
check('and one line says which note actually went',
      len(r['said']) == 1 and 'Research/quarterly.md' in r['said'][0], r['said'])

r = S['delete-unchanged-buffer']
check('negative — deleting the note in front of you still closes the editor',
      r['deleted'] and r['editorClosed'] and r['said'] == [], r)

r = S['delete-declined']
check('negative — a declined delete keeps the note and the editor',
      r['stillOnDisk'] and r['editorStillOpen'] and r['wrote'] == [], r)

r = S['the-slow-read-lands-last']
check('the note the boss clicked LAST is the note they end up on',
      r['bufferAfterBothLanded'] == 'Inbox/fast.md', r)
check('and the typing they did into it survives the earlier read landing',
      r['typedTextSurvived'] and r['bufferDirtyAfter'], r)

r = S['typed-into-the-buffer-during-the-read']
check('a keystroke during the read is FILED rather than dropped',
      r['typedTextOnDisk'], r)
check('and the note the boss asked for still opens',
      r['bufferAfter'] == 'Research/slow.md', r)

r = S['a-quiet-open']
check('negative — an ordinary open with nothing racing it still works',
      r['bufferPath'] == 'Inbox/idea.md' and r['bufferContent'] == 'IDEA BODY'
      and r['busyCleared'] and r['snags'] == [], r)

r = S['movebydrag-already-re-derives']
check('negative — moveByDrag, driven: a swapped buffer is not retargeted',
      r['renamedOnDisk'] and r['bufferNotRetargeted'], r)

print()
if FAILS:
    print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
    sys.exit(1)
print('all good — the Library acts on the buffer it has when it acts, not the '
      'one it had when it asked.')
