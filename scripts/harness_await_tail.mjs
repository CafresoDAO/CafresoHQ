#!/usr/bin/env node
// #400 — the diagnosed-but-unfixed tail of #398's sweep of the class #394
// opened: an observation made BEFORE an `await`, acted upon AFTER it, when the
// observed thing can change during the wait.
//
// #398 fixed two doors and named three more precisely. This harness drives all
// three of those, against the REAL source (marker-bounded / brace-balanced
// extraction of the committed files — no re-implementation of anything under
// test):
//
//   1. onDeleteTask's OTHER direction. `running` FALSE at observe time, the
//      boss answering the RESULT-GUARD confirm, and a chain step auto-starting
//      the card inside the gap:
//
//        const running = … agentAbortersRef.current.has(t.assignedTo);  // obs
//        } else if (t.result && !(await window.hqConfirm("… work will be
//                                 lost"))) return;                      // gap
//        …
//        if (running) abortAgentRun(t.assignedTo);   // still false → no abort
//
//      The card goes, the run lives, and a delivery is filed for work the boss
//      explicitly removed — which is verbatim the failure the abort's own
//      comment says was fixed.
//
//   2. isVaultReady (hq-runtime.jsx). A `clearVaultReadyCache()` landing
//      during an in-flight probe is undone by the probe writing the OLD
//      vault's answer back over the cleared cache; and the freshness stamp is
//      taken BEFORE the await.
//
//   3. onStopAll. #398 filed it visible-only ("the sweep it performs is
//      unconditional and correct"). True of every arm but one: the night-shift
//      arm sweeps by ITERATING a pre-dialog array, so a schedule that comes up
//      on the 15s poll's shoulder during the dialog is never DELETEd.
//
// Usage: node harness_await_tail.mjs <repo-root> [scenario]
// Prints one JSON object per line to stdout, one per scenario run.

import fs from 'node:fs';
import path from 'node:path';

const root = process.argv[2];
if (!root) {
  console.error('usage: harness_await_tail.mjs <repo-root> [scenario]');
  process.exit(2);
}
const appSrc = fs.readFileSync(path.join(root, 'app.jsx'), 'utf8');
const rtSrc = fs.readFileSync(path.join(root, 'hq-runtime.jsx'), 'utf8');
const worklogSrc = fs.readFileSync(path.join(root, 'app', 'worklog.jsx'), 'utf8');

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

const bare = stripComments(appSrc);
const bareRt = stripComments(rtSrc);
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

/* ── the real pieces ─────────────────────────────────────────────────── */
const onDeleteTaskBody = extractBalanced(bare, 'const onDeleteTask = async (id) =>');
const onStopAllBody = extractBalanced(bare, 'const onStopAll = async () =>');
const beginAgentRunBody = extractBalanced(appSrc, 'const beginAgentRun = (agentId) => {');
const endAgentRunBody = extractBalanced(appSrc, 'const endAgentRun = (agentId, controller) => {');
const abortAgentRunBody = extractBalanced(appSrc, 'const abortAgentRun = (agentId) => {');
const abortAllAgentRunsBody = extractBalanced(appSrc, 'const abortAllAgentRuns = () => {');
const applyStatusBody = extractBalanced(stripComments(worklogSrc), 'function applyStatus(task, status, now)');
const triggerChainStepBody = extractBalanced(bare,
  'const triggerChainStep = React.useCallback((nextTask, priorResult, fromAgent, fromRun) =>');

/* The REAL card-assign block out of onTaskDropOnAgent — the statements a
   chain step runs to put the folder on a desk. Bounded by its own two
   markers (the applyStatus write and the say() that closes the block); the
   claim itself is the REAL beginAgentRun, called right after, exactly as
   the handler calls it a few lines further down. Lifting the whole tail of
   onTaskDropOnAgent would drag in HQ.agentStream and half the runtime and
   would prove nothing more about the door under test, which is the ✕. */
const ASSIGN_HEAD = "? { ...applyStatus(t, 'doing'), assignedTo: agent.id, stalledNote: null,";
const assignHeadAt = bare.indexOf(ASSIGN_HEAD);
if (assignHeadAt < 0) throw new Error("onTaskDropOnAgent's assign block not found in app.jsx");
const assignStart = bare.lastIndexOf('setTasks(', assignHeadAt);
const SAY_TAIL = "say(`${agent.name} is on \"${task.title}\"`, 'DELEGATE');";
const sayAt = bare.indexOf(SAY_TAIL, assignHeadAt);
if (sayAt < 0) throw new Error("onTaskDropOnAgent's say() tail not found in app.jsx");
const assignBlock = bare.slice(assignStart, sayAt + SAY_TAIL.length);

/* ── the desk registry, real ─────────────────────────────────────────── */
function makeDesk() {
  const agentAbortersRef = { current: new Map() };
  const bossTurnRef = { current: null };
  const turnRunsRef = { current: new Set() };
  const stopEpochRef = { current: 0 };
  const turnEpochRef = { current: 0 };
  const deskWorkRef = { current: new Map() };
  const rawBegin = new Function('agentAbortersRef', 'bossTurnRef', 'turnRunsRef', 'AbortController',
    'agentId', beginAgentRunBody);
  const rawEnd = new Function('agentAbortersRef', 'turnRunsRef', 'deskWorkRef', 'agentId', 'controller',
    endAgentRunBody);
  const rawAbort = new Function('agentAbortersRef', 'agentId', abortAgentRunBody);
  const rawAbortAll = new Function('agentAbortersRef', 'turnRunsRef', 'stopEpochRef', 'turnEpochRef',
    abortAllAgentRunsBody);
  return {
    agentAbortersRef, bossTurnRef, turnRunsRef, stopEpochRef, turnEpochRef, deskWorkRef,
    beginAgentRun: (agentId) => rawBegin(agentAbortersRef, bossTurnRef, turnRunsRef, AbortController, agentId),
    endAgentRun: (agentId, controller) => rawEnd(agentAbortersRef, turnRunsRef, deskWorkRef, agentId, controller),
    abortAgentRun: (agentId) => rawAbort(agentAbortersRef, agentId),
    abortAllAgentRuns: () => rawAbortAll(agentAbortersRef, turnRunsRef, stopEpochRef, turnEpochRef),
  };
}
const applyStatus = new Function('task', 'status', 'now', applyStatusBody);

const DELETE_PARAMS = ['tasks', 'agents', 'agentAbortersRef', 'abortAgentRun',
  'setTasks', 'setApprovals', 'logActivity', 'say', 'window',
  'displaceDeskNote',
  // added by this hunt (#400): the live board and the live roster, which is
  // what the far side of the ask has to be re-derived against.
  'tasksRef', 'agentsRef'];

/* ═══ 1. the chain step that started the card the boss was deleting ═══ */
//
// Card B is a workflow successor sitting in `inbox` carrying the `result` of
// an earlier run — the field, and the only field, that raises the result-guard
// confirm. Card A is its predecessor, running. The boss clicks ✕ on B; while
// the dialog is open A finishes and its autoDispatch chain fires
// triggerChainStep → onTaskDropOnAgent({auto:true}), which never asks. B is
// assigned, set `doing`, and a run is claimed on Vera's desk. The boss says
// yes.
async function chainStartsDuringConfirm(name, { dialogMs = 400, chainAt = 120,
                                                confirm = true, chain = true } = {}) {
  const desk = makeDesk();
  const vera = { id: 'a_vera', name: 'Vera', role: 'analyst', status: 'idle' };
  const board = [{ id: 'tk_b', title: 'the follow-up memo', status: 'inbox',
                   assignedTo: null, result: 'a first pass from yesterday' }];
  const tasksRef = { current: board };
  const agentsRef = { current: [vera] };
  const activity = [], said = [], dialogs = [], aborted = [], deleted = [];

  const setTasks = (fn) => {
    const next = fn(tasksRef.current);
    const gone = tasksRef.current.filter(t => !next.some(n => n.id === t.id));
    deleted.push(...gone.map(t => t.id));
    tasksRef.current = next;
  };
  const logActivity = (row) => activity.push(row);
  const say = (msg) => said.push(msg);
  const win = {
    hqConfirm: async (msg) => {
      dialogs.push(msg);
      await new Promise(r => setTimeout(r, dialogMs));
      return confirm;
    },
  };
  const world = {
    tasks: tasksRef.current.slice(),   // the RENDER closure — frozen, as React freezes it
    agents: agentsRef.current.slice(),
    agentAbortersRef: desk.agentAbortersRef,
    abortAgentRun: (aid) => { aborted.push(aid); return desk.abortAgentRun(aid); },
    setTasks, setApprovals: (fn) => fn([]), logActivity, say,
    window: win, displaceDeskNote: () => null,
    tasksRef, agentsRef,
  };

  const del = new AsyncFunction(...DELETE_PARAMS, 'id', onDeleteTaskBody);
  const deleting = del(...DELETE_PARAMS.map(k => world[k]), 'tk_b');

  // The predecessor finishes mid-dialog and hands over. The REAL assign block.
  let chainRun = null;
  await new Promise(r => setTimeout(r, chainAt));
  if (chain) {
    const startCard = new Function('setTasks', 'applyStatus', 'onUpdateAgent', 'logActivity',
      'say', 'agent', 'taskId', 'task', assignBlock);
    const task = tasksRef.current.find(t => t.id === 'tk_b');
    startCard(setTasks, applyStatus, () => {}, logActivity, say, vera, 'tk_b', task);
    chainRun = desk.beginAgentRun(vera.id);
  }

  await deleting;
  // The run streams on for a moment after the ✕, the way a real one does.
  await new Promise(r => setTimeout(r, 30));

  console.log(JSON.stringify({
    scenario: name,
    dialogs,
    dialogWasTheResultGuard: dialogs.some(d => /work on it will be lost/.test(d)),
    chainStarted: !!chainRun,
    cardDeleted: deleted.includes('tk_b'),
    // THE BUG: a run left alive on a card that no longer exists. It goes on to
    // file a delivery into the cabinet for work the boss explicitly removed.
    runStillAlive: !!chainRun && !chainRun.signal.aborted,
    deskStillLit: desk.agentAbortersRef.current.has('a_vera'),
    abortFired: aborted.length > 0,
    // Did anything anywhere tell the boss a second run had been stopped?
    lateStopReported: activity.some(r => /while you were deciding/i.test(r.text || '')),
    said,
    activity: activity.map(r => r.text),
  }));
}

/* ═══ 2. the vault cache cleared while a probe is in flight ═══════════ */
function makeVault() {
  /* The whole cache region of hq-runtime.jsx, lifted as ONE scope so the
     module-level `let`s the fix touches are genuinely shared between the
     probe and the clear — a lift that rebuilt them per function would give
     each its own and prove nothing. Bounded by the cache declaration and by
     `onVaultReadyChange`'s closing brace. */
  const head = bareRt.indexOf('let _vaultConfiguredCache =');
  const tailMark = bareRt.indexOf('function onVaultReadyChange(fn)', head);
  if (head < 0 || tailMark < 0) throw new Error('vault cache region not found in hq-runtime.jsx');
  const close = bareRt.indexOf('\n}', tailMark);
  const region = bareRt.slice(head, close + 2);
  const make = new Function('CafresoHQClient', 'Date', region
    + '\nreturn { isVaultReady, clearVaultReadyCache, vaultReadySync, onVaultReadyChange };');
  return make;
}
const makeVaultRegion = makeVault();

async function vaultClearedMidProbe(name, { probeMs = 200, clearAt = 60, clear = true } = {}) {
  let answer = { configured: true, exists: true };   // the OLD vault: connected
  const CafresoHQClient = {
    vaultStatus: async () => {
      await new Promise(r => setTimeout(r, probeMs));
      return answer;
    },
  };
  const V = makeVaultRegion(CafresoHQClient, Date);
  const watched = [];
  V.onVaultReadyChange(v => watched.push(v));

  const probe = V.isVaultReady();
  await new Promise(r => setTimeout(r, clearAt));
  // Settings → Connections: the boss disconnects the vault / swaps backend.
  if (clear) V.clearVaultReadyCache();
  const syncRightAfterClear = V.vaultReadySync();
  const probeAnswer = await probe;
  await new Promise(r => setTimeout(r, 10));

  // `undefined` is a load-bearing value here and JSON.stringify eats it, so
  // every vault answer is reported as a string.
  const show = (v) => (v === undefined ? 'undefined' : v === true ? 'true' : v === false ? 'false' : String(v));
  console.log(JSON.stringify({
    scenario: name,
    cleared: clear,
    syncRightAfterClear: show(syncRightAfterClear),   // 'undefined' — nobody has looked
    // THE BUG: the in-flight probe writes the OLD vault's answer back over the
    // deliberate invalidation, so the office resumes advertising a vault the
    // boss just disconnected — and toolsForAgent, which awaits this same
    // function, hands out VAULT_* for it.
    syncAfterProbeLanded: show(V.vaultReadySync()),
    clearSurvivedTheProbe: V.vaultReadySync() === undefined,
    probeAnswer,
    // The watcher trail the coworker cards actually render off.
    watched: watched.map(show),
  }));
}

/* The freshness half, driven rather than described: a stubbed clock, so the
   stamp itself is observable through the 5s window's own behaviour. */
async function vaultStaleStamp(name, { probeMs = 4000 } = {}) {
  let clock = 1000000;
  const FakeDate = { now: () => clock };
  let probes = 0;
  const CafresoHQClient = {
    vaultStatus: async () => {
      probes++;
      const started = clock;
      await new Promise(r => setTimeout(r, 5));
      clock = started + probeMs;          // the probe took `probeMs` of wall time
      return { configured: true, exists: true };
    },
  };
  const V = makeVaultRegion(CafresoHQClient, FakeDate);
  await V.isVaultReady();                 // asked at T, answered at T+4000
  clock += 1500;                          // 1.5s after the answer landed
  await V.isVaultReady();                 // well inside a 5s window from the ANSWER
  console.log(JSON.stringify({
    scenario: name,
    probeMs,
    probes,
    // 1 == the answer's own freshness window is measured from when it landed.
    // 2 == the stamp was taken before the await, so a 4s probe's answer was
    //      born 4s old and expired 1s after arriving.
    reProbedImmediately: probes > 1,
  }));
}

/* ═══ 3. STOP ALL and the night shift that came up during the dialog ═══ */
async function stopAllNightShiftMidDialog(name, { dialogMs = 300, arrivesAt = 80,
                                                  arrives = true } = {}) {
  const desk = makeDesk();
  const missionsState = [{ id: 'm1', status: 'running' }];
  const nightState = { current: [] };
  const deletes = [], chat = [], said = [], dialogs = [];
  const world = {
    agentAbortersRef: desk.agentAbortersRef,
    missions: missionsState.slice(),          // the render closure
    nightShiftBoard: nightState.current.slice(),
    nightShiftBoardRef: nightState,
    abortAllAgentRuns: desk.abortAllAgentRuns,
    setAgents: (fn) => fn([]),
    setMissions: (fn) => fn(missionsState),
    setNightShiftBoard: (v) => { nightState.current = typeof v === 'function' ? v(nightState.current) : v; },
    setChat: (fn) => { const next = fn(chat.slice()); chat.length = 0; chat.push(...next); },
    say: (msg) => said.push(msg),
    logActivity: () => {},
    HQ: { uid: (p) => `${p}_x` },
    CafresoHQClient: { backendBase: () => 'http://x' },
    fetch: async (url, opts) => { deletes.push({ url, method: opts && opts.method }); return { ok: true }; },
    window: { hqConfirm: async (m) => { dialogs.push(m); await new Promise(r => setTimeout(r, dialogMs)); return true; } },
  };
  const PARAMS = Object.keys(world);
  const stopAll = new AsyncFunction(...PARAMS, onStopAllBody);

  // One coworker is streaming when the boss reaches for the button.
  desk.beginAgentRun('a_vera');
  const running = stopAll(...PARAMS.map(k => world[k]));

  await new Promise(r => setTimeout(r, arrivesAt));
  if (arrives) {
    // 2:00 AM. The schedule fires server-side; the 15s poll picks it up while
    // the dialog is still open. The render closure above can never see it.
    nightState.current = [{ id: 'ns_1', topic: 'the overnight digest' }];
  }
  // …and a second coworker starts a run in the same window.
  desk.beginAgentRun('a_kip');

  await running;

  console.log(JSON.stringify({
    scenario: name,
    dialogs,
    // THE FUNCTIONAL MISS: was the night shift that came up during the dialog
    // actually cancelled server-side, or did STOP ALL walk past it?
    nightShiftDeleted: deletes.some(d => d.url.includes('ns_1') && d.method === 'DELETE'),
    deletes,
    boardCleared: nightState.current.length === 0,
    // THE COUNT: what the office told the boss it had just done.
    chatLine: (chat[0] || {}).text || '',
    said,
    streamsAtSweepTime: 2,
  }));
}

/* ── runner ──────────────────────────────────────────────────────────── */
const only = process.argv[3];
const scenarios = {
  'chain-step-starts-during-the-result-confirm': () =>
    chainStartsDuringConfirm('chain-step-starts-during-the-result-confirm'),
  'no-chain-step-nothing-said': () =>
    chainStartsDuringConfirm('no-chain-step-nothing-said', { chain: false }),
  'declined-delete-keeps-the-card-and-the-run': () =>
    chainStartsDuringConfirm('declined-delete-keeps-the-card-and-the-run', { confirm: false }),
  'vault-cleared-mid-probe': () => vaultClearedMidProbe('vault-cleared-mid-probe'),
  // The load-bearing negative: with nobody clearing anything, the probe must
  // still land and the office must still hear the answer. An epoch guard that
  // swallowed ordinary probes would close this door by breaking the feature.
  'vault-untouched-probe-still-answers': () =>
    vaultClearedMidProbe('vault-untouched-probe-still-answers', { clear: false, probeMs: 40, clearAt: 10 }),
  'vault-slow-probe-freshness': () => vaultStaleStamp('vault-slow-probe-freshness'),
  'stop-all-night-shift-arrives-mid-dialog': () =>
    stopAllNightShiftMidDialog('stop-all-night-shift-arrives-mid-dialog'),
  'stop-all-quiet-office': () =>
    stopAllNightShiftMidDialog('stop-all-quiet-office', { arrives: false }),
};
if (only && !scenarios[only]) { console.error('unknown scenario: ' + only); process.exit(2); }
const run = only ? [scenarios[only]] : Object.values(scenarios);
for (const fn of run) await fn();
