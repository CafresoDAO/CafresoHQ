#!/usr/bin/env node
// #391 left one finding for its own hunt: dispatchToAgent's busy-desk `while`
// poll — "two office-initiated notes can both wake on the same clear tick and
// both proceed … two DISTINCT messages where one gets evicted (lost work)".
//
// This harness answers that, and then answers the question the finding was
// really pointing at. It lifts, verbatim (marker-bounded / brace-balanced
// extraction of the actual committed source — no re-implementation):
//
//   - the REAL busy-desk deferral block out of dispatchToAgent (the gate, the
//     750ms poll, the sweep check, the recipient-gone check),
//   - the REAL beginAgentRun / endAgentRun desk registry it polls,
//   - the REAL onTaskDropOnAgent handler, whose ▶ START / drop path is the
//     other claimant of the same desk.
//
// Scenario 1-3 (two-notes / three-notes / one-note): two genuinely distinct
// office-initiated notes wait out one busy desk and wake on the same clear
// tick. Result: they SERIALIZE. The `while` re-tests `has(agent.id)` at the
// top of every iteration, each 750ms timer is its own macrotask, the
// microtask checkpoint between two timer tasks lets the first waiter's
// continuation run to completion, and the stretch from the loop's exit to
// `beginAgentRun` is 320 lines of straight-line synchronous prompt assembly
// with no await in it — so the second waiter re-tests a desk the first has
// already claimed and goes back to sleep. #391's literal claim does not
// reproduce.
//
// Scenario 4 (dialog-outlives-the-occupant): the same desk, the same lost
// work, a different pair of racers — and this one does reproduce. Both
// boss-initiated claim paths (onTaskDropOnAgent ~5357, onDelegate ~4623) read
// the desk, then `await window.hqConfirm(...)` — a modal the boss can sit on
// for as long as they like — and only then call `beginAgentRun`, which
// evicts whatever is on the desk at THAT moment rather than what the dialog
// described. A note that queued politely behind the busy desk, waited out the
// poll and finally started streaming is killed mid-token by a dialog answered
// about somebody else, with nothing said anywhere.
//
// Usage: node harness_busydesk_race.mjs <app.jsx> <hq-runtime.jsx> [scenario]
// Prints one JSON object per line to stdout, one per scenario run.

import fs from 'node:fs';

const appJsxPath = process.argv[2];
const hqRuntimePath = process.argv[3];
if (!appJsxPath || !hqRuntimePath) {
  console.error('usage: harness_busydesk_race.mjs <app.jsx> <hq-runtime.jsx> [scenario]');
  process.exit(2);
}
const appSrc = fs.readFileSync(appJsxPath, 'utf8');
const hqSrc = fs.readFileSync(hqRuntimePath, 'utf8');

function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^[ \t]*\/\/.*$/gm, '');
}
function extractBalanced(source, marker) {
  const start = source.indexOf(marker);
  if (start < 0) throw new Error('marker not found: ' + marker);
  const braceStart = start + marker.length - 1;
  let depth = 0;
  for (let k = braceStart; k < source.length; k++) {
    const c = source[k];
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) return source.slice(braceStart + 1, k); }
  }
  throw new Error('unbalanced braces for marker: ' + marker);
}

const bare = stripComments(appSrc);
const GATE = 'if (agentAbortersRef.current.has(agent.id)) {';
const BUBBLE = "const agentMsgId = HQ.uid('m');";
const gateAt = bare.indexOf(GATE);
const bubbleAt = bare.indexOf(BUBBLE);
if (gateAt < 0 || bubbleAt < gateAt) throw new Error('busy-desk deferral block not found in app.jsx');
const deferralBlock = bare.slice(gateAt, bubbleAt);
const beginAgentRunBody = extractBalanced(appSrc, 'const beginAgentRun = (agentId) => {');
const endAgentRunBody = extractBalanced(appSrc, 'const endAgentRun = (agentId, controller) => {');
const onTaskDropOnAgentBody = extractBalanced(appSrc,
  'const onTaskDropOnAgent = async (taskId, agent, taskFresh, opts = {}) => {');
const displacedTaskBody = extractBalanced(hqSrc, 'function displacedTask(tasks, agentId, taskId, running) {');
// #394's own honest-displacement report, lifted rather than re-stated — the
// whole point of the fix is what THIS function does, so the harness must run
// the committed one. Absent pre-fix; the harness reports that as a null.
let displaceDeskNoteBody = null;
try {
  displaceDeskNoteBody = extractBalanced(appSrc,
    'const displaceDeskNote = (agentId, agentName, since, byWhat) => {');
} catch (_e) { /* pre-fix source has no such function */ }

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

/* ── the desk registry, real ─────────────────────────────────────────── */
function makeDesk() {
  const agentAbortersRef = { current: new Map() };
  const bossTurnRef = { current: null };
  const turnRunsRef = { current: new Set() };
  const stopEpochRef = { current: 0 };
  const turnEpochRef = { current: 0 };
  // #394's desk ledger — one Map per world, exactly like useRefA(new Map()).
  const deskWorkRef = { current: new Map() };
  // eslint-disable-next-line no-new-func
  const rawBegin = new Function('agentAbortersRef', 'bossTurnRef', 'turnRunsRef', 'AbortController', 'agentId',
    beginAgentRunBody);
  // eslint-disable-next-line no-new-func
  const rawEnd = new Function('agentAbortersRef', 'turnRunsRef', 'deskWorkRef', 'agentId', 'controller', endAgentRunBody);
  const beginAgentRun = (agentId) => rawBegin(agentAbortersRef, bossTurnRef, turnRunsRef, AbortController, agentId);
  const endAgentRun = (agentId, controller) => rawEnd(agentAbortersRef, turnRunsRef, deskWorkRef, agentId, controller);
  return { agentAbortersRef, bossTurnRef, turnRunsRef, stopEpochRef, turnEpochRef, deskWorkRef,
    beginAgentRun, endAgentRun };
}

// The REAL claim, lifted too: everything dispatchToAgent does between taking
// the desk and stamping in_progress — post-#394 that is the claim AND the
// signature that lets a displacement name this note. Pre-fix it is the claim
// alone, which is exactly what the fire-test needs to see.
const CLAIM = 'const controller = beginAgentRun(agent.id);';
const IN_PROGRESS = "MessageRegistry.transition(messageId, 'in_progress'";
const claimAt = bare.indexOf(CLAIM, bubbleAt);
const inProgAt = bare.indexOf(IN_PROGRESS, claimAt);
if (claimAt < 0 || inProgAt < claimAt) throw new Error("dispatchToAgent's claim not found in app.jsx");
const claimBlock = bare.slice(claimAt, inProgAt);

/* A waiting office note: the REAL deferral block, then the REAL claim. */
const waiterSrc = `
  ${deferralBlock}
  ${claimBlock}
  started.push(tag);
  await new Promise(res => setTimeout(res, runMs));
  if (controller.signal.aborted) evicted.push(tag); else delivered.push(tag);
  endAgentRun(agent.id, controller);
  return tag;
`;
const WAITER_PARAMS = ['agent', 'dmFrom', 'messageId', 'tag', 'runMs', 'inBossTurn',
  'agentAbortersRef', 'agentsRef', 'stopEpochRef', 'turnEpochRef',
  'beginAgentRun', 'endAgentRun', 'setChat', 'MessageRegistry', 'HQ',
  'started', 'delivered', 'evicted',
  // #394: the desk ledger dispatchToAgent signs after claiming.
  'deskWorkRef', 'sender'];

function makeNoteWorld(desk, agent, chat, transitions) {
  const setChat = (fn) => { const next = typeof fn === 'function' ? fn(chat.slice()) : fn; chat.length = 0; chat.push(...next); };
  return {
    agent,
    agentsRef: { current: [agent] },
    setChat,
    MessageRegistry: { transition: (id, state, meta) => transitions.push({ id, state, note: meta && meta.note }) },
    HQ: { uid: (p) => `${p}_${Math.random().toString(36).slice(2, 8)}` },
    ...desk,
  };
}

/* ── scenarios 1-3: two distinct notes, one busy desk ────────────────── */
async function notesRace(name, { notes = 2, runMs = 40, busyMs = 60 } = {}) {
  const desk = makeDesk();
  const agent = { id: 'a_vera', name: 'Vera' };
  const chat = [], transitions = [], started = [], delivered = [], evicted = [];
  const world = makeNoteWorld(desk, agent, chat, transitions);
  const waiter = new AsyncFunction(...WAITER_PARAMS, waiterSrc);
  const call = (tag, sender) => waiter(agent, { id: 's_' + tag, name: sender }, 'msg_' + tag, tag, runMs,
    false, world.agentAbortersRef, world.agentsRef, world.stopEpochRef, world.turnEpochRef,
    world.beginAgentRun, world.endAgentRun, world.setChat, world.MessageRegistry, world.HQ,
    started, delivered, evicted, world.deskWorkRef, { name: sender });

  const incumbent = desk.beginAgentRun(agent.id);      // somebody is mid-reply
  const pending = [];
  for (let i = 1; i <= notes; i++) pending.push(call('note' + i, 'Sender' + i));
  await new Promise(res => setTimeout(res, busyMs));
  desk.endAgentRun(agent.id, incumbent);               // …and the desk clears
  await Promise.all(pending);

  console.log(JSON.stringify({
    scenario: name, notes, started, delivered, evicted, lost: evicted.length,
    deskEmptyAtEnd: desk.agentAbortersRef.current.size === 0,
    waitNotes: chat.filter(m => /waits its turn/.test(m.text || '')).length,
  }));
}

/* ── scenario 4: the boss's dialog outlives the occupant it named ─────── */
// Free variables the extracted onTaskDropOnAgent body reads from its
// enclosing component scope. Same list harness_taskdrop_race.mjs uses.
const DROP_PARAMS = [
  'tasks', 'tasksRef', 'agents', 'agentsRef', 'agentAbortersRef', 'startingTaskIdsRef',
  'HQ', 'setTasks', 'onUpdateAgent', 'logActivity', 'say', 'setChat',
  'beginAgentRun', 'endAgentRun', 'makeScreenEmitter',
  'stripToolEcho', 'hasSubstance', 'shortfallLine', 'snagSentence', 'applyStatus',
  'fileDelivery', 'agentFiledPath', 'settleAfterRun', 'pulseGraph', 'attachVisit',
  'toolActivity', 'recordToolReceipt', 'recordXp', 'taskKind', 'doneLine',
  'appendJournal', 'floorEmit', 'firstDeliverySeen', 'setFirstDeliverySeen', 'setDelivery',
  'cabinetIsEncrypted', 'onApprovalRequest', 'triggerChainStep', 'chatErrorText',
  'consumeDmBudget', 'dmBudgetExhaustedNote', 'dispatchToAgent', 'chainHoldLine',
  'visitLine', 'visitPlace',
  // Added by this hunt (#394): the desk ledger and the honest report that
  // reads it, plus the registry the report files the displaced note against.
  'deskWorkRef', 'displaceDeskNote', 'MessageRegistry',
];

async function dialogOutlivesOccupant(name, { dialogMs = 900, noteRunMs = 600 } = {}) {
  const desk = makeDesk();
  const agent = { id: 'a_vera', name: 'Vera', role: 'Coding Agent', color: 'blue', tokens: 0 };
  const task = { id: 'task_board', title: 'Write the quarterly summary', detail: '', assignedTo: null, status: 'todo' };
  const chat = [], transitions = [], started = [], delivered = [], evicted = [];
  const noteWorld = makeNoteWorld(desk, agent, chat, transitions);
  const deskWorkRef = desk.deskWorkRef;
  const displaceDeskNote = displaceDeskNoteBody
    // eslint-disable-next-line no-new-func
    ? new Function('agentAbortersRef', 'deskWorkRef', 'MessageRegistry', 'setChat', 'HQ',
        `return (agentId, agentName, since, byWhat) => {${displaceDeskNoteBody}};`)(
        desk.agentAbortersRef, deskWorkRef, noteWorld.MessageRegistry, noteWorld.setChat, noteWorld.HQ)
    : () => null;

  global.AbortController = AbortController;
  const hqConfirmSeen = [];
  global.window = {
    hqConfirm: async (msg) => { hqConfirmSeen.push(msg); await new Promise(r => setTimeout(r, dialogMs)); return true; },
    cafresohqToast: { warn: () => {}, error: () => {}, success: () => {} },
  };

  // eslint-disable-next-line no-new-func
  const realDisplacedTask = new Function('tasks', 'agentId', 'taskId', 'running', displacedTaskBody);
  const setChat = noteWorld.setChat;
  const dropWorld = {
    tasks: [task], tasksRef: { current: [task] }, agents: [agent], agentsRef: { current: [agent] },
    agentAbortersRef: desk.agentAbortersRef, startingTaskIdsRef: { current: new Set() },
    deskWorkRef, displaceDeskNote, MessageRegistry: noteWorld.MessageRegistry,
    HQ: {
      displacedTask: (...a) => realDisplacedTask(...a),
      uid: (p) => `${p}_${Math.random().toString(36).slice(2)}`,
      agentStream: () => new Promise((_res, rej) => setTimeout(() => rej(new Error('stub: no real model')), 5)),
      cleanHarmony: (s) => s, visibleReply: (s) => s,
      throttleTokens: () => ({ note: () => {}, flushNow: () => {}, cancel: () => {}, withNotes: (s) => s || '' }),
      honestyNotes: undefined, publishDoorNote: undefined, icpPublishEnabled: undefined,
      extractApproval: () => null, approvalBody: () => '',
    },
    setTasks: () => {}, onUpdateAgent: () => {}, logActivity: () => {}, say: () => {}, setChat,
    beginAgentRun: desk.beginAgentRun, endAgentRun: desk.endAgentRun,
    makeScreenEmitter: () => ({ stream: () => {}, done: () => {}, error: () => {} }),
    stripToolEcho: (b) => b, hasSubstance: (s) => !!(s && String(s).trim()),
    shortfallLine: () => 'came back with nothing', snagSentence: () => 'hit a snag',
    applyStatus: (t, status) => ({ ...t, status }),
    fileDelivery: async () => null, agentFiledPath: () => null, settleAfterRun: () => {},
    pulseGraph: () => {}, attachVisit: () => {}, toolActivity: () => ({}), recordToolReceipt: () => {},
    recordXp: () => {}, taskKind: () => 'generic', doneLine: () => '', appendJournal: () => {},
    floorEmit: () => {}, firstDeliverySeen: true, setFirstDeliverySeen: () => {}, setDelivery: () => {},
    cabinetIsEncrypted: () => false, onApprovalRequest: () => {}, triggerChainStep: () => {},
    chatErrorText: () => 'error', consumeDmBudget: () => true, dmBudgetExhaustedNote: () => {},
    dispatchToAgent: async () => {}, chainHoldLine: () => '', visitLine: () => '', visitPlace: () => '',
  };

  const waiter = new AsyncFunction(...WAITER_PARAMS, waiterSrc);
  const drop = new AsyncFunction(...DROP_PARAMS, 'taskId', 'agent', 'taskFresh', 'opts = {}',
    onTaskDropOnAgentBody);

  // 1. Kip's reply is on Vera's desk.
  const incumbent = desk.beginAgentRun(agent.id);
  deskWorkRef.current.set(agent.id, { controller: incumbent, what: "Kip's reply to the boss" });

  // 2. Sam's note arrives, finds the desk busy, and queues on the real poll.
  const samsNote = waiter(agent, { id: 's_sam', name: 'Sam' }, 'msg_sam', 'sams-note', noteRunMs,
    false, desk.agentAbortersRef, noteWorld.agentsRef, desk.stopEpochRef, desk.turnEpochRef,
    desk.beginAgentRun, desk.endAgentRun, setChat, noteWorld.MessageRegistry, noteWorld.HQ,
    started, delivered, evicted, deskWorkRef, { name: 'Sam' });

  // 3. The boss drops a card on the same busy desk; the dialog names Kip.
  const dropped = drop(...DROP_PARAMS.map(k => dropWorld[k]), 'task_board', agent, task, {});

  // 4. Kip finishes while the dialog is still open. Sam's note wakes, claims
  //    the desk it waited its turn for, and starts streaming.
  await new Promise(r => setTimeout(r, 20));
  desk.endAgentRun(agent.id, incumbent);
  deskWorkRef.current.delete(agent.id);

  await Promise.allSettled([dropped, samsNote]);

  console.log(JSON.stringify({
    scenario: name,
    dialogsShown: hqConfirmSeen.length,
    dialogNamed: hqConfirmSeen.map(m => /mid-conversation/.test(m) ? 'chatCut' : (/still on/.test(m) ? 'displaced' : 'other')),
    samsNoteStarted: started.includes('sams-note'),
    samsNoteDelivered: delivered.includes('sams-note'),
    samsNoteEvicted: evicted.includes('sams-note'),
    // Did ANYTHING anywhere say Sam's note was displaced?
    displacementReported: chat.some(m => /displaced|was interrupted|put aside|not delivered|stopped/i.test(m.text || ''))
      || transitions.some(t => t.state === 'cancelled' || t.state === 'failed'),
    chatLines: chat.map(m => m.text),
    transitions,
  }));
}

const only = process.argv[4];
const all = {
  'two-notes-one-busy-desk': () => notesRace('two-notes-one-busy-desk', { notes: 2 }),
  'three-notes-one-busy-desk': () => notesRace('three-notes-one-busy-desk', { notes: 3 }),
  'one-note-one-busy-desk': () => notesRace('one-note-one-busy-desk', { notes: 1 }),
  'dialog-outlives-the-occupant': () => dialogOutlivesOccupant('dialog-outlives-the-occupant'),
};
for (const [k, fn] of Object.entries(all)) { if (!only || only === k) await fn(); }
