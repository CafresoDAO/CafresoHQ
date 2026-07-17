// ─────────────────────────────────────────────────────────────────────────────
// Ai Cafreso Search — public library client (cafresohq_state.library_*)
//
// The library is the search flywheel: every EXPLICITLY published query becomes
// a public, on-chain {query, answer, sources, graph} entry that (a) answers
// repeat searches instantly without hitting Brave, and (b) merges into the
// public graph view. Publishing is always a deliberate user action — searching
// alone never writes anything here.
//
// Until the ONE cafresohq_state upgrade lands, the library_* methods don't
// exist on mainnet yet: every call throws, and publishToLibrary() queues the
// entry in localStorage so it can be retried after the upgrade.
// ─────────────────────────────────────────────────────────────────────────────
import { get } from 'svelte/store';
import { getStateActor, stateCanisterId, stateCanisterConfigured } from './stateActor.js';
import { HQ_UI_CANISTER_ORIGIN } from '$lib/config.js';

const PENDING_KEY = 'cafreso:library:pending';

/** Public (no-session) base URL for library reads served by the canister.
    localStorage 'cafreso:library-base' overrides for local-replica dev. */
export function libraryPublicBase() {
  try {
    const o = localStorage.getItem('cafreso:library-base');
    if (o) return o.replace(/\/$/, '');
  } catch (_e) {}
  const id = get(stateCanisterId);
  return id ? `https://${id}.icp0.io` : '';
}

/** Where graph-viewer.html is served from. The hq-ui canister in production;
    a localStorage override ('cafreso:graphviewer-origin') for local dev, where
    the https canister page can't fetch a http://localhost graph (mixed content). */
export function graphViewerOrigin() {
  try {
    const o = localStorage.getItem('cafreso:graphviewer-origin');
    if (o) return o.replace(/\/$/, '');
  } catch (_e) {}
  return HQ_UI_CANISTER_ORIGIN;
}

/** Fully public graph-viewer link for a library entry — canister-hosted end to end.

    For a deep-research entry, pass `{ deep:true }` to also hand the viewer the
    entry's note pages (`&pages=<research.json>`): the research tree then opens
    the note page IN the viewer when a topic node is clicked, instead of only
    linking sources out — the "explorable research" experience. */
export function libraryGraphViewerUrl(id, { deep = false } = {}) {
  const base = libraryPublicBase();
  if (!base) return '';
  const g = encodeURIComponent(`${base}/library/${id}/graph.json`);
  let url = `${graphViewerOrigin()}/graph-viewer.html?g=${g}&background=dark&maxnodes=150&selected=highlight`;
  if (deep) url += `&pages=${encodeURIComponent(`${base}/library/${id}/research.json`)}`;
  return url;
}

/** Public URL of a deep entry's note pages (research.json), or '' if unconfigured. */
export function libraryResearchUrl(id) {
  const base = libraryPublicBase();
  return base ? `${base}/library/${id}/research.json` : '';
}

/** The whole library as one neural web — the /library page hero. Runs with
    chrome=none: the hero overlays its own headline and search box, so the
    viewer's controls would only compete with them. */
export function libraryMergedGraphViewerUrl() {
  const base = libraryPublicBase();
  if (!base) return '';
  const g = encodeURIComponent(`${base}/library/graph.json`);
  // embed=post: clicking a question node posts to this page (opens the in-page
  // drawer) instead of a new tab. embedorigin pins postMessage's target so the
  // message can't leak to a hostile framer.
  const origin = (typeof location !== 'undefined' && location.origin) || 'https://cafreso.com';
  return `${graphViewerOrigin()}/graph-viewer.html?g=${g}&background=dark&maxnodes=300&selected=highlight&chrome=none`
    + `&embed=post&embedorigin=${encodeURIComponent(origin)}`;
}

/** Library-first lookup: exact normalized-query hit or null. Never throws. */
export async function findInLibrary(q) {
  if (!stateCanisterConfigured()) return null;
  try {
    const actor = await getStateActor();
    const res = await actor.library_find(q);
    return res && res.length ? res[0] : null;   // Candid ?T → [] | [T]
  } catch (_e) {
    return null;   // canister not upgraded yet / offline → just search the web
  }
}

/**
 * Publish an entry (explicit opt-in). Returns:
 *   { status: 'ok', id, existing, publicUrl, viewerUrl }
 *   { status: 'queued' }  — canister method not live yet; saved locally
 *   { status: 'error', error }
 */
export async function publishToLibrary({ q, answer, sources, graphJson, model, searchEngine }) {
  const entry = {
    q: String(q).slice(0, 400),
    answer: String(answer || '').slice(0, 4000),
    sources: (sources || []).slice(0, 10).map((s) => ({
      title: String(s.title || '').slice(0, 600),
      url: String(s.url || '').slice(0, 600)
    })),
    graphJson: String(graphJson || ''),
    model: String(model || '').slice(0, 80),
    searchEngine: String(searchEngine || '').slice(0, 80)
  };
  try {
    const actor = await getStateActor();
    const res = await actor.library_put(entry.q, entry.answer, entry.sources, entry.graphJson,
                                        entry.model, entry.searchEngine);
    if ('err' in res) return { status: 'error', error: res.err };
    const { id, existing } = res.ok;
    return {
      status: 'ok', id, existing,
      publicUrl: `${libraryPublicBase()}/library/${id}.json`,
      viewerUrl: libraryGraphViewerUrl(id)
    };
  } catch (e) {
    const msg = e?.message || String(e);
    // Method missing = the state canister predates the library (upgrade pending).
    if (/has no (update|query) method|method not found|Canister trapped/i.test(msg)) {
      queuePending(entry);
      return { status: 'queued' };
    }
    return { status: 'error', error: msg };
  }
}

/** Latest library summaries (for a future public browse page). */
export async function listLibrary(offset = 0, limit = 50) {
  const actor = await getStateActor();
  return actor.library_list(BigInt(offset), BigInt(limit));
}

// ── Pending queue (pre-upgrade) ─────────────────────────────────────────────
function readPending() {
  try { return JSON.parse(localStorage.getItem(PENDING_KEY) || '[]'); }
  catch (_e) { return []; }
}
function queuePending(entry) {
  const all = readPending().filter((p) => p.q !== entry.q);
  all.push({ ...entry, queuedAt: Date.now() });
  try { localStorage.setItem(PENDING_KEY, JSON.stringify(all.slice(-50))); } catch (_e) {}
}
export function pendingCount() { return readPending().length; }

/** Retry every queued publish; returns how many landed. Call after the upgrade. */
export async function flushPending() {
  const all = readPending();
  if (!all.length) return 0;
  let ok = 0;
  const remaining = [];
  for (const p of all) {
    const res = await publishToLibrary(p);
    if (res.status === 'ok') ok += 1;
    else if (res.status === 'queued') return ok;   // still not upgraded; stop
    else remaining.push(p);
  }
  try { localStorage.setItem(PENDING_KEY, JSON.stringify(remaining)); } catch (_e) {}
  return ok;
}
