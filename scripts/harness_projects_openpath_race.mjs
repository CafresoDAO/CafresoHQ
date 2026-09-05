#!/usr/bin/env node
// #409 — the stale-observation class (#394 / #398 / #400 / #404) carried from
// views/vault.jsx into views/projects.jsx, the OTHER editor in this office.
// `## 404` named `openPath` as its strongest unfixed lead and did not drive
// it; this harness drives it, and its sibling `reloadOpen` with it.
//
// WorkspaceView keeps ONE editor buffer (`openFile` / `openFileRef`). Two
// doors observe it, suspend, and then write it back unconditionally:
//
//   openPath    const cur = openFileRef.current            // observe: dirty?
//               await window.hqConfirm('Discard …')        // gap (user arm)
//               const r = await C.fsReadText(path)         // gap (both arms)
//               setOpenFile({ path, content: r.content, dirty: false })  // act
//
//   reloadOpen  const cur = openFileRef.current            // observe: clean?
//               (agent-bus branch: cur.dirty ? banner : reloadOpen(arg))
//               const r = await C.fsReadText(path)         // gap
//               setOpenFile(o => o.path === path ? { …r.content, dirty:false })
//
// The buffer changes under both gaps without any bad luck at all:
//
//   * The IDEEditor textarea stays LIVE through the read. `busy` is wired to
//     exactly one thing in this pane — `disabled={busy}` on the Save button
//     (line 661) — so keystrokes land during a slow `fsReadText`. `save()`
//     twenty lines below openPath already carries a comment saying precisely
//     this about its own three round trips.
//   * The LocalTree stays clickable, so a second click supersedes the first.
//   * The agent bus (`cafresohq:agentTool`, a window event fired by the
//     coworker runtime) is not a DOM click at all: no overlay, no backdrop,
//     no modal stops it. It calls BOTH doors — reloadOpen for a clean buffer
//     and openPath(arg,{auto:true}) for Follow along.
//
// Everything under test is LIFTED from the committed views/projects.jsx by
// brace-balanced extraction. Nothing under test is re-implemented here.
//
// Usage: node harness_projects_openpath_race.mjs <repo-root> [scenario]
// Prints one JSON object per line, one per scenario run.

import fs from 'node:fs';
import path from 'node:path';

const root = process.argv[2];
if (!root) {
  console.error('usage: harness_projects_openpath_race.mjs <repo-root> [scenario]');
  process.exit(2);
}
const src = fs.readFileSync(path.join(root, 'views', 'projects.jsx'), 'utf8');

function stripComments(s) {
  return s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^[ \t]*\/\/.*$/gm, '');
}
function extractBalanced(source, marker, nth) {
  let start = -1;
  for (let n = 0; n <= (nth || 0); n++) start = source.indexOf(marker, start + 1);
  if (start < 0) throw new Error('marker not found: ' + marker);
  const braceStart = source.indexOf('{', start + marker.length - 1);
  let depth = 0;
  for (let k = braceStart; k < source.length; k++) {
    const c = source[k];
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) return source.slice(braceStart + 1, k); }
  }
  throw new Error('unbalanced braces for marker: ' + marker);
}

const bare = stripComments(src);
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

/* ── the real doors ──────────────────────────────────────────────────── */
const openPathBody      = extractBalanced(bare, 'const openPath = async (path, opts) =>');
const switchProjectBody = extractBalanced(bare, 'const switchProject = async (id) =>');
const saveBody       = extractBalanced(bare, 'const save = async (force) =>');
const reloadOpenBody = extractBalanced(bare, 'const reloadOpen = async (path) =>');

/* ── the SECOND pane on this screen: Classic (ProjectsView) ──────────────
   Same product, same buffer idea, no ref at all — its doors read the RENDER
   value `openFile`, which is a snapshot taken when the handler was created.
   Modelled below by binding `openFile` at CALL time, which is the freshest
   snapshot React could ever have handed it. */
const classicReadFileBody = extractBalanced(bare, 'const readFile = async (path) =>');
const classicRenameBody   = extractBalanced(bare, 'const renameEntry = async (entry) =>', 1);
const classicDeleteBody   = extractBalanced(bare, 'const deleteEntry = async (entry) =>', 1);

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

/* ── the world ───────────────────────────────────────────────────────── */
function makeWorld(opts = {}) {
  return {
    disk: new Map(opts.disk || []),
    openFile: opts.openFile || null,
    said: [],
    snags: [],
    err: null,
    conflict: false,
    busy: false,
    previewMode: false,
    log: [],
    readDelay: opts.readDelay || {},
    writeDelay: opts.writeDelay || 1,
  };
}

function buildRoom(w) {
  const openFileRef = { current: w.openFile };
  const setOpenFile = (v) => {
    const next = typeof v === 'function' ? v(openFileRef.current) : v;
    // `openFileRef.current = openFile` runs on every render (line 182), so the
    // ref IS the buffer. Modelling it as immediately current is the
    // CONSERVATIVE choice: React's batching makes reads staler, not fresher.
    openFileRef.current = next;
    w.openFile = next;
    w.log.push('setOpenFile:' + (next ? next.path + (next.dirty ? '*' : '') : 'null'));
  };
  const openSeqRef = { current: 0 };   // only read by the FIXED source
  const saveRef = { current: null };   // only read by the FIXED source

  const C = {
    async fsReadText(p) {
      const d = w.readDelay[p];
      if (d) await sleep(d);
      if (!w.disk.has(p)) throw new Error('Not a file: ' + p);
      return { content: w.disk.get(p), mtime: 100, hash: 'h:' + w.disk.get(p) };
    },
    async fsStat(p) {
      await sleep(1);
      if (!w.disk.has(p)) return { ok: false };
      return { ok: true, mtime: 100, hash: 'h:' + w.disk.get(p) };
    },
    async fsMkdir(p) { await sleep(1); return { ok: true, path: p, existed: true }; },
    async fsRename(from, to) {
      await sleep(2);
      for (const k of [...w.disk.keys()]) {
        if (k === from || k.startsWith(from + '/')) {
          w.disk.set(to + k.slice(from.length), w.disk.get(k));
          w.disk.delete(k);
        }
      }
      w.log.push('fsRename:' + from + '->' + to);
      return { ok: true };
    },
    async fsDelete(p) {
      await sleep(2);
      for (const k of [...w.disk.keys()]) if (k === p || k.startsWith(p + '/')) w.disk.delete(k);
      w.log.push('fsDelete:' + p);
      return { ok: true };
    },
    async toolExec(name, p, args) {
      await sleep(w.writeDelay);
      if (name !== 'FILE_WRITE') throw new Error('unexpected tool ' + name);
      w.disk.set(p, args.body);
      w.log.push('FILE_WRITE:' + p);
      return { ok: true };
    },
  };

  const scope = {
    openFileRef, setOpenFile, openSeqRef, saveRef, C,
    setErr: (e) => { w.err = e; },
    setConflict: (v) => { w.conflict = v; w.log.push('conflict:' + v); },
    setBusy: (b) => { w.busy = b; },
    setPreviewMode: (v) => { w.previewMode = v; },
    setPreviewNonce: () => {},
    setTreeNonce: () => {},
    baseName: (p) => String(p || '').split(/[/\\]/).pop(),
    previewKind: (p) => (/\.(png|jpe?g|gif|webp)$/i.test(p) ? 'image'
      : /\.pdf$/i.test(p) ? 'pdf' : 'code'),
    toast: (k, m) => { w.said.push({ k, m }); },
    snag: (what, e) => { w.snags.push(what + ' :: ' + ((e && e.message) || e)); },
    officeCause: (m) => String(m || ''),
    window: globalThis.window,
    pulseTimers: { current: {} },
    idleTimer: { current: null },
    selectedId: 'old',
    setSelectedId: (id) => { w.selectedId = id; },
    setLedger: () => {},
    setAgentStatus: () => {},
    setPulse: () => {},
  };

  const names = Object.keys(scope);
  const vals = () => names.map(n => scope[n]);

  scope.save = async (force) =>
    new AsyncFunction(...names, 'force', saveBody).apply(null, [...vals(), force]);
  names.push('save');
  saveRef.current = scope.save;

  scope.openPath = async (p, o) =>
    new AsyncFunction(...names, 'path', 'opts', openPathBody).apply(null, [...vals(), p, o]);
  names.push('openPath');

  scope.switchProject = async (id) =>
    new AsyncFunction(...names, 'id', switchProjectBody).apply(null, [...vals(), id]);
  names.push('switchProject');

  scope.reloadOpen = async (p) =>
    new AsyncFunction(...names, 'path', reloadOpenBody).apply(null, [...vals(), p]);

  /* Verbatim copy of line 223's one-liner, which is the ONLY way a keystroke
     reaches the buffer:
       const onEdit = (val) => setOpenFile(f => f ? { ...f, content: val, dirty: true } : f);
     Pinned as source text by the test that owns this harness, so a change to
     it cannot leave this model quietly describing something else. */
  scope.onEdit = (val) => setOpenFile(f => f ? { ...f, content: val, dirty: true } : f);
  return scope;
}

function buildClassicRoom(w) {
  const base = buildRoom(w);
  const CafresoHQClient = base.C;
  const scope = {
    CafresoHQClient,
    setOpenFile: base.setOpenFile,
    setErr: base.setErr,
    setBusy: base.setBusy,
    setConflict: base.setConflict,
    setPreviewMode: base.setPreviewMode,
    setTreeNonce: () => {},
    previewKind: base.previewKind,
    toast: base.toast,
    snag: base.snag,
    fsClient: () => CafresoHQClient,
    isUnder: (p, b) => p === b || p.startsWith(b + '/') || p.startsWith(b + '\\'),
    window: globalThis.window,
    openFile: null,   // rebound per call: the render closure
  };
  const names = Object.keys(scope);
  const vals = () => names.map(n => scope[n]);
  const call = (body, argNames, args) => {
    scope.openFile = base.openFileRef.current;   // the freshest render snapshot
    return new AsyncFunction(...names, ...argNames, body).apply(null, [...vals(), ...args]);
  };
  return {
    ...base,
    readFile: (p) => call(classicReadFileBody, ['path'], [p]),
    renameEntry: (e) => call(classicRenameBody, ['entry'], [e]),
    deleteEntry: (e) => call(classicDeleteBody, ['entry'], [e]),
  };
}

/* The coworker runtime firing `cafresohq:agentTool` for a FILE_WRITE. This is
   the handler's own shape (line 363-380), which is a window event: no DOM
   overlay is involved anywhere in it. */
function agentWrote(room, w, arg, body, followAlong) {
  w.disk.set(arg, body);
  const cur = room.openFileRef.current;
  if (cur && cur.path === arg) {
    if (cur.dirty) { room.setConflict(true); return null; }
    return room.reloadOpen(arg);
  }
  if (followAlong) return room.openPath(arg, { auto: true });
  return null;
}

/* ── scenarios ───────────────────────────────────────────────────────── */
const scenarios = {};

// 1. Follow along opens the coworker's file while the boss is typing in the
//    one on screen. The `auto` arm's dirty-check is made BEFORE the read.
scenarios['follow-along-lands-on-your-typing'] = async () => {
  const w = makeWorld({
    disk: [['/p/notes.md', 'NOTES BODY'], ['/p/index.js', 'INDEX BODY']],
    openFile: { path: '/p/notes.md', content: 'NOTES BODY', mtime: 100, hash: 'h:NOTES BODY', dirty: false, binary: false },
    readDelay: { '/p/index.js': 60 },
  });
  const room = buildRoom(w);
  const p = agentWrote(room, w, '/p/index.js', 'INDEX BODY', true);
  await sleep(10);
  const bailedEarly = w.openFile && w.openFile.path === '/p/index.js';
  // the boss, who has been typing all along, adds a paragraph
  room.onEdit('NOTES BODY\n\nMY PARAGRAPH');
  await p;
  const buf = w.openFile;
  return {
    scenario: 'follow-along-lands-on-your-typing',
    autoOpenBailedBeforeTheRead: !!bailedEarly,
    bufferPathAfter: buf && buf.path,
    typedTextStillInBuffer: !!(buf && String(buf.content).includes('MY PARAGRAPH')),
    typedTextOnDisk: String(w.disk.get('/p/notes.md') || '').includes('MY PARAGRAPH'),
    said: w.said.map(s => s.m),
    conflictRaised: w.conflict,
  };
};

// 2. Two tree clicks in a slow project: last read to LAND wins, which is not
//    the last file clicked.
scenarios['two-clicks-last-read-to-land-wins'] = async () => {
  const w = makeWorld({
    disk: [['/p/slow.js', 'SLOW BODY'], ['/p/fast.js', 'FAST BODY'], ['/p/open.md', 'OPEN']],
    openFile: { path: '/p/open.md', content: 'OPEN', mtime: 100, hash: 'h:OPEN', dirty: false, binary: false },
    readDelay: { '/p/slow.js': 80, '/p/fast.js': 5 },
  });
  const room = buildRoom(w);
  const a = room.openPath('/p/slow.js');
  await sleep(5);
  const b = room.openPath('/p/fast.js');   // the boss changes their mind
  await Promise.all([a, b]);
  return {
    scenario: 'two-clicks-last-read-to-land-wins',
    lastClicked: '/p/fast.js',
    bufferAfterBothLanded: w.openFile && w.openFile.path,
    bufferContentAfter: w.openFile && w.openFile.content,
    endedOnTheFileTheyClickedLast: !!(w.openFile && w.openFile.path === '/p/fast.js'),
    busyCleared: w.busy === false,
  };
};

// 3. A superseded read that FAILS paints its refusal over the file that did
//    open — the same write, pointed at `err`.
scenarios['superseded-failure-blots-the-open-file'] = async () => {
  const w = makeWorld({
    disk: [['/p/fast.js', 'FAST BODY']],
    openFile: null,
    readDelay: { '/p/gone.js': 80, '/p/fast.js': 5 },
  });
  const room = buildRoom(w);
  const a = room.openPath('/p/gone.js');   // deleted under them
  await sleep(5);
  const b = room.openPath('/p/fast.js');
  await Promise.all([a, b]);
  return {
    scenario: 'superseded-failure-blots-the-open-file',
    bufferAfter: w.openFile && w.openFile.path,
    errShown: w.err,
    errAboutTheFileOnScreen: !w.err,
  };
};

// 4. The boss types during a read they asked for themselves (clean buffer, so
//    no confirm was ever shown).
scenarios['typing-during-your-own-open'] = async () => {
  const w = makeWorld({
    disk: [['/p/notes.md', 'NOTES BODY'], ['/p/index.js', 'INDEX BODY']],
    openFile: { path: '/p/notes.md', content: 'NOTES BODY', mtime: 100, hash: 'h:NOTES BODY', dirty: false, binary: false },
    readDelay: { '/p/index.js': 60 },
  });
  const room = buildRoom(w);
  const p = room.openPath('/p/index.js');
  await sleep(10);
  room.onEdit('NOTES BODY\n\nMY PARAGRAPH');
  await p;
  return {
    scenario: 'typing-during-your-own-open',
    bufferPathAfter: w.openFile && w.openFile.path,
    typedTextOnDisk: String(w.disk.get('/p/notes.md') || '').includes('MY PARAGRAPH'),
    typedTextStillInBuffer: !!(w.openFile && String(w.openFile.content).includes('MY PARAGRAPH')),
    said: w.said.map(s => s.m),
    gestureHonoured: !!(w.openFile && w.openFile.path === '/p/index.js'),
  };
};

// 5. reloadOpen: the agent bus chose "silent reload" because the buffer was
//    clean AT THAT INSTANT. The boss starts typing while the reload is in
//    flight, and the dirty half of that choice expires.
scenarios['silent-reload-lands-on-your-typing'] = async () => {
  const w = makeWorld({
    disk: [['/p/index.js', 'INDEX BODY']],
    openFile: { path: '/p/index.js', content: 'INDEX BODY', mtime: 100, hash: 'h:INDEX BODY', dirty: false, binary: false },
    readDelay: { '/p/index.js': 60 },
  });
  const room = buildRoom(w);
  const p = agentWrote(room, w, '/p/index.js', 'COWORKER BODY', false);
  await sleep(10);
  room.onEdit('INDEX BODY\n\nMY PARAGRAPH');
  await p;
  const buf = w.openFile;
  return {
    scenario: 'silent-reload-lands-on-your-typing',
    bufferContentAfter: buf && buf.content,
    typedTextStillInBuffer: !!(buf && String(buf.content).includes('MY PARAGRAPH')),
    bufferStillDirty: !!(buf && buf.dirty),
    conflictBannerRaised: w.conflict,
    typedTextOnDisk: String(w.disk.get('/p/index.js') || '').includes('MY PARAGRAPH'),
  };
};

// 6. Control: an ordinary open with nothing racing it.
scenarios['ordinary-open'] = async () => {
  const w = makeWorld({
    disk: [['/p/index.js', 'INDEX BODY']],
    openFile: null,
  });
  const room = buildRoom(w);
  await room.openPath('/p/index.js');
  return {
    scenario: 'ordinary-open',
    bufferPathAfter: w.openFile && w.openFile.path,
    bufferContentAfter: w.openFile && w.openFile.content,
    dirty: !!(w.openFile && w.openFile.dirty),
    busyCleared: w.busy === false,
    err: w.err,
  };
};

// 7. Control: the boss declines the discard confirm. Nothing moves.
scenarios['declined-discard'] = async () => {
  const w = makeWorld({
    disk: [['/p/notes.md', 'NOTES BODY'], ['/p/index.js', 'INDEX BODY']],
    openFile: { path: '/p/notes.md', content: 'NOTES BODY EDITED', mtime: 100, hash: 'h:NOTES BODY', dirty: true, binary: false },
  });
  const room = buildRoom(w);
  globalThis.window.hqConfirm = async () => false;
  await room.openPath('/p/index.js');
  return {
    scenario: 'declined-discard',
    bufferPathAfter: w.openFile && w.openFile.path,
    bufferContentAfter: w.openFile && w.openFile.content,
    reads: w.log.filter(l => l.startsWith('setOpenFile')),
  };
};

// 8. Control: the boss accepts the discard, and gets what they asked for.
scenarios['accepted-discard'] = async () => {
  const w = makeWorld({
    disk: [['/p/notes.md', 'NOTES BODY'], ['/p/index.js', 'INDEX BODY']],
    openFile: { path: '/p/notes.md', content: 'NOTES BODY EDITED', mtime: 100, hash: 'h:NOTES BODY', dirty: true, binary: false },
    readDelay: { '/p/index.js': 20 },
  });
  const room = buildRoom(w);
  globalThis.window.hqConfirm = async () => true;
  await room.openPath('/p/index.js');
  return {
    scenario: 'accepted-discard',
    bufferPathAfter: w.openFile && w.openFile.path,
    discardWasHonoured: !String(w.disk.get('/p/notes.md') || '').includes('EDITED'),
    said: w.said.map(s => s.m),
  };
};

// 10. The convention this fix copies, driven so the claim about it is a
//     measurement: `save` twenty lines below openPath already re-derives, and
//     only stamps clean the content it actually wrote.
scenarios['save-already-re-derives'] = async () => {
  const w = makeWorld({
    disk: [['/p/index.js', 'INDEX BODY']],
    openFile: { path: '/p/index.js', content: 'INDEX BODY ONE', mtime: 100, hash: 'h:INDEX BODY', dirty: true, binary: false },
    writeDelay: 30,
  });
  const room = buildRoom(w);
  const p = room.save(false);
  await sleep(10);
  room.onEdit('INDEX BODY ONE TWO');   // keystrokes during the round trips
  await p;
  return {
    scenario: 'save-already-re-derives',
    wroteToDisk: w.disk.get('/p/index.js'),
    bufferContentAfter: w.openFile && w.openFile.content,
    stillDirtyBecauseNewerKeystrokes: !!(w.openFile && w.openFile.dirty),
  };
};

// 11. switchProject clears the deck. A read started in the OLD project lands
//     after the switch and hangs that project's file inside the new one.
scenarios['read-lands-after-a-project-switch'] = async () => {
  const w = makeWorld({
    disk: [['/old/slow.js', 'OLD PROJECT BODY']],
    openFile: null,
    readDelay: { '/old/slow.js': 60 },
  });
  const room = buildRoom(w);
  const p = room.openPath('/old/slow.js');
  await sleep(10);
  await room.switchProject('new');            // the boss picks another project
  const clearedAtSwitch = w.openFile === null;
  await p;
  return {
    scenario: 'read-lands-after-a-project-switch',
    clearedAtSwitch,
    projectNow: w.selectedId,
    bufferAfterSwitch: w.openFile && w.openFile.path,
    deckStayedClear: w.openFile === null,
  };
};

// 12. The discard confirm's own gap, driven rather than reasoned about: a
//     coworker writes the dirty file while the dialog is up (a window event —
//     no backdrop is involved), and Follow along fires under it too.
scenarios['coworker-writes-under-the-discard-confirm'] = async () => {
  const w = makeWorld({
    disk: [['/p/notes.md', 'NOTES BODY'], ['/p/index.js', 'INDEX BODY'], ['/p/other.js', 'OTHER BODY']],
    openFile: { path: '/p/notes.md', content: 'NOTES BODY EDITED', mtime: 100, hash: 'h:NOTES BODY', dirty: true, binary: false },
    readDelay: { '/p/index.js': 5 },
  });
  const room = buildRoom(w);
  let followAlongOpened = null;
  globalThis.window.hqConfirm = async () => {
    agentWrote(room, w, '/p/notes.md', 'COWORKER BODY', true);   // same file → banner
    followAlongOpened = agentWrote(room, w, '/p/other.js', 'OTHER BODY', true);
    await followAlongOpened;
    return true;
  };
  await room.openPath('/p/index.js');
  return {
    scenario: 'coworker-writes-under-the-discard-confirm',
    followAlongBailedOnTheDirtyBuffer: !!(w.openFile && w.openFile.path !== '/p/other.js'),
    bufferAfter: w.openFile && w.openFile.path,
    bufferContentAfter: w.openFile && w.openFile.content,
    endedWhereTheBossAsked: !!(w.openFile && w.openFile.path === '/p/index.js'),
  };
};

// 12. Classic (ProjectsView), which has no ref at all: renameEntry reads the
//     RENDER value and spreads it back whole after two awaits.
scenarios['classic-rename-restores-the-file-you-left'] = async () => {
  const w = makeWorld({
    disk: [['/p/a.md', 'A BODY'], ['/p/b.md', 'B BODY']],
    openFile: { path: '/p/a.md', content: 'A BODY', mtime: 100, hash: 'h:A BODY', dirty: false },
    readDelay: { '/p/b.md': 40 },
  });
  const room = buildClassicRoom(w);
  const reading = room.readFile('/p/b.md');        // the boss clicks another file
  globalThis.window.hqPrompt = async () => { await sleep(60); return 'renamed.md'; };
  await room.renameEntry({ path: '/p/a.md', name: 'a.md', isDir: false });
  await reading;
  const buf = w.openFile;
  return {
    scenario: 'classic-rename-restores-the-file-you-left',
    fileTheyClicked: '/p/b.md',
    bufferPathAfter: buf && buf.path,
    bufferContentAfter: buf && buf.content,
    theFileTheyOpenedSurvived: !!(buf && buf.path === '/p/b.md' && buf.content === 'B BODY'),
    renamedOnDisk: w.disk.has('/p/renamed.md'),
  };
};

// 13. Classic deleteEntry: the same stale render read, clearing a deck that
//     now holds a different file.
scenarios['classic-delete-clears-the-wrong-buffer'] = async () => {
  const w = makeWorld({
    disk: [['/p/a.md', 'A BODY'], ['/p/b.md', 'B BODY']],
    openFile: { path: '/p/a.md', content: 'A BODY', mtime: 100, hash: 'h:A BODY', dirty: false },
    readDelay: { '/p/b.md': 40 },
  });
  const room = buildClassicRoom(w);
  const reading = room.readFile('/p/b.md');
  globalThis.window.hqConfirm = async () => { await sleep(60); return true; };
  await room.deleteEntry({ path: '/p/a.md', name: 'a.md', isDir: false });
  await reading;
  return {
    scenario: 'classic-delete-clears-the-wrong-buffer',
    deletedOnDisk: !w.disk.has('/p/a.md'),
    bufferAfter: w.openFile && w.openFile.path,
    theFileTheyOpenedSurvived: !!(w.openFile && w.openFile.path === '/p/b.md'),
  };
};

// 14. Control for both: with nothing racing, Classic still rebases the open
//     file's path onto a renamed folder and still closes a deleted one.
scenarios['classic-rename-and-delete-alone'] = async () => {
  const w = makeWorld({
    disk: [['/p/dir/a.md', 'A BODY']],
    openFile: { path: '/p/dir/a.md', content: 'A BODY', mtime: 100, hash: 'h:A BODY', dirty: false },
  });
  const room = buildClassicRoom(w);
  globalThis.window.hqPrompt = async () => 'folder';
  await room.renameEntry({ path: '/p/dir', name: 'dir', isDir: true });
  const rebased = w.openFile && w.openFile.path;
  globalThis.window.hqConfirm = async () => true;
  await room.deleteEntry({ path: '/p/folder', name: 'folder', isDir: true });
  return {
    scenario: 'classic-rename-and-delete-alone',
    rebasedTo: rebased,
    followedTheFolderRename: rebased === '/p/folder/a.md',
    deckClearedByTheDelete: w.openFile === null,
  };
};

/* ── run ─────────────────────────────────────────────────────────────── */
globalThis.window = globalThis.window || {};
globalThis.window.hqConfirm = async () => true;

const only = process.argv[3];
const names = only ? [only] : Object.keys(scenarios);
let bad = 0;
for (const n of names) {
  if (!scenarios[n]) { console.error('no such scenario: ' + n); process.exit(2); }
  globalThis.window.hqConfirm = async () => true;
  try {
    console.log(JSON.stringify(await scenarios[n]()));
  } catch (e) {
    bad++;
    console.log(JSON.stringify({ scenario: n, harnessError: String((e && e.stack) || e) }));
  }
}
process.exit(bad ? 1 : 0);
