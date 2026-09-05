#!/usr/bin/env node
// Lifts the REAL resendMessage function body out of app.jsx (verbatim source
// text, brace-balanced extraction — no re-implementation) and drives it with
// stub dependencies to test whether two re-entrant calls for the SAME failed
// message (the shape of a fast double-click on the Inbox row's own ↻ RE-SEND
// button, which calls resendMessage with confirm:false and so never hits the
// window.hqConfirm await that would otherwise serialize the clicks) cause
// dispatchToAgent — a real dispatch to a real coworker — to fire twice.
//
// resendMessage's own guard reads messagesRef.current (the "already retried"
// check) to decide whether to no-op. That ref is only kept in sync with
// state by the render-time assignment `messagesRef.current = messages;` —
// it is NOT updated synchronously inside the handler the way approvedIdsRef
// is for onApprove (#388). A second call landing before React commits the
// new message and re-renders sees the exact same stale messagesRef.current
// the first call saw, "already" is still undefined, and it dispatches again.
//
// Post-fix, resendMessage claims m.id in a new resendingIdsRef Set as the
// very first thing it does, before messagesRef.current is even read — this
// harness drives that ref exactly like a fresh useRefA(new Set()) on a real
// render (a new empty Set per scenario, since each `run()` below is its own
// simulated click sequence from a clean slate).
//
// Usage: node harness_resend_race.mjs <path-to-app.jsx>
// Prints one JSON object per line to stdout, one per scenario run.

import fs from 'node:fs';

const appJsxPath = process.argv[2];
if (!appJsxPath) { console.error('usage: harness_resend_race.mjs <app.jsx>'); process.exit(2); }
const src = fs.readFileSync(appJsxPath, 'utf8');

function extractBalanced(source, marker) {
  const start = source.indexOf(marker);
  if (start < 0) throw new Error('marker not found: ' + marker);
  // The marker itself is written to END with the function's own opening
  // brace ("=> {"), so that brace IS `marker`'s last character — searching
  // for '{' from `start` (as a naive scan would) can instead match one of
  // the braces INSIDE the marker text (resendMessage's own destructuring
  // default, `{ confirm = true } = {}`), truncating the extraction to just
  // that literal. Use the marker's own trailing brace directly.
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

const resendMessageBody = extractBalanced(src, 'const resendMessage = async (m, { confirm = true } = {}) => {');

// Free variables the extracted body reads from its enclosing component
// scope, in the order they'll be bound as function parameters. `window` is
// left as a real global (set up below) rather than a parameter, matching
// how the source itself reads it (a bare global, not a closed-over local).
const PARAM_NAMES = ['messagesRef', 'agents', 'dispatchToAgent', 'resendingIdsRef'];

// resendMessage is declared `async` in the real source (it awaits
// window.hqConfirm on the confirm:true / oversized-body path) — the plain
// Function constructor rejects `await` in its body regardless of whether
// that branch is reached, so this uses the AsyncFunction constructor
// instead (there is no literal `AsyncFunction` global; recovering it via an
// async function's own constructor is the standard way to get one).
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

function buildResendMessage() {
  // eslint-disable-next-line no-new-func
  return new AsyncFunction(...PARAM_NAMES, 'm', '{ confirm = true } = {}', resendMessageBody);
}

function makeWorld(overrides = {}) {
  const calls = { dispatchToAgent: [], hqConfirm: [] };
  global.window = {
    hqConfirm: async (msg, opts) => { calls.hqConfirm.push(msg); return overrides.confirmReturns !== undefined ? overrides.confirmReturns : true; },
    cafresohqToast: { warn: () => {}, error: () => {}, success: () => {} },
  };
  const world = {
    messagesRef: { current: overrides.messages || [] },
    agents: overrides.agents || [],
    // Real dispatchToAgent creates a new message record via setMessages
    // (async React state) — it does NOT synchronously update messagesRef.
    // The stub mirrors exactly that: it counts the call but never mutates
    // messagesRef.current, same as the real one until a render commits.
    dispatchToAgent: (agent, body, opts) => { calls.dispatchToAgent.push({ agentId: agent && agent.id, body, opts }); },
    // Present regardless of whether the extracted body references it (the
    // pre-fix source doesn't) — a fresh Set every call, exactly like
    // useRefA(new Set()) on a fresh render, so each `run()` starts unclaimed.
    resendingIdsRef: { current: new Set() },
    calls,
  };
  return world;
}

async function callN(world, m, opts, n) {
  const fn = buildResendMessage();
  const args = PARAM_NAMES.map(k => world[k]);
  // N re-entrant invocations against the IDENTICAL world snapshot — the
  // exact shape of a double-click landing before React ever re-renders
  // messagesRef.current with the first call's new message.
  const proms = [];
  for (let i = 0; i < n; i++) proms.push(fn(...args, m, opts));
  await Promise.all(proms);
}

async function run(name, m, opts, worldExtra, n = 2) {
  const world = makeWorld(worldExtra);
  let threw = null;
  try { await callN(world, m, opts, n); } catch (e) { threw = String(e && e.stack || e); }
  console.log(JSON.stringify({ scenario: name, threw, calls: world.calls }));
}

async function main() {
  const failedMessage = {
    id: 'msg1', toAgentId: 'agentA', toAgentName: 'A', fromAgentId: 'boss',
    state: 'failed', body: 'do the thing', bodyDropped: 0,
  };
  // The exact call shape onRetryActivity uses for a named message off the
  // Inbox row's own ↻ RE-SEND button: confirm:false, so the `(confirm || cut
  // > 0)` gate is false and resendMessage never awaits window.hqConfirm —
  // nothing serializes the two clicks.
  await run('retry-row-confirm-false', failedMessage, { confirm: false },
    { messages: [failedMessage], agents: [{ id: 'agentA', name: 'A' }] });

  // Sanity: a single call still dispatches exactly once.
  await run('single-call-sanity', { ...failedMessage, id: 'msg2' }, { confirm: false },
    { messages: [{ ...failedMessage, id: 'msg2' }], agents: [{ id: 'agentA', name: 'A' }] }, 1);

  // A boss who declines the confirm door (palette path, confirm:true) must
  // still be able to retry the SAME message afterward — the release() on
  // that path must actually un-claim the id, not just look like it does.
  {
    const m = { ...failedMessage, id: 'msg3' };
    const world = makeWorld({ messages: [m], agents: [{ id: 'agentA', name: 'A' }], confirmReturns: false });
    const fn = buildResendMessage();
    const args = PARAM_NAMES.map(k => world[k]);
    let threw = null;
    try {
      await fn(...args, m, { confirm: true }); // declined — should be a no-op, and release the claim
      world.calls.hqConfirm.length = 0; // reset for clarity, not load-bearing
      // Second attempt, confirm accepted this time — must go through.
      global.window.hqConfirm = async () => true;
      await fn(...args, m, { confirm: true });
    } catch (e) { threw = String(e && e.stack || e); }
    console.log(JSON.stringify({ scenario: 'declined-confirm-then-retry-succeeds', threw, calls: world.calls }));
  }
}

main();
