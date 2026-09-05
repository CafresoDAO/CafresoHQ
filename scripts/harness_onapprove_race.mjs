#!/usr/bin/env node
// Lifts the REAL onApprove function body out of app.jsx (verbatim source
// text, brace-balanced extraction — no re-implementation) and drives it
// with stub dependencies to test whether two re-entrant calls for the SAME
// approval id (the shape of a fast double-click, or a duplicate synthetic
// event, landing before React has re-rendered with the post-first-call
// state) cause the real side-effecting action to fire twice.
//
// Usage: node harness_onapprove_race.mjs <path-to-app.jsx>
// Prints one JSON object per line to stdout, one per scenario run.

import fs from 'node:fs';

const appJsxPath = process.argv[2];
if (!appJsxPath) { console.error('usage: harness_onapprove_race.mjs <app.jsx>'); process.exit(2); }
const src = fs.readFileSync(appJsxPath, 'utf8');

function extractBalanced(source, marker) {
  const start = source.indexOf(marker);
  if (start < 0) throw new Error('marker not found: ' + marker);
  const braceStart = source.indexOf('{', start);
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

const onApproveBody = extractBalanced(src, 'const onApprove = (id) => {');

// Free variables the extracted body reads from its enclosing component
// scope, in the order they'll be bound as function parameters. Missing any
// identifier the body actually references would throw a ReferenceError at
// call time, so this list is exhaustive by construction (any run below that
// throws is a signal the list needs an addition, not a silent pass).
const PARAM_NAMES = [
  'approvals', 'setApprovals', 'clearApprovalNotice', 'recordReceipt',
  'setChat', 'HQ', 'CafresoHQClient', 'settleReceipt', 'logActivity',
  'officeCause', 'say', 'pendingHiresRef', 'agents', 'onHire',
  'downgradeElevatedModel', 'brainName', 'pendingAssistantHiresRef',
  'pendingElevationRef', 'onUpdateAgent', 'dispatchToAgent', 'tasks',
  'triggerChainStep', 'decideExternal', 'approvedIdsRef',
];

function buildOnApprove() {
  // eslint-disable-next-line no-new-func
  return new Function(...PARAM_NAMES, 'id', onApproveBody);
}

function makeWorld(overrides = {}) {
  const calls = {
    onHire: [], onUpdateAgent: [], dispatchToAgent: [], setApprovals: [],
    triggerChainStep: [], publishSite: [], setChat: [],
  };
  let uidCounter = 0;
  const world = {
    approvals: overrides.approvals || [],
    setApprovals: (fn) => { calls.setApprovals.push('called'); },
    clearApprovalNotice: () => {},
    recordReceipt: () => 'rc1',
    setChat: (fn) => { calls.setChat.push('called'); },
    HQ: {
      uid: (prefix) => `${prefix}-${++uidCounter}`,
      AGENT_COLORS: ['red'],
    },
    CafresoHQClient: {
      publishSite: async (path, opts) => { calls.publishSite.push({ path, opts }); return { mode: 'preview', url: 'http://x', file: 'x' }; },
      getSettings: () => ({}),
    },
    settleReceipt: () => {},
    logActivity: () => {},
    officeCause: (m) => m,
    say: () => {},
    pendingHiresRef: { current: new Set(overrides.pendingHires || []) },
    agents: overrides.agents || [],
    onHire: (a) => { calls.onHire.push(a); },
    downgradeElevatedModel: (model) => ({ model, swapped: false }),
    brainName: () => 'a brain',
    pendingAssistantHiresRef: { current: new Set() },
    pendingElevationRef: { current: new Set(overrides.pendingElevation || []) },
    onUpdateAgent: (id, patch) => { calls.onUpdateAgent.push({ id, patch }); },
    dispatchToAgent: (target, text, opts) => { calls.dispatchToAgent.push({ target: target && target.id, text }); },
    tasks: overrides.tasks || [],
    triggerChainStep: (task, prior, from) => { calls.triggerChainStep.push({ taskId: task && task.id }); },
    decideExternal: async () => {},
    // Present regardless of whether the extracted body references it (the
    // pre-fix source doesn't) — a fresh Set every call, exactly like
    // useRefA(new Set()) on a fresh render, so each `run()` starts unclaimed.
    approvedIdsRef: { current: new Set() },
    calls,
  };
  return world;
}

function callTwice(world, id) {
  const fn = buildOnApprove();
  const args = PARAM_NAMES.map(n => world[n]);
  // Two re-entrant invocations against the IDENTICAL world snapshot — the
  // exact shape of a double-click / duplicate event landing before React's
  // setApprovals (and the fresh closure it would produce on the next
  // render) has taken effect.
  fn(...args, id);
  fn(...args, id);
}

function run(name, kind, approvalExtra, worldExtra) {
  const ap = { id: 'ap1', kind, title: 't', ...approvalExtra };
  const world = makeWorld({ approvals: [ap], ...worldExtra });
  let threw = null;
  try { callTwice(world, 'ap1'); } catch (e) { threw = String(e && e.stack || e); }
  console.log(JSON.stringify({ scenario: name, threw, calls: world.calls }));
}

run('hire-agent', 'hire-agent', {
  hireProposal: { proposedBy: 'agentX', name: 'Newbie', role: 'analyst', proposedByName: 'Boss Agent', rationale: 'r' },
}, { agents: [{ id: 'agentX', name: 'Boss Agent' }] });

run('grant-elevation', 'grant-elevation', {
  elevationRequest: { requestedBy: 'agentY', reason: 'need shell' },
}, { agents: [{ id: 'agentY', name: 'Y' }] });

run('workflow-step', 'workflow-step', {
  taskId: 'task1', fromAgent: 'agentZ', priorResult: 'done part 1',
}, { tasks: [{ id: 'task1', title: 'Step 2', status: 'inbox' }], agents: [{ id: 'agentZ', name: 'Z' }] });

run('hire-assistant', 'hire-assistant', {
  assistantProposal: { proposedBy: 'agentW', name: 'Assist', role: 'helper', proposedByName: 'W', rationale: 'r', inheritModel: 'haiku', inheritColor: 'blue', inheritTools: [] },
}, { agents: [{ id: 'agentW', name: 'W' }] });

run('publish', 'publish', {
  publishRequest: { path: '/vault/site/index.html', agentId: 'agentP', agentName: 'P' },
}, { agents: [{ id: 'agentP', name: 'P' }] });
