// ─────────────────────────────────────────────────────────────────────────────
// Ai Cafreso Search — anonymous network client.
//
// Everything here is plain fetch against the state canister's public HTTP
// routes — no identity, no agent, works for a signed-out visitor on
// cafreso.com. The flow the UI composes: findPublic (library cache) →
// networkHealth (are workers online?) → submitJob → pollJob. All functions
// resolve null / safe defaults instead of throwing so UI states stay honest
// without try/catch pyramids.
// ─────────────────────────────────────────────────────────────────────────────
import { libraryPublicBase } from './library.js';

const TIMEOUT_MS = 15_000;

async function jget(path) {
  const base = libraryPublicBase();
  if (!base) return null;
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    const r = await fetch(base + path, { signal: ctrl.signal });
    clearTimeout(t);
    if (!r.ok) return null;
    return await r.json();
  } catch (_e) {
    return null;
  }
}

/** Exact library hit for a query (normalized server-side) or null. */
export function findPublic(q) {
  return jget('/library/find.json?q=' + encodeURIComponent(q));
}

/** {workers, activeWorkers, pending, answeredToday, budget, entries, payoutsEnabled} | null. */
export function networkHealth() {
  return jget('/search/health.json');
}

/** Newest library summaries: {count, entries:[{id, query, ts, sources}]} | null. */
export function libraryIndex() {
  return jget('/library/index.json');
}

/** Full entry by id (answer, sources, provenance, graphUrl) | null. */
export function libraryEntry(id) {
  return jget('/library/' + encodeURIComponent(id) + '.json');
}

/**
 * Queue a query on-chain. Returns:
 *   {status:'hit', entry} | {status:'queued', jobId} |
 *   {status:'rejected', reason:'busy'|'budget'|'dark'|'bad-query'} | null (offline)
 *
 * `deep:true` submits a Deep Research job (?mode=deep): a worker runs the
 * multi-angle HQ research loop instead of a single-shot answer. Deep jobs draw
 * on a separate, smaller daily budget on-chain, so a 'budget' rejection here
 * means the deep lane is spent for the day — not the fast one.
 */
export async function submitJob(q, { deep = false } = {}) {
  const base = libraryPublicBase();
  if (!base) return null;
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    const r = await fetch(base + '/search/submit' + (deep ? '?mode=deep' : ''), {
      method: 'POST',
      headers: { 'content-type': 'text/plain' },   // simple request → no CORS preflight
      body: encodeURIComponent(q),
      signal: ctrl.signal
    });
    clearTimeout(t);
    if (!r.ok) return null;
    return await r.json();
  } catch (_e) {
    return null;
  }
}

/** The multi-angle note pages behind a deep-research entry:
    {q, answer, pages:[{id, title, question, body, sources}], ts} | null. */
export function libraryResearch(id) {
  return jget('/library/' + encodeURIComponent(id) + '/research.json');
}

/** {status:'pending'|'claimed'|'done'|'failed'|'expired', entry?} | null. */
export function pollJob(jobId) {
  return jget('/search/job/' + encodeURIComponent(jobId) + '.json');
}

/**
 * Poll until the job reaches a terminal state or ~maxMs elapses.
 * onTick(status, elapsedMs) fires per poll so the UI can narrate progress.
 *
 * maxMs tracks the worker's own budget (WORKER_JOB_BUDGET, 200s) rather than
 * the old 90s: the canister's claim lease is 240s, so giving up at 90s showed
 * a healthy worker's 120s answer as "still researching" — a failure state for
 * a job that actually succeeded.
 */
export async function awaitJob(jobId, { maxMs = 200_000, intervalMs = 3_000, onTick = (_status, _elapsedMs) => {} } = {}) {
  const t0 = Date.now();
  while (Date.now() - t0 < maxMs) {
    await new Promise((res) => setTimeout(res, intervalMs));
    const st = await pollJob(jobId);
    if (!st) continue;
    if (onTick) onTick(st.status, Date.now() - t0);
    if (st.status === 'done' || st.status === 'failed' || st.status === 'expired') return st;
  }
  return { status: 'timeout' };
}
