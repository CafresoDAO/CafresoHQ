#!/usr/bin/env node
// #404 — the stale-observation class (#394 / #398 / #400) carried out of
// app.jsx + hq-runtime.jsx and into the view layer, where #398's sweep of 85
// suspend points never reached.
//
// views/vault.jsx keeps ONE editor buffer (`openNote` / `openNoteRef`) and
// three doors that read it, suspend, and then WRITE it back:
//
//   renameNote  const n = openNoteRef.current                        // observe
//               await window.hqPrompt('Rename / move to …')          // gap
//               await CafresoHQClient.vaultRename(n.path, to)        // gap
//               setOpenNote(o => o ? { ...o, path: to.trim() } : o)  // act
//
//   deleteNote  const n = openNoteRef.current                        // observe
//               await window.hqConfirm(`Delete "${n.path}"? …`)      // gap
//               await CafresoHQClient.vaultDelete(n.path)            // gap
//               setOpenNote(null)                                    // act
//
//   openByPath  await flushBeforeLeave()      // observes: nothing to lose
//               text = await CafresoHQClient.vaultRead(path)         // gap
//               setOpenNote({ path, content: text, dirty: false })   // act
//
// All three writes are unconditional. `moveByDrag` — thirty lines above
// renameNote, same server call, same buffer — re-derives on the far side
// (`const o0 = openNoteRef.current; if (o0 && inside(o0.path)) …`), which is
// what says the shape is this file's own and not an invention.
//
// The buffer changes underneath a modal for two ordinary reasons:
//
//   * The graph POPOUT (`?popout=graph`, app.jsx GraphPopout) is a SEPARATE
//     WINDOW. Clicking a node there posts `{type:'open-note'}` on
//     BroadcastChannel('cafresohq-graph'); the main window answers with
//     goTo('vault') + a `cafresohq:openNote` CustomEvent, which vault.jsx
//     listens for and hands straight to openByPath. The main window's modal
//     `.backdrop` (ui/feedback.jsx) covers the main window and nothing else.
//   * A second tree click during a slow `vaultRead` — no modal involved at
//     all, and the boss typing into the buffer that landed first.
//
// This harness lifts the REAL renameNote, deleteNote, openByPath, saveNote and
// flushBeforeLeave out of the committed views/vault.jsx (brace-balanced
// extraction, no re-implementation of anything under test) and drives them
// against a modelled buffer + an in-memory Library.
//
// Usage: node harness_vault_note_race.mjs <repo-root> [scenario]
// Prints one JSON object per line, one per scenario run.

import fs from 'node:fs';
import path from 'node:path';

const root = process.argv[2];
if (!root) {
  console.error('usage: harness_vault_note_race.mjs <repo-root> [scenario]');
  process.exit(2);
}
const vaultSrc = fs.readFileSync(path.join(root, 'views', 'vault.jsx'), 'utf8');

function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^[ \t]*\/\/.*$/gm, '');
}
function extractBalanced(source, marker) {
  const start = source.indexOf(marker);
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

const bare = stripComments(vaultSrc);
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

/* ── the real doors ──────────────────────────────────────────────────── */
const flushBody      = extractBalanced(bare, 'const flushBeforeLeave = async () =>');
const openByPathBody = extractBalanced(bare, 'const openByPath = async (path) =>');
const saveNoteBody   = extractBalanced(bare, 'const saveNote = async (opts) =>');
const renameBody     = extractBalanced(bare, 'const renameNote = async () =>');
const deleteBody     = extractBalanced(bare, 'const deleteNote = async () =>');
const moveByDragBody = extractBalanced(bare, 'const moveByDrag = async (src, destFolder) =>');

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

/* ── the world ───────────────────────────────────────────────────────── */
function makeWorld(opts = {}) {
  const w = {
    // the Library on disk
    disk: new Map(opts.disk || []),
    // the editor buffer, modelled the way the file does it: `openNoteRef.current
    // = openNote` runs on every render, so the ref is the buffer. Modelling the
    // ref as immediately current is the CONSERVATIVE choice — React's own
    // batching would make the reads staler, not fresher.
    openNote: opts.openNote || null,
    files: [],
    said: [],
    snags: [],
    saveState: '',
    busy: false,
    err: null,
    log: [],
    // openByPath's read latency, per path
    readDelay: opts.readDelay || {},
  };
  w.files = [...w.disk.keys()].map(p => ({ path: p, mtime: 1, size: (w.disk.get(p) || '').length }));
  return w;
}

function buildRoom(w) {
  const openNoteRef = { current: w.openNote };
  const setOpenNote = (v) => {
    const next = typeof v === 'function' ? v(openNoteRef.current) : v;
    openNoteRef.current = next;
    w.openNote = next;
    w.log.push('setOpenNote:' + (next ? next.path : 'null'));
  };
  const lastLinkSigRef = { current: {} };
  const saveNoteRef = { current: null };
  const openSeqRef = { current: 0 };   // only read by the FIXED source

  const CafresoHQClient = {
    async vaultRead(p) {
      const d = w.readDelay[p];
      if (d) await sleep(d);
      if (!w.disk.has(p)) throw new Error('no such note: ' + p);
      return w.disk.get(p);
    },
    async vaultWrite(p, content) {
      await sleep(1);
      w.disk.set(p, content);
      w.log.push('vaultWrite:' + p);
    },
    async vaultRename(src, dst) {
      await sleep(1);
      if (!w.disk.has(src)) throw new Error('no such note: ' + src);
      w.disk.set(dst, w.disk.get(src));
      w.disk.delete(src);
      w.log.push('vaultRename:' + src + '->' + dst);
      return { linksRewritten: 0, filesTouched: 0, moved: 1 };
    },
    async vaultDelete(p) {
      await sleep(1);
      w.disk.delete(p);
      w.log.push('vaultDelete:' + p);
      return { ok: true };
    },
    async vaultList() { return [...w.disk.keys()].map(p => ({ path: p, mtime: 1, size: 0 })); },
  };

  const scope = {
    openNoteRef, setOpenNote, saveNoteRef, lastLinkSigRef, openSeqRef,
    CafresoHQClient,
    _bridge: null,
    _pathToId: { current: {} },
    _isMobileV: false,
    setVaultTab: () => {},
    get files() { return w.files; },
    setFiles: (f) => { w.files = f; },
    setBusy: (b) => { w.busy = b; },
    setErr: (e) => { w.err = e; },
    setSaveState: (s) => { w.saveState = s; w.log.push('saveState:' + s); },
    setPreview: () => {},
    setExpanded: () => {},
    expanded: new Set(),
    say: (t, tone) => { w.said.push({ t, tone: tone || 'info' }); },
    snag: (t, e) => { w.snags.push(t + ' :: ' + (e && e.message)); },
    sayStranded: () => {},
    refresh: async () => { w.files = [...w.disk.keys()].map(p => ({ path: p, mtime: 1, size: 0 })); },
    refreshGraph: () => {},
    officeCause: (m) => String(m || ''),
    _nothingToPreview: () => false,
    _hiddenPart: () => null,
    _hiddenMsg: (h) => 'hidden: ' + h,
    _wikiResolvePath: () => null,
    uploadReceipt: () => null,
    _adaptBridgeFiles: (x) => x,
    window: globalThis.window,
    document: { hidden: false },
  };

  const mk = (body, args = []) =>
    new AsyncFunction(...Object.keys(scope), ...args,
      'return (async function(){' + body + '}).apply(this, arguments)');
  // Bind each door with the same scope object, in dependency order.
  const names = Object.keys(scope);
  const vals = () => names.map(n => scope[n]);

  scope.flushBeforeLeave = async () =>
    new AsyncFunction(...names, flushBody).apply(null, vals());
  names.push('flushBeforeLeave');

  scope.openByPath = async (p) =>
    new AsyncFunction(...names, 'path', openByPathBody).apply(null, [...vals(), p]);
  names.push('openByPath');

  scope.saveNote = async (o) =>
    new AsyncFunction(...names, 'opts', saveNoteBody).apply(null, [...vals(), o]);
  names.push('saveNote');
  saveNoteRef.current = scope.saveNote;

  scope.renameNote = async () =>
    new AsyncFunction(...names, renameBody).apply(null, vals());
  names.push('renameNote');

  scope.deleteNote = async () =>
    new AsyncFunction(...names, deleteBody).apply(null, vals());
  names.push('deleteNote');

  scope.moveByDrag = async (src, dest) =>
    new AsyncFunction(...names, 'src', 'destFolder', moveByDragBody)
      .apply(null, [...vals(), src, dest]);

  return scope;
}

/* The graph POPOUT clicking a node: app.jsx's BroadcastChannel handler does
   goTo('vault') then, 80ms later, dispatches cafresohq:openNote — which
   vault.jsx's listener hands straight to openByPath. Nothing about the main
   window's modal backdrop is in that path. */
function popoutOpens(room, p) { return room.openByPath(p); }

/* ── scenarios ───────────────────────────────────────────────────────── */
const scenarios = {};

scenarios['rename-dialog-outlives-the-note'] = async () => {
  const w = makeWorld({
    disk: [['Research/quarterly.md', 'QUARTERLY BODY'], ['Inbox/idea.md', 'IDEA BODY']],
    openNote: { path: 'Research/quarterly.md', id: null, content: 'QUARTERLY BODY', dirty: false },
  });
  const room = buildRoom(w);
  let swapped = false;
  globalThis.window.hqPrompt = async () => {
    // The boss is reading the dialog. In the popout window — a separate
    // browser window, untouched by this window's modal backdrop — they click
    // the Inbox/idea node.
    await popoutOpens(room, 'Inbox/idea.md');
    swapped = w.openNote && w.openNote.path === 'Inbox/idea.md';
    return 'Archive/2026-quarterly.md';
  };
  await room.renameNote();

  const bufAfter = w.openNote;
  // The boss types one word into what the editor is showing, and the 2.5s
  // quiet autosave files it.
  room.setOpenNote({ ...bufAfter, content: bufAfter.content + ' EDITED', dirty: true });
  await room.saveNote({ quiet: true });

  return {
    scenario: 'rename-dialog-outlives-the-note',
    dialogNamed: 'Research/quarterly.md',
    bufferSwappedDuringDialog: swapped,
    renamedOnDisk: !w.disk.has('Research/quarterly.md') && w.disk.has('Archive/2026-quarterly.md'),
    bufferPathAfter: bufAfter && bufAfter.path,
    bufferContentAfter: bufAfter && bufAfter.content,
    // the whole point: what is sitting at the renamed path once the autosave lands
    renamedNoteBody: w.disk.get('Archive/2026-quarterly.md'),
    quarterlyBodySurvivesSomewhere:
      [...w.disk.values()].some(v => String(v).startsWith('QUARTERLY BODY')),
    ideaStillAtItsOwnPath: w.disk.get('Inbox/idea.md'),
    displacementReported: w.said.map(s => s.t),
  };
};

scenarios['rename-unchanged-buffer'] = async () => {
  const w = makeWorld({
    disk: [['Research/quarterly.md', 'QUARTERLY BODY']],
    openNote: { path: 'Research/quarterly.md', id: null, content: 'QUARTERLY BODY', dirty: false },
  });
  const room = buildRoom(w);
  globalThis.window.hqPrompt = async () => 'Archive/2026-quarterly.md';
  await room.renameNote();
  return {
    scenario: 'rename-unchanged-buffer',
    renamedOnDisk: w.disk.has('Archive/2026-quarterly.md'),
    bufferPathAfter: w.openNote && w.openNote.path,
    bufferFollowedTheRename: !!(w.openNote && w.openNote.path === 'Archive/2026-quarterly.md'),
    said: w.said.map(s => s.t),
  };
};

scenarios['rename-declined'] = async () => {
  const w = makeWorld({
    disk: [['Research/quarterly.md', 'QUARTERLY BODY']],
    openNote: { path: 'Research/quarterly.md', id: null, content: 'QUARTERLY BODY', dirty: false },
  });
  const room = buildRoom(w);
  globalThis.window.hqPrompt = async () => null;
  await room.renameNote();
  return {
    scenario: 'rename-declined',
    stillAtOldPath: w.disk.has('Research/quarterly.md'),
    bufferPathAfter: w.openNote && w.openNote.path,
    wrote: w.log.filter(l => l.startsWith('vault')),
  };
};

scenarios['delete-dialog-outlives-the-note'] = async () => {
  const w = makeWorld({
    disk: [['Research/quarterly.md', 'QUARTERLY BODY'], ['Inbox/idea.md', 'IDEA BODY']],
    openNote: { path: 'Research/quarterly.md', id: null, content: 'QUARTERLY BODY', dirty: false },
  });
  const room = buildRoom(w);
  let swapped = false;
  globalThis.window.hqConfirm = async () => {
    await popoutOpens(room, 'Inbox/idea.md');
    // and the boss types into the note the popout just put in front of them
    room.setOpenNote({ ...w.openNote, content: 'IDEA BODY + NEW PARAGRAPH', dirty: true });
    swapped = w.openNote && w.openNote.path === 'Inbox/idea.md';
    return true;
  };
  await room.deleteNote();
  return {
    scenario: 'delete-dialog-outlives-the-note',
    dialogNamed: 'Research/quarterly.md',
    bufferSwappedDuringDialog: swapped,
    quarterlyDeleted: !w.disk.has('Research/quarterly.md'),
    // the buffer the boss was typing into, after the delete
    bufferAfter: w.openNote ? { path: w.openNote.path, dirty: w.openNote.dirty } : null,
    typedTextStillInBuffer: !!(w.openNote && String(w.openNote.content || '').includes('NEW PARAGRAPH')),
    typedTextOnDisk: String(w.disk.get('Inbox/idea.md') || '').includes('NEW PARAGRAPH'),
    saveStateAfter: w.saveState,
    said: w.said.map(s => s.t),
  };
};

scenarios['delete-unchanged-buffer'] = async () => {
  const w = makeWorld({
    disk: [['Research/quarterly.md', 'QUARTERLY BODY']],
    openNote: { path: 'Research/quarterly.md', id: null, content: 'QUARTERLY BODY', dirty: false },
  });
  const room = buildRoom(w);
  globalThis.window.hqConfirm = async () => true;
  await room.deleteNote();
  return {
    scenario: 'delete-unchanged-buffer',
    deleted: !w.disk.has('Research/quarterly.md'),
    editorClosed: w.openNote === null,
    said: w.said.map(s => s.t),
  };
};

scenarios['delete-declined'] = async () => {
  const w = makeWorld({
    disk: [['Research/quarterly.md', 'QUARTERLY BODY']],
    openNote: { path: 'Research/quarterly.md', id: null, content: 'QUARTERLY BODY', dirty: false },
  });
  const room = buildRoom(w);
  globalThis.window.hqConfirm = async () => false;
  await room.deleteNote();
  return {
    scenario: 'delete-declined',
    stillOnDisk: w.disk.has('Research/quarterly.md'),
    editorStillOpen: !!w.openNote,
    wrote: w.log.filter(l => l.startsWith('vault')),
  };
};

// Two tree clicks in a slow Library — no modal anywhere in this one.
scenarios['the-slow-read-lands-last'] = async () => {
  const w = makeWorld({
    disk: [['Research/slow.md', 'SLOW BODY'], ['Inbox/fast.md', 'FAST BODY']],
    openNote: null,
    readDelay: { 'Research/slow.md': 60, 'Inbox/fast.md': 5 },
  });
  const room = buildRoom(w);
  const a = room.openByPath('Research/slow.md');
  await sleep(2);
  const b = room.openByPath('Inbox/fast.md');
  await b;
  const landedFirst = w.openNote && w.openNote.path;
  // the boss starts typing into what is in front of them
  room.setOpenNote({ ...w.openNote, content: 'FAST BODY + TYPED', dirty: true });
  await a;
  return {
    scenario: 'the-slow-read-lands-last',
    lastClicked: 'Inbox/fast.md',
    landedFirst,
    bufferAfterBothLanded: w.openNote && w.openNote.path,
    typedTextSurvived: !!(w.openNote && String(w.openNote.content || '').includes('TYPED')),
    typedTextOnDisk: String(w.disk.get('Inbox/fast.md') || '').includes('TYPED'),
    bufferDirtyAfter: !!(w.openNote && w.openNote.dirty),
  };
};

// The boss types into the buffer WHILE the note they clicked is being read.
// flushBeforeLeave already answered "nothing to lose" before the read began.
scenarios['typed-into-the-buffer-during-the-read'] = async () => {
  const w = makeWorld({
    disk: [['Research/slow.md', 'SLOW BODY'], ['Inbox/here.md', 'HERE BODY']],
    openNote: { path: 'Inbox/here.md', id: null, content: 'HERE BODY', dirty: false },
    readDelay: { 'Research/slow.md': 60 },
  });
  const room = buildRoom(w);
  const p = room.openByPath('Research/slow.md');
  await sleep(10);
  room.setOpenNote({ ...w.openNote, content: 'HERE BODY + TYPED', dirty: true });
  await p;
  return {
    scenario: 'typed-into-the-buffer-during-the-read',
    bufferAfter: w.openNote && w.openNote.path,
    typedTextSurvived: !!(w.openNote && String(w.openNote.content || '').includes('TYPED')),
    typedTextOnDisk: String(w.disk.get('Inbox/here.md') || '').includes('TYPED'),
    said: w.said.map(s => s.t),
  };
};

// Ordinary single open, nothing racing it — the door must still work.
scenarios['a-quiet-open'] = async () => {
  const w = makeWorld({
    disk: [['Inbox/idea.md', 'IDEA BODY']],
    openNote: null,
  });
  const room = buildRoom(w);
  await room.openByPath('Inbox/idea.md');
  return {
    scenario: 'a-quiet-open',
    bufferPath: w.openNote && w.openNote.path,
    bufferContent: w.openNote && w.openNote.content,
    busyCleared: w.busy === false,
    snags: w.snags,
  };
};

// The pattern this fix copies, driven so the entry's claim about it is a
// measurement too: moveByDrag re-derives the buffer on the far side.
scenarios['movebydrag-already-re-derives'] = async () => {
  const w = makeWorld({
    disk: [['Research/quarterly.md', 'QUARTERLY BODY'], ['Inbox/idea.md', 'IDEA BODY']],
    openNote: { path: 'Research/quarterly.md', id: null, content: 'QUARTERLY BODY', dirty: false },
  });
  const room = buildRoom(w);
  const orig = room.CafresoHQClient.vaultRename.bind(room.CafresoHQClient);
  room.CafresoHQClient.vaultRename = async (s, d) => {
    const r = await orig(s, d);
    await popoutOpens(room, 'Inbox/idea.md');   // buffer swaps mid-flight
    return r;
  };
  await room.moveByDrag('Research/quarterly.md', 'Archive');
  return {
    scenario: 'movebydrag-already-re-derives',
    renamedOnDisk: w.disk.has('Archive/quarterly.md'),
    bufferPathAfter: w.openNote && w.openNote.path,
    bufferNotRetargeted: !!(w.openNote && w.openNote.path === 'Inbox/idea.md'),
  };
};

/* ── run ─────────────────────────────────────────────────────────────── */
globalThis.window = globalThis.window || {};
globalThis.window.CafresoHQGraph = null;
globalThis.document = { hidden: false };

const only = process.argv[3];
const names = only ? [only] : Object.keys(scenarios);
let bad = 0;
for (const n of names) {
  if (!scenarios[n]) { console.error('no such scenario: ' + n); process.exit(2); }
  try {
    console.log(JSON.stringify(await scenarios[n]()));
  } catch (e) {
    bad++;
    console.log(JSON.stringify({ scenario: n, harnessError: String(e && e.stack || e) }));
  }
}
process.exit(bad ? 1 : 0);
