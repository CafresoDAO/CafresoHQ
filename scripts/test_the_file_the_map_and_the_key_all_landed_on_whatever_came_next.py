#!/usr/bin/env python3
"""#414 — the tail of the stale-observation sweep.

The class #394 opened and #398/#400/#404/#409 carried: an observation made
BEFORE an `await`, acted on AFTER it, when the observed thing can change during
the wait. #409 swept views/projects.jsx's WorkspaceView and left THREE doors
NAMED but not measured. These are those three, driven — through the new
scripts/harness_await_tail_two.mjs, which lifts the REAL bodies out of the
committed sources by brace-balanced extraction. Nothing under test is
re-implemented.

1. views/projects.jsx — ProjectsView (Classic) `readFile`. The same
   unconditional `setOpenFile({ path, content: r.content, … })` on the far side
   of a read that #409 fixed in WorkspaceView, but Classic has no ref, no
   sequence number, and no discard check AT ALL. Measured pre-fix:
     * `bufferAfterBothLanded: "/p/slow.js"` for a boss whose last click was
       /p/fast.js;
     * `typedTextStillInBuffer: false, typedTextOnDisk: false, said: []`;
     * `askedBeforeDroppingTheEdits: false` — a dirty buffer replaced with no
       question, which is a MISSING observation, not an expired one;
     * `errShown: "Not a file: /p/gone.js"` painted over the file that opened;
     * `previewModeAfter: true` with a .md in the buffer — `setPreviewMode` was
       decided before the read and never revisited, so an image clicked while a
       text read was in flight stranded the text file in the read-only preview.

2. views/graph.jsx — `window.CafresoHQGraph.refresh`. `mountData` DESTROYS the
   engine on the canvas before mounting the next, and three things start a
   rebuild without freezing the other two (the source/scope effect, ↻ Rebuild,
   and refresh() — which views/vault.jsx:450 fires after EVERY note write and
   agent_runner.jsx fires from four places, none of them a DOM click). #409
   assessed the cost as "a stale picture". Measured, it is more than that:
     * `mountedAfterBoth: "/a.md"` after the boss wrote note A then note B, and
       `_lastGraph` left holding that same stale shape — which is what
       views/vault.jsx:1408 counts to name the links a delete will break, so
       `deadLinksNamedByTheConfirm: []` where the live library had one;
     * `mountedSource: "links"` on a canvas whose toolbar said Concept map;
     * a superseded refresh that FAILED raised its card over the map that DID
       mount (`loadError: "the office is not answering"`).

3. views/terminal.jsx — `saveKey` / `clearKey`. `setKeyInput('')` and
   `setKeyPanel(false)` fired unconditionally after the round trip, and nothing
   in the panel is disabled while it runs. #409 declined to harness this path
   because it handles real credentials. It is harnessed here under a rule the
   harness states and this test pins: the store is a stub that records its
   arguments, no environment, keychain or file is read, and every value is an
   obvious `sk-FAKE-…`. Measured pre-fix: `typedAfterSaveSurvived: false,
   panelStillOpen: false, fieldLeftEmpty: true` — a secret the boss pasted,
   gone, with nothing said. CLEAR KEY is the same door the other way:
   `replacementSurvivedGettingBackToIt: false`, because the 🔓 button that is
   the only way back into the panel clears the field on its way in.

`provider` is NOT part of 3: it is derived from the `cli` PROP and every
session panel stays mounted with its own fixed `cli`, so no instance can change
provider under its own await. Pinned below, because it is the reason the
functional `setKeyStored` updater beside these two lines is correct — and a
functional updater is not what makes the lines under it safe (#404).

Run: python3 scripts/test_the_file_the_map_and_the_key_all_landed_on_whatever_came_next.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / 'views' / 'projects.jsx'
GRAPH = ROOT / 'views' / 'graph.jsx'
TERMINAL = ROOT / 'views' / 'terminal.jsx'
SETTINGS = ROOT / 'modals' / 'settings.jsx'
HARNESS = ROOT / 'scripts' / 'harness_await_tail_two.mjs'
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
    """The body `header` introduces, or None when the header is gone. A missing
    marker must FAIL its check, never crash the run over the other forty —
    #404's fire test is what found that out, and #414 keeps the rule."""
    if src is None:
        return None
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


def idx(src, needle):
    """`str.find`, never `str.index` — a marker absent before the fix must make
    its check FAIL, not raise and swallow the rest of the run (#404)."""
    return -1 if src is None else src.find(needle)


# ── sources ──────────────────────────────────────────────────────────────────
projects = strip_comments(PROJECTS.read_text(encoding='utf-8'))
graph = strip_comments(GRAPH.read_text(encoding='utf-8'))
terminal = strip_comments(TERMINAL.read_text(encoding='utf-8'))
settings = strip_comments(SETTINGS.read_text(encoding='utf-8'))
projects_raw = PROJECTS.read_text(encoding='utf-8')
harness_raw = HARNESS.read_text(encoding='utf-8')

print('#414 — the file, the map and the key all landed on whatever came next')
print()

# ── 1. structure: views/projects.jsx Classic readFile ────────────────────────
print('views/projects.jsx — Classic readFile')
read = brace_lift(projects, 'const readFile = async (path) =>')
check('found Classic readFile', read is not None)

check('it reads the LIVE buffer from a ref, not the render value it used to '
      'have no access to at all',
      has(read, 'const cur = openFileRef.current'))
check('ProjectsView declares that ref and keeps it current from an effect',
      bool(re.search(r"const openFileRef = React\.useRef\(null\);\s*React\.useEffect\(\(\) => \{ openFileRef\.current = openFile; \}, \[openFile\]\);",
                     projects)))
check('ProjectsView declares the sequence ref this file already uses in '
      'WorkspaceView',
      'const openSeqRef = React.useRef(0);' in projects
      and projects.count('const openSeqRef = React.useRef(0);') == 2)

check('the number is claimed BEFORE the first suspend — the discard confirm '
      'is one, so the claim must precede it',
      0 <= idx(read, 'const seq = ++openSeqRef.current') < idx(read, 'window.hqConfirm')
      and idx(read, 'window.hqConfirm') >= 0)
check('nothing suspends between reading the buffer and claiming the number',
      no_await_between(read, 'const cur = openFileRef.current',
                       'const seq = ++openSeqRef.current'))
check('the confirm gap is re-checked before anything is set',
      0 <= idx(read, 'if (openSeqRef.current !== seq) return;') < idx(read, 'setBusy(true)'))
check('the READ gap is re-checked, and it clears busy on the way out',
      'if (openSeqRef.current !== seq) { setBusy(false); return; }' in (read or ''))
check('the far side re-derives the LIVE buffer rather than trusting `cur`',
      0 <= idx(read, 'const live = openFileRef.current;')
      and idx(read, 'const live = openFileRef.current;') > idx(read, 'await CafresoHQClient.fsReadText(path)'))
check('nothing suspends between that re-read and the branch it guards',
      no_await_between(read, 'const live = openFileRef.current;',
                       'if (live && live.dirty'))
check('typing that landed during the read is FILED, not dropped',
      has(read, 'await saveFileRef.current(false)')
      and has(read, 'Filed your changes to'))
check('the FLUSH is itself a suspend, and is re-checked too',
      idx(read, 'await saveFileRef.current(false)') <
      idx(read, 'const still = openFileRef.current;')
      and read.count('if (openSeqRef.current !== seq) { setBusy(false); return; }') >= 3)
check('a flush that could not land keeps the boss where their typing is and '
      'names that file',
      has(read, "Still on ${baseName(still.path)}")
      and has(read, "so ${baseName(path)} stayed shut."))
check('an accepted Discard is honoured on the far side — the flush must not '
      'quietly file what the boss just threw away',
      has(read, 'let discarded = null;')
      and has(read, 'discarded = cur.path;')
      and has(read, 'live.path !== discarded'))
check('the failure arm belongs to the open it came from',
      0 <= idx(read, 'if (openSeqRef.current !== seq) { setBusy(false); return; }')
      < idx(read, 'setErr(e.message || String(e));')
      and idx(read, 'setErr(e.message || String(e));') >= 0)
check('preview mode is decided on the far side of the read, not before it',
      idx(read, 'setPreviewMode(false)') > idx(read, 'await CafresoHQClient.fsReadText(path)')
      and 'setPreviewMode(isBinary)' not in (read or ''))
check('the binary arm still previews immediately and still reads nothing',
      no_await_between(read, 'if (isBinary) {', 'setBusy(false);'))
check('every early return after busy was raised clears it',
      (read or '').count('setBusy(false); return;') >= 4)

check('saveFile is reachable from readFile through a forward ref, the same '
      'shape WorkspaceView uses for save',
      'const saveFileRef = React.useRef(null);' in projects
      and 'saveFileRef.current = saveFile;' in projects
      and projects.find('saveFileRef.current = saveFile;') > projects.find('const saveFile = async (force) =>'))

check('a sequence number is not a guard unless every seeder claims it: every '
      'door that clears Classic\'s buffer goes through clearOpenFile',
      'const clearOpenFile = () => { openSeqRef.current++; setOpenFile(null); };' in projects
      and projects.count('clearOpenFile()') >= 6)
check('no bare setOpenFile(null) is left in ProjectsView — the only one is '
      'inside clearOpenFile itself',
      projects[projects.find('function ProjectsView'):].count('setOpenFile(null)') == 1)

# The MECHANISM, pinned as a property: if `busy` ever reaches the tree or the
# editor, this door stops being a race and these checks should be revisited
# rather than quietly still passing.
# `busy` DOES reach a `disabled={busy}` elsewhere in this file — WorkspaceView's
# Save (763) and the AddProjectModal footer — so the property to pin is not
# "the word is absent", it is that the two things a boss can use to supersede a
# read, the tree and the editor, are never handed it.
_classic = between(projects_raw, 'function ProjectsView', 'function FileBrowserModal')
check('MECHANISM — `busy` in ProjectsView reaches the two Save buttons and '
      'nothing else: the LocalTree and the IDEEditor stay live through a read',
      _classic is not None
      and _classic.count('disabled={!openFile.dirty || busy}') == 2
      and 'disabled={busy}' not in _classic
      and _classic.count('<LocalTree') >= 1
      and not re.search(r'<(LocalTree|IDEEditor)\b[^>]*disabled', _classic, re.S))
check('MECHANISM — the harness copies Classic\'s only keystroke path, so pin '
      'it verbatim',
      projects_raw.count('onChange={(v) => setOpenFile({ ...openFile, content: v, dirty: true })}') == 2)

# Load-bearing negatives: the read itself, and saveFile's own convention.
check('negative — readFile still reads through fsReadText and still keeps the '
      'mtime/hash saveFile\'s conflict check needs',
      has(read, 'await CafresoHQClient.fsReadText(path)')
      and has(read, 'setOpenFile({ path, content: r.content, mtime: r.mtime, hash: r.hash, dirty: false });'))
save_file = brace_lift(projects, 'const saveFile = async (force) =>')
check('negative — saveFile still stamps clean only what it actually wrote',
      has(save_file, 'dirty: o.content !== openFile.content'))

print()
print('views/graph.jsx — the one canvas')
refresh = brace_lift(graph, 'refresh: async () =>')
load_effect = between(graph, 'let cancelled = false;', '}, [source, scope, reloadTick]);')
check('found the refresh door and the load effect', refresh is not None and load_effect is not None)
check('graph declares the sequence ref', 'const mountSeqRef = React.useRef(0);' in graph)
check('refresh claims its number BEFORE its read',
      0 <= idx(refresh, 'const seq2 = ++mountSeqRef.current;') < idx(refresh, 'await loadData()'))
check('refresh re-checks after the read, before it touches the canvas',
      0 <= idx(refresh, 'if (mountSeqRef.current !== seq2 || !containerRef.current) return;')
      < idx(refresh, 'const e2 = mountData(g2);'))
check('nothing suspends between that re-check and the mount it guards',
      no_await_between(refresh, 'if (mountSeqRef.current !== seq2', 'mountData(g2)'))
check('a superseded refresh that FAILED raises no card',
      0 <= idx(refresh, 'if (mountSeqRef.current !== seq2) return;')
      < idx(refresh, 'setLoadError('))
check('refresh does not assume the API object outlived the panel — the '
      'unmount effect deletes it',
      has(refresh, 'const api = window.CafresoHQGraph;')
      and has(refresh, 'if (e2 && api) api._lastGraph = g2;'))
check('the load effect claims a number too, and `cancelled` alone is not the '
      'guard (it only covers this effect being torn down)',
      has(load_effect, 'const seq = ++mountSeqRef.current;')
      and idx(load_effect, 'const seq = ++mountSeqRef.current;') < idx(load_effect, 'await loadData()'))
check('the effect re-checks the number alongside cancelled and the container',
      has(load_effect, 'if (cancelled || mountSeqRef.current !== seq || !containerRef.current) { setLoading(false); return; }'))
check('negative — the engine-missing card and the load-failure card are '
      'untouched',
      'the graph engine did not load' in graph
      and load_effect.count('setLoadError(officeCause(') >= 1)
check('MECHANISM — mountData still DESTROYS the engine on the canvas before '
      'mounting the next one, which is why "last to land" decides the map',
      has(brace_lift(graph, 'const mountData = (g) =>'), 'engineRef.current && engineRef.current.destroy()'))
check('MECHANISM — refresh is reachable without any DOM click: views/vault.jsx '
      'fires it after a note write',
      'window.CafresoHQGraph && window.CafresoHQGraph.refresh()'
      in strip_comments((ROOT / 'views' / 'vault.jsx').read_text(encoding='utf-8')))

print()
print('views/terminal.jsx — the key field')
savek = brace_lift(terminal, 'const saveKey = async () =>')
cleark = brace_lift(terminal, 'const clearKey = async () =>')
check('found saveKey and clearKey', savek is not None and cleark is not None)
check('the key field has a live-value ref, kept current from an effect',
      bool(re.search(r"const keyInputRef = React\.useRef\(''\);\s*React\.useEffect\(\(\) => \{ keyInputRef\.current = keyInput; \}, \[keyInput\]\);",
                     terminal)))
check('saveKey captures what it is FILING before the round trip',
      0 <= idx(savek, 'const filed = keyInput.trim();') < idx(savek, 'await oc.setAgentKey(provider, filed)'))
check('saveKey clears the field only when the field still holds what it filed',
      has(savek, 'const kept = keyInputRef.current.trim() !== filed;')
      and has(savek, "if (!kept) { setKeyInput(''); setKeyPanel(false); }"))
check('nothing suspends between that re-read and the act it guards',
      no_await_between(savek, 'const kept =', 'if (!kept)'))
check('saveKey no longer clears the field unconditionally',
      "setKeyInput('');\n    setKeyPanel(false);" not in (savek or ''))
check('clearKey keeps the panel open when a replacement was typed during the '
      'delete',
      has(cleark, "setKeyPanel(p => (keyInputRef.current.trim() ? p : false));"))
# Not a "negative": pre-fix these read `keyInput.trim()` inline, so both of
# these DO change with the fix. They pin that what the door files is unchanged
# in substance — the same call, the same empty string — only captured first.
check('both doors still write through setAgentKey, and clearKey still files '
      'the empty string',
      has(savek, 'await oc.setAgentKey(provider, filed);')
      and has(cleark, "await oc.setAgentKey(provider, '');"))
check('the stored-key flag is still stamped with a functional updater keyed '
      'by the provider that was actually filed',
      has(savek, 'setKeyStored(prev => ({ ...prev, [provider]: !!filed }));')
      and has(cleark, 'setKeyStored(prev => ({ ...prev, [provider]: false }));'))
check('MECHANISM — `provider` is derived from the `cli` PROP, so no mounted '
      'session can change it under its own await',
      "const provider    = cli === 'claude' ? 'anthropic'" in terminal
      and 'function TerminalSession({ project, cli, sessionId, visible, ptySupported, spawnSupported })' in terminal)
# `disabled={busy}` exists in this file, but it belongs to the CHAT composer,
# not the key panel — so pin the panel itself.
_panel = between(terminal, '{keyPanel && authMethod ===', 'AES-256-GCM · device key')
check('MECHANISM — nothing in the key panel is disabled during the round trip '
      'except SAVE, and that only on an empty field',
      _panel is not None
      and 'disabled={!keyInput.trim()}' in _panel
      and _panel.count('disabled=') == 1
      and 'autoFocus' in _panel)
check('MECHANISM — the 🔓 button clears the field on its way in, which is why '
      'a panel shut over a typed replacement destroys it',
      "onClick={() => { setKeyPanel(p => !p); setKeyInput(''); }}" in terminal)

# CREDENTIAL SAFETY, pinned. This is the constraint #409 declined to work
# under; if the harness ever grows a real read, this check must fail loudly.
print()
print('credential safety of the harness itself')
check('the harness never reads an environment variable, a file other than the '
      'three committed sources it lifts from, or any credential store',
      'process.env' not in harness_raw
      and harness_raw.count('readFileSync') == 4
      and 'getAgentKey' not in harness_raw
      and 'child_process' not in harness_raw)
check('every key value the harness uses is an obvious fake',
      all(v.startswith('sk-FAKE-') for v in re.findall(r"'(sk-[^']*)'", harness_raw))
      and "'sk-FAKE-truncated'" in harness_raw)
check('the harness never prints a key value — only whether the field still '
      'holds what was typed into it',
      'value: room.w' not in harness_raw
      and 'keyInput,' not in re.sub(r'\s+', ' ', harness_raw).replace('w.keyInput,', ''))

# ── behaviour, through the harness ───────────────────────────────────────────
print()
print('driven — scripts/harness_await_tail_two.mjs')
_cache = {}


def sc(name):
    if not _cache:
        p = subprocess.run([sys.executable and 'node', str(HARNESS), str(ROOT)],
                           capture_output=True, text=True)
        for line in p.stdout.splitlines():
            line = line.strip()
            if not line.startswith('{'):
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            _cache[d.get('scenario')] = d
        if not _cache:
            _cache['__err__'] = {'stderr': p.stderr[-2000:]}
    return _cache.get(name) or {'missing': name, 'why': _cache.get('__err__')}


r = sc('classic-two-clicks-last-read-to-land-wins')
check('Classic: the deck ends on the file clicked LAST, not the read that '
      'landed last',
      r.get('bufferAfterBothLanded') == '/p/fast.js'
      and r.get('endedOnTheFileTheyClickedLast') is True
      and r.get('busyCleared') is True, r)

r = sc('classic-typing-during-the-read')
check('Classic: typing during a read is FILED and said once, naming both '
      'files — not destroyed',
      r.get('typedTextOnDisk') is True
      and r.get('endedOnTheFileTheyAskedFor') is True
      and r.get('said') == ['Filed your changes to notes.md before opening index.js.'], r)

r = sc('classic-dirty-buffer-never-asked')
check('Classic: a dirty buffer is no longer replaced without a question',
      r.get('askedBeforeDroppingTheEdits') is True
      and r.get('asked') == ['Discard unsaved changes to notes.md?'], r)

r = sc('classic-cancelled-discard-stays-put')
check('Classic: CANCEL on that question leaves the boss where they were, with '
      'their typing',
      r.get('stayedWhereTheySaid') is True
      and r.get('unsavedTextStillInBuffer') is True, r)

r = sc('classic-accepted-discard-is-honoured')
check('negative — an accepted Discard is still a discard: the far side does '
      'not quietly file what was thrown away',
      r.get('discardWasHonoured') is True
      and r.get('bufferAfter') == '/p/index.js', r)

r = sc('classic-superseded-failure-blots-the-open-file')
check('Classic: a superseded read that FAILED no longer paints its refusal '
      'over the file that did open',
      r.get('bufferAfter') == '/p/fast.js'
      and r.get('errAboutTheFileOnScreen') is True, r)

r = sc('classic-image-click-strands-the-text-file-in-preview')
check('Classic: an image clicked mid-read no longer strands the text file in '
      'the read-only preview',
      r.get('bufferAfter') == '/p/shot.png'
      and r.get('previewModeAgreesWithTheBuffer') is True, r)

r = sc('classic-save-stamps-only-what-it-wrote')
check('negative — saveFile, driven: it files what it captured and leaves '
      'newer keystrokes dirty',
      r.get('wroteToDisk') == 'INDEX BODY ONE'
      and r.get('bufferContentAfter') == 'INDEX BODY ONE TWO'
      and r.get('stillDirtyBecauseNewerKeystrokes') is True, r)

r = sc('graph-two-refreshes-last-to-land-wins')
check('graph: the canvas ends on the NEWEST library, not the rebuild that '
      'landed last',
      r.get('showsTheNewestWrite') is True
      and r.get('mountedAfterBoth') == '/a.md+/b.md', r)
check('graph: `_lastGraph` is the newest too — it is what the delete confirm '
      'counts to name the links it is about to break',
      r.get('deadLinksNamedByTheConfirm') == ['/b.md'], r)

r = sc('graph-refresh-lands-in-the-wrong-source')
check('graph: a rebuild started under the old source no longer lands on the '
      'new one',
      r.get('mountedSource') == 'concepts'
      and r.get('canvasAgreesWithTheToolbar') is True, r)

r = sc('graph-refresh-overtaken-by-a-slow-first-load')
check('graph: the other direction — a slow effect load no longer lands on top '
      'of a newer refresh',
      r.get('newestWriteSurvived') is True, r)

r = sc('graph-superseded-failure-raises-no-card')
check('graph: a superseded refresh that FAILED raises no card over the map '
      'that did mount',
      r.get('cardAboutTheMapOnScreen') is True
      and r.get('mountedAfterBoth') == '/a.md+/b.md', r)

r = sc('graph-refresh-outlives-the-panel')
check('negative — a refresh still in flight when the panel closes mounts '
      'nothing and throws nothing',
      r.get('didNotThrowPastItsOwnCatch') is True
      and r.get('mountedAfterTheClose') == 1, r)

r = sc('key-typed-during-the-save-is-wiped')
check('key: a correction typed while the save is in flight survives, and the '
      'panel stays open on it',
      r.get('typedAfterSaveSurvived') is True
      and r.get('panelStillOpen') is True
      and r.get('fieldLeftEmpty') is False
      and r.get('filedCount') == 1, r)

r = sc('key-plain-save-still-clears-and-closes')
check('negative — an ordinary SAVE still files the key, clears the field and '
      'closes the panel',
      r.get('fieldCleared') is True
      and r.get('panelClosed') is True
      and r.get('storedForProvider') is True
      and r.get('filedCount') == 1, r)

r = sc('key-typed-during-the-clear-is-shut-away')
check('key: a replacement typed during CLEAR KEY is still there when the boss '
      'looks for it',
      r.get('panelStillOpen') is True
      and r.get('replacementSurvivedGettingBackToIt') is True
      and r.get('storedFlagCleared') is True, r)

r = sc('key-plain-clear-still-closes')
check('negative — an ordinary CLEAR KEY still files the empty string and '
      'closes the panel',
      r.get('panelClosed') is True
      and r.get('filedEmptyString') is True
      and r.get('storedFlagCleared') is True, r)

# ── the door this entry leaves EXPOSED, pinned as a measurement ───────────────
print()
print('EXPOSED — modals/settings.jsx, measured and left standing')
r = sc('settings-typing-during-the-readback-is-wiped')
check('modals/settings.jsx: the agent-wallet card\'s post-save read-back still '
      'overwrites an amount typed while it was running — measured, NOT fixed '
      'by #414, and this check pins the measurement so the day it is repaired '
      'this line is what changes',
      r.get('typedAmountSurvived') is False
      and r.get('replacedWithTheSavedValue') is True
      and r.get('putsMade') == 1, r)
check('the mechanism behind it: `busy` in that card reaches BUTTONS only, so '
      'the amount inputs stay live through the round trip',
      "disabled={busy === 'pay'}" in settings
      and "disabled={busy === 'cap'}" in settings
      and 'disabled={!!busy}' not in settings, )

print()
if FAILS:
    print('FAILED (%d): %s' % (len(FAILS), ', '.join(FAILS)))
    sys.exit(1)
print('all good — the deck, the map and the key field each end on what the '
      'boss last asked for, and say so when something of theirs was moved.')
