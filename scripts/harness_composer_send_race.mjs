#!/usr/bin/env node
// Lifts the REAL `send`/`_send` function bodies out of the three composer
// surfaces — ui/chat.jsx's ChatPanel, features.jsx's FocusMode, and
// views/terminal.jsx's TerminalChat — as verbatim source text
// (brace-balanced extraction of the actual committed source, no
// re-implementation) and drives them with stub dependencies to test whether
// two re-entrant calls (a fast double-click, Enter-then-click, or a
// duplicate synthetic click off a double-tap, landing before React has
// re-rendered with the post-first-call state) cause the real model calls to
// fire twice.
//
// All three guard themselves on a REACT STATE value — the two chat panels on
// `streaming`, the terminal on `busy` — which is exactly the ## 388 / ## 389
// / ## 390 / ## 391 bug shape: the handler closes over this render's copy,
// and the setState that would flip it only lands on the NEXT render.
//
// Usage: node harness_composer_send_race.mjs <repo-root>
// Prints one JSON object per line to stdout, one per scenario run.

import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.argv[2];
if (!ROOT) { console.error('usage: harness_composer_send_race.mjs <repo-root>'); process.exit(2); }

const readSrc = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');

function extractBalanced(source, marker) {
  const start = source.indexOf(marker);
  if (start < 0) throw new Error('marker not found: ' + marker);
  const braceStart = source.indexOf('{', start + marker.length - 1);
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

/* Build the entry point (`send`, what the button and Enter are wired to)
   with the round itself (`_send`) passed in as a parameter. Post-fix `send`
   is a thin claim-wrapper around `_send`; pre-fix the whole body sits
   directly in `send` and the `_send` marker is absent, so the harness falls
   back to calling the entry point alone. Either way it is the REAL
   committed source that runs. */
function buildPair(src, params, entryMarker, innerMarker) {
  const outer = extractBalanced(src, entryMarker);
  const inner = src.indexOf(innerMarker) >= 0 ? extractBalanced(src, innerMarker) : null;
  // eslint-disable-next-line no-new-func
  const mkOuter = new Function(...params, `return (async () => {${outer}});`);
  // eslint-disable-next-line no-new-func
  const mkInner = inner ? new Function(...params, `return (async () => {${inner}});`) : null;
  return { mkOuter, mkInner };
}

/* Wire the world: every param except the `_send` slot comes from `w`, and
   `_send` is the inner body built against that same world. */
function instantiate(params, innerName, { mkOuter, mkInner }, w) {
  const argsFor = (self) => params.map(n => (n === innerName ? self : w[n]));
  const inner = mkInner ? mkInner(...argsFor(null)) : null;
  return mkOuter(...argsFor(inner));
}

async function drive(fn, { times, sequential }) {
  let threw = null;
  try {
    if (sequential) {
      for (let i = 0; i < times; i++) await fn();
    } else {
      // Re-entrant: fire N times back-to-back against ONE unchanged
      // snapshot, without awaiting between — a double-click (or Enter and
      // then the button) lands before any state the first call sets could
      // have re-rendered anything.
      const ps = [];
      for (let i = 0; i < times; i++) ps.push(fn());
      await Promise.all(ps);
    }
  } catch (e) { threw = String((e && e.stack) || e); }
  return threw;
}

/* ── shared stubs ───────────────────────────────────────────────────── */

// Real spend. Resolves on a later macrotask so a second re-entrant call
// lands while the first is genuinely still in flight — the live shape.
const later = (v, fn) => new Promise((res) => setTimeout(() => { try { fn && fn(); } catch (_e) {} res(v); }, 5));

const snagCause = (m) => String(m || 'snag');
const snagOpener = (m) => 'hit a snag — ' + String(m || '');
const snagSentence = (m) => 'hit a snag — ' + String(m || '');
const requestAnimationFrame = (fn) => setTimeout(fn, 1);

function makeThrottle(calls) {
  return () => {
    const f = () => {};
    f.cancel = () => {}; f.flushNow = () => {}; f.note = () => {}; f.raw = () => '';
    return f;
  };
}

let uidN = 0;

/* ── 1. ui/chat.jsx — ChatPanel.send ────────────────────────────────── */

const CHAT_PARAMS = [
  'input', 'streaming', 'backendDown', 'window', 'HQ', 'setChat', 'setInput',
  'setStreaming', 'activeRoom', 'activeThread', 'agents', 'roomStrayNote',
  'onDispatchToAgent', 'snagCause', 'turnEpochRef', 'onInferTaskAssignment',
  'handoffAgent', 'returnToCEO', 'setHandoffFor', 'chatRef', 'onBossAsk',
  'onBossAskSettled', 'abortRef', 'attachVisit', 'onCeoUsage',
  'onApprovalRequest', 'withRouteOut', 'snagOpener', 'withHandoff',
  'CafresoHQClient', 'sendRunningRef', '_send',
];

function chatWorld(text, nAgents) {
  const calls = { ceoStream: [], dispatch: [], bossAsk: [] };
  const agents = Array.from({ length: nAgents }, (_, i) => ({ id: 'a' + i, name: 'A' + i, role: 'r', color: 'sky' }));
  let chat = [];
  const w = {
    input: text,
    streaming: false,           // the stale value a second call still sees
    backendDown: false,
    window: {},
    agents,
    activeRoom: null,
    activeThread: 'direct',
    setInput: () => {},
    setStreaming: () => {},
    setChat: (u) => { chat = typeof u === 'function' ? u(chat) : u; },
    chatRef: { get current() { return chat; } },
    roomStrayNote: () => '',
    onDispatchToAgent: (a, body, opts) => { calls.dispatch.push({ id: a && a.id }); return later('said'); },
    snagCause, snagOpener, snagSentence,
    turnEpochRef: { current: 0 },
    onInferTaskAssignment: null,
    handoffAgent: null,
    returnToCEO: () => {},
    setHandoffFor: () => {},
    onBossAsk: (t) => { calls.bossAsk.push(t); return 'ask_' + calls.bossAsk.length; },
    onBossAskSettled: () => {},
    abortRef: { current: null },
    attachVisit: () => {},
    onCeoUsage: null,
    onApprovalRequest: null,
    withRouteOut: (s) => s,
    withHandoff: (s) => s,
    CafresoHQClient: {},
    sendRunningRef: { current: false },
    calls,
  };
  w.HQ = {
    uid: (p) => p + '_' + (++uidN),
    publishDoorNote: () => null,
    icpPublishEnabled: () => false,
    extractAllMentions: (t, roster) => {
      const names = [];
      for (const n of roster) {
        if (new RegExp('@' + n + '\\b', 'i').test(t)) names.push(n);
      }
      if (!names.length) return null;
      return { targetNames: names, body: t.replace(/@\S+\s*/g, '').trim() || 'do the thing' };
    },
    // Real spend.
    ceoStream: (prompt, flush, opts) => { calls.ceoStream.push({ n: calls.ceoStream.length }); return later('ok'); },
    throttleTokens: makeThrottle(calls),
    extractApproval: () => null,
    approvalBody: (s) => s,
    visibleReply: (s) => String(s || ''),
    cleanHarmony: (s) => String(s || ''),
    honestyNotes: null,
    CHIEF_OF_STAFF: 'cos',
  };
  return w;
}

const chatSrc = () => readSrc('ui/chat.jsx');

async function runChat(name, { text, nAgents = 3, times = 2, sequential = false }) {
  const w = chatWorld(text, nAgents);
  const pair = buildPair(chatSrc(), CHAT_PARAMS, 'const send = async () => {', 'const _send = async () => {');
  const fn = instantiate(CHAT_PARAMS, '_send', pair, w);
  const threw = await drive(fn, { times, sequential });
  console.log(JSON.stringify({
    scenario: name, threw,
    ceoStream: w.calls.ceoStream.length,
    dispatch: w.calls.dispatch.length,
    bossAsk: w.calls.bossAsk.length,
  }));
}

/* ── 2. features.jsx — FocusMode.send ───────────────────────────────── */

const FOCUS_PARAMS = [
  'input', 'streaming', 'setInput', 'setStreaming', 'chat', 'setChat',
  'agents', 'abortRef', 'HQ', 'snagSentence', 'runningRef', '_send',
];

function focusWorld() {
  const calls = { ceoStream: [], userMsgs: [] };
  let chat = [];
  return {
    input: 'what should I do today?',
    streaming: false,
    setInput: () => {},
    setStreaming: () => {},
    get chat() { return chat; },
    setChat: (u) => {
      chat = typeof u === 'function' ? u(chat) : u;
      calls.userMsgs = chat.filter(m => m.from === 'user');
    },
    agents: [{ id: 'a0', name: 'A0', role: 'r' }],
    abortRef: { current: null },
    snagSentence,
    runningRef: { current: false },
    HQ: {
      ceoStream: (t, flush, opts) => { calls.ceoStream.push(1); return later('ok'); },
      throttleTokens: makeThrottle(calls),
      visibleReply: (s) => String(s || ''),
      cleanHarmony: (s) => String(s || ''),
    },
    calls,
  };
}

async function runFocus(name, { times = 2, sequential = false } = {}) {
  const w = focusWorld();
  const pair = buildPair(readSrc('features.jsx'), FOCUS_PARAMS,
    'const send = async () => {', 'const _send = async () => {');
  const fn = instantiate(FOCUS_PARAMS, '_send', pair, w);
  const threw = await drive(fn, { times, sequential });
  console.log(JSON.stringify({
    scenario: name, threw,
    ceoStream: w.calls.ceoStream.length,
    userMsgs: w.calls.userMsgs.length,
  }));
}

/* ── 3. views/terminal.jsx — TerminalChat.send ──────────────────────── */

const TERM_PARAMS = [
  'input', 'busy', 'project', 'msgs', 'setMsgs', 'setInput', 'setBusy',
  'setErr', 'ctrlRef', 'cli', 'model', 'CafresoHQClient', 'sessionId',
  'authMethod', 'inputRef', 'sendRunningRef', '_send',
];

function termWorld(cli) {
  const calls = { terminalStream: [], stream: [] };
  let msgs = [];
  return {
    input: 'refactor the parser',
    busy: false,                // the stale value a second tap still sees
    project: { id: 'p1', name: 'proj', path: '/tmp/proj' },
    get msgs() { return msgs; },
    setMsgs: (u) => { msgs = typeof u === 'function' ? u(msgs) : u; },
    setInput: () => {},
    setBusy: () => {},
    setErr: () => {},
    ctrlRef: { current: null },
    cli,
    model: '',
    sessionId: 's1',
    authMethod: 'subscription',
    inputRef: { current: null },
    sendRunningRef: { current: false },
    CafresoHQClient: {
      // Real turns on the USER'S OWN subscription.
      terminalStream: (o) => { calls.terminalStream.push({ cli: o.cli }); return later('ok'); },
      stream: (o) => { calls.stream.push(1); return later('ok'); },
    },
    calls,
  };
}

async function runTerm(name, { cli = 'claude', times = 2, sequential = false } = {}) {
  const w = termWorld(cli);
  const pair = buildPair(readSrc('views/terminal.jsx'), TERM_PARAMS,
    'const send = async () => {', 'const _send = async () => {');
  const fn = instantiate(TERM_PARAMS, '_send', pair, w);
  const threw = await drive(fn, { times, sequential });
  console.log(JSON.stringify({
    scenario: name, threw,
    terminalStream: w.calls.terminalStream.length,
    stream: w.calls.stream.length,
    msgs: w.msgs.length,
  }));
}

/* ── scenarios ──────────────────────────────────────────────────────── */

const MENTION = '@A0 @A1 @A2 please look at the margin thread';
const PLAIN = 'what is our margin?';

const main = async () => {
  // The race on the main composer, @mention fan-out: one message's worth of
  // intent, two events. One round is 3 onDispatchToAgent, 0 ceoStream.
  await runChat('chat-mention-double', { text: MENTION, times: 2 });
  await runChat('chat-mention-triple', { text: MENTION, times: 3 });
  await runChat('chat-mention-single', { text: MENTION, times: 1 });
  // …and the CEO path. One round is 1 ceoStream and 1 onBossAsk.
  await runChat('chat-ceo-double', { text: PLAIN, times: 2 });
  await runChat('chat-ceo-triple', { text: PLAIN, times: 3 });
  await runChat('chat-ceo-single', { text: PLAIN, times: 1 });
  // Not over-blocked: once a turn has ENDED, the next message must go.
  await runChat('chat-ceo-second-turn-after-finish', { text: PLAIN, times: 2, sequential: true });

  await runFocus('focus-double', { times: 2 });
  await runFocus('focus-triple', { times: 3 });
  await runFocus('focus-single', { times: 1 });
  await runFocus('focus-second-turn-after-finish', { times: 2, sequential: true });

  await runTerm('terminal-double', { times: 2 });
  await runTerm('terminal-triple', { times: 3 });
  await runTerm('terminal-single', { times: 1 });
  await runTerm('terminal-second-turn-after-finish', { times: 2, sequential: true });
};

main().catch(e => { console.error(e); process.exit(1); });
