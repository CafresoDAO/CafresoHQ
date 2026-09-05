#!/usr/bin/env node
// Lifts the REAL StandupModal `start`/`_start` and MeetingRoom
// `moderate`/`_moderate` function bodies out of features.jsx (verbatim
// source text, brace-balanced extraction — no re-implementation) and drives
// them with stub dependencies to test whether two re-entrant calls (the
// shape of a fast double-click, or a duplicate synthetic click event,
// landing before React has re-rendered with the post-first-call state)
// cause the real model calls to fire twice.
//
// Both surfaces guard themselves on a REACT STATE value — the stand-up on
// `phase`, the meeting room on `streaming` — which is exactly the ## 388 /
// ## 389 / ## 390 bug shape: the handler closes over this render's copy,
// and the setState that would flip it only lands on the NEXT render.
//
// Usage: node harness_standup_meeting_race.mjs <path-to-features.jsx>
// Prints one JSON object per line to stdout, one per scenario run.

import fs from 'node:fs';

const featuresPath = process.argv[2];
if (!featuresPath) { console.error('usage: harness_standup_meeting_race.mjs <features.jsx>'); process.exit(2); }
const src = fs.readFileSync(featuresPath, 'utf8');

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

function bodyOf(marker) { return extractBalanced(src, marker); }

// The two entry points the buttons are wired to. Post-fix these are thin
// claim-wrappers around `_start` / `_moderate`; pre-fix the whole body sits
// directly in `start` / `moderate` and the `_`-prefixed marker is absent,
// so the harness falls back to calling the entry point alone. Either way it
// is the REAL committed source that runs.
const has = (marker) => src.indexOf(marker) >= 0;

/* ── shared stubs ───────────────────────────────────────────────────── */

function makeCalls() {
  return { agentStream: [], ceoStream: [], setPhase: [], setStreaming: [], setMsgs: [] };
}

function makeHQ(calls) {
  return {
    // Real spend. Resolves on a later macrotask so a second re-entrant call
    // lands while the first is genuinely still in flight — the live shape.
    agentStream: (agent, prompt, onTok, opts) => new Promise((res) => {
      calls.agentStream.push({ agent: agent && agent.id });
      setTimeout(() => { try { onTok && onTok('ok'); } catch (_e) {} res('ok'); }, 5);
    }),
    ceoStream: (prompt, onTok, opts) => new Promise((res) => {
      calls.ceoStream.push({ n: calls.ceoStream.length });
      setTimeout(() => { try { onTok && onTok('sum'); } catch (_e) {} res('sum'); }, 5);
    }),
    visibleReply: (buf) => String(buf || ''),
    cleanHarmony: (s) => String(s || ''),
    throttleTokens: () => { const f = () => {}; f.cancel = () => {}; return f; },
  };
}

// jsdom-free rAF: the gates only need "run it eventually".
const requestAnimationFrame = (fn) => setTimeout(fn, 1);
const snagSentence = (m) => String(m || 'snag');

/* ── stand-up ───────────────────────────────────────────────────────── */

const STANDUP_PARAMS = [
  'phase', 'participating', 'setArchived', 'setSummary', 'setSummaryFail',
  'setReports', 'setPhase', 'abortRef', 'STANDUP_TIMEOUT_MS', 'STANDUP_PROMPT',
  'STANDUP_MAX_TOKENS', 'HQ', 'snagSentence', 'agents', 'requestAnimationFrame',
  'standupRunningRef', '_start',
];

function buildStandup() {
  const inner = has('const _start = async () => {')
    ? bodyOf('const _start = async () => {') : null;
  const outer = bodyOf('const start = async () => {');
  // eslint-disable-next-line no-new-func
  const mkInner = inner ? new Function(...STANDUP_PARAMS, `return (async () => {${inner}});`) : null;
  // eslint-disable-next-line no-new-func
  const mkOuter = new Function(...STANDUP_PARAMS, `return (async () => {${outer}});`);
  return { mkInner, mkOuter };
}

function standupWorld(nAgents) {
  const calls = makeCalls();
  const agents = Array.from({ length: nAgents }, (_, i) => ({ id: 'a' + i, name: 'A' + i, role: 'r', color: 'sky', model: 'haiku' }));
  const w = {
    // A stand-up starts from 'idle' (▶ START) — the state the second
    // re-entrant call still sees, because setPhase hasn't committed.
    phase: 'idle',
    participating: agents,
    agents,
    setArchived: () => {}, setSummary: () => {}, setSummaryFail: () => {},
    setReports: () => {},
    setPhase: (p) => { calls.setPhase.push(p); },
    abortRef: { current: null },
    STANDUP_TIMEOUT_MS: 90000,
    STANDUP_PROMPT: 'report in',
    STANDUP_MAX_TOKENS: 200,
    HQ: makeHQ(calls),
    snagSentence, requestAnimationFrame,
    standupRunningRef: { current: false },
    calls,
  };
  return w;
}

async function runStandup(name, { times = 2, sequential = false, nAgents = 3 } = {}) {
  const w = standupWorld(nAgents);
  const { mkInner, mkOuter } = buildStandup();
  const args = STANDUP_PARAMS.map(n => (n === '_start' ? (mkInner ? mkInner(...STANDUP_PARAMS.map(m => m === '_start' ? null : w[m])) : null) : w[n]));
  const fn = mkOuter(...args);
  let threw = null;
  try {
    if (sequential) {
      for (let i = 0; i < times; i++) await fn();
    } else {
      // Re-entrant: fire N times back-to-back against ONE unchanged
      // snapshot, without awaiting between — a double-click lands before
      // any state the first call sets could have re-rendered anything.
      const ps = [];
      for (let i = 0; i < times; i++) ps.push(fn());
      await Promise.all(ps);
    }
  } catch (e) { threw = String((e && e.stack) || e); }
  console.log(JSON.stringify({
    scenario: name, threw, nAgents,
    agentStream: w.calls.agentStream.length,
    ceoStream: w.calls.ceoStream.length,
  }));
}

/* ── meeting room ───────────────────────────────────────────────────── */

const MEETING_PARAMS = [
  'input', 'streaming', 'setInput', 'setStreaming', 'newId', 'msgs',
  'liveParticipants', 'setMsgs', 'abortRef', 'HQ', 'floorEmit',
  'onUpdateAgent', 'snagSentence', 'requestAnimationFrame',
  'roundRunningRef', '_moderate',
];

function buildMeeting() {
  const inner = has('const _moderate = async () => {')
    ? bodyOf('const _moderate = async () => {') : null;
  const outer = bodyOf('const moderate = async () => {');
  // eslint-disable-next-line no-new-func
  const mkInner = inner ? new Function(...MEETING_PARAMS, `return (async () => {${inner}});`) : null;
  // eslint-disable-next-line no-new-func
  const mkOuter = new Function(...MEETING_PARAMS, `return (async () => {${outer}});`);
  return { mkInner, mkOuter };
}

let mtgId = 0;
function meetingWorld(nSeats) {
  const calls = makeCalls();
  const seats = Array.from({ length: nSeats }, (_, i) => ({ id: 's' + i, name: 'S' + i, color: 'sky' }));
  return {
    input: 'what is the plan?',
    streaming: false,           // the stale value a second click still sees
    setInput: () => {},
    setStreaming: (v) => { calls.setStreaming.push(v); },
    newId: () => 'mtg_' + (++mtgId),
    msgs: [],
    liveParticipants: seats,
    setMsgs: () => { calls.setMsgs.push(1); },
    abortRef: { current: null },
    HQ: makeHQ(calls),
    floorEmit: () => {},
    onUpdateAgent: () => {},
    snagSentence, requestAnimationFrame,
    roundRunningRef: { current: false },
    calls,
  };
}

async function runMeeting(name, { times = 2, sequential = false, nSeats = 3 } = {}) {
  const w = meetingWorld(nSeats);
  const { mkInner, mkOuter } = buildMeeting();
  const args = MEETING_PARAMS.map(n => (n === '_moderate' ? (mkInner ? mkInner(...MEETING_PARAMS.map(m => m === '_moderate' ? null : w[m])) : null) : w[n]));
  const fn = mkOuter(...args);
  let threw = null;
  try {
    if (sequential) {
      for (let i = 0; i < times; i++) await fn();
    } else {
      const ps = [];
      for (let i = 0; i < times; i++) ps.push(fn());
      await Promise.all(ps);
    }
  } catch (e) { threw = String((e && e.stack) || e); }
  console.log(JSON.stringify({
    scenario: name, threw, nSeats,
    agentStream: w.calls.agentStream.length,
    ceoStream: w.calls.ceoStream.length,
  }));
}

/* ── scenarios ──────────────────────────────────────────────────────── */

const main = async () => {
  // The race: one click's worth of intent, two events.
  await runStandup('standup-double-click', { times: 2 });
  await runStandup('standup-triple-click', { times: 3 });
  // Sanity: a plain single stand-up still runs exactly one round.
  await runStandup('standup-single', { times: 1 });
  // Not over-blocked: once a run has ENDED, RE-RUN must work again. This is
  // the stand-up's analogue of ## 390's "a different taskId still starts" —
  // the claim is scoped to a live round, not to the modal forever.
  await runStandup('standup-rerun-after-finish', { times: 2, sequential: true });

  await runMeeting('meeting-double-send', { times: 2 });
  await runMeeting('meeting-triple-send', { times: 3 });
  await runMeeting('meeting-single', { times: 1 });
  await runMeeting('meeting-second-round-after-finish', { times: 2, sequential: true });
};

main().catch(e => { console.error(e); process.exit(1); });
