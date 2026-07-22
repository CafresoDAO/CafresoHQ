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

/** Public URL of an entry's own graph blob (the worker-authored graphJson).
    Carries the Brave-harvest enrichment the flat entry JSON lacks — per-source
    publish dates + thumbnails, and the "people also ask" suggestion nodes. */
export function libraryEntryGraphUrl(id) {
  const base = libraryPublicBase();
  return base ? `${base}/library/${id}/graph.json` : '';
}

/** Fetch + parse an entry's graph blob into its raw node list, or [] on any
    failure. Shared by libraryEntryEnrichment (drawer) and libraryCardVisual
    (browse-grid cards) so the fetch/parse isn't duplicated. */
async function fetchEntryGraphNodes(id) {
  const url = libraryEntryGraphUrl(id);
  if (!url) return [];
  try {
    const r = await fetch(url);
    if (!r.ok) return [];
    const j = await r.json();
    let g = j && (j.graph || j);
    if (typeof g === 'string') g = JSON.parse(g);
    return (g && g.nodes) || [];
  } catch (_e) {
    return [];
  }
}

/** Distill an entry's graph blob into drawer-ready enrichment:
      { byUrl: Map<url,{age,img}>, suggests: [{q, a}], favicons: string[] }
    Returns null on any failure — the drawer just renders its plain sources. */
export async function libraryEntryEnrichment(id) {
  const nodes = await fetchEntryGraphNodes(id);
  const byUrl = new Map();
  const suggests = [];
  const favicons = [];
  for (const n of nodes) {
    const a = (n && n.attributes) || {};
    if (a.suggest) { if (a.label) suggests.push({ q: String(a.label).replace(/^✦\s*/, ''), a: a.snippet || '' }); }
    else if (a.url && (a.age || a.img)) byUrl.set(a.url, { age: a.age || '', img: a.img || '' });
    if (a.kind === 'domain' && a.favicon && /^https:\/\//.test(a.favicon)) favicons.push(a.favicon);
  }
  return (byUrl.size || suggests.length || favicons.length) ? { byUrl, suggests, favicons } : null;
}

// Module-level cache: a browse-grid page re-renders (filter/sort changes)
// without needing to refetch cards already visited this session.
const _cardVisualCache = new Map();

/** Cheap per-card visual for the browse grid: one hero thumbnail (the first
    Brave-harvested source image) and up to 3 source favicons, or null if the
    entry predates enrichment / carries neither. Cached per id — call once
    per card, not on every re-render. */
export async function libraryCardVisual(id) {
  if (_cardVisualCache.has(id)) return _cardVisualCache.get(id);
  const p = (async () => {
    const nodes = await fetchEntryGraphNodes(id);
    let thumb = null;
    const favicons = [];
    for (const n of nodes) {
      const a = (n && n.attributes) || {};
      if (!thumb && a.img && /^https:\/\//.test(a.img)) thumb = a.img;
      if (a.kind === 'domain' && a.favicon && /^https:\/\//.test(a.favicon) && favicons.length < 3) {
        favicons.push(a.favicon);
      }
    }
    return (thumb || favicons.length) ? { thumb, favicons } : null;
  })();
  _cardVisualCache.set(id, p);
  return p;
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

/** The same merged web, but the FULL interactive viewer — every control on
    (topic filter legend, node search, analytics, shortest-path). No chrome=none
    and no embed bridge: this opens standalone in a new tab, so the hero can stay
    a clean backdrop while "Explore the full graph" gives visitors the real tool. */
export function libraryFullGraphViewerUrl() {
  const base = libraryPublicBase();
  if (!base) return '';
  const g = encodeURIComponent(`${base}/library/graph.json`);
  return `${graphViewerOrigin()}/graph-viewer.html?g=${g}&background=dark&maxnodes=300&selected=highlight&show_analytics=1`;
}

/** The full viewer with the growth replay auto-playing on load — the library
    re-asks itself in chronological order. The hero's "watch it grow" link. */
export function libraryReplayGraphViewerUrl() {
  const u = libraryFullGraphViewerUrl();
  return u ? `${u}&replay=1` : '';
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
