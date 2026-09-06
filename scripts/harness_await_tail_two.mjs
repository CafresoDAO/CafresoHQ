#!/usr/bin/env node
// #414 — the tail of the stale-observation sweep (#394 / #398 / #400 / #404 /
// #409): an observation made BEFORE an `await`, acted on AFTER it, when the
// observed thing can change during the wait.
//
// `#409` carried the class through views/projects.jsx's WorkspaceView and left
// THREE doors named but not measured. This harness drives all three, by
// brace-balanced extraction of the REAL bodies out of the committed sources.
// Nothing under test is re-implemented.
//
//   1. views/projects.jsx  ProjectsView.readFile   — Classic's reading door.
//        (no ref, no sequence number, and no discard check at ALL)
//   2. views/graph.jsx     CafresoHQGraph.refresh  — the one canvas, and the
//        load effect that shares it.
//   3. views/terminal.jsx  saveKey / clearKey      — the key field, which stays
//        live through its own round trip.
//
// CREDENTIAL SAFETY (this harness exists under the constraint `#409` declined
// to work under): nothing here reads a credential store, an environment
// variable, a keychain or a file. `setAgentKey` is a stub that records its
// arguments in memory. Every value used is an obvious fake of the form
// `sk-FAKE-…`. The doors under test never route the field anywhere but into
// that stub, which is itself part of what is measured below.
//
// Usage: node harness_await_tail_two.mjs <repo-root> [scenario]
// Prints one JSON object per line, one per scenario run.

import fs from 'node:fs';
import path from 'node:path';

const root = process.argv[2];
if (!root) {
  console.error('usage: harness_await_tail_two.mjs <repo-root> [scenario]');
  process.exit(2);
}

function stripComments(s) {
  return s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^[ \t]*\/\/.*$/gm, '');
}
function balancedFrom(source, braceStart) {
  let depth = 0;
  for (let k = braceStart; k < source.length; k++) {
    const c = source[k];
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) return source.slice(braceStart + 1, k); }
  }
  throw new Error('unbalanced braces at ' + braceStart);
}
function extractBalanced(source, marker, nth) {
  let start = -1;
  for (let n = 0; n <= (nth || 0); n++) start = source.indexOf(marker, start + 1);
  if (start < 0) throw new Error('marker not found: ' + marker);
  return balancedFrom(source, source.indexOf('{', start + marker.length - 1));
}
/* An effect body identified by its DEPENDENCY LIST rather than by anything in
   the body — so the same extraction works against the fixed source and against
   a reverted one, which is what the fire test needs. */
function extractEffectByDeps(source, depsTail) {
  const end = source.indexOf(depsTail);
  if (end < 0) throw new Error('deps not found: ' + depsTail);
  const open = source.lastIndexOf('React.useEffect(() => {', end);
  if (open < 0) throw new Error('no useEffect before ' + depsTail);
  return balancedFrom(source, source.indexOf('{', open + 'React.useEffect(() => '.length - 1));
}

const projectsSrc = stripComments(fs.readFileSync(path.join(root, 'views', 'projects.jsx'), 'utf8'));
const graphSrc    = stripComments(fs.readFileSync(path.join(root, 'views', 'graph.jsx'), 'utf8'));
const termSrc     = stripComments(fs.readFileSync(path.join(root, 'views', 'terminal.jsx'), 'utf8'));
const settingsSrc = stripComments(fs.readFileSync(path.join(root, 'modals', 'settings.jsx'), 'utf8'));

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

/* ── 1. views/projects.jsx — Classic (ProjectsView) ───────────────────────── */

const classicReadFileBody = extractBalanced(projectsSrc, 'const readFile = async (path) =>');
const classicSaveFileBody = extractBalanced(projectsSrc, 'const saveFile = async (force) =>');

function makeClassicWorld(opts = {}) {
  return {
    disk: new Map(opts.disk || []),
    openFile: opts.openFile || null,
    said: [], err: null, conflict: false, busy: false, previewMode: false,
    asked: [], confirmAnswer: opts.confirmAnswer !== false,
    readDelay: opts.readDelay || {}, log: [],
  };
}

function buildClassicRoom(w) {
  /* ProjectsView's buffer. `openFileRef.current = openFile` runs from an
     effect on every render, so modelling the ref as immediately current is the
     CONSERVATIVE choice — React's batching makes reads staler, not fresher,
     and every conclusion below is about the ref being STALE. */
  const openFileRef = { current: w.openFile };
  const setOpenFile = (v) => {
    const next = typeof v === 'function' ? v(openFileRef.current) : v;
    openFileRef.current = next;
    w.openFile = next;
    w.log.push('setOpenFile:' + (next ? next.path + (next.dirty ? '*' : '') : 'null'));
  };
  const openSeqRef = { current: 0 };    // only read by the FIXED source
  const saveFileRef = { current: null };  // only read by the FIXED source

  const CafresoHQClient = {
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
    async toolExec(name, p, args) {
      await sleep(1);
      if (name !== 'FILE_WRITE') throw new Error('unexpected tool ' + name);
      w.disk.set(p, args.body);
      w.log.push('FILE_WRITE:' + p);
      return { ok: true };
    },
  };

  const scope = {
    CafresoHQClient,
    setOpenFile, openFileRef, openSeqRef, saveFileRef,
    setErr: (e) => { w.err = e; },
    setBusy: (b) => { w.busy = b; },
    setConflict: (v) => { w.conflict = v; },
    setPreviewMode: (v) => { w.previewMode = v; },
    setTreeNonce: () => {},
    previewKind: (p) => (/\.(png|jpe?g|gif|webp)$/i.test(p) ? 'image' : /\.pdf$/i.test(p) ? 'pdf' : 'code'),
    baseName: (p) => String(p || '').split(/[/\\]/).pop(),
    toast: (k, m) => { w.said.push({ k, m }); },
    officeCause: (m) => String(m || ''),
    window: {
      async hqConfirm(msg) { w.asked.push(msg); await sleep(2); return w.confirmAnswer; },
      cafresohqToast: null,
    },
    openFile: null,   // rebound per call: Classic's doors read the RENDER value
  };

  const names = Object.keys(scope);
  const vals = () => names.map(n => scope[n]);
  const call = (body, argNames, args) => {
    // The freshest render snapshot React could ever have handed the closure.
    scope.openFile = openFileRef.current;
    return new AsyncFunction(...names, ...argNames, body).apply(null, [...vals(), ...args]);
  };

  scope.saveFile = (force) => call(classicSaveFileBody, ['force'], [force]);
  names.push('saveFile');
  saveFileRef.current = scope.saveFile;

  /* Verbatim copy of the ONLY way a keystroke reaches Classic's buffer — both
     IDEEditor onChange handlers in ProjectsView are this line:
       onChange={(v) => setOpenFile({ ...openFile, content: v, dirty: true })}
     Pinned as source text by the test that owns this harness. */
  const onEdit = (val) => { const o = openFileRef.current; setOpenFile({ ...o, content: val, dirty: true }); };

  return {
    w, openFileRef, onEdit,
    readFile: (p) => call(classicReadFileBody, ['path'], [p]),
    saveFile: scope.saveFile,
  };
}

/* ── 2. views/graph.jsx — the one canvas ──────────────────────────────────── */

const graphLoadEffectBody = extractEffectByDeps(graphSrc, '}, [source, scope, reloadTick]);');
const graphRefreshBody    = extractBalanced(graphSrc, 'refresh: async () =>');
const graphMountDataBody  = extractBalanced(graphSrc, 'const mountData = (g) =>');
const graphLoadDataBody   = extractBalanced(graphSrc, 'const loadData = async () =>');
const graphConceptDocsBody = extractBalanced(graphSrc, 'const loadConceptDocs = async () =>');

function makeGraphWorld(opts = {}) {
  return {
    // The library, as /vault/graph would report it right now.
    graph: opts.graph || { nodes: [], edges: [] },
    conceptDocs: opts.conceptDocs || [],
    graphDelay: opts.graphDelay || 0,
    conceptDelay: opts.conceptDelay || 0,
    mounts: [],          // every engine actually put on the canvas, in order
    destroyed: [],
    loadError: null, loading: false,
    label: opts.label || (() => 'g'),
  };
}

function buildGraphRoom(w, opts = {}) {
  const containerRef = { current: { id: 'canvas' } };
  const engineRef = { current: null };
  const rawRef = { current: { byId: {}, maxInlinks: 0, mtimeRange: null } };
  const mountSeqRef = { current: 0 };   // only read by the FIXED source
  const sourceRef = { current: opts.source || 'links' };
  const scopeRef = { current: opts.scope || '__all__' };

  const win = {};
  win.CafresoGraphEngine = {
    mount(el, data, o) {
      const eng = {
        _data: data, _dead: false,
        destroy() { this._dead = true; w.destroyed.push(this._tag); },
        on() {}, setFilter() {}, setActivePath() {}, setLocalMode() {},
        setColorMode() {}, setColorFor() {}, setEdgeMode() {}, resize() {},
        focusNode() {}, exportSnapshot() { return {}; },
      };
      eng._tag = w.label(data);
      w.mounts.push(eng._tag);
      return eng;
    },
  };
  win.CafresoCooccur = {
    build(docs) {
      return {
        nodes: docs.map(d => ({ id: 't:' + d.id, type: 'term' })),
        edges: [],
        _kind: 'concepts',
      };
    },
  };

  const CafresoHQClient = {
    async vaultGraph() {
      /* The shape the office answers with is decided when the request is MADE,
         not when it lands — which is the whole point: a rebuild carries the
         library as it was when somebody asked for it. Captured here, before
         the wait, so a slow answer is genuinely an OLD answer. */
      const at = w.graphAtRequest;
      let snap, boom = null;
      try { snap = at ? at() : JSON.parse(JSON.stringify(w.graph)); }
      catch (e) { boom = e; }
      const d = w.graphDelay;
      if (d) await sleep(d);
      if (boom) throw boom;
      return snap;
    },
    async vaultList() {
      if (w.conceptDelay) await sleep(w.conceptDelay);
      return w.conceptDocs.map(d => ({ path: d.id, title: d.title, mtime: 1 }));
    },
    async vaultRead(p) {
      const d = w.conceptDocs.find(x => x.id === p);
      return d ? d.text : '';
    },
  };

  const scope = {
    containerRef, engineRef, rawRef, mountSeqRef,
    sourceRef, scopeRef,
    filterRef: { current: '' },
    colorModeRef: { current: 'type' },
    localModeRef: { current: 'global' },
    activePathRef: { current: null },
    edgesHoverRef: { current: false },
    CafresoHQClient,
    window: win,
    isDark: false,
    colorFor: () => null,
    wireEngine: () => {},
    filterMatcher: () => null,
    titleFor: (p) => p,
    edgeColorForType: () => '#000',
    CONCEPT_NOTE_CAP: 50,
    officeCause: (m) => String(m || ''),
    setLoading: (v) => { w.loading = v; },
    setLoadError: (v) => { w.loadError = v; },
    setConceptMeta: () => {},
    /* mountData's real body calls buildData(g) — a pure reducer over the same
       object — and the canvas is what this harness is about, so buildData is
       stubbed to hand the engine the graph it was given. */
    buildData: (g) => ({ nodes: g.nodes, edges: g.edges, _kind: g._kind }),
  };

  const names = Object.keys(scope);
  const vals = () => names.map(n => scope[n]);

  scope.loadConceptDocs = async () => new AsyncFunction(...names, graphConceptDocsBody).apply(null, vals());
  names.push('loadConceptDocs');
  scope.loadData = async () => new AsyncFunction(...names, graphLoadDataBody).apply(null, vals());
  names.push('loadData');
  scope.mountData = (g) => new Function(...names, 'g', graphMountDataBody).apply(null, [...vals(), g]);
  names.push('mountData');

  const room = {
    w, win, sourceRef, scopeRef, containerRef, engineRef,
    // The load effect, lifted whole. Returns its own cleanup like React's does.
    runLoadEffect() {
      return new Function(...names, graphLoadEffectBody).apply(null, vals());
    },
    refresh: () => new AsyncFunction(...names, graphRefreshBody).apply(null, vals()),
  };
  return room;
}

/* ── 3. views/terminal.jsx — the key field ────────────────────────────────── */

const saveKeyBody  = extractBalanced(termSrc, 'const saveKey = async () =>');
const clearKeyBody = extractBalanced(termSrc, 'const clearKey = async () =>');

function buildKeyRoom(opts = {}) {
  const w = {
    // The stub credential store. Records arguments; touches nothing real.
    filed: [],
    stored: {},
    keyInput: opts.keyInput || '',
    keyPanel: true,
    writeDelay: opts.writeDelay || 30,
  };
  const keyInputRef = { current: w.keyInput };   // only read by the FIXED source
  const setKeyInput = (v) => {
    const next = typeof v === 'function' ? v(keyInputRef.current) : v;
    keyInputRef.current = next;
    w.keyInput = next;
  };
  const scope = {
    CafresoHQClient: {
      async setAgentKey(provider, value) {
        await sleep(w.writeDelay);
        w.filed.push({ provider, value });
        if (value) w.stored[provider] = true; else delete w.stored[provider];
        return { ok: true };
      },
    },
    provider: opts.provider || 'anthropic',
    keyInputRef,
    setKeyInput,
    setKeyPanel: (v) => { w.keyPanel = typeof v === 'function' ? v(w.keyPanel) : v; },
    setKeyStored: (v) => { w.stored = typeof v === 'function' ? v({ ...w.stored }) : v; },
    keyInput: '',   // rebound per call: the render value
  };
  const names = Object.keys(scope);
  const vals = () => names.map(n => scope[n]);
  const call = (body) => {
    scope.keyInput = keyInputRef.current;
    return new AsyncFunction(...names, body).apply(null, vals());
  };
  return {
    w,
    // The ONLY way a keystroke reaches the field, verbatim from the panel:
    //   onChange={e => setKeyInput(e.target.value)}
    type: (v) => setKeyInput(v),
    saveKey: () => call(saveKeyBody),
    clearKey: () => call(clearKeyBody),
  };
}

/* ── 4. modals/settings.jsx — the agent wallet card (MEASURED, NOT FIXED) ──
   `load()` re-seeds the DRAFT boxes (cap amount, cap window, salary amount,
   period, watermark) out of the canister, and every save calls it on the far
   side of its own write. Nothing freezes those boxes while that runs — `busy`
   reaches individual BUTTONS only (`disabled={busy === 'pay'}` etc.), never an
   `<input>` — so this is the views/projects.jsx keystroke, on a panel whose
   fields are amounts of real money. Driven here to make the EXPOSED verdict a
   measurement rather than a reading. */

const settingsLoadBody    = extractBalanced(settingsSrc, 'const load = async () =>');
const settingsSavePayBody = extractBalanced(settingsSrc, 'const savePay = async () =>');

function buildSettingsRoom(opts = {}) {
  const w = {
    // What the canister holds. The boxes are seeded from it.
    salary: { agentId: 'a1', token: 'ICP', mode: 'salary', amount: '1000000', periodSecs: 86400, lowWatermark: '5000000' },
    policy: null,
    boxes: { capTok: 'ICP', capAmt: '0.1', capHrs: '24', payTok: 'ICP', payMode: 'salary', payAmt: '0.01', payHrs: '24', payWm: '0.05' },
    puts: [], msg: '', busy: '',
    putDelay: opts.putDelay || 20,
    listDelay: opts.listDelay || 20,
  };
  const set = (k) => (v) => { w.boxes[k] = v; };
  const scope = {
    agentId: 'a1',
    WALLET_TOKEN_DECIMALS: { ICP: 8 },
    fromBaseUnits: (v, d) => String(Number(v) / Math.pow(10, d)),
    toBaseUnits: (v, d) => String(Math.round(Number(v) * Math.pow(10, d))),
    secsToHoursText: (s) => String(s / 3600),
    hoursToSecs: (h) => (String(h).trim() === '' ? null : Math.round(Number(h) * 3600)),
    cleanCause: (m) => String(m || ''),
    setPolicy: (p) => { w.policy = p; },
    setSal: (s) => { w.salary_shown = s; },
    setCapTok: set('capTok'), setCapAmt: set('capAmt'), setCapHrs: set('capHrs'),
    setPayTok: set('payTok'), setPayMode: set('payMode'), setPayAmt: set('payAmt'),
    setPayHrs: set('payHrs'), setPayWm: set('payWm'),
    setMsg: (m) => { w.msg = m; },
    setBusy: (b) => { w.busy = b; },
    chain: () => ({
      wallet: { async policy() { await sleep(2); return w.policy; } },
      payroll: {
        async list() { await sleep(w.listDelay); return { salaries: [w.salary] }; },
        async put(rec) { await sleep(w.putDelay); w.puts.push(rec); w.salary = { agentId: rec.agentId, token: rec.token, mode: rec.mode, amount: rec.amount, periodSecs: rec.periodSecs, lowWatermark: rec.lowWatermark }; return { ok: 1 }; },
      },
    }),
    // the render values the handler closes over
    payHrs: '', payTok: '', payAmt: '', payMode: '', payWm: '',
  };
  const names = Object.keys(scope);
  const vals = () => names.map(n => scope[n]);
  scope.load = async () => new AsyncFunction(...names, settingsLoadBody).apply(null, vals());
  names.push('load');
  const callSavePay = () => {
    // React hands the handler the box values as of the render it was made in.
    for (const k of ['payHrs', 'payTok', 'payAmt', 'payMode', 'payWm']) scope[k] = w.boxes[k];
    return new AsyncFunction(...names, settingsSavePayBody).apply(null, vals());
  };
  return { w, load: scope.load, savePay: callSavePay, type: (k, v) => { w.boxes[k] = v; } };
}

/* ── scenarios ─────────────────────────────────────────────────────────────── */
const scenarios = {};

// ---- Classic readFile ------------------------------------------------------

// C1. Two tree clicks in a slow project. Nothing disables the tree during a
//     read — `busy` reaches the two Save buttons and nothing else.
scenarios['classic-two-clicks-last-read-to-land-wins'] = async () => {
  const w = makeClassicWorld({
    disk: [['/p/slow.js', 'SLOW BODY'], ['/p/fast.js', 'FAST BODY'], ['/p/open.md', 'OPEN']],
    openFile: { path: '/p/open.md', content: 'OPEN', mtime: 100, hash: 'h:OPEN', dirty: false },
    readDelay: { '/p/slow.js': 80, '/p/fast.js': 5 },
  });
  const room = buildClassicRoom(w);
  const a = room.readFile('/p/slow.js');
  await sleep(5);
  const b = room.readFile('/p/fast.js');   // the boss changes their mind
  await Promise.all([a, b]);
  return {
    scenario: 'classic-two-clicks-last-read-to-land-wins',
    lastClicked: '/p/fast.js',
    bufferAfterBothLanded: w.openFile && w.openFile.path,
    endedOnTheFileTheyClickedLast: !!(w.openFile && w.openFile.path === '/p/fast.js'),
    busyCleared: w.busy === false,
  };
};

// C2. The boss types while the file they asked for is being read.
scenarios['classic-typing-during-the-read'] = async () => {
  const w = makeClassicWorld({
    disk: [['/p/notes.md', 'NOTES BODY'], ['/p/index.js', 'INDEX BODY']],
    openFile: { path: '/p/notes.md', content: 'NOTES BODY', mtime: 100, hash: 'h:NOTES BODY', dirty: false },
    readDelay: { '/p/index.js': 60 },
  });
  const room = buildClassicRoom(w);
  const p = room.readFile('/p/index.js');
  await sleep(10);
  room.onEdit('NOTES BODY\n\nMY PARAGRAPH');   // clean buffer: nothing was asked
  await p;
  const buf = w.openFile;
  return {
    scenario: 'classic-typing-during-the-read',
    bufferPathAfter: buf && buf.path,
    typedTextStillInBuffer: !!(buf && String(buf.content).includes('MY PARAGRAPH')),
    typedTextOnDisk: String(w.disk.get('/p/notes.md') || '').includes('MY PARAGRAPH'),
    said: w.said.map(s => s.m),
    endedOnTheFileTheyAskedFor: !!(buf && buf.path === '/p/index.js'),
  };
};

// C3. A DIRTY buffer and a click on another file. WorkspaceView asks; Classic
//     never did — a missing observation, not an expired one.
scenarios['classic-dirty-buffer-never-asked'] = async () => {
  const w = makeClassicWorld({
    disk: [['/p/notes.md', 'NOTES BODY'], ['/p/index.js', 'INDEX BODY']],
    openFile: { path: '/p/notes.md', content: 'NOTES BODY\n\nUNSAVED', mtime: 100, hash: 'h:NOTES BODY', dirty: true },
    readDelay: { '/p/index.js': 20 },
  });
  const room = buildClassicRoom(w);
  await room.readFile('/p/index.js');
  return {
    scenario: 'classic-dirty-buffer-never-asked',
    askedBeforeDroppingTheEdits: w.asked.length > 0,
    asked: w.asked,
    unsavedTextOnDisk: String(w.disk.get('/p/notes.md') || '').includes('UNSAVED'),
    bufferAfter: w.openFile && w.openFile.path,
  };
};

// C4. The same click, with the boss answering CANCEL. Post-fix only: pre-fix
//     there is no dialog to answer, which is what C3 measures.
scenarios['classic-cancelled-discard-stays-put'] = async () => {
  const w = makeClassicWorld({
    disk: [['/p/notes.md', 'NOTES BODY'], ['/p/index.js', 'INDEX BODY']],
    openFile: { path: '/p/notes.md', content: 'NOTES BODY\n\nUNSAVED', mtime: 100, hash: 'h:NOTES BODY', dirty: true },
    readDelay: { '/p/index.js': 20 },
    confirmAnswer: false,
  });
  const room = buildClassicRoom(w);
  await room.readFile('/p/index.js');
  return {
    scenario: 'classic-cancelled-discard-stays-put',
    bufferAfter: w.openFile && w.openFile.path,
    stayedWhereTheySaid: !!(w.openFile && w.openFile.path === '/p/notes.md'),
    unsavedTextStillInBuffer: !!(w.openFile && String(w.openFile.content).includes('UNSAVED')),
  };
};

// C5. The boss said DISCARD. The far side must not quietly file what they
//     just threw away. (A negative that must hold on BOTH sides of the fix.)
scenarios['classic-accepted-discard-is-honoured'] = async () => {
  const w = makeClassicWorld({
    disk: [['/p/notes.md', 'NOTES BODY'], ['/p/index.js', 'INDEX BODY']],
    openFile: { path: '/p/notes.md', content: 'NOTES BODY\n\nTHROWN AWAY', mtime: 100, hash: 'h:NOTES BODY', dirty: true },
    readDelay: { '/p/index.js': 20 },
    confirmAnswer: true,
  });
  const room = buildClassicRoom(w);
  await room.readFile('/p/index.js');
  return {
    scenario: 'classic-accepted-discard-is-honoured',
    discardWasHonoured: !String(w.disk.get('/p/notes.md') || '').includes('THROWN AWAY'),
    bufferAfter: w.openFile && w.openFile.path,
  };
};

// C6. A superseded read that FAILED painting its refusal over the file that
//     did open.
scenarios['classic-superseded-failure-blots-the-open-file'] = async () => {
  const w = makeClassicWorld({
    disk: [['/p/fast.js', 'FAST BODY']],
    openFile: null,
    readDelay: { '/p/gone.js': 80, '/p/fast.js': 5 },
  });
  const room = buildClassicRoom(w);
  const a = room.readFile('/p/gone.js');   // deleted under them
  await sleep(5);
  const b = room.readFile('/p/fast.js');
  await Promise.all([a, b]);
  return {
    scenario: 'classic-superseded-failure-blots-the-open-file',
    bufferAfter: w.openFile && w.openFile.path,
    errShown: w.err,
    errAboutTheFileOnScreen: !w.err,
  };
};

// C7. An IMAGE clicked while a text read is in flight. `setPreviewMode` was
//     decided before the read and never revisited.
scenarios['classic-image-click-strands-the-text-file-in-preview'] = async () => {
  const w = makeClassicWorld({
    disk: [['/p/slow.md', 'SLOW BODY']],
    openFile: null,
    readDelay: { '/p/slow.md': 60 },
  });
  const room = buildClassicRoom(w);
  const a = room.readFile('/p/slow.md');
  await sleep(5);
  await room.readFile('/p/shot.png');   // binary: returns without any read
  await a;
  return {
    scenario: 'classic-image-click-strands-the-text-file-in-preview',
    bufferAfter: w.openFile && w.openFile.path,
    previewModeAfter: w.previewMode,
    // Post-fix the png is what is open AND what is previewed; pre-fix the .md
    // landed on top of it with previewMode still true.
    previewModeAgreesWithTheBuffer: !!(w.openFile && w.openFile.binary) === w.previewMode,
  };
};

// C8. `saveFile`'s own convention, driven so the claim above it is a
//     measurement too. Must hold on BOTH sides of the fix.
scenarios['classic-save-stamps-only-what-it-wrote'] = async () => {
  const w = makeClassicWorld({
    disk: [['/p/index.js', 'INDEX BODY']],
    openFile: { path: '/p/index.js', content: 'INDEX BODY ONE', mtime: 100, hash: 'h:INDEX BODY', dirty: true },
  });
  const room = buildClassicRoom(w);
  const p = room.saveFile();
  await sleep(1);
  room.onEdit('INDEX BODY ONE TWO');
  await p;
  return {
    scenario: 'classic-save-stamps-only-what-it-wrote',
    wroteToDisk: w.disk.get('/p/index.js'),
    bufferContentAfter: w.openFile && w.openFile.content,
    stillDirtyBecauseNewerKeystrokes: !!(w.openFile && w.openFile.dirty),
  };
};

// ---- graph refresh ---------------------------------------------------------

const noteGraph = (...paths) => ({
  nodes: paths.map(p => ({ id: p, type: 'note', inlinks: 0, mtime: 1 })),
  edges: paths.length > 1
    ? [{ source: paths[1], target: paths[0], type: 'link' }]
    : [],
});

// G1. Two note writes, two refreshes. The canvas ends on whichever `loadData`
//     LANDS last, which is not the last write.
scenarios['graph-two-refreshes-last-to-land-wins'] = async () => {
  const w = makeGraphWorld({ label: (d) => d.nodes.map(n => n.id).sort().join('+') });
  w.graph = noteGraph('/a.md');
  const room = buildGraphRoom(w);
  // The first mount, as the panel opens.
  w.graphDelay = 0;
  room.runLoadEffect();
  await sleep(5);

  // The boss writes note A (slow rebuild), then note B (fast rebuild).
  w.graphDelay = 70;
  w.graphAtRequest = () => JSON.parse(JSON.stringify(noteGraph('/a.md')));
  const r1 = room.refresh();
  await sleep(5);
  w.graphDelay = 5;
  w.graphAtRequest = () => JSON.parse(JSON.stringify(noteGraph('/a.md', '/b.md')));
  const r2 = room.refresh();
  await Promise.all([r1, r2]);

  const last = w.mounts[w.mounts.length - 1];
  const lg = room.win.CafresoHQGraph && room.win.CafresoHQGraph._lastGraph;
  /* Copy of views/vault.jsx:1408-1412 — the delete confirm counts inbound
     wikilinks out of `_lastGraph` to name what goes dead. A stale snapshot is
     not a picture here; it is the number in that sentence. */
  const inbound = lg ? [...new Set((lg.edges || [])
    .filter(e => String(e.target) === '/a.md' && /\.md$/i.test(String(e.source)))
    .map(e => String(e.source)))] : [];
  return {
    scenario: 'graph-two-refreshes-last-to-land-wins',
    mounts: w.mounts,
    mountedAfterBoth: last,
    showsTheNewestWrite: last === '/a.md+/b.md',
    deadLinksNamedByTheConfirm: inbound,
  };
};

// G2. A rebuild started under the OLD source landing on the NEW one.
scenarios['graph-refresh-lands-in-the-wrong-source'] = async () => {
  const w = makeGraphWorld({ label: (d) => (d._kind === 'concepts' ? 'concepts' : 'links') });
  w.graph = noteGraph('/a.md', '/b.md');
  w.conceptDocs = [{ id: '/a.md', title: 'A', text: 'alpha beta' }];
  const room = buildGraphRoom(w);
  room.runLoadEffect();
  await sleep(5);

  // A note write fires a refresh under source=links, and it is slow.
  w.graphDelay = 70;
  const r = room.refresh();
  await sleep(5);
  // The boss flips the picker to the concept map, which re-runs the effect.
  room.sourceRef.current = 'concepts';
  const cleanup = room.runLoadEffect();
  await sleep(20);
  const afterTheSwitch = w.mounts[w.mounts.length - 1];
  await r;
  if (cleanup) cleanup();
  return {
    scenario: 'graph-refresh-lands-in-the-wrong-source',
    mounts: w.mounts,
    mountedRightAfterTheSwitch: afterTheSwitch,
    sourceTheBossIsLookingAt: 'concepts',
    mountedSource: w.mounts[w.mounts.length - 1],
    canvasAgreesWithTheToolbar: w.mounts[w.mounts.length - 1] === 'concepts',
  };
};

// G3. The other direction: a refresh landing while the effect's own first load
//     is still out. The effect had `cancelled` for its own teardown and
//     nothing at all for this.
scenarios['graph-refresh-overtaken-by-a-slow-first-load'] = async () => {
  const w = makeGraphWorld({ label: (d) => d.nodes.map(n => n.id).sort().join('+') });
  const room = buildGraphRoom(w);
  // First mount, fast, so the API object exists.
  w.graph = noteGraph('/a.md');
  room.runLoadEffect();
  await sleep(5);

  // A slow effect re-run (the boss nudged the scope), and a note write whose
  // refresh is quick and carries the NEWER library.
  w.graphDelay = 70;
  w.graphAtRequest = () => JSON.parse(JSON.stringify(noteGraph('/a.md')));
  room.runLoadEffect();
  await sleep(5);
  w.graphDelay = 5;
  w.graphAtRequest = () => JSON.parse(JSON.stringify(noteGraph('/a.md', '/b.md')));
  await room.refresh();
  await sleep(90);
  return {
    scenario: 'graph-refresh-overtaken-by-a-slow-first-load',
    mounts: w.mounts,
    mountedAfterBoth: w.mounts[w.mounts.length - 1],
    newestWriteSurvived: w.mounts[w.mounts.length - 1] === '/a.md+/b.md',
  };
};

// G4. A refresh that FAILS after being superseded must not paint its card over
//     the map that did mount.
scenarios['graph-superseded-failure-raises-no-card'] = async () => {
  const w = makeGraphWorld({ label: (d) => d.nodes.map(n => n.id).sort().join('+') });
  w.graph = noteGraph('/a.md');
  const room = buildGraphRoom(w);
  room.runLoadEffect();
  await sleep(5);

  w.graphDelay = 60;
  w.graphAtRequest = () => { throw new Error('the office is not answering'); };
  const bad = room.refresh();
  await sleep(5);
  w.graphDelay = 2;
  w.graphAtRequest = null;
  w.graph = noteGraph('/a.md', '/b.md');
  await room.refresh();
  await bad;
  return {
    scenario: 'graph-superseded-failure-raises-no-card',
    mountedAfterBoth: w.mounts[w.mounts.length - 1],
    loadError: w.loadError,
    cardAboutTheMapOnScreen: !w.loadError,
  };
};

// G5. A refresh still in flight when the panel closes. The unmount effect does
//     `delete window.CafresoHQGraph`. (Negative: must hold on both sides — it
//     is caught pre-fix, so what changes is only whether it raises a card.)
scenarios['graph-refresh-outlives-the-panel'] = async () => {
  const w = makeGraphWorld({ label: (d) => d.nodes.map(n => n.id).sort().join('+') });
  w.graph = noteGraph('/a.md');
  const room = buildGraphRoom(w);
  room.runLoadEffect();
  await sleep(5);
  w.graphDelay = 40;
  const r = room.refresh();
  await sleep(5);
  delete room.win.CafresoHQGraph;      // the unmount effect
  room.containerRef.current = null;    // React drops the canvas node
  let threw = null;
  try { await r; } catch (e) { threw = String(e && e.message); }
  return {
    scenario: 'graph-refresh-outlives-the-panel',
    threw,
    didNotThrowPastItsOwnCatch: threw === null,
    mountedAfterTheClose: w.mounts.length,
  };
};

// ---- terminal saveKey / clearKey -------------------------------------------
// Obvious fakes only. Nothing here reads a real credential store.

// K1. The boss pastes a truncated key, hits SAVE, then corrects it while the
//     write is still out.
scenarios['key-typed-during-the-save-is-wiped'] = async () => {
  const room = buildKeyRoom({ keyInput: 'sk-FAKE-truncated', writeDelay: 40 });
  const p = room.saveKey();
  await sleep(5);
  room.type('sk-FAKE-the-whole-thing');   // the field is live; nothing disabled it
  await p;
  return {
    scenario: 'key-typed-during-the-save-is-wiped',
    filedProviders: room.w.filed.map(f => f.provider),
    filedCount: room.w.filed.length,
    // Never print a value. What matters is only whether the boss's newer
    // typing is still in the field they typed it into.
    typedAfterSaveSurvived: room.w.keyInput === 'sk-FAKE-the-whole-thing',
    panelStillOpen: room.w.keyPanel,
    fieldLeftEmpty: room.w.keyInput === '',
  };
};

// K2. Nothing typed during the round trip: the panel must still close and the
//     field must still clear. (Negative — must hold on BOTH sides.)
scenarios['key-plain-save-still-clears-and-closes'] = async () => {
  const room = buildKeyRoom({ keyInput: 'sk-FAKE-plain', writeDelay: 10 });
  await room.saveKey();
  return {
    scenario: 'key-plain-save-still-clears-and-closes',
    filedCount: room.w.filed.length,
    fieldCleared: room.w.keyInput === '',
    panelClosed: room.w.keyPanel === false,
    storedForProvider: room.w.stored.anthropic === true,
  };
};

// K3. CLEAR KEY, then the boss types the replacement while the delete is out.
scenarios['key-typed-during-the-clear-is-shut-away'] = async () => {
  const room = buildKeyRoom({ keyInput: '', writeDelay: 40 });
  room.w.stored.anthropic = true;
  const p = room.clearKey();
  await sleep(5);
  room.type('sk-FAKE-replacement');
  await p;
  const panelStillOpen = room.w.keyPanel;
  /* If the panel shut, the only way back in is the 🔓 button, whose onClick is
     verbatim `() => { setKeyPanel(p => !p); setKeyInput(''); }` — so the
     replacement is not merely hidden, it is gone the moment the boss reopens
     the panel to look for it. */
  if (!panelStillOpen) { room.w.keyPanel = true; room.type(''); }
  return {
    scenario: 'key-typed-during-the-clear-is-shut-away',
    panelStillOpen,
    replacementSurvivedGettingBackToIt: room.w.keyInput === 'sk-FAKE-replacement',
    storedFlagCleared: room.w.stored.anthropic !== true,
  };
};

// K4. A plain CLEAR KEY still closes the panel. (Negative — both sides.)
scenarios['key-plain-clear-still-closes'] = async () => {
  const room = buildKeyRoom({ keyInput: '', writeDelay: 10 });
  room.w.stored.anthropic = true;
  await room.clearKey();
  return {
    scenario: 'key-plain-clear-still-closes',
    panelClosed: room.w.keyPanel === false,
    storedFlagCleared: room.w.stored.anthropic !== true,
    filedEmptyString: room.w.filed.length === 1 && room.w.filed[0].value === '',
  };
};

// S1. modals/settings.jsx — a salary amount typed while the SAVE that
//     preceded it is still running its read-back. EXPOSED, not fixed.
scenarios['settings-typing-during-the-readback-is-wiped'] = async () => {
  const room = buildSettingsRoom({ putDelay: 20, listDelay: 40 });
  const p = room.savePay();
  await sleep(5);
  // The boss, looking at the row they just saved, corrects the amount. The
  // input is not disabled — `busy` reaches the buttons only.
  room.type('payAmt', '0.25');
  await p;
  return {
    scenario: 'settings-typing-during-the-readback-is-wiped',
    typedAmount: '0.25',
    amountBoxAfterTheReadback: room.w.boxes.payAmt,
    typedAmountSurvived: room.w.boxes.payAmt === '0.25',
    // and what it was replaced with is the value the canister already held
    replacedWithTheSavedValue: room.w.boxes.payAmt === '0.01',
    putsMade: room.w.puts.length,
  };
};

/* ── run ───────────────────────────────────────────────────────────────────── */
const only = process.argv[3];
const names = only ? [only] : Object.keys(scenarios);
for (const n of names) {
  if (!scenarios[n]) { console.error('no such scenario: ' + n); process.exit(2); }
  const out = await scenarios[n]();
  console.log(JSON.stringify(out));
}
