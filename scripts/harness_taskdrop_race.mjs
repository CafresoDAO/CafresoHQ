#!/usr/bin/env node
// Lifts the REAL onTaskDropOnAgent function body out of app.jsx (verbatim
// source text, brace-balanced extraction — no re-implementation), plus the
// REAL beginAgentRun/endAgentRun it depends on and the REAL displacedTask
// from hq-runtime.jsx, and drives them with stub dependencies to test
// whether two re-entrant calls for the SAME (task, agent) pair — the shape
// of a fast double-click on the Task board's own ▶ START button
// (features.jsx: `onClick={(e) => { e.stopPropagation(); onStartTask(t.id,
// a); }}`, no disabled state, no debounce — the exact same physical action
// shape as #388's stamp double-click — the board's own comment already
// calls it "one click away and looks like queueing") or a flaky double
// 'drop' event on an agent's desk — cause HQ.agentStream, the real call to
// a real model, to fire twice.
//
// Background: a prior sweep (leading to #389) flagged onTaskDropOnAgent as
// "not independently guarded, but bounded — a double-drop is caught by
// beginAgentRun's own eviction (second dispatch aborts the first's
// controller before real work happens) rather than any guard in the
// handler itself" — and deferred a real harness-based check to a future
// hunt. This harness is that check, and the claim didn't hold up.
//
// What it actually found (pre-fix): displacedTask explicitly excludes the
// task's OWN id (`t.id !== taskId`) from "is this coworker already working
// on something that would be displaced" — so the second call's `running`
// check (agentAbortersRef.current.get(agent.id), a REF the first call
// already populated synchronously via beginAgentRun) finds a live run, but
// `displaced` comes back null for a same-task double-drop. Control falls
// into the `chatCut` branch instead, whose own comment claims "every
// cardless registrant is a chat surface" — false here, the registrant IS
// this task's own just-started run — and it shows a dialog that lies about
// why ("mid-conversation in chat … Their reply stops where it is") with an
// OK button reading "Start it", exactly what a boss who meant to click
// ▶ START once would click. Confirming it runs the whole handler again:
// beginAgentRun DOES evict the first run's controller, but only AFTER the
// first HQ.agentStream call already fired — the eviction happens too late
// to stop it. Pre-fix, this harness measured two live agentStream calls
// for one card, confirming the "too late abort" shape the hunt asked
// about, not the "eviction catches it" shape the #389 sweep assumed.
//
// Fix: a new startingTaskIdsRef (a Set keyed by taskId, same shape as
// #388's approvedIdsRef and #389's resendingIdsRef) is checked-and-claimed
// as the very first thing onTaskDropOnAgent does. A second call for a
// taskId already mid-start is now a silent no-op before it ever reaches
// the mislabeled chatCut dialog — this harness's job post-fix is to prove
// agentStream fires exactly once for the double/triple-drop scenarios,
// while a genuinely DIFFERENT task dropped on the same busy desk (a
// different taskId, never claimed) still reaches the legitimate
// interrupt-and-replace confirm flow unimpeded.
//
// Usage: node harness_taskdrop_race.mjs <path-to-app.jsx> <path-to-hq-runtime.jsx>
// Prints one JSON object per line to stdout, one per scenario run.

import fs from 'node:fs';

const appJsxPath = process.argv[2];
const hqRuntimePath = process.argv[3];
if (!appJsxPath || !hqRuntimePath) {
  console.error('usage: harness_taskdrop_race.mjs <app.jsx> <hq-runtime.jsx>');
  process.exit(2);
}
const appSrc = fs.readFileSync(appJsxPath, 'utf8');
const hqSrc = fs.readFileSync(hqRuntimePath, 'utf8');

function extractBalanced(source, marker) {
  const start = source.indexOf(marker);
  if (start < 0) throw new Error('marker not found: ' + marker);
  if (marker[marker.length - 1] !== '{') throw new Error('marker must end with the function\'s opening brace: ' + marker);
  const braceStart = start + marker.length - 1;
  let depth = 0;
  for (let k = braceStart; k < source.length; k++) {
    const c = source[k];
    if (c === '{') depth++;
    else if (c === '}') {
      depth--;
      if (depth === 0) return source.slice(braceStart + 1, k);
    }
  }
  throw new Error('unbalanced braces for marker: ' + marker);
}

const onTaskDropOnAgentBody = extractBalanced(appSrc,
  'const onTaskDropOnAgent = async (taskId, agent, taskFresh, opts = {}) => {');
const beginAgentRunBody = extractBalanced(appSrc, 'const beginAgentRun = (agentId) => {');
const endAgentRunBody = extractBalanced(appSrc, 'const endAgentRun = (agentId, controller) => {');
// The one piece of real logic this hunt is actually about: whether a
// same-task double-drop counts as "displacing" something. Lifted verbatim
// rather than re-derived, same reasoning as the two functions above.
const displacedTaskBody = extractBalanced(hqSrc, 'function displacedTask(tasks, agentId, taskId, running) {');

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

function buildBeginAgentRun() {
  // eslint-disable-next-line no-new-func
  return new Function('agentAbortersRef', 'bossTurnRef', 'turnRunsRef', 'AbortController', 'agentId',
    beginAgentRunBody);
}
function buildEndAgentRun() {
  // eslint-disable-next-line no-new-func
  return new Function('agentAbortersRef', 'turnRunsRef', 'agentId', 'controller', endAgentRunBody);
}
function buildDisplacedTask() {
  // eslint-disable-next-line no-new-func
  return new Function('tasks', 'agentId', 'taskId', 'running', displacedTaskBody);
}

// Free variables the extracted onTaskDropOnAgent body reads from its
// enclosing component scope, in the order they'll be bound as function
// parameters. `window` (hqConfirm, cafresohqToast) is left as a real
// global, matching how the source itself reads it.
const PARAM_NAMES = [
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
  // #394: the desk ledger and the honest displacement report the drop path
  // now calls before it claims a desk. This harness never sets up a
  // displaced note, so both are inert here — they just have to exist.
  'deskWorkRef', 'displaceDeskNote',
];

function buildOnTaskDropOnAgent() {
  // eslint-disable-next-line no-new-func
  return new AsyncFunction(...PARAM_NAMES, 'taskId', 'agent', 'taskFresh', 'opts = {}',
    onTaskDropOnAgentBody);
}

function makeWorld(overrides = {}) {
  const calls = { agentStream: [], hqConfirm: [], dispatchToAgent: [], beginAgentRun: [] };

  // The real ref registry beginAgentRun/endAgentRun/displacedTask all share
  // — a plain Map, mutated synchronously, exactly like useRefA(new Map()).
  const agentAbortersRef = { current: new Map() };
  const bossTurnRef = { current: null };
  const turnRunsRef = { current: new Set() };
  const realBeginAgentRun = buildBeginAgentRun();
  const realEndAgentRun = buildEndAgentRun();
  const realDisplacedTask = buildDisplacedTask();

  global.window = {
    hqConfirm: async (msg, opts) => {
      calls.hqConfirm.push(msg);
      return overrides.confirmReturns !== undefined ? overrides.confirmReturns : true;
    },
    cafresohqToast: { warn: () => {}, error: () => {}, success: () => {} },
  };
  global.AbortController = AbortController;

  const tasks = overrides.tasks || [];
  const agents = overrides.agents || [];

  const world = {
    tasks,
    tasksRef: { current: tasks },
    agents,
    agentsRef: { current: agents },
    agentAbortersRef,
    // Present regardless of whether the extracted body references it (the
    // pre-fix source doesn't) — a fresh Set every call, exactly like
    // useRefA(new Set()) on a fresh render, so each `run()` starts unclaimed.
    startingTaskIdsRef: { current: new Set() },
    deskWorkRef: { current: new Map() },
    displaceDeskNote: () => null,
    HQ: {
      displacedTask: (...a) => realDisplacedTask(...a),
      uid: (p) => `${p}_${Math.random().toString(36).slice(2)}`,
      // The real side effect under test: a real call to a real model. Records
      // the call SYNCHRONOUSLY (the very first thing it does), exactly like a
      // real fetch()-backed implementation issues the network request before
      // its own first internal await — then awaits a tick and rejects, so the
      // harness doesn't need to stub the entire success/delivery path.
      agentStream: (agent, prompt, onToken, opts) => {
        calls.agentStream.push({ agentId: agent && agent.id, prompt });
        return new Promise((_resolve, reject) => {
          setTimeout(() => reject(new Error('stub: no real model in this harness')), 5);
        });
      },
      cleanHarmony: (s) => s,
      visibleReply: (s) => s,
      throttleTokens: () => ({ note: () => {}, flushNow: () => {}, cancel: () => {}, withNotes: (s) => s || '' }),
      honestyNotes: undefined,
      publishDoorNote: undefined,
      icpPublishEnabled: undefined,
      extractApproval: () => null,
      approvalBody: () => '',
    },
    setTasks: () => {},
    onUpdateAgent: () => {},
    logActivity: () => {},
    say: () => {},
    setChat: () => {},
    beginAgentRun: (agentId) => {
      calls.beginAgentRun.push(agentId);
      return realBeginAgentRun(agentAbortersRef, bossTurnRef, turnRunsRef, AbortController, agentId);
    },
    endAgentRun: (agentId, controller) => realEndAgentRun(agentAbortersRef, turnRunsRef, agentId, controller),
    makeScreenEmitter: () => ({ stream: () => {}, done: () => {}, error: () => {} }),
    stripToolEcho: (buf) => buf,
    hasSubstance: (s) => !!(s && String(s).trim()),
    shortfallLine: () => 'came back with nothing',
    snagSentence: () => 'hit a snag',
    applyStatus: (t, status) => ({ ...t, status }),
    fileDelivery: async () => null,
    agentFiledPath: () => null,
    settleAfterRun: () => {},
    pulseGraph: () => {},
    attachVisit: () => {},
    toolActivity: () => ({}),
    recordToolReceipt: () => {},
    recordXp: () => {},
    taskKind: () => 'generic',
    doneLine: () => '',
    appendJournal: () => {},
    floorEmit: () => {},
    firstDeliverySeen: true, // avoid the setDelivery/setFirstDeliverySeen branch — irrelevant to this hunt
    setFirstDeliverySeen: () => {},
    setDelivery: () => {},
    cabinetIsEncrypted: () => false,
    onApprovalRequest: () => {},
    triggerChainStep: () => {},
    chatErrorText: () => 'error',
    consumeDmBudget: () => true,
    dmBudgetExhaustedNote: () => {},
    dispatchToAgent: async () => {},
    chainHoldLine: () => '',
    visitLine: () => '',
    visitPlace: () => '',
    calls,
  };
  return world;
}

async function callN(world, taskId, agent, taskFresh, opts, n) {
  const fn = buildOnTaskDropOnAgent();
  const args = PARAM_NAMES.map((k) => world[k]);
  // N re-entrant invocations against the IDENTICAL world snapshot — the
  // exact shape of two 'drop' events (or two ▶ START clicks) landing in
  // one tick, before React ever re-renders `tasks`/`agents` or the drag
  // library disables the source element.
  const proms = [];
  for (let i = 0; i < n; i++) proms.push(fn(...args, taskId, agent, taskFresh, opts));
  await Promise.allSettled(proms);
}

// Two GENUINELY different cards dropped on the same busy desk right after
// each other — the legitimate "interrupt and replace" flow (`displaced` or
// `chatCut`, gated on a real window.hqConfirm the boss must click through).
// The new taskId-keyed claim must NOT block this: it is keyed per task, so
// a different taskId is never already claimed. Confirming the dialog is
// expected to run the handler again and dispatch the second, different
// card — that is the feature working as designed, not the bug this hunt
// is about.
async function runTwoDifferentTasks(name, worldExtra) {
  const world = makeWorld({ ...worldExtra, confirmReturns: true });
  const fn = buildOnTaskDropOnAgent();
  const args = PARAM_NAMES.map((k) => world[k]);
  let threw = null;
  try {
    const p1 = fn(...args, 'task1', worldExtra.agent, worldExtra.task1, {});
    const p2 = fn(...args, 'task2', worldExtra.agent, worldExtra.task2, {});
    await Promise.allSettled([p1, p2]);
  } catch (e) { threw = String(e && e.stack || e); }
  console.log(JSON.stringify({ scenario: name, threw, calls: world.calls }));
}

async function run(name, taskId, agent, taskFresh, opts, worldExtra, n = 2) {
  const world = makeWorld(worldExtra);
  let threw = null;
  try { await callN(world, taskId, agent, taskFresh, opts, n); } catch (e) { threw = String(e && e.stack || e); }
  console.log(JSON.stringify({ scenario: name, threw, calls: world.calls }));
}

async function main() {
  const agent = { id: 'agentA', name: 'Vera', role: 'Coding Agent', color: 'blue', tokens: 0 };
  const task = { id: 'task1', title: 'Write the quarterly summary', detail: '', assignedTo: null, status: 'todo' };

  // The ▶ START double-click / double-drop-event shape: same taskId, same
  // agent, no opts (manual, not chain-auto), called twice with no await
  // between the two calls.
  await run('same-task-same-agent-double-drop', 'task1', agent, task, {},
    { tasks: [task], agents: [agent] }, 2);

  // Sanity: a single call still runs exactly once.
  await run('single-call-sanity', 'task1', agent, task, {},
    { tasks: [task], agents: [agent] }, 1);

  // Three rapid drops for good measure — not just two.
  await run('same-task-same-agent-triple-drop', 'task1', agent, task, {},
    { tasks: [task], agents: [agent] }, 3);

  // Sanity: the fix must not block a genuinely different card from
  // displacing a busy desk once the boss confirms it.
  const task2 = { id: 'task2', title: 'A second, different card', detail: '', assignedTo: null, status: 'todo' };
  await runTwoDifferentTasks('two-different-tasks-same-agent-confirmed', {
    agent, task1: task, task2, tasks: [task, task2], agents: [agent],
  });
}

main();
