#!/usr/bin/env node
// #398 — the sweep of the class #394 opened: an observation made BEFORE an
// `await`, acted upon AFTER it, when the observed thing can change during the
// wait. #394 fixed two of the doors (onDelegate's hand-off, onTaskDropOnAgent's
// ▶ START). This harness drives the third, which nobody had looked at:
// `onDeleteTask`.
//
//   const running = t.status === 'doing' && !t.blockedReason && !!t.assignedTo
//     && agentAbortersRef.current.has(t.assignedTo);       // ← the observation
//   if (running) { … await window.hqConfirm("… is working on X … stop them?") }
//   …
//   if (running) abortAgentRun(t.assignedTo);              // ← acting on it
//
// `abortAgentRun` kills whatever is on that desk WHEN THE DIALOG CLOSES, which
// is not necessarily the card run the dialog named. A note that queued behind
// the same busy desk (#98's `while` poll in dispatchToAgent) can wake inside
// the gap, claim the cleared desk and start streaming — and the ✕ then takes
// the note.
//
// Everything below is lifted, verbatim, out of the committed source
// (marker-bounded / brace-balanced extraction — no re-implementation):
//
//   - the REAL onDeleteTask handler,
//   - the REAL busy-desk deferral block + claim out of dispatchToAgent,
//   - the REAL beginAgentRun / endAgentRun / abortAgentRun desk registry,
//   - the REAL displaceDeskNote (#394's honest-displacement report; absent
//     pre-fix, which is what the fire-test needs to see),
//   - the REAL night-shift poll body, for the second finding.
//
// Usage: node harness_delete_desk_race.mjs <app.jsx> [scenario]
// Prints one JSON object per line to stdout, one per scenario run.

import fs from 'node:fs';

const appJsxPath = process.argv[2];
if (!appJsxPath) {
  console.error('usage: harness_delete_desk_race.mjs <app.jsx> [scenario]');
  process.exit(2);
}
const appSrc = fs.readFileSync(appJsxPath, 'utf8');

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
/* Same, but starting the search from a unique earlier anchor — three
   `const poll = async () => {` live in app.jsx and only the position
   distinguishes them. */
function extractBalancedAfter(source, anchor, marker) {
  const a = source.indexOf(anchor);
  if (a < 0) throw new Error('anchor not found: ' + anchor);
  return extractBalanced(source.slice(a), marker);
}

const bare = stripComments(appSrc);
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

const onDeleteTaskBody = extractBalanced(bare, 'const onDeleteTask = async (id) =>');
const beginAgentRunBody = extractBalanced(appSrc, 'const beginAgentRun = (agentId) => {');
const endAgentRunBody = extractBalanced(appSrc, 'const endAgentRun = (agentId, controller) => {');
const abortAgentRunBody = extractBalanced(appSrc, 'const abortAgentRun = (agentId) => {');
let displaceDeskNoteBody = null;
try {
  displaceDeskNoteBody = extractBalanced(appSrc,
    'const displaceDeskNote = (agentId, agentName, since, byWhat) => {');
} catch (_e) { /* pre-#394 source has no such function */ }

/* ── the desk registry, real ─────────────────────────────────────────── */
function makeDesk() {
  const agentAbortersRef = { current: new Map() };
  const bossTurnRef = { current: null };
  const turnRunsRef = { current: new Set() };
  const stopEpochRef = { current: 0 };
  const turnEpochRef = { current: 0 };
  const deskWorkRef = { current: new Map() };
  // eslint-disable-next-line no-new-func
  const rawBegin = new Function('agentAbortersRef', 'bossTurnRef', 'turnRunsRef', 'AbortController',
    'agentId', beginAgentRunBody);
  // eslint-disable-next-line no-new-func
  const rawEnd = new Function('agentAbortersRef', 'turnRunsRef', 'deskWorkRef', 'agentId', 'controller',
    endAgentRunBody);
  // eslint-disable-next-line no-new-func
  const rawAbort = new Function('agentAbortersRef', 'agentId', abortAgentRunBody);
  return {
    agentAbortersRef, bossTurnRef, turnRunsRef, stopEpochRef, turnEpochRef, deskWorkRef,
    beginAgentRun: (agentId) => rawBegin(agentAbortersRef, bossTurnRef, turnRunsRef, AbortController, agentId),
    endAgentRun: (agentId, controller) => rawEnd(agentAbortersRef, turnRunsRef, deskWorkRef, agentId, controller),
    abortAgentRun: (agentId) => rawAbort(agentAbortersRef, agentId),
  };
}

/* ── a waiting office note: the REAL deferral block, then the REAL claim ── */
const GATE = 'if (agentAbortersRef.current.has(agent.id)) {';
const BUBBLE = "const agentMsgId = HQ.uid('m');";
const gateAt = bare.indexOf(GATE);
const bubbleAt = bare.indexOf(BUBBLE);
if (gateAt < 0 || bubbleAt < gateAt) throw new Error('busy-desk deferral block not found in app.jsx');
const deferralBlock = bare.slice(gateAt, bubbleAt);
const CLAIM = 'const controller = beginAgentRun(agent.id);';
const IN_PROGRESS = "MessageRegistry.transition(messageId, 'in_progress'";
const claimAt = bare.indexOf(CLAIM, bubbleAt);
const inProgAt = bare.indexOf(IN_PROGRESS, claimAt);
if (claimAt < 0 || inProgAt < claimAt) throw new Error("dispatchToAgent's claim not found in app.jsx");
const claimBlock = bare.slice(claimAt, inProgAt);

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
  'started', 'delivered', 'evicted', 'deskWorkRef', 'sender'];

/* ── onDeleteTask's own free variables ───────────────────────────────── */
const DELETE_PARAMS = ['tasks', 'agents', 'agentAbortersRef', 'abortAgentRun',
  'setTasks', 'setApprovals', 'logActivity', 'say', 'window',
  // added by this hunt (#398): the honest report #394 built for the other
  // two doors. Absent pre-fix — passed as a no-op so the lift still runs.
  'displaceDeskNote',
  // added by #400: the handler now re-derives the board and the roster on the
  // far side of the ask, against the LIVE refs rather than this render's
  // closure. Neither scenario below moves the CARD mid-dialog (what moves is
  // the desk, which is #398's own subject), so both refs just mirror the
  // closure — they have to exist or the lift throws ReferenceError.
  'tasksRef', 'agentsRef'];

/* ── scenario 1: the ✕ dialog outlives the run it named ──────────────── */
async function deleteDialogRace(name, { dialogMs = 900, noteRunMs = 600,
                                        cardRunEndsAt = 200, confirm = true } = {}) {
  const desk = makeDesk();
  const agent = { id: 'a_vera', name: 'Vera' };
  const task = { id: 'tk_l', title: 'the quarterly summary', status: 'doing', assignedTo: 'a_vera' };
  const chat = [], transitions = [], started = [], delivered = [], evicted = [];
  const setChat = (fn) => {
    const next = typeof fn === 'function' ? fn(chat.slice()) : fn;
    chat.length = 0; chat.push(...next);
  };
  const MessageRegistry = {
    transition: (id, state, meta) => transitions.push({ id, state, note: meta && meta.note }),
  };
  const HQ = { uid: (p) => `${p}_${Math.random().toString(36).slice(2, 8)}` };
  const displaceDeskNote = displaceDeskNoteBody
    // eslint-disable-next-line no-new-func
    ? new Function('agentAbortersRef', 'deskWorkRef', 'MessageRegistry', 'setChat', 'HQ',
        `return (agentId, agentName, since, byWhat) => {${displaceDeskNoteBody}};`)(
        desk.agentAbortersRef, desk.deskWorkRef, MessageRegistry, setChat, HQ)
    : () => null;

  const dialogs = [];
  const win = {
    hqConfirm: async (msg) => {
      dialogs.push(msg);
      await new Promise(r => setTimeout(r, dialogMs));
      return confirm;
    },
  };
  const aborted = [];
  const deleted = [];
  const deleteWorld = {
    tasks: [task], agents: [agent],
    agentAbortersRef: desk.agentAbortersRef,
    abortAgentRun: (aid) => { aborted.push(aid); return desk.abortAgentRun(aid); },
    setTasks: (fn) => { const kept = fn([task]); deleted.push(...[task].filter(t => !kept.includes(t)).map(t => t.id)); },
    setApprovals: (fn) => fn([]),
    logActivity: () => {}, say: () => {},
    window: win, displaceDeskNote,
    tasksRef: { current: [task] }, agentsRef: { current: [agent] },
  };

  // 1. The CARD's own run is on Vera's desk — this is what the ✕ dialog names.
  const cardRun = desk.beginAgentRun(agent.id);

  // 2. Sam's note arrives, finds the desk busy, and queues on the REAL poll.
  const waiter = new AsyncFunction(...WAITER_PARAMS, waiterSrc);
  const samsNote = waiter(agent, { id: 's_sam', name: 'Sam' }, 'msg_sam', 'sams-note', noteRunMs,
    false, desk.agentAbortersRef, { current: [agent] }, desk.stopEpochRef, desk.turnEpochRef,
    desk.beginAgentRun, desk.endAgentRun, setChat, MessageRegistry, HQ,
    started, delivered, evicted, desk.deskWorkRef, { name: 'Sam' });

  // 3. The boss clicks ✕ on the card. The dialog names Vera and the card.
  const del = new AsyncFunction(...DELETE_PARAMS, 'id', onDeleteTaskBody);
  const deleting = del(...DELETE_PARAMS.map(k => deleteWorld[k]), 'tk_l');

  // 4. The card's run finishes on its own while the dialog is still open.
  //    Sam's note wakes, claims the desk it waited its turn for, and starts.
  await new Promise(r => setTimeout(r, cardRunEndsAt));
  desk.endAgentRun(agent.id, cardRun);

  await Promise.allSettled([deleting, samsNote]);

  console.log(JSON.stringify({
    scenario: name,
    dialogs,
    dialogNamedTheCard: dialogs.some(d => /is working on "the quarterly summary" right now/.test(d)),
    cardDeleted: deleted.includes('tk_l'),
    abortFired: aborted.length > 0,
    samsNoteStarted: started.includes('sams-note'),
    samsNoteDelivered: delivered.includes('sams-note'),
    samsNoteEvicted: evicted.includes('sams-note'),
    // Did ANYTHING anywhere say Sam's note was the thing that stopped?
    displacementReported:
      chat.some(m => /took the desk|displaced|not the one you were asked about/i.test(m.text || ''))
      || transitions.some(t => t.state === 'cancelled'),
    chatLines: chat.map(m => m.text),
    transitions,
  }));
}

/* ── scenario 2: the desk did NOT change hands ───────────────────────── */
// The card's own run is still on the desk when the boss answers. The abort is
// correct, nothing was displaced, and the office must say nothing. #394's own
// rule: an unchanged desk gets no line.
async function deleteUnchangedDesk(name) {
  const desk = makeDesk();
  const agent = { id: 'a_vera', name: 'Vera' };
  const task = { id: 'tk_l', title: 'the quarterly summary', status: 'doing', assignedTo: 'a_vera' };
  const chat = [], transitions = [];
  const setChat = (fn) => {
    const next = typeof fn === 'function' ? fn(chat.slice()) : fn;
    chat.length = 0; chat.push(...next);
  };
  const MessageRegistry = {
    transition: (id, state, meta) => transitions.push({ id, state, note: meta && meta.note }),
  };
  const HQ = { uid: (p) => `${p}_${Math.random().toString(36).slice(2, 8)}` };
  const displaceDeskNote = displaceDeskNoteBody
    // eslint-disable-next-line no-new-func
    ? new Function('agentAbortersRef', 'deskWorkRef', 'MessageRegistry', 'setChat', 'HQ',
        `return (agentId, agentName, since, byWhat) => {${displaceDeskNoteBody}};`)(
        desk.agentAbortersRef, desk.deskWorkRef, MessageRegistry, setChat, HQ)
    : () => null;

  const aborted = [], deleted = [], dialogs = [];
  const del = new AsyncFunction(...DELETE_PARAMS, 'id', onDeleteTaskBody);
  const cardRun = desk.beginAgentRun(agent.id);
  const world = {
    tasks: [task], agents: [agent], agentAbortersRef: desk.agentAbortersRef,
    abortAgentRun: (aid) => { aborted.push(aid); return desk.abortAgentRun(aid); },
    setTasks: (fn) => { const kept = fn([task]); deleted.push(...[task].filter(t => !kept.includes(t)).map(t => t.id)); },
    setApprovals: (fn) => fn([]), logActivity: () => {}, say: () => {},
    window: { hqConfirm: async (m) => { dialogs.push(m); await new Promise(r => setTimeout(r, 50)); return true; } },
    displaceDeskNote,
    tasksRef: { current: [task] }, agentsRef: { current: [agent] },   // #400, as above
  };
  await del(...DELETE_PARAMS.map(k => world[k]), 'tk_l');
  console.log(JSON.stringify({
    scenario: name,
    cardDeleted: deleted.includes('tk_l'),
    abortFired: aborted.includes('a_vera'),
    cardRunAborted: cardRun.signal.aborted,
    saidAnything: chat.map(m => m.text),
    transitions,
  }));
}

/* ── scenario 3: the boss declines ───────────────────────────────────── */
// A declined dialog must displace nothing and delete nothing, even though the
// desk changed hands while it was open.
async function deleteDeclined(name) {
  return deleteDialogRace(name, { confirm: false });
}

/* ── scenario 4: the night-shift poll, run twice overlapping ─────────── */
// A separate finding in the same class. `## 391` listed the night-run XP guard
// (`experienceRef.current.some(e => e.taskId === r.id)`) as SAFE because "it
// runs inside the serialised poll above" — but the serialised poll (the
// chain/wallet one, `if (dead || polling || document.hidden) return; polling =
// true;`) is a DIFFERENT poll, a few thousand lines away. This one has only
// `if (document.hidden || stop) return;` and is fired from three places (mount,
// a 15s interval, and every visibilitychange), so two invocations can overlap
// across its own `await`s and both act on the same snapshot.
// Lifted from the effect's OWN `let stop = …` declaration through the end of
// `poll`, not just the function body: the latch this hunt adds is a plain
// closure variable declared out there beside `stop`, exactly as the sibling
// chain/wallet poll declares its own, and a lift that started inside `poll`
// would give each invocation a fresh one and prove nothing.
const NIGHT_ANCHOR = 'const [nightShiftPending, setNightShiftPending] = useStateA([]);';
const nightPollSrc = (() => {
  const tail = bare.slice(bare.indexOf(NIGHT_ANCHOR));
  const declAt = tail.indexOf('let stop = false');
  const fnAt = tail.indexOf('const poll = async () =>', declAt);
  if (declAt < 0 || fnAt < 0) throw new Error("night-shift poll's own scope not found in app.jsx");
  const braceStart = tail.indexOf('{', fnAt);
  let depth = 0;
  for (let k = braceStart; k < tail.length; k++) {
    if (tail[k] === '{') depth++;
    else if (tail[k] === '}') { depth--; if (depth === 0) return tail.slice(declAt, k + 1) + ';'; }
  }
  throw new Error("unbalanced braces in the night-shift poll");
})();
const NIGHT_PARAMS = ['document', 'CafresoHQClient', 'fetch',
  'setNightShiftBoard', 'setNightShiftPending', 'setNightShiftRuns',
  'experienceRef', 'recordXp', 'agentsRef', 'logActivity'];

// `sequential: true` runs the second poll only AFTER the first has finished —
// this hunt's analogue of `## 390`'s "a genuinely different taskId still
// starts": a latch that never releases is a board that stops updating.
async function nightPollReentrancy(name, { fetchMs = 60, outcome = 'snag', sequential = false } = {}) {
  const runs = [{
    id: 'nr_1', agentId: 'a_kenji', topic: 'overnight competitor scan',
    finishedAt: Date.now(), iterations: 3,
    errors: outcome === 'snag' ? 2 : 0,
    lastError: outcome === 'snag' ? 'the brain stopped answering' : '',
    stoppedByBoss: false,
  }];
  const ledger = [];               // the committed experience ledger
  /* The two halves that make this bug possible, modelled exactly as the app
     wires them:
       · `recordXp` is `setExperience(prev => xpRecord(prev, e))` — a
         FUNCTIONAL updater, so the WRITE always sees the latest ledger and
         xpRecord's one-'done'-per-taskId guard really does apply; and
       · `experienceRef` is EFFECT-assigned (`useEffectA(() => {
         experienceRef.current = experience; }, [experience])`), so the READ
         the guard at app.jsx:1352 makes only catches up after React commits
         AND paints. Two poll invocations 5ms apart both read the snapshot
         from before either of them wrote.
     `commitRender()` is that catch-up, and nothing in this scenario calls it
     — which is the point: it cannot happen inside the window. */
  let snapshot = [];
  const experienceRef = { current: snapshot };
  const commitRender = () => { snapshot = ledger.slice(); experienceRef.current = snapshot; };
  const xpEntries = [], activity = [], boardWrites = [];
  const recordXp = (e) => {
    xpEntries.push(e);
    if (e.outcome === 'done' && e.taskId
        && ledger.some(x => x.taskId === e.taskId && x.outcome === 'done')) return;  // xpRecord's guard
    ledger.push(e);
  };
  const fakeFetch = async () => {
    await new Promise(r => setTimeout(r, fetchMs));
    return { ok: true, json: async () => ({ schedules: [], running: [], runs }) };
  };
  const world = {
    document: { hidden: false },
    CafresoHQClient: { backendBase: () => '' },
    fetch: fakeFetch,
    setNightShiftBoard: (b) => boardWrites.push(b),
    setNightShiftPending: () => {}, setNightShiftRuns: () => {},
    experienceRef, recordXp,
    agentsRef: { current: [{ id: 'a_kenji', name: 'Kenji', color: 'red' }] },
    logActivity: (e) => activity.push(e),
  };
  // eslint-disable-next-line no-new-func
  const poll = new Function(...NIGHT_PARAMS, nightPollSrc + '\nreturn poll;')(
    ...NIGHT_PARAMS.map(k => world[k]));
  const call = () => poll();
  // Two triggers landing inside one fetch: a visibilitychange and the timer,
  // or two visibilitychanges from an alt-tab. Both are ordinary.
  if (sequential) {
    await call();
    commitRender();       // React gets its turn between the two, as it would
    await call();
  } else {
    const a = call();
    await new Promise(r => setTimeout(r, 5));
    const b = call();
    await Promise.allSettled([a, b]);
  }
  commitRender();
  console.log(JSON.stringify({
    scenario: name,
    outcome,
    boardRefreshes: boardWrites.length,
    xpCallsMade: xpEntries.length,
    ledgerEntries: ledger.length,
    activityRows: activity.length,
    activityText: activity.map(e => e.text),
  }));
}

const only = process.argv[3];
const all = {
  'delete-dialog-outlives-the-run': () => deleteDialogRace('delete-dialog-outlives-the-run'),
  'delete-on-an-unchanged-desk': () => deleteUnchangedDesk('delete-on-an-unchanged-desk'),
  'delete-declined': () => deleteDeclined('delete-declined'),
  'night-poll-reentrancy-snag': () => nightPollReentrancy('night-poll-reentrancy-snag', { outcome: 'snag' }),
  'night-poll-reentrancy-done': () => nightPollReentrancy('night-poll-reentrancy-done', { outcome: 'done' }),
  'night-poll-sequential': () => nightPollReentrancy('night-poll-sequential', { outcome: 'snag', sequential: true }),
};
for (const [k, fn] of Object.entries(all)) { if (!only || only === k) await fn(); }
