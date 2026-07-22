/**
 * graph-viewer.js — standalone READ-ONLY public graph viewer (sigma + graphology).
 *
 * Bundled by esbuild into dist-ui/graph-viewer.js and paired with graph-viewer.html.
 * Renders a snapshot produced by graph-engine.js exportSnapshot() or by the search
 * worker's _sw_graph: colors and seed positions arrive precomputed, and this viewer
 * settles them with a live ForceAtlas2 pass so the web drifts and calms the way
 * Obsidian's graph view does, instead of landing frozen.
 *
 * Mirrors the InfraNodus share-URL contract:
 *   ?g=<snapshot-url>  &background=dark|default
 *   &most_influential=bc|bc2  &maxnodes=N  &labelsize=proportional
 *   &drawedges=true|false  &selected=highlight  &dynamic=highlight
 *   &show_analytics=1  &layout=none  &demo=1
 * plus one of our own:
 *   &chrome=none        — backdrop mode; hide every persistent control
 *
 * Physics runs on the main thread in small rAF-stepped bursts rather than through
 * graphology's FA2 web-worker: that worker is spawned from a blob: URL, and the
 * canister serves `script-src 'self' 'unsafe-inline'` with no worker-src, so the
 * blob path is blocked in production. Stepping forceAtlas2.assign() also re-reads
 * each node's `fixed` flag every call, which is what lets a dragged node pin
 * itself mid-simulation. At library scale (tens to a few hundred nodes) a burst
 * costs well under a millisecond.
 *
 * The web is meant to read as a nervous system rather than a diagram, which is
 * three things working together:
 *   structure — hover falls off by hop distance (BFS), not in/out of a set, so
 *               attention has a gradient the way activation does;
 *   motion    — signals travel the edges: idle firing at rest, and a pulse that
 *               propagates outward hop by hop from whatever you touch;
 *   growth    — nodes absent from the last visit ignite on arrival, so an
 *               ever-expanding library shows you what it grew.
 * Signals draw on their own Canvas2D layer registered with sigma (it clears only
 * labels/hovers/edgeLabels, and sizes every registered context on resize), so
 * they ride the live physics positions without touching sigma's render path.
 */
import Graph from 'graphology';
import Sigma from 'sigma';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import louvain from 'graphology-communities-louvain';
import { bidirectional } from 'graphology-shortest-path/unweighted';
import betweennessCentrality from 'graphology-metrics/centrality/betweenness';
import modularity from 'graphology-metrics/graph/modularity';

const qs = new URLSearchParams(location.search);
const P = (k, d) => { const v = qs.get(k); return v == null ? d : v; };

function titleOf(id) { return String(id).split('/').pop().replace(/\.md$/, ''); }

/* Node identity stays in the snapshot's colors; gold is reserved as the single
   "attention" channel (hover, halo, adjacent edges) so the two never compete.
   Edge alphas are tuned against premultiplied blending (see glRgba) — at rest
   they land a hairline just above the plane, ~rgb(53,48,42) on dark.
   `spark` is a third channel, deliberately hotter than gold: growth is data
   saying something, not the cursor, and the two must never be confused. */
const THEME = {
  dark: {
    bg: '#14110E',
    // Resting edges sit just above the visibility floor: at 300 nodes / 577
    // links the web at 0.18 read as fog behind the dense core. Hover heat and
    // the hot channel carry the structure when you actually ask for it.
    edge: [201, 191, 169, 0.10], edgeDim: [201, 191, 169, 0.02], edgeHot: [245, 210, 93, 0.7],
    nodeDim: [38, 33, 25], label: [220, 211, 192], ring: 'rgba(245,210,93,0.9)',
    pulse: [245, 210, 93], spark: [255, 243, 208],
  },
  light: {
    bg: '#F6F1E7',
    edge: [92, 82, 64, 0.12], edgeDim: [92, 82, 64, 0.03], edgeHot: [158, 112, 20, 0.7],
    nodeDim: [230, 222, 206], label: [58, 52, 43], ring: 'rgba(158,112,20,0.9)',
    pulse: [158, 112, 20], spark: [186, 106, 12],
  },
};

const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const smoothstep = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t));

function parseColor(c) {
  const s = String(c || '').trim();
  let m = /^#([0-9a-f]{6})$/i.exec(s);
  if (m) { const n = parseInt(m[1], 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
  m = /^#([0-9a-f]{3})$/i.exec(s);
  if (m) { const h = m[1]; return [parseInt(h[0] + h[0], 16), parseInt(h[1] + h[1], 16), parseInt(h[2] + h[2], 16)]; }
  m = /^rgba?\(([^)]+)\)$/i.exec(s);
  if (m) { const p = m[1].split(',').map(Number); return [p[0] | 0, p[1] | 0, p[2] | 0]; }
  return [202, 191, 169];
}
const rgbCss = (c) => 'rgb(' + (c[0] | 0) + ',' + (c[1] | 0) + ',' + (c[2] | 0) + ')';
const rgbaCss = (c, a) => 'rgba(' + (c[0] | 0) + ',' + (c[1] | 0) + ',' + (c[2] | 0) + ',' + a + ')';
/* Sigma's WebGL layers blend premultiplied (gl.ONE, gl.ONE_MINUS_SRC_ALPHA) but
   hand the shader raw rgba out of floatColor(), and nothing premultiplies in
   between — so a plain alpha fade still paints its rgb at full strength, and
   "7% opacity" edges come out nearly white. Premultiply here for anything WebGL
   draws (nodes, edges). Canvas2D layers — labels, halo — must NOT use this. */
const glRgba = (c, a) => 'rgba(' + Math.round(c[0] * a) + ',' + Math.round(c[1] * a) + ',' + Math.round(c[2] * a) + ',' + a + ')';
const lerp = (a, b, t) => a + (b - a) * t;
const lerpRgb = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];

async function main() {
  const container = document.getElementById('graph');
  const dark = !['default', 'light'].includes(P('background', 'dark'));
  const T = dark ? THEME.dark : THEME.light;
  document.body.style.background = T.bg;
  document.body.classList.toggle('gv-light', !dark);

  const compact = () => container.clientHeight < 420 || container.clientWidth < 560;
  document.body.classList.toggle('gv-compact', compact());
  // chrome=none: the graph is a backdrop (the library hero overlays its own
  // headline and search on top), so every persistent control would just compete
  // with that page's copy. Hover and its tip card still work. Applied before the
  // fetch so a failure message doesn't surface the chrome we were asked to hide.
  document.body.classList.toggle('gv-nochrome', P('chrome', '') === 'none');

  const src = P('g', null) || P('graph', null);
  // Deep-research note pages (research.json): when present, a topic node opens
  // its note page IN this viewer instead of linking out — the explorable
  // research tree. Fetched lazily on the first topic-node click.
  const pagesSrc = P('pages', null);
  let pagesData = null, pagesReq = null;
  async function loadPages() {
    if (pagesData) return pagesData;
    if (!pagesSrc) return null;
    if (!pagesReq) pagesReq = fetch(pagesSrc).then((r) => r.json()).catch(() => null);
    pagesData = await pagesReq;
    return pagesData;
  }
  // Curated topic filters (topics.json) — the 6-hourly worker cron summarizes
  // the library's questions into named topics with `match` terms. When present
  // they replace the client-side Louvain topic legend; when absent (fetch fails
  // or cron hasn't run) the Louvain fallback stands. Default URL is derived from
  // the graph snapshot's own path, overridable with &topics=.
  const topicsSrc = P('topics', null)
    || (src && /\/library\/graph\.json/.test(src) ? src.replace(/\/library\/graph\.json.*$/, '/library/topics.json') : null);
  let curatedReq = null;
  async function loadCuratedTopics() {
    if (!topicsSrc) return null;
    if (!curatedReq) curatedReq = fetch(topicsSrc)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => (j && Array.isArray(j.topics) ? j.topics : null))
      .catch(() => null);
    return curatedReq;
  }
  // Full entry JSON (query + answer + sources) for the in-viewer reader drawer —
  // served at /library/<id>.json on the same canister as the graph snapshot. Lets
  // a question-node click pop the answer open INSIDE the graph instead of
  // navigating the whole tab away. Derived from the snapshot path; null (→ the
  // click falls back to navigation) for a non-library graph.
  const entryBase = src && /\/library\/graph\.json/.test(src)
    ? src.replace(/\/library\/graph\.json.*$/, '/library/') : null;
  const entryReqs = new Map();
  function loadEntry(id) {
    if (!entryBase) return Promise.resolve(null);
    if (!entryReqs.has(id)) {
      entryReqs.set(id, fetch(entryBase + encodeURIComponent(id) + '.json')
        .then((r) => (r.ok ? r.json() : null)).catch(() => null));
    }
    return entryReqs.get(id);
  }
  // Shared search-network client — the magnifying glass AND the drawer's
  // dig-deeper button both run this: exact library hit → submit (?mode=news|deep)
  // → poll. Resolves to an entry id; rejects with a user-facing message.
  const searchApiBase = entryBase ? entryBase.replace(/\/library\/$/, '') : null;
  async function netResearch(query, mode, onStatus) {
    if (!searchApiBase) throw new Error('Not a library graph');
    const say = onStatus || (() => {});
    const jget = (p) => fetch(searchApiBase + p).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    say('Checking the library…');
    const hit = await jget('/library/find.json?q=' + encodeURIComponent(query));
    if (hit && hit.id) return hit.id;
    const health = await jget('/search/health.json');
    if (!health || !health.activeWorkers) throw new Error('Search network is asleep — try later');
    say(mode === 'deep' ? 'Deep research queued — takes a few minutes…' : 'Researching — a worker is on it…');
    const sub = await fetch(searchApiBase + '/search/submit' + (mode && mode !== 'fast' ? '?mode=' + mode : ''),
      { method: 'POST', headers: { 'content-type': 'text/plain' }, body: encodeURIComponent(query) })
      .then((r) => (r.ok ? r.json() : null)).catch(() => null);
    if (!sub) throw new Error('Network unavailable — try again');
    if (sub.status === 'hit' && sub.entry) return sub.entry.id;
    if (sub.status === 'rejected') {
      throw new Error(sub.reason === 'budget' ? "Today's research budget is spent"
        : sub.reason === 'deep-budget' ? "Today's deep-research budget is spent"
        : 'Network busy — try again shortly');
    }
    if (sub.status !== 'queued' || !sub.jobId) throw new Error('Could not queue that one');
    // Deep jobs run a multi-hop loop under a ~6.3-min canister lease — poll well
    // past it so a slow-but-successful run still lands in this session.
    const limit = mode === 'deep' ? 460000 : 200000;
    const t0 = Date.now();
    while (Date.now() - t0 < limit) {
      await new Promise((r) => setTimeout(r, 3000));
      const stt = await jget('/search/job/' + encodeURIComponent(sub.jobId) + '.json');
      if (!stt) continue;
      if (Date.now() - t0 > 45000) say(mode === 'deep' ? 'Deep research running — notes are being written…' : 'Still researching — a slow one…');
      if (stt.status === 'done' && stt.entry) return stt.entry.id;
      if (stt.status === 'failed' || stt.status === 'expired') throw new Error('No answer this time — try rephrasing');
    }
    throw new Error('Timed out — it may still land in the library');
  }
  let snap = window.__SNAPSHOT__ || null;
  try { if (!snap && src) snap = await (await fetch(src)).json(); }
  catch (_) { container.textContent = 'Could not load this graph.'; return; }
  if (!snap || !snap.graph) { container.textContent = 'No graph data.'; return; }

  let g;
  try { g = Graph.from(snap.graph); } catch (_) { container.textContent = 'Invalid graph data.'; return; }

  // most_influential=bc2 → re-size nodes by diversity (BC/degree) from analytics.
  const infl = P('most_influential', 'bc');
  if (infl === 'bc2' && snap.analytics && snap.analytics.nodeAttrs) {
    const na = snap.analytics.nodeAttrs; let max = 0;
    for (const id in na) max = Math.max(max, na[id].bc2 || 0);
    g.forEachNode((id) => { const v = na[id] ? na[id].bc2 : 0; g.setNodeAttribute(id, 'size', 3 + (max > 0 ? Math.sqrt(v / max) * 13 : 0)); });
  }

  // maxnodes: keep the N most influential (by size), drop the rest.
  const maxn = parseInt(P('maxnodes', '0'), 10);
  if (maxn > 0 && g.order > maxn) {
    const keep = new Set(g.nodes().sort((a, b) => (g.getNodeAttribute(b, 'size') || 0) - (g.getNodeAttribute(a, 'size') || 0)).slice(0, maxn));
    g.forEachNode((n) => { if (!keep.has(n)) g.dropNode(n); });
  }

  // Blend the snapshot's own weighting with degree: the snapshot sizes a query
  // hub by betweenness, but Obsidian's read of "important" is how many things
  // connect here, and the blend keeps both legible after maxnodes pruning.
  /* ── library mode ────────────────────────────────────────────────────────
     The merged library snapshot marks question nodes with `entryId` (the
     on-chain entry the node IS) and carries domain nodes with hash-random
     palette colors. When that shape is detected:
       · labels get clamped (questions arrive as full 70-char sentences that
         spill off the canvas), with the full text kept for the tip and search;
       · Louvain communities recolor the domain nodes, so color becomes topic
         structure instead of hash noise — and the legend can honestly name
         each cluster after its biggest question. Questions stay gold: that is
         their identity channel, and the topic tint belongs to the sources. */
  const fullLabel = new Map();
  const LABEL_MAX = 44;
  let libMode = false;
  g.forEachNode((id, a) => {
    fullLabel.set(id, a.label || '');
    if (a.entryId) libMode = true;
    if ((a.label || '').length > LABEL_MAX) {
      g.setNodeAttribute(id, 'label', a.label.slice(0, LABEL_MAX - 2).trimEnd() + '…');
    }
    // Ghost "people also wonder" questions read as invitations, not answers —
    // the ✦ marks them apart from real (answered) question nodes.
    if (a.suggest) g.setNodeAttribute(id, 'label', '✦ ' + g.getNodeAttribute(id, 'label'));
  });

  // community -> {color, size, topLabel} — built only when the recolor runs.
  let commOf = null, commMeta = null;
  const COMM_PALETTE = ['#7DC9B0', '#C9B8E0', '#E8A9A9', '#F0C987', '#9BC0E8', '#B8E09A', '#E0A47C', '#D89BE0'];
  if (libMode && g.order > 12) {
    try {
      // Seeded rng (mulberry32): louvain's random node walk is the last source
      // of run-to-run variance in the layout pipeline. With it pinned, the same
      // snapshot always yields the same communities, the same ring order, and —
      // via the fixed-iteration bloom — the same settled map, so "News lives
      // top-right" stays true between loads.
      let rs = 0x9e3779b9;
      const rng = () => {
        rs = (rs + 0x6D2B79F5) | 0;
        let t = Math.imul(rs ^ (rs >>> 15), 1 | rs);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
      };
      commOf = louvain(g, { rng });
      const bySize = new Map();
      g.forEachNode((id) => {
        const c = commOf[id];
        bySize.set(c, (bySize.get(c) || 0) + 1);
      });
      const ranked = [...bySize.entries()].sort((a, b) => b[1] - a[1]);
      commMeta = new Map();
      ranked.forEach(([c, n], i) => commMeta.set(c, { color: COMM_PALETTE[i % COMM_PALETTE.length], size: n, topLabel: '', topSize: -1 }));
      g.forEachNode((id, a) => {
        // Name each topic after its most-connected question — a question names
        // a topic the way a domain never can.
        const m = commMeta.get(commOf[id]);
        if (a.entryId && m && g.degree(id) > m.topSize) { m.topSize = g.degree(id); m.topLabel = fullLabel.get(id) || ''; }
        // Recolor sources only; gold stays the question channel.
        if (!a.entryId && m) g.setNodeAttribute(id, 'color', m.color);
      });
      // Loosen the glue between communities so the layout opens into distinct
      // islands instead of one hairball: cross-community edges pull at a
      // fraction of within-community strength (FA2 reads the 'weight' edge
      // attribute when edgeWeightInfluence is on — unused here otherwise).
      g.forEachEdge((e, attrs, s, t) => {
        g.setEdgeAttribute(e, 'weight', commOf[s] === commOf[t] ? 1 : 0.15);
      });
    } catch (_) { commOf = null; commMeta = null; }
  }

  /* ── view topics ─────────────────────────────────────────────────────────
     One shared topic model feeding three consumers: the legend rows, the
     on-canvas cluster labels (the InfraNodus read — "News is over THERE"),
     and the topic color mode. Starts from the Louvain clusters, swapped for
     the cron's curated topics.json when that loads — same shape either way:
       { key, label, color, set:Set<nodeId> }
     Sets are cached at build time: nodes() per frame would be O(N·topics). */
  let viewTopics = [];
  let topicByNode = new Map();   // node -> topic (first/biggest match wins)
  let activeTopic = null;        // key | null — the engaged legend/label filter
  let onTopicsChanged = [];      // consumers re-render when the model swaps
  // Declared here (not in the hover/search block below) because
  // installViewTopics runs at load, before that block would initialize it.
  let topicSet = null;

  function installViewTopics(list) {
    viewTopics = list;
    topicByNode = new Map();
    for (const t of list) {
      for (const id of t.set) if (!topicByNode.has(id)) topicByNode.set(id, t);
    }
    activeTopic = null; topicSet = null;
    for (const fn of onTopicsChanged) { try { fn(); } catch (_) {} }
  }

  if (commMeta && commMeta.size > 1) {
    installViewTopics([...commMeta.entries()]
      .filter(([, m]) => m.topLabel)
      .sort((a, b) => b[1].size - a[1].size).slice(0, 7)
      .map(([c, m]) => {
        const s = new Set();
        g.forEachNode((id) => { if (commOf[id] === c) s.add(id); });
        return { key: 'c' + c, label: m.topLabel, color: m.color, set: s };
      }));
  }

  // Curated topics (topics.json) replace the Louvain naming when they arrive
  // and actually match nodes — real category names ("News", "Health") beat a
  // cluster named after its biggest question.
  loadCuratedTopics().then((curated) => {
    if (!curated || !curated.length) return;
    const list = curated.map((t, i) => {
      const terms = (Array.isArray(t.match) && t.match.length ? t.match : [t.label])
        .map((s) => String(s || '').toLowerCase()).filter(Boolean);
      const s = new Set();
      g.forEachNode((id) => {
        const lab = String(fullLabel.get(id) || '').toLowerCase();
        if (terms.some((term) => lab.includes(term))) s.add(id);
      });
      return { key: 'k' + i, label: String(t.label || ''), color: COMM_PALETTE[i % COMM_PALETTE.length], set: s };
    }).filter((t) => t.label && t.set.size > 0);
    if (list.length) installViewTopics(list);
  });

  /* ── provenance (Graph Styler-style rule coloring) ───────────────────────
     index.json carries askedBy per entry: 'human' | 'ai-gap' | 'ai-news'.
     Fetched lazily the first time the Origin color mode is selected. */
  let provReq = null;
  function loadProvenance() {
    if (!entryBase) return Promise.resolve(null);
    if (!provReq) provReq = fetch(entryBase + 'index.json')
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        const m = new Map();
        // ts is nanoseconds; kept as Number — the 2^53 precision loss is far
        // below the ordering granularity replay needs.
        for (const e of (j && j.entries) || []) {
          if (e.id) m.set(e.id, { askedBy: e.askedBy || 'human', ts: Number(e.ts) || 0 });
        }
        return m.size ? m : null;
      })
      .catch(() => null);
    return provReq;
  }
  const ORIGIN_COLORS = { human: '#F5D25D', 'ai-gap': '#C9B8E0', 'ai-news': '#9BC0E8' };
  let colorMode = 'identity';   // 'identity' | 'topic' | 'origin' | 'fresh'
  let provOf = null;

  /* Freshness ramp: newest → oldest as warm gold → deep slate. Fed by two
     sources depending on what the graph carries — a question's answer date
     (prov ts, present in the merged web) and a source's publish date (the
     Brave-harvested `age` attr, present in enriched per-entry graphs). Nodes
     with no date get a distinct true-gray (not a ramp endpoint) so "unknown"
     is never one step from misreading as "oldest".
     Two ramps: dark-theme stops read fine on the near-black plane, but at
     light-theme contrast the same values land under 2:1 against parchment
     (the amber/gold stops especially) — light gets its own darker, more
     saturated stops so freshest still reads as the boldest color either way. */
  const FRESH_STOPS = dark
    ? [[245, 158, 66], [245, 210, 93], [155, 192, 232], [90, 86, 120]]
    : [[196, 100, 20], [176, 120, 10], [50, 92, 158], [70, 66, 96]];
  const FRESH_UNDATED = dark ? [110, 108, 112] : [150, 145, 138];
  function freshColor(t) {                 // t in [0,1]: 0 newest, 1 oldest
    const s = clamp(t, 0, 1) * (FRESH_STOPS.length - 1);
    const i = Math.min(FRESH_STOPS.length - 2, Math.floor(s)), f = s - i;
    const a = FRESH_STOPS[i], b = FRESH_STOPS[i + 1];
    return [0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * f));
  }
  function nodeEpochMs(id, a) {
    if (a.entryId && provOf) { const ts = (provOf.get(a.entryId) || {}).ts; if (ts) return ts / 1e6; }
    const age = a.age;                     // ISO 'YYYY-MM-DD' or free text ("2 hours ago")
    if (age && /^\d{4}-\d{2}-\d{2}/.test(age)) { const ms = Date.parse(age); if (!isNaN(ms)) return ms; }
    return null;
  }
  async function applyColorMode(mode) {
    colorMode = mode;
    if ((mode === 'origin' || mode === 'fresh') && !provOf) provOf = await loadProvenance();
    if (mode === 'fresh') {
      // One shared min/max over every datable node so questions and sources
      // land on the same timeline — a fresh source and a fresh question read
      // the same warm.
      let lo = Infinity, hi = -Infinity;
      g.forEachNode((id, a) => { const t = nodeEpochMs(id, a); if (t != null) { if (t < lo) lo = t; if (t > hi) hi = t; } });
      const span = hi - lo;
      g.forEachNode((id, a) => {
        const t = nodeEpochMs(id, a);
        const c = t == null ? FRESH_UNDATED : freshColor(span > 0 ? 1 - (t - lo) / span : 0);
        g.setNodeAttribute(id, 'color', rgbCss(c));
        baseRgb.set(id, c);
      });
      renderer.refresh({ skipIndexation: true });
      return;
    }
    g.forEachNode((id, a) => {
      if (!a.entryId) {
        // Leaving 'fresh' mode: it's the only mode that retints non-question
        // nodes, so restore them — otherwise a domain/source node stays
        // stuck on the freshness ramp forever after the first switch away.
        const orig = origRgb.get(id);
        if (orig && baseRgb.get(id) !== orig) {
          g.setNodeAttribute(id, 'color', rgbCss(orig));
          baseRgb.set(id, orig);
        }
        return;
      }
      let c = '#F5D25D';
      if (mode === 'topic') { const t = topicByNode.get(id); if (t) c = t.color; }
      else if (mode === 'origin' && provOf) c = ORIGIN_COLORS[(provOf.get(a.entryId) || {}).askedBy] || '#F5D25D';
      g.setNodeAttribute(id, 'color', c);
      baseRgb.set(id, parseColor(c));
    });
    renderer.refresh({ skipIndexation: true });
  }

  const baseRgb = new Map();   // node -> [r,g,b] as authored (dim lerps from this)
  const baseSize = new Map();
  // Immutable snapshot of each node's ORIGINAL color, taken once here before
  // any color mode runs. 'fresh' mode recolors every node including
  // domains/sources (unlike topic/origin, which only ever retint questions),
  // so switching away from 'fresh' needs something to restore non-question
  // nodes back to — without this they'd stay stuck on the freshness ramp.
  const origRgb = new Map();
  const minSize = compact() ? 3 : 2.5;
  g.forEachNode((id, a) => {
    const degSize = 2 + Math.sqrt(g.degree(id)) * 1.6;
    const snapSize = typeof a.size === 'number' ? a.size : 4;
    const size = clamp(0.45 * snapSize + 0.55 * degSize, minSize, 14);
    g.setNodeAttribute(id, 'size', size);
    baseSize.set(id, size);
    const rgb = parseColor(a.color);
    baseRgb.set(id, rgb);
    origRgb.set(id, rgb);
  });

  const drawEdges = P('drawedges', 'true') !== 'false';
  const highlight = P('selected', 'highlight') === 'highlight' || P('dynamic', '') === 'highlight';
  const proportional = P('labelsize', '') === 'proportional';
  const reduceMotion = (() => { try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (_) { return false; } })();
  const coarse = (() => { try { return matchMedia('(pointer: coarse)').matches; } catch (_) { return false; } })();

  /* ── circle-bloom intro (ported from graph-engine.js) ────────────────────
     Discard the snapshot's pre-baked ball and seed every node onto a clean
     evenly-spaced ring, grouped so each Louvain community owns a contiguous
     arc. The intro holds this circle briefly (see the delayed warm() at the
     bottom), then FA2 blooms it into formation — and because same-community
     nodes start adjacent and cross-community edges are down-weighted, the
     bloom settles into separated islands instead of re-forming the hairball.
     The ring's absolute radius is irrelevant: sim frames re-index, so sigma
     refits its normalization as the layout expands. Deterministic jitter
     (same trick as graph-engine) breaks the ring's symmetry for FA2. */
  let ringSeeded = false;
  if (commOf && P('layout', 'fa2') !== 'none' && g.order <= 600 && !reduceMotion) {
    const byComm = new Map();
    for (const c of commMeta.keys()) byComm.set(c, []);
    const stray = [];
    g.forEachNode((id) => {
      const bucket = byComm.get(commOf[id]);
      (bucket || stray).push(id);
    });
    const order = [...byComm.values()].flat().concat(stray);
    const R = 10 + Math.sqrt(order.length) * 1.5;
    order.forEach((id, i) => {
      const a = (i / Math.max(1, order.length)) * Math.PI * 2;
      g.setNodeAttribute(id, 'x', Math.cos(a) * R + (((i * 37) % 11) - 5) * 0.15);
      g.setNodeAttribute(id, 'y', Math.sin(a) * R + (((i * 53) % 13) - 6) * 0.15);
    });
    ringSeeded = true;
  }

  /* ── hover / search state ────────────────────────────────────────────────
     `h` is the animated hover intensity (0..1). Everything dim-related reads
     it, so sliding from one node to the next swaps the neighborhood while h
     stays high — no fade-out-and-back-in flicker.

     `hops` is the reason this reads as a nervous system rather than a
     spotlight: a BFS from the hovered node out to HOP_MAX, so attention falls
     off with distance the way activation does. A binary in/out set makes the
     2nd degree look as irrelevant as the far side of the graph; it isn't. */
  const HOP_MAX = 3;
  const HOP_DIM = [0, 0.2, 0.52, 0.74];   // dim per hop; past HOP_MAX → HOP_FAR
  const HOP_FAR = 0.9;
  let hovered = null, hops = null, h = 0, hTarget = 0;
  let searchSet = null;
  // Topic filter (topicSet, declared with the view-topics model above) is
  // independent of text search — they compose as an intersection in dimFactor.

  /* ── auto-wikilinks ──────────────────────────────────────────────────────
     Two questions that lean on the same source domain are related. The merged
     library graph is bipartite (gold entry nodes ↔ deduped "d:" domain nodes),
     so relatedness falls straight out of the domain nodes' neighborhoods — no
     backend change. Domains shared by >6 entries are ambient glue (wikipedia,
     reddit) that would link everything to everything; skipped. The pairs
     become togglable dashed-faint edges AND the Related [[wikilinks]] in the
     Obsidian exports. */
  const relatedOf = new Map();   // entryId -> Map(otherEntryId -> sharedDomains)
  let showRel = false;
  {
    const isEntry = (n) => !!g.getNodeAttribute(n, 'entryId');
    const bump = (a, b) => {
      const m = relatedOf.get(a) || new Map();
      m.set(b, (m.get(b) || 0) + 1);
      relatedOf.set(a, m);
    };
    g.forEachNode((d) => {
      if (isEntry(d) || !String(d).startsWith('d:')) return;
      const ents = g.neighbors(d).filter(isEntry);
      if (ents.length < 2 || ents.length > 6) return;
      for (let i = 0; i < ents.length; i++) {
        for (let j = i + 1; j < ents.length; j++) { bump(ents[i], ents[j]); bump(ents[j], ents[i]); }
      }
    });
    // The edges are added/dropped on toggle rather than sitting hidden in the
    // graph: an invisible edge would still count as a hop for the hover
    // activation, silently lighting up "neighbors" no visible line explains.
    const relKeys = [];
    const relRow = document.getElementById('gv-related-row');
    const relCheck = document.getElementById('gv-related');
    if (relRow && relCheck && relatedOf.size > 0) {
      relRow.style.display = '';
      relCheck.addEventListener('change', () => {
        showRel = relCheck.checked;
        if (showRel) {
          for (const [a, m] of relatedOf) {
            for (const b of m.keys()) {
              if (a < b && !g.hasEdge(a, b)) {
                const k = 'rel:' + a + ':' + b;
                g.addEdgeWithKey(k, a, b, { rel: true });
                relKeys.push(k);
              }
            }
          }
        } else {
          while (relKeys.length) { const k = relKeys.pop(); if (g.hasEdge(k)) g.dropEdge(k); }
        }
        renderer.refresh();
      });
    }
  }
  // A click on a non-actionable node latches its neighborhood highlight so you
  // can read the labels; Escape / stage-click releases it.
  let pinned = null;
  // The nodes on a shift-click shortest-path route; when set, everything off the
  // route dims so the connection reads even after the sparks fade.
  let pathSet = null;
  // The copy-link control (assigned in the controls block); showTip reveals it.
  let copyBtn = null;
  const dimOf = new Map();     // node -> 0..1, written by nodeReducer, read by drawLabel
  // Placed-label boxes for this frame's greedy collision cull; reset on
  // beforeRender (below), grown biggest-first as sigma draws each label.
  const labelBoxes = [];
  // Cluster-label hit boxes ({x,y,w,h,key} in viewport px), rebuilt each frame
  // by drawClusterLabels. Declared up here (not in that block) because the
  // beforeRender handler pre-seeds labelBoxes from it, and resize(true) in the
  // signal-layer setup can fire a render before that block would run.
  const labelRects = [];
  // Reading trail: the question nodes visited this session, oldest first.
  // Drawn as a golden thread on the clusters layer; the ⟵ control retraces it.
  const trail = [];
  // Growth-replay state (the engine lives after the controls block). While a
  // replay runs, the reducers hide everything not yet revealed — declared here
  // so the reducer closures never race their own declaration.
  let replayActive = false, replayVisible = null;
  function pushTrail(id) {
    if (!g.hasNode(id) || trail[trail.length - 1] === id) return;
    trail.push(id);
    if (trail.length > 40) trail.shift();   // a trail, not a transcript
    updateTrailUi();
    renderer.refresh({ skipIndexation: true });
  }
  function updateTrailUi() {
    const b = document.getElementById('gv-trail-back');
    if (b) b.style.display = trail.length > 1 ? '' : 'none';
  }

  /** BFS out to HOP_MAX. Returns [hops, tree] — tree is the parent→child edge
      list in discovery order, which is exactly the path a pulse should travel. */
  function neighborhood(node) {
    const d = new Map([[node, 0]]);
    const tree = [];
    let frontier = [node];
    for (let hop = 1; hop <= HOP_MAX && frontier.length; hop++) {
      const next = [];
      for (const cur of frontier) {
        g.forEachNeighbor(cur, (x) => {
          if (d.has(x)) return;
          d.set(x, hop);
          tree.push({ from: cur, to: x, hop: hop - 1 });
          next.push(x);
        });
      }
      frontier = next;
    }
    return [d, tree];
  }

  function setHovered(node) {
    hovered = node;
    hops = null;
    if (node && g.hasNode(node)) {
      const [d, tree] = neighborhood(node);
      hops = d;
      pulse(tree);
    }
    hTarget = node ? 1 : 0;
    tick();
  }

  // How dimmed a node currently is: search misses dim hard and immediately,
  // hover falls off by hop distance as `h` ramps in.
  function dimFactor(id) {
    if (pathSet) return pathSet.has(id) ? 0 : 0.9;
    if (searchSet && !searchSet.has(id)) return 1;
    if (topicSet && !topicSet.has(id)) return 1;
    if (highlight && hops) {
      const k = hops.get(id);
      return (k === undefined ? HOP_FAR : HOP_DIM[k]) * h;
    }
    return 0;
  }

  let fadeStart = parseFloat(P('textfade', '8')) || 8;

  const renderer = new Sigma(g, container, {
    allowInvalidContainer: true,
    renderLabels: true,
    labelFont: 'Inter, system-ui, sans-serif',
    labelSize: 11,
    labelWeight: '500',
    // The alpha ramp in drawNodeLabel is the real gate; sigma's own threshold
    // would pop labels in and out on top of it.
    labelRenderedSizeThreshold: 0,
    // Library labels are full question sentences (~200px wide), so sigma's
    // 100px default grid cell lets two "winners" from adjacent cells overlap
    // badly. Per-cell count is ceil(density/ratio²) — independent of cellSize —
    // so a wider cell just coarsens WHERE labels may appear; sizing it to the
    // label width means roughly one label per label-width of canvas, and the
    // greedy collision cull in defaultDrawNodeLabel guarantees the rest.
    labelGridCellSize: libMode ? 170 : 100,
    labelDensity: libMode ? 0.7 : 1,
    defaultEdgeColor: glRgba(T.edge, T.edge[3]),
    // Default floor is 1.7px, which would swallow the hairline edges entirely.
    minEdgeThickness: 0.5,
    minCameraRatio: 0.05, maxCameraRatio: 14, zIndex: true,
    // Labels fade in with zoom instead of appearing at a threshold: alpha ramps
    // over rendered size, so hubs surface first and the graph reads as calm at
    // any zoom. `data.size/x/y` are already viewport px here.
    defaultDrawNodeLabel: (ctx, data) => {
      if (!data.label) return;
      const t = (data.size - fadeStart) / 4;
      const alpha = clamp(smoothstep(t) * (1 - (dimOf.get(data.key) || 0)), 0, 1);
      if (alpha < 0.02) return;
      const fs = proportional ? 9 + data.size * 0.35 : 11;
      ctx.font = fs + "px 'Inter', system-ui, sans-serif";
      const x = data.x + data.size + 4, y = data.y + 4;
      // Greedy declutter: sigma's grid hands us labels biggest-first, so the
      // first to claim a patch of canvas is the most important one there. Any
      // later label whose box overlaps a placed one is dropped this frame —
      // the Obsidian/InfraNodus read where hubs keep their names and the
      // small fry yield. The hovered node draws through defaultDrawNodeHover,
      // so it's never subject to this. 3px vertical slack = breathing room.
      const w = ctx.measureText(data.label).width;
      const bx = x, by = y - fs, bw = w, bh = fs + 3;
      for (let i = 0; i < labelBoxes.length; i++) {
        const b = labelBoxes[i];
        if (bx < b.x + b.w && bx + bw > b.x && by < b.y + b.h && by + bh > b.y) return;
      }
      labelBoxes.push({ x: bx, y: by, w: bw, h: bh });
      ctx.fillStyle = rgbaCss(T.label, alpha.toFixed(3));
      ctx.fillText(data.label, x, y);
    },
    // Sigma's stock hover draws a white label pill — unreadable on the dark
    // plane and not the look we want. The halo/ring is drawn here instead.
    defaultDrawNodeHover: (ctx, data) => {
      const base = baseRgb.get(data.key) || [202, 191, 169];
      const r = data.size;
      const grad = ctx.createRadialGradient(data.x, data.y, r * 0.6, data.x, data.y, r * 3.2);
      grad.addColorStop(0, rgbaCss(base, (0.3 * h).toFixed(3)));
      grad.addColorStop(1, rgbaCss(base, '0'));
      ctx.fillStyle = grad;
      ctx.beginPath(); ctx.arc(data.x, data.y, r * 3.2, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = T.ring; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(data.x, data.y, r + 1, 0, Math.PI * 2); ctx.stroke();
      if (data.label) {
        ctx.font = "500 11px 'Inter', system-ui, sans-serif";
        ctx.fillStyle = rgbCss(T.label);
        ctx.fillText(data.label, data.x + r + 4, data.y + 4);
      }
    },
    nodeReducer: (id, d) => {
      const r = { ...d };
      // Mid-replay, a node that hasn't been "asked yet" doesn't exist yet.
      if (replayActive && replayVisible && !replayVisible.has(id)) {
        r.hidden = true;
        dimOf.set(id, 1);
        return r;
      }
      const dim = dimFactor(id);
      dimOf.set(id, dim);
      if (dim > 0.001) {
        r.color = rgbCss(lerpRgb(baseRgb.get(id) || [202, 191, 169], T.nodeDim, dim));
        r.zIndex = 0;
      } else if (id === hovered) r.zIndex = 2;
      else if (hops && hops.has(id)) r.zIndex = 1;
      // Sigma treats `highlighted` as "draw the hover layer"; we drive it
      // ourselves so the halo only ever tracks the real hovered node.
      r.highlighted = id === hovered && h > 0.01;
      return r;
    },
    edgeReducer: (id, d) => {
      const r = { ...d };
      if (!drawEdges) { r.hidden = true; return r; }
      // Related links (shared sources) are an overlay lens, not part of the
      // web: hidden until toggled, and drawn as their own faint violet so they
      // never masquerade as citation edges.
      if (d.rel) {
        if (!showRel) { r.hidden = true; return r; }
        r.color = 'rgba(190,150,255,0.30)'; r.size = 0.7; r.zIndex = 0;
        return r;
      }
      const s = g.source(id), t = g.target(id);
      if (replayActive && replayVisible && (!replayVisible.has(s) || !replayVisible.has(t))) {
        r.hidden = true;
        return r;
      }
      const sd = dimOf.has(s) ? dimOf.get(s) : dimFactor(s);
      const td = dimOf.has(t) ? dimOf.get(t) : dimFactor(t);
      // An edge is as hot as its furthest end is near: hop-1 edges (touching
      // the hovered node) burn, hop-2 edges glow, past that they're just web.
      // Same falloff as the nodes, so the gold traces the activation instead
      // of stopping at a hard ring one step out.
      const far = hovered && hops ? Math.max(hops.get(s) ?? 99, hops.get(t) ?? 99) : 99;
      const heat = far <= 1 ? 1 : far === 2 ? 0.42 : 0;
      if (highlight && heat > 0) {
        r.color = glRgba(T.edgeHot, +lerp(T.edge[3], T.edgeHot[3] * heat, h).toFixed(3));
        r.size = lerp(0.6, heat > 0.9 ? 1.1 : 0.8, h);
        r.zIndex = 1;
      } else {
        // Fade rather than hide: near-invisible edges keep the shape of the
        // web readable behind the focused neighborhood.
        const dim = Math.max(sd, td);
        r.color = glRgba(T.edge, +lerp(T.edge[3], T.edgeDim[3], dim).toFixed(4));
        r.size = 0.6;
        r.zIndex = 0;
      }
      return r;
    },
  });

  const camera = renderer.getCamera();

  // Clear the greedy label-collision boxes at the start of every render, before
  // sigma's label pass repopulates them biggest-first. Pre-seed with last
  // frame's cluster-label plates (labelRects, filled on afterRender) so node
  // labels yield to the topic names rather than getting stamped over by them —
  // the orientation cue outranks any single node.
  renderer.on('beforeRender', () => {
    labelBoxes.length = 0;
    for (let i = 0; i < labelRects.length; i++) {
      const r = labelRects[i];
      labelBoxes.push({ x: r.x, y: r.y, w: r.w, h: r.h });
    }
  });

  /* ── signal layer ────────────────────────────────────────────────────────
     Its own Canvas2D layer under sigma's mouse captor. Registering it through
     createCanvasContext (rather than appending a canvas by hand) hands sigma
     the sizing: it rewrites width/height and re-applies the pixelRatio scale
     on every resize, and its clear() only touches labels/hovers/edgeLabels, so
     nothing here fights the render path. Positions are read from the graph
     every frame, so signals ride the live physics instead of drifting off it.

     Two kinds of signal, one mechanism:
       ambient — the library idling. A spark crosses a random edge every so
                 often, in the source node's own color. This is what makes a
                 still graph feel alive rather than printed.
       pulse   — you touched a node, and the charge propagates outward along
                 the BFS tree, one hop per PULSE_STEP. Gold: it's attention. */
  let fxc = null;
  try {
    renderer.createCanvasContext('signals', {
      beforeLayer: 'mouse',
      style: { pointerEvents: 'none' },
    });
    fxc = renderer.canvasContexts && renderer.canvasContexts.signals;
    // resize() early-returns when the dimensions haven't changed, and they
    // haven't — so a layer registered after construction keeps the default
    // 300x150 bitmap stretched over the container until something forces the
    // first sizing pass. Force it here, once.
    if (fxc) renderer.resize(true);
  } catch (_) { fxc = null; }   // no layer → no signals; everything else stands

  const MAX_SPARKS = 60, PULSE_STEP = 130, SPARK_MS = 620;
  const sparks = [];   // {s, t, at, dur, rgb, hot}
  const rings = [];    // {node, at, dur} — new-node ignition
  let signalsOn = !!fxc && !reduceMotion;

  function emit(s, t, delay, rgb, hot) {
    if (!signalsOn || sparks.length >= MAX_SPARKS) return;
    sparks.push({ s, t, at: performance.now() + delay, dur: SPARK_MS, rgb, hot });
  }
  // A shift-click path pulse is a direct request, not ambient life, so it fires
  // even with Signals toggled off (still needs the canvas layer + a spark slot).
  function emitForce(s, t, delay, rgb, hot) {
    if (!fxc || sparks.length >= MAX_SPARKS) return;
    sparks.push({ s, t, at: performance.now() + delay, dur: SPARK_MS, rgb, hot });
  }

  /* Fire along the BFS tree, delayed by hop: the charge visibly leaves the node
     you touched and spreads. Stops at hop 2 — a 3rd wave is noise, not signal. */
  function pulse(tree) {
    if (!signalsOn || !highlight) return;
    let n = 0;
    for (const e of tree) {
      if (e.hop > 1 || n++ > 26) break;
      emit(e.from, e.to, e.hop * PULSE_STEP, T.pulse, true);
    }
  }

  const vp = (id) => renderer.graphToViewport({ x: g.getNodeAttribute(id, 'x'), y: g.getNodeAttribute(id, 'y') });

  /* ── cluster labels ──────────────────────────────────────────────────────
     Topic names drawn ON the canvas at each cluster's weighted centroid — the
     InfraNodus read of a knowledge graph: zoomed out you see WHERE "News" or
     "Health" lives, zoom in and the labels yield to the node labels. Own
     Canvas2D layer (same registration pattern as signals); redrawn from
     sigma's afterRender so they track camera and live physics.
     Labels are also click targets: labelRects carries the hit boxes, and the
     clickStage handler toggles that topic's filter. &clusterlabels=0 opts out. */
  let clc = null;
  const clusterLabelsOn = P('clusterlabels', '1') !== '0';
  if (clusterLabelsOn) {
    try {
      renderer.createCanvasContext('clusters', {
        beforeLayer: 'mouse',
        style: { pointerEvents: 'none' },
      });
      clc = renderer.canvasContexts && renderer.canvasContexts.clusters;
      if (clc) renderer.resize(true);   // same 300x150-default gotcha as signals
    } catch (_) { clc = null; }
  }
  /* Favicons drawn INSIDE domain nodes — the web suddenly reads as the actual
     web (you recognize bbc.com or arxiv.org at a glance instead of a colored
     dot). Enriched entry graphs carry a worker-harvested `favicon` attr; the
     merged library web derives one from the hostname via DuckDuckGo's public
     icon endpoint (pure client-side — nothing stored, nothing spent). Images
     load lazily on first draw and failures are remembered, never retried. */
  const favNodes = [];
  g.forEachNode((id, a) => {
    if (a.kind === 'domain' || String(id).indexOf('d:') === 0) {
      const dom = a.domain || String(id).slice(2);
      const src = (a.favicon && /^https:\/\//.test(a.favicon)) ? a.favicon
        : (/^[a-z0-9.-]+\.[a-z]{2,}$/i.test(dom) ? 'https://icons.duckduckgo.com/ip3/' + dom + '.ico' : null);
      if (src) favNodes.push({ id, src });
    }
  });
  const favCache = new Map();   // src -> {img, ok: null|true|false}
  function favIcon(src) {
    let c = favCache.get(src);
    if (!c) {
      c = { img: new Image(), ok: null };
      c.img.onload = () => { c.ok = true; try { renderer.refresh({ skipIndexation: true }); } catch (_) {} };
      c.img.onerror = () => { c.ok = false; };
      c.img.src = src;
      favCache.set(src, c);
    }
    return c.ok ? c.img : null;
  }
  // Kick the loads at startup (biggest domains first — favNodes follows node
  // order, fine) so icons appear as soon as the first frame settles instead of
  // waiting for a hover or zoom to trigger the first draw attempt.
  if (favNodes.length) setTimeout(() => { for (const f of favNodes.slice(0, 60)) favIcon(f.src); }, 600);
  function drawFavicons() {
    // Skip entirely while FA2 is simming (the intro bloom, ~160 frames of
    // every node moving every frame): icons are illegible on moving nodes
    // anyway, and save/clip/drawImage across ~130 domains is the single
    // costliest per-frame addition here — pure waste during the bloom.
    if (!favNodes.length || (animateOn && (simBudget > 0 || simIters > 0))) return;
    const dims = renderer.getDimensions();
    const scale = (typeof renderer.scaleSize === 'function') ? (s) => renderer.scaleSize(s)
      : (s) => s / Math.sqrt(camera.ratio);
    for (const f of favNodes) {
      if (!g.hasNode(f.id)) continue;
      if (replayActive && replayVisible && !replayVisible.has(f.id)) continue;
      const r = scale(g.getNodeAttribute(f.id, 'size')) * 0.8;
      if (r < 3.5) continue;                     // too small to read — keep the dot
      const p = vp(f.id);
      if (p.x < -20 || p.y < -20 || p.x > dims.width + 20 || p.y > dims.height + 20) continue;
      const img = favIcon(f.src);
      if (!img) continue;
      const alpha = 0.95 * (1 - (dimOf.get(f.id) || 0));
      if (alpha < 0.05) continue;
      clc.save();
      clc.globalAlpha = alpha;
      clc.beginPath();
      clc.arc(p.x, p.y, r, 0, 6.2832);
      clc.clip();
      clc.drawImage(img, p.x - r, p.y - r, r * 2, r * 2);
      clc.restore();
    }
  }
  function drawClusterLabels() {
    if (!clc) return;
    try {
      const dims = renderer.getDimensions();
      clc.clearRect(0, 0, dims.width, dims.height);
      labelRects.length = 0;
      drawFavicons();
      // The reading trail rides this layer (not the fx layer) because this one
      // redraws on every render and tracks the camera; fx clears itself the
      // moment no spark is alive. Drawn before the plates so topic names stay
      // on top. A dashed gold thread with a dot per stop — where you've been.
      if (trail.length > 1) {
        clc.save();
        clc.strokeStyle = rgbaCss(T.pulse, '0.32');
        clc.fillStyle = rgbaCss(T.pulse, '0.55');
        clc.lineWidth = 1.4;
        clc.lineJoin = 'round';
        clc.setLineDash([6, 5]);
        clc.beginPath();
        let started = false;
        for (const id of trail) {
          if (!g.hasNode(id)) continue;
          const p = vp(id);
          if (started) clc.lineTo(p.x, p.y); else { clc.moveTo(p.x, p.y); started = true; }
        }
        clc.stroke();
        clc.setLineDash([]);
        for (const id of trail) {
          if (!g.hasNode(id)) continue;
          const p = vp(id);
          clc.beginPath(); clc.arc(p.x, p.y, 2.4, 0, 6.2832); clc.fill();
        }
        clc.restore();
      }
      if (!viewTopics.length) return;
      // Fade with zoom-in (node labels take over) and duck while a hover
      // neighborhood is hot — the cluster name must never fight the question.
      const zoomFade = clamp((camera.ratio - 0.16) / 0.22, 0, 1);
      const alpha = 0.85 * zoomFade * (1 - 0.6 * h);
      if (alpha < 0.03) return;
      clc.save();
      clc.textAlign = 'center';
      clc.textBaseline = 'middle';
      const placed = [];   // measured first, collision-relaxed, then drawn
      for (const t of viewTopics) {
        if (!t.set || t.set.size < 2) continue;
        // A curated topic's members are scattered across the whole layout
        // (FA2 places by links, not by topic), so a plain centroid — even over
        // exclusively-owned nodes — lands every label at the graph's center of
        // mass and they stack into a column that hides the graph. Anchor each
        // label where the topic is DENSEST instead: the Louvain community
        // holding most of its owned nodes is spatially coherent by
        // construction, so the centroid over that intersection sits on a real
        // visual cluster.
        const owned = [];
        for (const id of t.set) {
          if (g.hasNode(id) && topicByNode.get(id) === t) owned.push(id);
        }
        let anchor = owned.length >= 2 ? owned : [...t.set].filter((id) => g.hasNode(id));
        if (commOf && anchor.length > 3) {
          const byComm = new Map();
          for (const id of anchor) {
            const c = commOf[id];
            if (c === undefined) continue;
            (byComm.get(c) || byComm.set(c, []).get(c)).push(id);
          }
          let best = null;
          for (const ids of byComm.values()) if (!best || ids.length > best.length) best = ids;
          if (best && best.length >= 3) anchor = best;
        }
        let sx = 0, sy = 0, w = 0;
        for (const id of anchor) {
          const s = baseSize.get(id) || 3;
          const p = vp(id);
          sx += p.x * s; sy += p.y * s; w += s;
        }
        if (!w) continue;
        const x = sx / w, y = sy / w;
        if (x < -60 || y < -30 || x > dims.width + 60 || y > dims.height + 30) continue;
        const fs = clamp(11 + Math.sqrt(t.set.size) * 1.2, 12, 18);
        const a2 = activeTopic && activeTopic !== t.key ? alpha * 0.22 : alpha;
        const label = t.label.length > 26 ? t.label.slice(0, 24).trimEnd() + '…' : t.label;
        clc.font = '700 ' + fs + "px 'Inter', system-ui, sans-serif";
        const tw = clc.measureText(label).width;
        placed.push({ t, x, y, fs, a2, label, tw, pad: 8, ph: fs + 8 });
      }
      // Eight readable plates beat twelve fighting ones — and two topics
      // anchored on the same spot means the layout gave them one territory,
      // so only the bigger one gets to name it.
      placed.sort((a, b) => b.t.set.size - a.t.set.size);
      placed.length = Math.min(placed.length, 8);
      for (let i = placed.length - 1; i > 0; i--) {
        for (let j = 0; j < i; j++) {
          const dx = placed[i].x - placed[j].x, dy = placed[i].y - placed[j].y;
          if (dx * dx + dy * dy < 70 * 70) { placed.splice(i, 1); break; }
        }
      }
      // A few greedy passes separate overlapping plates along whichever axis
      // needs the smaller shove — always-vertical pushing turns co-anchored
      // labels back into the center column this placement exists to avoid.
      for (let pass = 0; pass < 3; pass++) {
        for (let i = 0; i < placed.length; i++) {
          for (let j = i + 1; j < placed.length; j++) {
            const a = placed[i], b = placed[j];
            const ox = Math.min(a.x + a.tw / 2 + a.pad, b.x + b.tw / 2 + b.pad) - Math.max(a.x - a.tw / 2 - a.pad, b.x - b.tw / 2 - b.pad);
            const oy = Math.min(a.y + a.ph / 2, b.y + b.ph / 2) - Math.max(a.y - a.ph / 2, b.y - b.ph / 2);
            if (ox <= 0 || oy <= 0) continue;
            if (ox < oy) {
              const push = (ox / 2 + 2) * (a.x <= b.x ? 1 : -1);
              a.x -= push; b.x += push;
            } else {
              const push = (oy / 2 + 2) * (a.y <= b.y ? 1 : -1);
              a.y -= push; b.y += push;
            }
          }
        }
      }
      for (const p of placed) {
        // Soft plate behind the text so it reads over edges without a box look.
        clc.font = '700 ' + p.fs + "px 'Inter', system-ui, sans-serif";
        clc.fillStyle = dark
          ? 'rgba(20,17,14,' + (0.5 * p.a2).toFixed(3) + ')'
          : 'rgba(246,241,231,' + (0.55 * p.a2).toFixed(3) + ')';
        const rx = p.x - p.tw / 2 - p.pad, ry = p.y - p.ph / 2, rw = p.tw + p.pad * 2, rr = p.ph / 2;
        clc.beginPath();   // rounded rect by hand — roundRect() is still too new
        clc.moveTo(rx + rr, ry);
        clc.arcTo(rx + rw, ry, rx + rw, ry + p.ph, rr);
        clc.arcTo(rx + rw, ry + p.ph, rx, ry + p.ph, rr);
        clc.arcTo(rx, ry + p.ph, rx, ry, rr);
        clc.arcTo(rx, ry, rx + rw, ry, rr);
        clc.closePath();
        clc.fill();
        clc.fillStyle = rgbaCss(parseColor(p.t.color), p.a2.toFixed(3));
        clc.fillText(p.label, p.x, p.y);
        labelRects.push({ x: rx, y: ry, w: rw, h: p.ph, key: p.t.key });
      }
      clc.restore();
    } catch (_) { /* never break the render loop over a label */ }
  }
  renderer.on('afterRender', drawClusterLabels);
  onTopicsChanged.push(() => { try { renderer.refresh({ skipIndexation: true }); } catch (_) {} });

  /** Engage/toggle a topic filter — shared by legend rows, cluster-label
      clicks, and Escape. Frames the topic on engage (question anchor first). */
  function setActiveTopic(key) {
    const t = key ? viewTopics.find((x) => x.key === key) : null;
    if (!t || activeTopic === key) {   // toggle off / unknown key
      activeTopic = null; topicSet = null;
    } else {
      activeTopic = key; topicSet = t.set;
      let anchor = null;
      for (const id of t.set) { if (g.hasNode(id) && g.getNodeAttribute(id, 'entryId')) { anchor = id; break; } }
      anchor = anchor || [...t.set].find((id) => g.hasNode(id));
      const d = anchor && renderer.getNodeDisplayData(anchor);
      if (d) camera.animate({ x: d.x, y: d.y, ratio: 0.5 }, { duration: 400 });
    }
    for (const fn of onTopicsChanged) { try { fn(); } catch (_) {} }
    renderer.refresh({ skipIndexation: true });
  }

  // Ambient rate scales with the web's size but stays sparse — a few crossings
  // a second at library scale, so it reads as idle firing and never as traffic.
  const ambientMs = clamp(60000 / clamp(g.size * 1.1, 40, 240), 250, 1500);
  let ambientAt = 0;
  function ambient(now) {
    if (!signalsOn || !g.size || !drawEdges) return;
    if (now < ambientAt) return;
    ambientAt = now + ambientMs * (0.6 + Math.random() * 0.8);
    // Hush while a pulse is playing: the ambient would only muddy it.
    if (h > 0.5 || dragged) return;
    const e = g.edges()[(Math.random() * g.size) | 0];
    if (!e) return;
    const s = g.source(e), t = g.target(e);
    emit(Math.random() < 0.5 ? s : t, Math.random() < 0.5 ? t : s, 0, baseRgb.get(s) || T.pulse, false);
  }

  let fxDirty = false;
  function drawFx(now) {
    if (!fxc) return false;
    if (!sparks.length && !rings.length) {
      // One last clear after the final spark dies, then stop touching it.
      if (fxDirty) { const d = renderer.getDimensions(); fxc.clearRect(0, 0, d.width, d.height); fxDirty = false; }
      return false;
    }
    const dim = renderer.getDimensions();
    fxc.clearRect(0, 0, dim.width, dim.height);
    fxDirty = true;
    fxc.save();
    // Additive on the dark plane is what makes a spark read as light rather
    // than paint; on the light theme it would just bleach out to white.
    fxc.globalCompositeOperation = dark ? 'lighter' : 'source-over';
    fxc.lineCap = 'round';

    for (let i = sparks.length - 1; i >= 0; i--) {
      const sp = sparks[i];
      const p = (now - sp.at) / sp.dur;
      if (p >= 1 || !g.hasNode(sp.s) || !g.hasNode(sp.t)) { sparks.splice(i, 1); continue; }
      if (p < 0) continue;
      const a = vp(sp.s), b = vp(sp.t);
      // Ease-out: charge leaves fast and arrives soft, like it's being absorbed.
      const e = 1 - Math.pow(1 - p, 2);
      const tail = Math.max(0, e - 0.18);
      const x1 = lerp(a.x, b.x, tail), y1 = lerp(a.y, b.y, tail);
      const x2 = lerp(a.x, b.x, e), y2 = lerp(a.y, b.y, e);
      const al = smoothstep(p / 0.12) * (1 - smoothstep((p - 0.6) / 0.4)) * (sp.hot ? 0.95 : 0.5);
      const grad = fxc.createLinearGradient(x1, y1, x2, y2);
      grad.addColorStop(0, rgbaCss(sp.rgb, 0));
      grad.addColorStop(1, rgbaCss(sp.rgb, al.toFixed(3)));
      fxc.strokeStyle = grad;
      fxc.lineWidth = sp.hot ? 1.6 : 1.1;
      fxc.beginPath(); fxc.moveTo(x1, y1); fxc.lineTo(x2, y2); fxc.stroke();
      fxc.fillStyle = rgbaCss(sp.rgb, al.toFixed(3));
      fxc.beginPath(); fxc.arc(x2, y2, sp.hot ? 1.8 : 1.3, 0, 6.2832); fxc.fill();
    }

    // Ignition: a node that wasn't here last visit announces itself once.
    for (let i = rings.length - 1; i >= 0; i--) {
      const rg = rings[i];
      const p = (now - rg.at) / rg.dur;
      if (p >= 1 || !g.hasNode(rg.node)) { rings.splice(i, 1); continue; }
      if (p < 0) continue;
      const c = vp(rg.node);
      const r0 = baseSize.get(rg.node) || 4;
      const out = 1 - Math.pow(1 - p, 3);
      const al = (1 - p) * 0.55;
      fxc.strokeStyle = rgbaCss(T.spark, al.toFixed(3));
      fxc.lineWidth = lerp(1.8, 0.4, p);
      fxc.beginPath(); fxc.arc(c.x, c.y, r0 + out * 22, 0, 6.2832); fxc.stroke();
      fxc.fillStyle = rgbaCss(T.spark, ((1 - smoothstep(p / 0.5)) * 0.7).toFixed(3));
      fxc.beginPath(); fxc.arc(c.x, c.y, r0 * 0.9, 0, 6.2832); fxc.fill();
    }

    fxc.restore();
    return true;
  }

  /* ── physics ─────────────────────────────────────────────────────────────
     One rAF ticker drives both the layout burst and the hover tween, so the
     page settles to zero CPU the moment neither has anything left to do. */
  // outboundAttractionDistribution keeps the domain hubs from dragging every
  // question into one dense core — the merged library graph is bipartite and
  // hub-dominated, so without it the layout is a ball no matter the repulsion.
  const fa2 = { ...forceAtlas2.inferSettings(g), gravity: 0.04, scalingRatio: 48, slowDown: 4, adjustSizes: true, edgeWeightInfluence: 1, outboundAttractionDistribution: true };
  const layoutOff = P('layout', 'fa2') === 'none' || g.order <= 2 || g.order > 600;
  let animateOn = !layoutOff && !reduceMotion;
  // Budget is measured in frames actually rendered, not wall-clock: a graph
  // opened in a background tab gets no rAF at all, and a deadline would expire
  // unspent and leave it frozen at its seed positions forever. Spending only on
  // real frames also means the browser's own rAF pause IS the battery guard.
  let simBudget = 0, simIters = 0, simDone = null, raf = 0, last = 0, lastFx = 0;

  function warm(ms) {
    if (!animateOn) return;
    simBudget = Math.max(simBudget, ms);
    tick();
  }
  /** Deterministic burst: exactly n FA2 iterations regardless of frame rate.
      Wall-clock budgets make the settled layout depend on how many frames the
      machine happened to render; a fixed count makes it a pure function of the
      seed. Slower machines take longer to finish the same bloom, never a
      different one. onDone fires once the count is spent (or immediately when
      the layout is off). */
  function warmIters(n, onDone) {
    if (!animateOn) { if (onDone) onDone(); return; }
    simIters = Math.max(simIters, n);
    simDone = onDone || null;
    tick();
  }
  function tick() { if (!raf) raf = requestAnimationFrame(frame); }

  function frame(ts) {
    raf = 0;
    const dt = last ? Math.min(ts - last, 64) : 16;
    last = ts;

    const simming = animateOn && (simBudget > 0 || simIters > 0);
    if (simming) {
      // The iteration channel (deterministic bloom) spends before the ms
      // channel (interaction reheats) so a drag mid-intro can't shorten it.
      // It also runs 4 iterations/frame instead of 2: the total count is what
      // determinism cares about, and doubling per-frame work keeps the intro
      // at ~2.7s on a 60Hz display instead of 5.
      let iters = 2;
      if (simIters > 0) { iters = Math.min(4, simIters); simIters -= iters; }
      else simBudget -= dt;
      // Pin before and after: assign() writes every node's position back from
      // its own matrix, so the dragged node has to be re-stated on both sides
      // of the burst to stay exactly under the cursor.
      if (dragged && dragPos) { g.setNodeAttribute(dragged, 'x', dragPos.x); g.setNodeAttribute(dragged, 'y', dragPos.y); }
      try { forceAtlas2.assign(g, { iterations: iters, settings: fa2 }); } catch (_) { simBudget = 0; simIters = 0; }
      if (dragged && dragPos) { g.setNodeAttribute(dragged, 'x', dragPos.x); g.setNodeAttribute(dragged, 'y', dragPos.y); }
      if (simIters <= 0 && simDone) { const f = simDone; simDone = null; f(); }
    }

    // ~95% of the way in ~210ms — an ease-out that retargets cleanly mid-slide.
    const tweening = Math.abs(hTarget - h) > 0.005;
    if (tweening) h += (hTarget - h) * (1 - Math.exp(-dt / 70));
    else h = hTarget;

    if (simming || tweening || h !== 0) {
      renderer.refresh({ skipIndexation: !simming });
      if (hovered) showTip(hovered);
    }

    // Signals are drawn on their own layer, so a frame that only carries a
    // spark costs a canvas clear and a handful of arcs — no sigma refresh, no
    // layout, no indexation.
    //
    // Capped at ~40fps when nothing else needs the frame: a spark takes 620ms
    // to cross, so 25 steps is already smoother than the eye asks for, and on
    // a 120Hz display the uncapped version would repaint the layer three times
    // per visible change — all cost, no motion. Physics and hover frames are
    // never throttled; they're the ones you can actually see stutter.
    ambient(ts);
    const busy = simming || tweening;
    let fxBusy = sparks.length > 0 || rings.length > 0 || fxDirty;
    if (busy || ts - lastFx >= 24) { lastFx = ts; fxBusy = drawFx(ts); }

    // Ambient firing is the one thing here that never finishes on its own, so
    // this loop only reaches zero CPU when signals are off. That's the deal
    // the Signals toggle exists to let you take back; rAF is already paused by
    // the browser whenever the tab (or, in Chrome, this offscreen cross-origin
    // iframe) isn't being looked at, which is the battery guard that matters.
    if (busy || fxBusy || signalsOn) tick(); else last = 0;
  }

  /* ── hover card ──────────────────────────────────────────────────────────
     Title, domain, and the worker LLM's one-line note for the source under the
     cursor. Nodes without extras just highlight their neighborhood. */
  const tip = document.getElementById('tip');
  const esc = (s) => String(s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  function showTip(node) {
    if (!tip || !g.hasNode(node)) return;
    const a = g.getNodeAttributes(node);
    if (!a.note && !a.url && !a.domain && !a.page && !a.snippet && !a.suggest && !libMode) { tip.style.display = 'none'; return; }
    if (tip.dataset.node !== node) {
      tip.dataset.node = node;
      const isPage = a.page && pagesSrc;
      const hint = a.suggest
        ? (coarse ? 'tap again to ask the library ↗' : 'click to ask the library ↗')
        : isPage
          ? (coarse ? 'tap again to read the note' : 'click to read the note')
          : a.entryId
            ? (coarse ? 'tap again to read the answer' : 'click to read the answer')
            : (a.url ? (coarse ? 'tap again to open ↗' : 'click to open ↗') : '');
      // Library mode: every node has a story even without note/url attrs — a
      // question knows how many sources answered it, a source knows how many
      // questions cite it. Full (unclamped) label in the title.
      let meta = '';
      if (libMode && !a.note) {
        const deg = g.degree(node);
        meta = a.entryId
          ? 'Question · ' + deg + (deg === 1 ? ' source' : ' sources') + ' · answered on-chain'
          : 'Source · cited by ' + deg + (deg === 1 ? ' question' : ' questions');
      }
      // Enriched entries carry img/age/snippet from the Brave harvest; older
      // entries simply lack the attrs and render exactly as before.
      const domLine = [a.domain, a.age].filter(Boolean).join(' · ');
      tip.innerHTML =
        (a.img && /^https:\/\//.test(a.img)
          ? '<img class="tip-img" src="' + esc(a.img) + '" alt="" loading="lazy" onerror="this.remove()">' : '') +
        '<div class="tip-title">' + (a.suggest ? '✦ ' : '') + esc(fullLabel.get(node) || a.label) + '</div>' +
        (domLine ? '<div class="tip-domain">' + esc(domLine) + '</div>' : '') +
        (meta ? '<div class="tip-domain">' + esc(meta) + '</div>' : '') +
        (a.suggest ? '<div class="tip-domain">the web says people also ask this</div>' : '') +
        (a.note ? '<div class="tip-note">' + esc(a.note) + '</div>' : '') +
        (a.snippet && a.snippet !== a.note ? '<div class="tip-snippet">' + esc(a.snippet) + '</div>' : '') +
        (hint ? '<div class="tip-hint">' + hint + '</div>' : '');
    }
    tip.style.display = 'block';
    // Touch: a fixed bottom sheet (CSS .gv-sheet pins it); the cursor-follow
    // geometry below is skipped since there's no cursor and the node is under
    // the thumb. Also surface the copy-link control for the focused node.
    if (coarse) {
      tip.classList.add('gv-sheet');
    } else {
      tip.classList.remove('gv-sheet');
      const p = renderer.graphToViewport({ x: a.x, y: a.y });
      const r = tip.getBoundingClientRect();
      tip.style.left = Math.min(Math.max(8, p.x + 14), innerWidth - r.width - 8) + 'px';
      tip.style.top = Math.min(Math.max(8, p.y - r.height / 2), innerHeight - r.height - 8) + 'px';
    }
    if (copyBtn) copyBtn.style.display = '';
  }
  function hideTip() {
    if (tip) { tip.style.display = 'none'; tip.dataset.node = ''; tip.classList.remove('gv-sheet'); }
    if (copyBtn && !pinned) copyBtn.style.display = 'none';
  }

  /* ── deep-research note panel ─────────────────────────────────────────────
     A slide-in reader for a topic node's note page: title, the angle it
     answers, the note body, and its sources — with prev/next to walk the tree
     as a small notebook. Built once, in JS, so the whole feature lives in this
     one bundled file (no graph-viewer.html edit to keep in sync across copies). */
  let notePanel = null, noteEls = null;
  function buildNotePanel() {
    if (notePanel) return;
    const st = document.createElement('style');
    st.textContent =
      '.gv-note-back{position:fixed;inset:0;z-index:40;background:rgba(10,8,6,0.5);' +
      'backdrop-filter:blur(3px);opacity:0;transition:opacity .2s;pointer-events:none;}' +
      '.gv-note-back.on{opacity:1;pointer-events:auto;}' +
      '.gv-note{position:fixed;z-index:41;top:0;right:0;bottom:0;width:min(460px,92vw);' +
      'background:#1b1712;color:#e8e0d2;border-left:1px solid #3a332a;' +
      'box-shadow:-24px 0 60px -20px rgba(0,0,0,0.6);transform:translateX(100%);' +
      'transition:transform .26s cubic-bezier(.2,.8,.2,1);overflow-y:auto;' +
      'padding:22px 22px 30px;font:14px/1.6 Inter,system-ui,sans-serif;}' +
      '.gv-note.on{transform:none;}' +
      '.gv-light .gv-note{background:#fbf7ee;color:#2e2820;border-left-color:#e2d9c6;}' +
      '.gv-note-x{position:absolute;top:14px;right:14px;width:30px;height:30px;border:0;' +
      'border-radius:8px;background:rgba(255,255,255,0.08);color:inherit;cursor:pointer;' +
      'font-size:17px;line-height:1;display:grid;place-items:center;}' +
      '.gv-light .gv-note-x{background:rgba(0,0,0,0.06);}' +
      '.gv-note-kick{font-size:10px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#c9b8e0;}' +
      '.gv-note-title{font-size:21px;font-weight:700;line-height:1.25;margin:8px 0 6px;}' +
      '.gv-note-q{font-size:12.5px;color:#a99;opacity:.85;margin:0 0 16px;font-style:italic;}' +
      '.gv-light .gv-note-q{color:#8a7f6c;}' +
      '.gv-note-body{font-size:14px;line-height:1.72;white-space:pre-wrap;margin:0 0 18px;}' +
      '.gv-note-srch{font-size:10px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#c9b8e0;opacity:.7;margin:16px 0 8px;}' +
      '.gv-note-src{display:block;text-decoration:none;color:inherit;padding:7px 0;border-top:1px solid rgba(255,255,255,0.07);}' +
      '.gv-light .gv-note-src{border-top-color:rgba(0,0,0,0.08);}' +
      '.gv-note-src b{font-weight:600;font-size:13px;}.gv-note-src span{display:block;font-size:11px;color:#a99;opacity:.8;font-family:ui-monospace,monospace;}' +
      '.gv-note-nav{display:flex;justify-content:space-between;gap:10px;margin-top:20px;}' +
      '.gv-note-nav button{flex:1;padding:9px;border:1px solid #3a332a;border-radius:9px;background:transparent;' +
      'color:inherit;cursor:pointer;font:600 12px Inter,system-ui,sans-serif;}' +
      '.gv-light .gv-note-nav button{border-color:#e2d9c6;}' +
      '.gv-note-nav button:disabled{opacity:.35;cursor:default;}' +
      '.gv-note-open{display:inline-block;margin-top:18px;padding:9px 14px;border:1px solid #3a332a;' +
      'border-radius:9px;color:inherit;text-decoration:none;font:600 12px Inter,system-ui,sans-serif;}' +
      '.gv-note-open:hover{background:rgba(255,255,255,0.05);}' +
      '.gv-light .gv-note-open{border-color:#e2d9c6;}' +
      '.gv-note-chips{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 16px;}' +
      '.gv-note-chip{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:600;' +
      'padding:4px 9px;border-radius:999px;background:rgba(255,255,255,0.06);' +
      'border:1px solid rgba(255,255,255,0.09);color:#cabfa9;white-space:nowrap;}' +
      '.gv-light .gv-note-chip{background:rgba(0,0,0,0.05);border-color:rgba(0,0,0,0.1);color:#6a5f4c;}' +
      '.gv-note-chip b{color:#e8e0d2;font-weight:700;}.gv-light .gv-note-chip b{color:#2e2820;}' +
      '.gv-note-chip.gv-chip-deep{color:#d8c3f0;border-color:rgba(201,184,224,0.35);}' +
      '.gv-note-chip.gv-chip-tok{color:#f0c98a;border-color:rgba(240,180,90,0.3);}' +
      '.gv-note-research{display:block;width:100%;margin-top:16px;padding:11px;cursor:pointer;text-align:center;' +
      'border:1px solid rgba(201,184,224,0.4);border-radius:9px;background:rgba(201,184,224,0.08);' +
      'color:#d8c3f0;font:700 12.5px Inter,system-ui,sans-serif;}' +
      '.gv-note-research:hover{background:rgba(201,184,224,0.16);}';
    document.head.appendChild(st);
    const back = document.createElement('div'); back.className = 'gv-note-back';
    const panel = document.createElement('div'); panel.className = 'gv-note';
    panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', 'Research note');
    panel.innerHTML =
      '<button class="gv-note-x" aria-label="Close">✕</button>' +
      '<div class="gv-note-kick">Research note</div>' +
      '<h2 class="gv-note-title"></h2>' +
      '<p class="gv-note-q"></p>' +
      '<div class="gv-note-chips"></div>' +
      '<div class="gv-note-body"></div>' +
      '<div class="gv-note-srcwrap"></div>' +
      '<button class="gv-note-research" style="display:none"></button>' +
      '<a class="gv-note-open" target="_blank" rel="noopener noreferrer" style="display:none">Open full page ↗</a>' +
      '<div class="gv-note-nav"><button class="gv-note-prev">← Previous</button>' +
      '<button class="gv-note-next">Next →</button></div>';
    document.body.appendChild(back); document.body.appendChild(panel);
    noteEls = {
      back, panel,
      kick: panel.querySelector('.gv-note-kick'),
      title: panel.querySelector('.gv-note-title'),
      q: panel.querySelector('.gv-note-q'),
      chips: panel.querySelector('.gv-note-chips'),
      body: panel.querySelector('.gv-note-body'),
      srcwrap: panel.querySelector('.gv-note-srcwrap'),
      research: panel.querySelector('.gv-note-research'),
      openLink: panel.querySelector('.gv-note-open'),
      nav: panel.querySelector('.gv-note-nav'),
      prev: panel.querySelector('.gv-note-prev'),
      next: panel.querySelector('.gv-note-next'),
    };
    back.addEventListener('click', closeNote);
    panel.querySelector('.gv-note-x').addEventListener('click', closeNote);
    noteEls.prev.addEventListener('click', () => stepNote(-1));
    noteEls.next.addEventListener('click', () => stepNote(1));
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && notePanel && notePanel.open) closeNote(); });
    notePanel = { open: false, pages: [], idx: 0 };
  }
  function renderNote() {
    const p = notePanel.pages[notePanel.idx];
    if (!p) return;
    noteEls.title.textContent = p.title || 'Untitled note';
    noteEls.q.textContent = p.question ? 'Angle: ' + p.question : '';
    noteEls.body.textContent = p.body || '';
    const srcs = p.sources || [];
    noteEls.srcwrap.innerHTML = srcs.length
      ? '<div class="gv-note-srch">Sources</div>' + srcs.map((s) => {
          const u = /^https?:\/\//i.test(s.url || '') ? s.url : '';
          const dom = (() => { try { return new URL(u).hostname.replace(/^www\./, ''); } catch (_) { return ''; } })();
          return '<a class="gv-note-src" ' + (u ? 'href="' + esc(u) + '" target="_blank" rel="noopener noreferrer"' : '') +
            '><b>' + esc(s.title || u) + '</b>' + (dom ? '<span>' + esc(dom) + '</span>' : '') + '</a>';
        }).join('')
      : '';
    noteEls.prev.disabled = notePanel.idx <= 0;
    noteEls.next.disabled = notePanel.idx >= notePanel.pages.length - 1;
  }
  function stepNote(d) {
    const i = notePanel.idx + d;
    if (i < 0 || i >= notePanel.pages.length) return;
    notePanel.idx = i; renderNote();
    // Nudge attention on the graph to the matching topic node.
    const key = notePanel.pages[i].id;
    if (g.hasNode(key)) { setHovered(key); }
  }
  function closeNote() {
    if (!notePanel) return;
    notePanel.open = false;
    noteEls.back.classList.remove('on'); noteEls.panel.classList.remove('on');
  }
  async function openNote(pageId) {
    buildNotePanel();
    const data = await loadPages();
    const pages = (data && data.pages) || [];
    if (!pages.length) return;
    // Reset the shared drawer back to research-note mode (openEntry repurposes it).
    noteEls.kick.textContent = 'Research note';
    noteEls.nav.style.display = ''; noteEls.openLink.style.display = 'none';
    noteEls.chips.innerHTML = ''; noteEls.research.style.display = 'none';
    const idx = Math.max(0, pages.findIndex((p) => p.id === pageId));
    notePanel.pages = pages; notePanel.idx = idx; notePanel.open = true;
    renderNote();
    noteEls.back.classList.add('on'); noteEls.panel.classList.add('on');
  }
  function renderSources(wrap, srcs) {
    wrap.innerHTML = (srcs && srcs.length)
      ? '<div class="gv-note-srch">Sources</div>' + srcs.map((s) => {
          const u = /^https?:\/\//i.test(s.url || '') ? s.url : '';
          const dom = (() => { try { return new URL(u).hostname.replace(/^www\./, ''); } catch (_) { return ''; } })();
          return '<a class="gv-note-src" ' + (u ? 'href="' + esc(u) + '" target="_blank" rel="noopener noreferrer"' : '') +
            '><b>' + esc(s.title || u) + '</b>' + (dom ? '<span>' + esc(dom) + '</span>' : '') + '</a>';
        }).join('')
      : '';
  }
  function fmtTokens(n) {
    n = Number(n) || 0;
    return n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1) + 'k' : String(n);
  }
  // Provenance chips: the AI agent that wrote the answer, the search engine, the
  // token spend, and a deep-research marker. tokens aren't stored on-chain yet —
  // the chip renders the instant the field appears (e.tokens / prov.tokens), so
  // no viewer change is needed when the backend starts sending it.
  function renderChips(e) {
    const chips = [];
    const model = String(e.model || '').trim();
    if (model) chips.push('<span class="gv-note-chip" title="AI agent that wrote this answer">🤖 <b>' + esc(model.split('/').pop()) + '</b></span>');
    const engine = String(e.engine || '').trim();
    if (engine) chips.push('<span class="gv-note-chip" title="Search engine">🔎 ' + esc(engine) + '</span>');
    const tok = e.tokens != null ? e.tokens : (e.tokensUsed != null ? e.tokensUsed : (e.prov && e.prov.tokens));
    if (tok != null && Number(tok) > 0) chips.push('<span class="gv-note-chip gv-chip-tok" title="Tokens burned generating this answer">⚡ <b>' + esc(fmtTokens(tok)) + '</b> tokens</span>');
    if (e.mode === 'deep') chips.push('<span class="gv-note-chip gv-chip-deep">✦ Deep research</span>');
    noteEls.chips.innerHTML = chips.join('');
  }
  // In-viewer reader: pop a library entry's full answer + sources open as the
  // side drawer, so a question click reads in place instead of jumping tabs.
  // fallbackUrl (the entry's public page) is used both as the "Open full page"
  // target and as the graceful fallback if the JSON can't be fetched.
  async function openEntry(entryId, fallbackUrl) {
    pushTrail(entryId);   // every answer read in this viewer extends the trail
    buildNotePanel();
    const e = await loadEntry(entryId);
    if (!e) {
      if (fallbackUrl) {
        if (window.top === window.self) location.href = fallbackUrl;
        else window.open(fallbackUrl, '_blank', 'noopener,noreferrer');
      }
      return;
    }
    const meta = [];
    const n = Number(e.answeredAt || e.ts || 0);
    if (n > 0) {
      const ms = n > 1e15 ? Math.round(n / 1e6) : n;   // ns snapshots vs ms
      try { meta.push(new Date(ms).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })); } catch (_) {}
    }
    meta.push(e.askedBy === 'ai-gap' ? 'the library asked this itself' : 'community question');
    noteEls.kick.textContent = e.mode === 'deep' ? 'Deep research' : 'Library answer';
    noteEls.title.textContent = e.query || 'Library entry';
    noteEls.q.textContent = meta.join(' · ');
    renderChips(e);
    noteEls.body.textContent = e.answer || '';
    renderSources(noteEls.srcwrap, e.sources || []);
    noteEls.nav.style.display = 'none';
    // Deep entries carry a research note tree (research.json) — offer to explore it.
    if (e.mode === 'deep') {
      noteEls.research.style.display = '';
      noteEls.research.textContent = '📄 Explore the research notes →';
      noteEls.research.onclick = () => openResearch(entryId, e.query || '');
    } else if (searchApiBase) {
      // Fast entry → offer to escalate. Dedup on the canister is mode-blind
      // (the exact question would just #hit this entry), so the deep run is
      // submitted as its own "Deep dive:" question — a separate library entry
      // with the full research tree.
      const idle = '🔬 Dig deeper — run deep research';
      noteEls.research.style.display = '';
      noteEls.research.textContent = idle;
      noteEls.research.onclick = async () => {
        if (noteEls.research.dataset.busy) return;
        noteEls.research.dataset.busy = '1';
        try {
          const nid = await netResearch('Deep dive: ' + (e.query || ''), 'deep',
            (t) => { noteEls.research.textContent = '⏳ ' + t; });
          delete noteEls.research.dataset.busy;
          openEntry(nid, entryLink + encodeURIComponent(nid));
        } catch (err) {
          delete noteEls.research.dataset.busy;
          noteEls.research.textContent = '⚠️ ' + ((err && err.message) || 'Failed — try again');
          setTimeout(() => { if (!noteEls.research.dataset.busy) noteEls.research.textContent = idle; }, 3600);
        }
      };
    } else {
      noteEls.research.style.display = 'none';
      noteEls.research.onclick = null;
    }
    noteEls.openLink.style.display = '';
    noteEls.openLink.href = fallbackUrl || (entryLink + encodeURIComponent(entryId));
    notePanel.pages = []; notePanel.idx = 0; notePanel.open = true;
    noteEls.back.classList.add('on'); noteEls.panel.classList.add('on');
    if (g.hasNode(entryId)) setHovered(entryId);
  }

  /* ── Deep-research browser ────────────────────────────────────────────────
     A deep entry ships a research.json ({q, answer, pages:[{id,title,question,
     body,sources}]}). This opens it as a full research workspace ON ONE SCREEN:
     a Reader (synthesis + every note) and a Browse view (file-tree + notes with
     clickable [[wikilinks]]), plus a one-click Obsidian export — a .md vault
     (index + one note per file, wikilinked) zipped with a tiny dependency-free
     STORE-mode zip writer. */
  function loadResearch(id) {
    if (!entryBase) return Promise.resolve(null);
    const key = '__res_' + id;
    if (!entryReqs.has(key)) {
      entryReqs.set(key, fetch(entryBase + encodeURIComponent(id) + '/research.json')
        .then((r) => (r.ok ? r.json() : null)).catch(() => null));
    }
    return entryReqs.get(key);
  }
  const _crcTable = (() => { const t = []; for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
  function crc32(b) { let c = 0xFFFFFFFF; for (let i = 0; i < b.length; i++) c = _crcTable[(c ^ b[i]) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; }
  function makeZip(files) {                                   // STORE only (no deflate)
    const u16 = (n) => [n & 255, (n >>> 8) & 255];
    const u32 = (n) => [n & 255, (n >>> 8) & 255, (n >>> 16) & 255, (n >>> 24) & 255];
    const parts = [], central = []; let off = 0;
    for (const f of files) {
      const name = new TextEncoder().encode(f.name), data = f.data, crc = crc32(data);
      const local = [0x50, 0x4b, 0x03, 0x04, ...u16(20), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(crc), ...u32(data.length), ...u32(data.length), ...u16(name.length), ...u16(0)];
      parts.push(new Uint8Array(local), name, data);
      // central dir header: sig, ver-made-by, ver-needed, flags, method, modtime,
      // moddate, crc, comp, uncomp, fnamelen, extralen, commentlen, disk#,
      // internal attrs, external attrs, local-header offset.
      central.push(new Uint8Array([0x50, 0x4b, 0x01, 0x02, ...u16(20), ...u16(20), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(crc), ...u32(data.length), ...u32(data.length), ...u16(name.length), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(0), ...u32(off)]), name);
      off += local.length + name.length + data.length;
    }
    let cenSize = 0; for (const c of central) cenSize += c.length;
    const end = new Uint8Array([0x50, 0x4b, 0x05, 0x06, ...u16(0), ...u16(0), ...u16(files.length), ...u16(files.length), ...u32(cenSize), ...u32(off), ...u16(0)]);
    return new Blob([...parts, ...central, end], { type: 'application/zip' });
  }
  function download(blob, name) {
    const u = URL.createObjectURL(blob), a = document.createElement('a');
    a.href = u; a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(u), 1500);
  }
  function slug(s) { return (String(s || 'note').replace(/[\\/:*?"<>|#^[\]]+/g, '').replace(/\s+/g, ' ').trim().slice(0, 80)) || 'note'; }
  function exportObsidian(s) {
    const enc = new TextEncoder(), files = [], idxName = slug(s.query || 'Research');
    let idx = '# ' + (s.query || 'Research') + '\n\n' + (s.answer || '') + '\n\n## Notes\n' +
      s.pages.map((p) => '- [[' + slug(p.title) + ']]').join('\n') + '\n';
    files.push({ name: idxName + '.md', data: enc.encode(idx) });
    const seen = {};
    for (const p of s.pages) {
      let nm = slug(p.title); if (seen[nm]) nm += '-' + (++seen[slug(p.title)]); else seen[nm] = 1;
      let md = '# ' + (p.title || 'Note') + '\n\n';
      if (p.question) md += '> Angle: ' + p.question + '\n\n';
      md += (p.body || '') + '\n\n';
      const srcs = p.sources || [];
      if (srcs.length) md += '## Sources\n' + srcs.map((sc) => '- [' + (sc.title || sc.url || 'source') + '](' + (sc.url || '') + ')').join('\n') + '\n\n';
      md += '---\nPart of [[' + idxName + ']]\n';
      files.push({ name: nm + '.md', data: enc.encode(md) });
    }
    download(makeZip(files), idxName + ' — research.zip');
  }
  // Whole-topic vault: every question in the active topic cluster becomes a
  // note, cross-linked with Related [[wikilinks]] from the shared-source map —
  // the Obsidian mirror of what the "Related links" toggle draws on the canvas.
  const TOPIC_EXPORT_MAX = 60;
  async function exportTopicVault(set, label) {
    const ids = [...set].filter((id) => g.getNodeAttribute(id, 'entryId')).slice(0, TOPIC_EXPORT_MAX);
    const entries = (await Promise.all(ids.map((id) => loadEntry(id)))).filter(Boolean);
    if (!entries.length) throw new Error('No entries in this topic');
    const enc = new TextEncoder(), files = [];
    const nameOf = new Map(), seen = {};
    for (const e of entries) {
      let nm = slug(e.query || e.id);
      if (seen[nm]) { seen[nm]++; nm += '-' + seen[nm]; } else seen[nm] = 1;
      nameOf.set(e.id, nm);
    }
    const vault = slug(label || 'Topic');
    files.push({ name: vault + '.md', data: enc.encode(
      '# ' + (label || 'Topic') + '\n\nA Cafreso Library topic cluster — ' + entries.length + ' research notes.\n\n## Notes\n' +
      entries.map((e) => '- [[' + nameOf.get(e.id) + ']]').join('\n') + '\n') });
    for (const e of entries) {
      let md = '# ' + (e.query || 'Entry') + '\n\n' + (e.answer || '') + '\n\n';
      const srcs = e.sources || [];
      if (srcs.length) md += '## Sources\n' + srcs.map((s) => '- [' + (s.title || s.url || 'source') + '](' + (s.url || '') + ')').join('\n') + '\n\n';
      const rel = [...(relatedOf.get(e.id) || new Map()).keys()].filter((r) => nameOf.has(r));
      if (rel.length) md += '## Related\n' + rel.map((r) => '- [[' + nameOf.get(r) + ']]').join('\n') + '\n\n';
      md += '---\nPart of [[' + vault + ']]\n';
      files.push({ name: nameOf.get(e.id) + '.md', data: enc.encode(md) });
    }
    download(makeZip(files), vault + ' — vault.zip');
    return entries.length;
  }
  let resPanel = null, resEls = null, resState = null;
  function noteSectionHtml(p) {
    const srcs = p.sources || [];
    return '<div class="gv-res-note"><h3>' + esc(p.title || 'Note') + '</h3>' +
      (p.question ? '<div class="gv-res-angle">Angle: ' + esc(p.question) + '</div>' : '') +
      '<div class="gv-res-ntext">' + esc(p.body || '').replace(/\n/g, '<br>') + '</div>' +
      (srcs.length ? '<div class="gv-res-h">Sources</div>' + srcs.map((sc) => {
        const u = /^https?:\/\//i.test(sc.url || '') ? sc.url : '';
        const dom = (() => { try { return new URL(u).hostname.replace(/^www\./, ''); } catch (_) { return ''; } })();
        return '<a class="gv-note-src" ' + (u ? 'href="' + esc(u) + '" target="_blank" rel="noopener noreferrer"' : '') + '><b>' + esc(sc.title || u) + '</b>' + (dom ? '<span>' + esc(dom) + '</span>' : '') + '</a>';
      }).join('') : '') + '</div>';
  }
  function wikilinkNav(s, cur) {
    const links = [];
    if (cur !== -1) links.push('<a class="gv-wl" data-i="-1">[[' + esc(s.query || 'Synthesis') + ']]</a>');
    s.pages.forEach((p, i) => { if (i !== cur) links.push('<a class="gv-wl" data-i="' + i + '">[[' + esc(p.title || ('Note ' + (i + 1))) + ']]</a>'); });
    return links.length ? '<div class="gv-res-links"><div class="gv-res-h">Linked notes</div>' + links.join(' ') + '</div>' : '';
  }
  function renderRes() {
    const s = resState; if (!s) return;
    resEls.title.textContent = s.query || 'Research';
    resEls.tabs.querySelectorAll('.gv-res-tab').forEach((b) => b.classList.toggle('gv-on', b.dataset.m === s.mode));
    resEls.treeToggle.style.display = s.mode === 'browse' ? '' : 'none';
    if (s.mode === 'read') {
      resEls.tree.style.display = 'none';
      resEls.main.innerHTML = '<div class="gv-res-doc">' +
        (s.answer ? '<div class="gv-res-synth"><div class="gv-res-h">Synthesis</div>' + esc(s.answer).replace(/\n/g, '<br>') + '</div>' : '') +
        s.pages.map((p) => noteSectionHtml(p)).join('') + '</div>';
    } else {
      resEls.tree.style.display = s.treeOn ? '' : 'none';
      resEls.tree.innerHTML = '<div class="gv-res-h">Notes</div>' +
        '<a class="gv-res-tnode' + (s.sel === -1 ? ' gv-on' : '') + '" data-i="-1">◆ ' + esc(s.query || 'Synthesis') + '</a>' +
        s.pages.map((p, i) => '<a class="gv-res-tnode' + (s.sel === i ? ' gv-on' : '') + '" data-i="' + i + '">' + esc(p.title || ('Note ' + (i + 1))) + '</a>').join('');
      if (s.sel === -1) resEls.main.innerHTML = '<div class="gv-res-doc"><h2>' + esc(s.query || 'Synthesis') + '</h2><div class="gv-res-ntext">' + esc(s.answer || '').replace(/\n/g, '<br>') + '</div>' + wikilinkNav(s, -1) + '</div>';
      else { const p = s.pages[s.sel] || s.pages[0]; resEls.main.innerHTML = '<div class="gv-res-doc">' + noteSectionHtml(p) + wikilinkNav(s, s.sel) + '</div>'; }
      resEls.main.scrollTop = 0;
    }
  }
  function buildResearchPanel() {
    if (resPanel) return;
    const st = document.createElement('style');
    st.textContent =
      '.gv-res-back{position:fixed;inset:0;z-index:50;background:rgba(10,8,6,0.55);backdrop-filter:blur(3px);opacity:0;transition:opacity .2s;pointer-events:none;}' +
      '.gv-res-back.on{opacity:1;pointer-events:auto;}' +
      '.gv-res{position:fixed;z-index:51;top:0;right:0;bottom:0;width:min(860px,96vw);display:flex;flex-direction:column;' +
      'background:#1b1712;color:#e8e0d2;border-left:1px solid #3a332a;box-shadow:-24px 0 60px -20px rgba(0,0,0,0.6);' +
      'transform:translateX(100%);transition:transform .26s cubic-bezier(.2,.8,.2,1);font:14px/1.6 Inter,system-ui,sans-serif;}' +
      '.gv-res.on{transform:none;}.gv-light .gv-res{background:#fbf7ee;color:#2e2820;border-left-color:#e2d9c6;}' +
      '.gv-res-head{position:relative;padding:18px 20px 12px;border-bottom:1px solid rgba(255,255,255,0.08);}' +
      '.gv-light .gv-res-head{border-bottom-color:rgba(0,0,0,0.08);}' +
      '.gv-res-x{position:absolute;top:14px;right:16px;width:30px;height:30px;border:0;border-radius:8px;background:rgba(255,255,255,0.08);color:inherit;cursor:pointer;font-size:17px;}' +
      '.gv-light .gv-res-x{background:rgba(0,0,0,0.06);}' +
      '.gv-res-kick{font-size:10px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#c9b8e0;}' +
      '.gv-res-title{font-size:18px;font-weight:700;line-height:1.3;margin:6px 0 12px;padding-right:36px;}' +
      '.gv-res-tabs{display:flex;align-items:center;gap:8px;}' +
      '.gv-res-tab,.gv-res-tree-toggle,.gv-res-dl{padding:6px 12px;border:1px solid #3a332a;border-radius:8px;background:transparent;color:inherit;cursor:pointer;font:600 12px Inter,system-ui,sans-serif;}' +
      '.gv-light .gv-res-tab,.gv-light .gv-res-tree-toggle,.gv-light .gv-res-dl{border-color:#e2d9c6;}' +
      '.gv-res-tab.gv-on{background:rgba(201,184,224,0.18);border-color:rgba(201,184,224,0.5);color:#e0d0f4;}' +
      '.gv-res-dl{margin-left:auto;color:#f0c98a;border-color:rgba(240,180,90,0.35);}.gv-res-dl:hover{background:rgba(240,180,90,0.1);}' +
      '.gv-res-body{flex:1;display:flex;min-height:0;overflow:hidden;}' +
      '.gv-res-tree{width:230px;flex-shrink:0;overflow-y:auto;padding:14px;border-right:1px solid rgba(255,255,255,0.08);}' +
      '.gv-light .gv-res-tree{border-right-color:rgba(0,0,0,0.08);}' +
      '.gv-res-tnode{display:block;padding:6px 8px;border-radius:7px;cursor:pointer;color:inherit;text-decoration:none;font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}' +
      '.gv-res-tnode:hover{background:rgba(255,255,255,0.06);}.gv-res-tnode.gv-on{background:rgba(201,184,224,0.16);color:#e0d0f4;font-weight:600;}' +
      '.gv-res-main{flex:1;overflow-y:auto;padding:20px 24px;}.gv-res-doc{max-width:660px;}' +
      '.gv-res-doc h2{font-size:19px;font-weight:700;margin:0 0 12px;}' +
      '.gv-res-h{font-size:10px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#c9b8e0;opacity:.75;margin:16px 0 8px;}' +
      '.gv-res-note{margin:0 0 26px;}.gv-res-note h3{font-size:16px;font-weight:700;margin:0 0 6px;}' +
      '.gv-res-angle{font-size:12px;font-style:italic;opacity:.75;margin:0 0 10px;}' +
      '.gv-res-ntext,.gv-res-synth{font-size:13.5px;line-height:1.72;margin:0 0 12px;}' +
      '.gv-res-links{margin-top:18px;display:flex;flex-wrap:wrap;gap:8px 10px;}' +
      '.gv-wl{cursor:pointer;color:#c9b8e0;text-decoration:none;font-size:12px;border-bottom:1px dashed rgba(201,184,224,0.4);}.gv-wl:hover{color:#e0d0f4;}' +
      '.gv-res-note .gv-note-src,.gv-res-doc .gv-note-src{display:block;text-decoration:none;color:inherit;padding:6px 0;border-top:1px solid rgba(255,255,255,0.07);}' +
      '.gv-light .gv-res-note .gv-note-src{border-top-color:rgba(0,0,0,0.08);}' +
      '.gv-res-note .gv-note-src b{font-weight:600;font-size:12.5px;}.gv-res-note .gv-note-src span{display:block;font-size:11px;opacity:.7;font-family:ui-monospace,monospace;}' +
      '@media (max-width:640px){.gv-res-tree{position:absolute;z-index:2;height:calc(100% - 0px);background:#1b1712;}.gv-light .gv-res-tree{background:#fbf7ee;}}';
    document.head.appendChild(st);
    const back = document.createElement('div'); back.className = 'gv-res-back';
    const panel = document.createElement('div'); panel.className = 'gv-res';
    panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', 'Deep research');
    panel.innerHTML =
      '<div class="gv-res-head"><button class="gv-res-x" aria-label="Close">✕</button>' +
      '<div class="gv-res-kick">Deep research</div><h2 class="gv-res-title"></h2>' +
      '<div class="gv-res-tabs">' +
      '<button class="gv-res-tab gv-on" data-m="read">Reader</button>' +
      '<button class="gv-res-tab" data-m="browse">Browse</button>' +
      '<button class="gv-res-tree-toggle" title="Toggle file tree" style="display:none">☰ Tree</button>' +
      '<button class="gv-res-dl" title="Download as a Markdown vault for Obsidian">⬇ .md</button>' +
      '</div></div>' +
      '<div class="gv-res-body"><div class="gv-res-tree"></div><div class="gv-res-main"></div></div>';
    document.body.appendChild(back); document.body.appendChild(panel);
    resEls = {
      back, panel,
      title: panel.querySelector('.gv-res-title'),
      tabs: panel.querySelector('.gv-res-tabs'),
      tree: panel.querySelector('.gv-res-tree'),
      main: panel.querySelector('.gv-res-main'),
      treeToggle: panel.querySelector('.gv-res-tree-toggle'),
      dl: panel.querySelector('.gv-res-dl'),
    };
    const closeRes = () => { resPanel.open = false; back.classList.remove('on'); panel.classList.remove('on'); };
    back.addEventListener('click', closeRes);
    panel.querySelector('.gv-res-x').addEventListener('click', closeRes);
    resEls.tabs.addEventListener('click', (ev) => {
      const t = ev.target.closest('.gv-res-tab'); if (!t) return;
      resState.mode = t.dataset.m; if (resState.mode === 'browse' && resState.sel == null) resState.sel = -1; renderRes();
    });
    resEls.treeToggle.addEventListener('click', () => { resState.treeOn = !resState.treeOn; renderRes(); });
    resEls.dl.addEventListener('click', () => { if (resState) exportObsidian(resState); });
    const pick = (ev) => { const a = ev.target.closest('[data-i]'); if (!a) return; resState.sel = parseInt(a.dataset.i, 10); if (resState.mode !== 'browse') resState.mode = 'browse'; renderRes(); };
    resEls.tree.addEventListener('click', pick);
    resEls.main.addEventListener('click', pick);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && resPanel && resPanel.open) closeRes(); });
    resPanel = { open: false };
  }
  async function openResearch(entryId, query) {
    buildResearchPanel();
    const data = await loadResearch(entryId);
    const pages = (data && Array.isArray(data.pages)) ? data.pages : [];
    resState = { id: entryId, query: (data && data.q) || query || 'Research', answer: (data && data.answer) || '', pages, mode: 'read', sel: -1, treeOn: true };
    resEls.dl.style.display = pages.length ? '' : 'none';
    if (!pages.length) resEls.main.innerHTML = '<div class="gv-res-doc"><p style="opacity:.7">No research notes were stored for this entry.</p></div>';
    else renderRes();
    resPanel.open = true; resEls.back.classList.add('on'); resEls.panel.classList.add('on');
  }

  renderer.on('enterNode', ({ node }) => {
    setHovered(node);
    container.style.cursor = nodeAction(node) ? 'pointer' : 'grab';
    showTip(node);
  });
  renderer.on('leaveNode', () => {
    if (dragged) return;
    // A pinned node keeps its highlight on mouseout — that's the whole point of
    // pinning. Move to a different node re-hovers normally (enterNode fires
    // first); leaving to empty space just holds the pin.
    if (pinned) { container.style.cursor = 'default'; return; }
    setHovered(null);
    container.style.cursor = 'default';
    hideTip();
  });
  // Safety net: sigma's leaveNode can miss a fast mouse exit off a small,
  // still-moving (physics/replay) node — the cursor leaves the canvas
  // entirely with no leaveNode ever firing, leaving the tip stuck on screen.
  // A real pointerleave on the container itself always fires, so use it as a
  // backstop (same pin exception as above — a pinned tip is meant to persist).
  container.addEventListener('mouseleave', () => {
    if (dragged || pinned) return;
    setHovered(null);
    hideTip();
  });

  /* ── drag ────────────────────────────────────────────────────────────────
     The dragged node pins (fixed) while the sim keeps running, so its
     neighbors trail after it on their springs. */
  let dragged = null, dragPos = null, didDrag = false;

  function startDrag(node) {
    dragged = node; dragPos = null; didDrag = false;
    g.setNodeAttribute(node, 'fixed', true);
    container.style.cursor = 'grabbing';
    warm(2000);
  }
  function moveDrag(coords) {
    if (!dragged) return;
    didDrag = true;
    dragPos = renderer.viewportToGraph(coords);
    g.setNodeAttribute(dragged, 'x', dragPos.x);
    g.setNodeAttribute(dragged, 'y', dragPos.y);
    if (animateOn) warm(2000); else renderer.refresh({ skipIndexation: true });
  }
  function endDrag() {
    if (!dragged) return;
    g.removeNodeAttribute(dragged, 'fixed');
    container.style.cursor = 'default';
    dragged = null; dragPos = null;
    warm(900);
    // A drag that ends off-node never fires leaveNode.
    if (hovered && !hops) setHovered(null);
  }

  renderer.on('downNode', ({ node }) => startDrag(node));
  const mouse = renderer.getMouseCaptor();
  mouse.on('mousemovebody', (e) => {
    if (!dragged) return;
    moveDrag(e);
    // Synchronous emit + post-emit flag check is what stops the camera panning.
    e.preventSigmaDefault();
    if (e.original) { e.original.preventDefault(); e.original.stopPropagation(); }
  });
  mouse.on('mouseup', endDrag);
  const touch = renderer.getTouchCaptor && renderer.getTouchCaptor();
  if (touch) {
    touch.on('touchup', endDrag);
    touch.on('touchmove', (e) => {
      if (!dragged) return;
      const t = e.touches && e.touches[0];
      if (!t || (e.touches && e.touches.length > 1)) return endDrag();  // 2 fingers = pinch
      moveDrag(t);
      e.preventSigmaDefault();
    });
  }

  /* What a click DOES on a node: a source node opens its URL; a topic node in a
     deep-research tree (carries a `page` id) opens its note page in the panel
     below. A node with neither just highlights. */
  // Where a question node's entry lives. Overridable (&entrylink=…) so a
  // staging deploy can point at itself; the default is the public library.
  const entryLink = P('entrylink', 'https://cafreso.com/library?e=');
  // Embed bridge: with &embed=post, a question click posts to the parent frame
  // (which opens its own in-page drawer) instead of a new tab. targetOrigin is
  // pinned — never '*' — so the message can't leak to a hostile embedder.
  const embedPost = P('embed', '') === 'post';
  const embedOrigin = P('embedorigin', 'https://cafreso.com');
  // Ghost "people also wonder" questions (worker-baked kind:'suggest' nodes)
  // click through to the library with the question pre-filled and running —
  // the graph as an exploration frontier, not just an archive.
  // Generic trailing-param swap: works whether entrylink ends in ?e= or a
  // custom &entrylink=…&entry= — a literal ?e=$ match silently fell through
  // to entryLink unchanged for any non-default entrylink, misrouting the
  // question text into the wrong param with no visible error.
  const askLink = /[?&][^=]+=$/.test(entryLink)
    ? entryLink.replace(/([^=]+)=$/, 'ask=')
    : entryLink + (entryLink.includes('?') ? '&' : '?') + 'ask=';
  function nodeAction(node) {
    const a = g.getNodeAttributes(node);
    if (a.suggest) return { kind: 'ask', q: fullLabel.get(node) || a.label };
    const url = a.url;
    if (url && /^https?:\/\//i.test(url)) return { kind: 'url', url };
    const page = g.getNodeAttribute(node, 'page');
    if (page && pagesSrc) return { kind: 'page', page };
    const entryId = g.getNodeAttribute(node, 'entryId');
    if (entryId) return { kind: 'entry', url: entryLink + encodeURIComponent(entryId), entryId };
    return null;
  }
  function doAction(act) {
    if (!act) return;
    if (act.kind === 'ask') { window.open(askLink + encodeURIComponent(act.q), '_blank', 'noopener,noreferrer'); return; }
    if (act.kind === 'url') window.open(act.url, '_blank', 'noopener,noreferrer');
    else if (act.kind === 'page') openNote(act.page);
    // Standalone, reading the answer is the natural next step — navigate in
    // place and let Back return to the web. Embedded (the library hero / an
    // explore iframe), never hijack the host page: post to the parent when it
    // opted in (&embed=post), else a new tab.
    else if (act.kind === 'entry') {
      // Embedded with embed=post (the library hero): let the parent run its own
      // in-page drawer. Everywhere else — the standalone full viewer, a plain
      // iframe — pop the answer open IN this viewer instead of navigating away.
      if (embedPost && window.parent !== window) {
        try { window.parent.postMessage({ type: 'cafreso:openEntry', entryId: act.entryId, url: act.url }, embedOrigin); return; }
        catch (_) {}
      }
      openEntry(act.entryId, act.url);
    }
  }

  /* Shift-click shortest path: the merged library web connects two questions
     THROUGH the sources they share, so "how are these related?" has a visible
     answer. bidirectional() returns the node route (or null if disconnected);
     we dim everything off it and pulse a charge down the line. */
  function showPath(a, b) {
    let route = null;
    try { route = bidirectional(g, a, b); } catch (_) { route = null; }
    pinned = null;
    if (!route || route.length < 2) {
      // Disconnected: say so via the tip rather than silently doing nothing.
      pathSet = null;
      setHovered(a); showTip(a);
      if (tip && tip.dataset.node === a) {
        tip.innerHTML += '<div class="tip-hint">no path to “' + esc(titleOf(b)) + '”</div>';
      }
      renderer.refresh({ skipIndexation: true });
      return;
    }
    pathSet = new Set(route);
    hovered = null; hops = null; hTarget = 0;
    for (let i = 0; i + 1 < route.length; i++) emitForce(route[i], route[i + 1], i * PULSE_STEP, T.pulse, true);
    // Frame the whole route: center on its midpoint node.
    const mid = renderer.getNodeDisplayData(route[(route.length / 2) | 0]);
    if (mid) camera.animate({ x: mid.x, y: mid.y }, { duration: 350 });
    renderer.refresh({ skipIndexation: true });
    tick();
  }

  /* Click acts. On touch there is no hover, so the first tap stands in for it
     and a second tap on the same node acts. */
  let tapped = null, tapAt = 0;
  // Shortest-path: shift-click one node, then another, and the connecting route
  // through shared sources pulses. pathA holds the first pick.
  let pathA = null;
  function clearPath() { pathA = null; pathSet = null; }
  /** Cluster-label plates are click targets that visually cover nodes, so the
      hit-test must run for BOTH clickNode and clickStage — sigma routes the
      event to whichever it finds first, and a label over a dense cluster
      almost always has a node under the cursor. */
  function hitClusterLabel(event) {
    if (!event || !labelRects.length) return false;
    const { x, y } = event;
    for (const r of labelRects) {
      if (x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) {
        setActiveTopic(r.key);
        return true;
      }
    }
    return false;
  }
  renderer.on('clickNode', ({ node, event }) => {
    if (didDrag) { didDrag = false; return; }
    if (hitClusterLabel(event)) return;
    // Shift-click builds a path between two picks (desktop only — no shift key
    // on touch). First pick arms; second draws.
    if (event && event.original && event.original.shiftKey && !coarse) {
      if (!pathA || pathA === node) { pathA = node; pinned = node; setHovered(node); showTip(node); return; }
      showPath(pathA, node);
      pathA = null;
      return;
    }
    const act = nodeAction(node);
    if (coarse) {
      if (!act) { setHovered(node); showTip(node); return; }
      const now = Date.now();
      if (tapped === node && now - tapAt < 4000) { doAction(act); tapped = null; return; }
      tapped = node; tapAt = now;
      setHovered(node); showTip(node);
      return;
    }
    if (!act) {
      // Non-actionable (a domain, or a question with no entry): latch the
      // neighborhood so the labels are readable. Click again / Escape releases.
      if (pinned === node) { pinned = null; clearPath(); setHovered(null); hideTip(); }
      else { pinned = node; setHovered(node); showTip(node); }
      return;
    }
    doAction(act);
  });
  renderer.on('clickStage', ({ event }) => {
    if (hitClusterLabel(event)) return;
    tapped = null; pinned = null; clearPath();
    setHovered(null); hideTip();
  });
  renderer.on('doubleClickNode', (e) => {
    e.preventSigmaDefault();
    const d = renderer.getNodeDisplayData(e.node);
    if (d) camera.animate({ x: d.x, y: d.y, ratio: Math.max(camera.ratio / 1.7, 0.08) }, { duration: 350 });
  });

  // Escape releases a pin, a drawn path, or an armed shift-click pick. Guarded
  // so it doesn't fight the search box / settings panel (those stopPropagation
  // their own Escape before it reaches here).
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (replayActive) { stopReplay(); return; }
    if (pinned || pathSet || pathA) {
      pinned = null; pathA = null; pathSet = null;
      setHovered(null); hideTip();
      renderer.refresh({ skipIndexation: true });
    }
  });

  camera.on('updated', () => { if (hovered) showTip(hovered); else hideTip(); });
  requestAnimationFrame(() => { try { renderer.refresh(); } catch (_) {} });
  if (typeof ResizeObserver !== 'undefined') {
    new ResizeObserver(() => {
      document.body.classList.toggle('gv-compact', compact());
      try { renderer.refresh(); } catch (_) {}
    }).observe(container);
  }

  /* ── controls ────────────────────────────────────────────────────────── */
  const zoomIn = document.getElementById('gv-zoom-in');
  const zoomOut = document.getElementById('gv-zoom-out');
  const resetBtn = document.getElementById('gv-reset');
  if (zoomIn) zoomIn.addEventListener('click', () => camera.animatedZoom({ duration: 200 }));
  if (zoomOut) zoomOut.addEventListener('click', () => camera.animatedUnzoom({ duration: 200 }));
  if (resetBtn) resetBtn.addEventListener('click', () => {
    // Re-frame the live node cloud rather than snapping to a fixed home: after
    // dragging/zooming, "reset" should mean "show me everything again."
    if (libMode) fitToNodes(0.1, 350);
    else camera.animate({ x: 0.5, y: 0.5, ratio: 1, angle: 0 }, { duration: 250 });
    warm(900);
  });

  // ⟵ retraces the reading trail: pop the current stop, land on the previous
  // one with its tip up. The thread on the canvas shortens with it.
  const trailBack = document.getElementById('gv-trail-back');
  if (trailBack) trailBack.addEventListener('click', () => {
    if (trail.length < 2) return;
    trail.pop();
    updateTrailUi();
    const id = trail[trail.length - 1];
    if (!g.hasNode(id)) return;
    const d = renderer.getNodeDisplayData(id);
    if (d) camera.animate({ x: d.x, y: d.y, ratio: Math.min(camera.ratio, 0.35) }, { duration: 350 });
    pinned = id; setHovered(id); showTip(id);
  });

  /* Copy a deep link to the focused node. Reuses the current URL, swaps in a
     fresh &focus=<id>, so pasting it reopens the graph centered on that node
     with its tip up — every question in the web is shareable. */
  copyBtn = document.getElementById('gv-copy-link');
  if (copyBtn) copyBtn.addEventListener('click', async () => {
    const node = pinned || hovered;
    if (!node) return;
    const u = new URL(location.href);
    u.searchParams.set('focus', node);
    // A trail makes the link a guided tour: the recipient gets the thread
    // drawn and can retrace it with ⟵, landing where the sender was looking.
    if (trail.length > 1) u.searchParams.set('trail', trail.join('~'));
    else u.searchParams.delete('trail');
    const link = u.toString();
    try { await navigator.clipboard.writeText(link); }
    catch (_) { try { prompt('Copy link to this node:', link); } catch (__) {} }
    const prev = copyBtn.textContent;
    copyBtn.textContent = '✓';
    setTimeout(() => { copyBtn.textContent = prev; }, 1200);
  });

  const hint = document.getElementById('hint');
  if (hint) {
    hint.textContent = coarse
      ? 'pinch to zoom · drag to pan · tap a node for details'
      : 'scroll to zoom · drag the canvas or a node · hover for details';
    // Fades on the first real interaction rather than on a timer, so nobody
    // loses it mid-sentence.
    const dismiss = () => hint.classList.add('gv-hidden');
    container.addEventListener('wheel', dismiss, { once: true, passive: true });
    container.addEventListener('mousedown', dismiss, { once: true });
    container.addEventListener('touchstart', dismiss, { once: true, passive: true });
  }

  /* ── growth replay ───────────────────────────────────────────────────────
     "Watch the library think": ▶ hides the web and re-asks it in order — each
     question ignites (ring + first sparks to its sources), its sources surface
     with it, and the hint pill becomes a date ticker. The reveal order comes
     from index.json timestamps (fallback: the zero-padded entry ids, which are
     append-ordered). ■ or Escape restores the full web instantly. */
  let replayTimer = 0, replayHintWas = '';
  const replayBtn = document.getElementById('gv-replay');
  function stopReplay() {
    if (!replayActive) return;
    clearTimeout(replayTimer);
    replayActive = false; replayVisible = null;
    if (replayBtn) {
      replayBtn.textContent = '▶'; replayBtn.title = "Replay the library's growth";
      replayBtn.setAttribute('aria-label', "Replay the library's growth");
      replayBtn.setAttribute('aria-pressed', 'false');
    }
    if (hint) { hint.textContent = replayHintWas; hint.classList.add('gv-hidden'); }
    renderer.refresh({ skipIndexation: true });
  }
  async function startReplay() {
    const prov = await loadProvenance();
    const entries = [];
    g.forEachNode((id, a) => { if (a.entryId) entries.push(id); });
    entries.sort((x, y) => {
      const tx = ((prov && prov.get(x)) || {}).ts || 0;
      const ty = ((prov && prov.get(y)) || {}).ts || 0;
      return (tx - ty) || (x < y ? -1 : 1);
    });
    if (entries.length < 2 || replayActive) return;
    // A lingering pin/tip from before the replay would ride the reveal with
    // its hover halo — the replay owns the stage while it runs.
    pinned = null; pathA = null; pathSet = null;
    setHovered(null); hideTip();
    replayActive = true;
    replayVisible = new Set();
    replayHintWas = hint ? hint.textContent : '';
    if (replayBtn) {
      replayBtn.textContent = '■'; replayBtn.title = 'Stop the replay';
      // Textual title/textContent alone left a screen reader announcing "Replay
      // the library's growth" throughout playback — aria-label/aria-pressed
      // need updating alongside the visual swap, same as the topic pills already do.
      replayBtn.setAttribute('aria-label', 'Stop the replay');
      replayBtn.setAttribute('aria-pressed', 'true');
    }
    fitToNodes(0.1, 400);
    const step = clamp(9000 / entries.length, 45, 260);
    let i = 0;
    const reveal = () => {
      if (!replayActive) return;
      if (i >= entries.length) {
        // Hold the completed web for a beat so the ending reads as an arrival.
        if (hint) hint.textContent = 'the library, ' + entries.length + ' questions later';
        replayTimer = setTimeout(stopReplay, 1600);
        return;
      }
      const id = entries[i++];
      replayVisible.add(id);
      let k = 0;
      g.forEachNeighbor(id, (nb) => {
        replayVisible.add(nb);
        if (k++ < 2) emitForce(id, nb, 140, T.spark, false);
      });
      if (fxc) rings.push({ node: id, at: performance.now(), dur: 1000 });
      if (hint) {
        const ts = ((prov && prov.get(id)) || {}).ts;
        const when = ts ? new Date(ts / 1e6) : null;
        hint.textContent =
          (when ? when.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) + ' · ' : '') +
          i + ' / ' + entries.length + ' questions';
        hint.classList.remove('gv-hidden');
      }
      renderer.refresh({ skipIndexation: true });
      tick();
      replayTimer = setTimeout(reveal, step);
    };
    reveal();
  }
  if (replayBtn && libMode && entryBase) {
    replayBtn.style.display = '';
    replayBtn.addEventListener('click', () => (replayActive ? stopReplay() : startReplay()));
    // ?replay=1 — auto-play on load, the target of the library page's "watch it
    // grow" link. Delayed past the intro bloom (700ms hold + 640-iteration
    // settle ≈ 3s) so the replay reveals a settled map, not a moving ring.
    if (P('replay', null) === '1') {
      setTimeout(() => { if (!replayActive) startReplay(); }, reduceMotion ? 400 : 3600);
    }
  }

  /* ── search ──────────────────────────────────────────────────────────────
     Dims everything that doesn't match as you type; Enter flies to the best
     hit. Keys are bound to the input only — an embedding page keeps its own. */
  const searchWrap = document.getElementById('gv-search');
  const searchInput = document.getElementById('gv-search-input');
  const searchBtn = document.getElementById('gv-search-toggle');
  if (searchInput && searchWrap) {
    let debounce = 0, flyDebounce = 0;
    // Prefix hits win, then the biggest node — "icp" should land on the
    // hub named ICP, not on the first source that mentions it.
    const bestMatch = (q) => {
      if (!q || !searchSet || !searchSet.size) return null;
      let best = null, bestScore = -1;
      for (const id of searchSet) {
        const label = String(fullLabel.get(id) || g.getNodeAttribute(id, 'label') || '').toLowerCase();
        const score = (label.startsWith(q) ? 1000 : 0) + (baseSize.get(id) || 0);
        if (score > bestScore) { bestScore = score; best = id; }
      }
      return best;
    };
    const apply = () => {
      const q = searchInput.value.trim().toLowerCase();
      if (!q) searchSet = null;
      else {
        searchSet = new Set();
        // Match the full label, not the clamped one — the tail of a question
        // is often the part someone remembers.
        g.forEachNode((id, a) => { if (String(fullLabel.get(id) || a.label || '').toLowerCase().includes(q)) searchSet.add(id); });
      }
      searchWrap.classList.toggle('gv-has-q', !!q);
      renderer.refresh({ skipIndexation: true });
      // Live fly-to: once the query is specific enough to mean something
      // (3+ chars, and it actually narrowed the graph), glide toward the best
      // hit and ping it — "where's the Pluto question" answers itself while
      // you're still typing. Slower debounce than the dim so the camera never
      // chases keystrokes; no hover/pin so nothing fights the input focus.
      clearTimeout(flyDebounce);
      if (q.length >= 3 && searchSet && searchSet.size && searchSet.size < g.order) {
        flyDebounce = setTimeout(() => {
          const best = bestMatch(q);
          if (!best) return;
          const d = renderer.getNodeDisplayData(best);
          if (!d) return;
          camera.animate({ x: d.x, y: d.y, ratio: clamp(camera.ratio, 0.18, 0.5) }, { duration: 450 });
          if (fxc) { rings.push({ node: best, at: performance.now() + 200, dur: 1200 }); tick(); }
        }, 320);
      }
    };
    searchInput.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(apply, 80); });
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        clearTimeout(flyDebounce);
        searchInput.value = ''; apply(); searchInput.blur();
        if (searchBtn) searchWrap.classList.remove('gv-open');
      } else if (e.key === 'Enter') {
        e.preventDefault();
        clearTimeout(flyDebounce);
        const best = bestMatch(searchInput.value.trim().toLowerCase());
        if (!best) return;
        const d = renderer.getNodeDisplayData(best);
        if (d) camera.animate({ x: d.x, y: d.y, ratio: 0.25 }, { duration: 400 });
        setHovered(best); showTip(best);
      }
    });
    if (searchBtn) {
      searchBtn.addEventListener('click', () => {
        searchWrap.classList.toggle('gv-open');
        if (searchWrap.classList.contains('gv-open')) searchInput.focus();
        if (hint) hint.classList.add('gv-hidden');
      });
      searchInput.addEventListener('blur', () => {
        if (!searchInput.value.trim()) searchWrap.classList.remove('gv-open');
      });
    }

    /* Magnifying glass = a NEW library search (not the node filter): look for an
       exact hit, else queue the query on the search network and open the answer
       in the drawer when it lands. Same public HTTP the /library page uses —
       find.json → /search/submit → poll /search/job. Needs the library base
       (derived from the graph snapshot path); hidden if this isn't a library graph. */
    const goBtn = document.getElementById('gv-search-go');
    const newsBtn = document.getElementById('gv-search-news');
    if (!searchApiBase) {
      if (goBtn) goBtn.style.display = 'none';
      if (newsBtn) newsBtn.style.display = 'none';
    }
    let netSearching = false;
    let newsMode = false;
    // Progress goes to a visible pill under the box — placeholder text is
    // hidden while a query is typed, which is exactly when feedback matters.
    const statusEl = document.getElementById('gv-search-status');
    let statusTimer = 0;
    const status = (t, hold) => {
      clearTimeout(statusTimer);
      if (statusEl) {
        statusEl.textContent = t || '';
        statusEl.classList.toggle('gv-show', !!t);
        if (t && hold) statusTimer = setTimeout(() => statusEl.classList.remove('gv-show'), hold);
      }
    };
    async function runNetworkSearch() {
      const query = searchInput.value.trim();
      if (!searchApiBase || netSearching) return;
      if (!query) {
        // An empty click must never be a no-op: open + focus the box and say why.
        searchWrap.classList.add('gv-open');
        searchInput.focus();
        status('Type a question, then hit 🔍 to research it', 3000);
        return;
      }
      netSearching = true;
      if (goBtn) { goBtn.disabled = true; goBtn.classList.add('gv-spin'); }
      const done = () => {
        netSearching = false;
        if (goBtn) { goBtn.disabled = false; goBtn.classList.remove('gv-spin'); }
      };
      try {
        const id = await netResearch(query, newsMode ? 'news' : 'fast', (t) => status(t));
        searchInput.value = ''; apply(); searchInput.blur();
        done(); status('');
        openEntry(id, entryLink + encodeURIComponent(id));
      } catch (err) {
        done(); status((err && err.message) || 'Search error — try again', 3200);
      }
    }
    if (goBtn) goBtn.addEventListener('click', runNetworkSearch);
    if (newsBtn) newsBtn.addEventListener('click', () => {
      newsMode = !newsMode;
      newsBtn.classList.toggle('gv-on', newsMode);
      newsBtn.setAttribute('aria-pressed', String(newsMode));
      status(newsMode ? 'News mode on — 🔍 will favor fresh, dated coverage' : 'News mode off', 2400);
    });
  }

  /* ── settings ────────────────────────────────────────────────────────────
     Only knobs FA2 actually has. It has no link-distance parameter — edge
     length is emergent from the repulsion/gravity equilibrium — so there is
     no slider pretending to be one. */
  const gearBtn = document.getElementById('gv-settings-toggle');
  const panel = document.getElementById('gv-settings');
  if (gearBtn && panel) {
    if (layoutOff) panel.classList.add('gv-no-physics');
    gearBtn.addEventListener('click', () => {
      panel.classList.toggle('gv-open');
      if (hint) hint.classList.add('gv-hidden');
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') panel.classList.remove('gv-open'); });

    const bind = (id, fn) => { const el = document.getElementById(id); if (el) el.addEventListener('input', fn); return el; };
    // Log scale: the interesting range of both forces is bunched at the low end.
    const logMap = (v, lo, hi) => Math.exp(Math.log(lo) + (v / 100) * (Math.log(hi) - Math.log(lo)));
    let reheat = 0;
    const applyPhysics = () => {
      clearTimeout(reheat);
      reheat = setTimeout(() => warm(2500), 150);
    };
    bind('gv-gravity', (e) => { fa2.gravity = logMap(+e.target.value, 0.005, 0.5); applyPhysics(); });
    bind('gv-repel', (e) => { fa2.scalingRatio = logMap(+e.target.value, 2, 120); applyPhysics(); });
    bind('gv-fade', (e) => { fadeStart = +e.target.value; renderer.refresh({ skipIndexation: true }); });
    const animEl = document.getElementById('gv-animate');
    if (animEl) {
      animEl.checked = animateOn;
      animEl.disabled = layoutOff;
      animEl.addEventListener('change', () => {
        animateOn = animEl.checked && !layoutOff;
        if (animateOn) warm(3000); else simBudget = 0;
      });
    }
    const sigEl = document.getElementById('gv-signals');
    if (sigEl) {
      sigEl.checked = signalsOn;
      sigEl.disabled = !fxc;
      sigEl.addEventListener('change', () => {
        signalsOn = sigEl.checked && !!fxc;
        // Off means off now, not once the last spark finishes crossing.
        if (!signalsOn) { sparks.length = 0; rings.length = 0; }
        tick();
      });
    }
    // Question color rules (Graph Styler-style): identity gold, topic tint,
    // or origin (who asked — community / gap cron / news cron). Library only.
    const modeRow = document.getElementById('gv-colormode-row');
    const modeEl = document.getElementById('gv-colormode');
    if (modeRow && modeEl && libMode) {
      modeRow.style.display = '';
      modeEl.addEventListener('change', () => { applyColorMode(modeEl.value); });
      onTopicsChanged.push(() => { if (colorMode === 'topic') applyColorMode('topic'); });
    }
    const clEl = document.getElementById('gv-clusterlabels');
    const clRow = document.getElementById('gv-clusterlabels-row');
    if (clEl && clRow && clc) {
      clRow.style.display = '';
      clEl.checked = true;
      clEl.addEventListener('change', () => {
        // Emptying viewTopics would kill the filter too; gate the draw instead.
        clc.canvas.style.display = clEl.checked ? '' : 'none';
        renderer.refresh({ skipIndexation: true });
      });
    }
  }

  /* ── legend ──────────────────────────────────────────────────────────────
     Data-driven from what actually rendered: the search worker colors source
     nodes by domain, but a generic knowledge graph carries no `domain` at all,
     and then there is nothing honest to explain. */
  const legendToggle = document.getElementById('legend-toggle');
  const legend = document.getElementById('legend');
  if (legendToggle && legend) {
    const byDomain = new Map();
    g.forEachNode((id, attrs) => {
      if (!attrs.domain) return;
      const cur = byDomain.get(attrs.domain);
      if (cur) cur.count++;
      else byDomain.set(attrs.domain, { color: attrs.color || '#cabfa9', count: 1 });
    });
    if (byDomain.size > 0) {
      const top = [...byDomain.entries()].sort((a, b) => b[1].count - a[1].count).slice(0, 8);
      const rest = byDomain.size - top.length;
      legend.innerHTML =
        '<div class="legend-title">Sources by domain</div>' +
        top.map(([d, v]) => (
          '<div class="legend-row"><span class="legend-swatch" style="background:' + esc(v.color) + '"></span>' + esc(d) + '</div>'
        )).join('') +
        (rest > 0 ? '<div class="legend-row gv-muted">+' + rest + ' more</div>' : '');
      legendToggle.addEventListener('click', () => legend.classList.toggle('gv-open'));
    } else if (viewTopics.length) {
      /* Library mode: each topic row is a FILTER — clicking dims everything
         outside the topic (via setActiveTopic) and frames it; clicking again
         clears. Rows render from the shared viewTopics model, so the legend,
         the on-canvas cluster labels, and the color modes always agree — and
         when the cron's curated topics.json swaps the model in, every
         consumer re-renders through onTopicsChanged at once. */
      const clampLabel = (s) => (s.length > 30 ? s.slice(0, 28).trimEnd() + '…' : s);
      function renderTopicLegend() {
        legend.innerHTML =
          '<div class="legend-title">Topics</div>' +
          '<div class="legend-row gv-muted"><span class="legend-swatch" style="background:#F5D25D"></span>questions (gold)</div>' +
          viewTopics.map((t) => (
            '<div class="legend-row legend-topic' + (activeTopic === t.key ? ' gv-on' : '') + '" data-key="' + esc(t.key) + '" title="' + esc(t.label) + '">' +
            '<span class="legend-swatch" style="background:' + esc(t.color) + '"></span>' + esc(clampLabel(t.label)) + '</div>'
          )).join('') +
          // Appears only while a topic filter is on: one click turns the whole
          // cluster into an Obsidian vault (exportTopicVault).
          '<div class="legend-row legend-export" style="display:' + (activeTopic && entryBase ? '' : 'none') + '" title="Download every question in this topic as a wikilinked Obsidian .md vault">⬇ Export topic as vault</div>';
      }
      legend.onclick = async (ev) => {
        const ex = ev.target.closest('.legend-export');
        if (ex) {
          if (ex.dataset.busy || !topicSet) return;
          const t = viewTopics.find((x) => x.key === activeTopic);
          ex.dataset.busy = '1';
          const orig = ex.textContent;
          ex.textContent = '⏳ Gathering entries…';
          try {
            const n = await exportTopicVault(topicSet, t ? t.label : 'Topic');
            ex.textContent = '✓ ' + n + ' notes exported';
          } catch (err) {
            ex.textContent = '⚠️ ' + ((err && err.message) || 'Export failed');
          }
          setTimeout(() => { delete ex.dataset.busy; ex.textContent = orig; }, 2800);
          return;
        }
        const row = ev.target.closest('[data-key]');
        if (row) setActiveTopic(row.dataset.key);
      };
      renderTopicLegend();
      onTopicsChanged.push(renderTopicLegend);
      legendToggle.addEventListener('click', () => legend.classList.toggle('gv-open'));

      /* First-glance key: a new user sees gold and tinted dots with no clue
         which is which. One always-on line answers it; clicking opens the full
         legend, and after the point is made it calms down rather than leaving. */
      const key = document.getElementById('gv-key');
      if (key) {
        function renderKey() {
          key.innerHTML =
            '<span class="legend-swatch" style="background:#F5D25D"></span>questions' +
            '<span class="gv-key-stack">' +
            viewTopics.slice(0, 3)
              .map((t) => '<span class="legend-swatch" style="background:' + esc(t.color) + '"></span>').join('') +
            '</span>topics';
        }
        renderKey();
        onTopicsChanged.push(renderKey);
        key.style.display = 'inline-flex';
        key.addEventListener('click', () => legend.classList.toggle('gv-open'));
        setTimeout(() => key.classList.add('gv-calm'), 9000);
      }
    } else {
      legendToggle.style.display = 'none';
    }
  }

  /* ── topic pills ─────────────────────────────────────────────────────────
     A tappable chip per topic riding the bottom edge — the graph's primary
     topic nav on touch (no hover, no on-canvas label precision) and a faster
     one on desktop. Same setActiveTopic the legend rows and cluster labels
     drive, so all three stay one filter. */
  const pillsEl = document.getElementById('gv-pills');
  if (pillsEl && libMode) {
    const shortLabel = (s) => (s.length > 22 ? s.slice(0, 20).trimEnd() + '…' : s);
    function renderPills() {
      if (!viewTopics.length) { pillsEl.style.display = 'none'; return; }
      pillsEl.style.display = 'block';
      pillsEl.innerHTML = viewTopics.map((t) => (
        '<button type="button" class="gv-pill' + (activeTopic === t.key ? ' gv-on' : '') + '"' +
        ' data-key="' + esc(t.key) + '" title="' + esc(t.label) + '"' +
        ' aria-pressed="' + (activeTopic === t.key) + '">' +
        '<span class="legend-swatch" style="background:' + esc(t.color) + '"></span>' +
        esc(shortLabel(t.label)) + '</button>'
      )).join('');
      // Keep the active pill in view when the row scrolls.
      const on = pillsEl.querySelector('.gv-on');
      if (on && on.scrollIntoView) { try { on.scrollIntoView({ block: 'nearest', inline: 'nearest' }); } catch (_) {} }
    }
    pillsEl.addEventListener('click', (ev) => {
      const b = ev.target.closest('.gv-pill');
      if (b) setActiveTopic(b.dataset.key);
    });
    renderPills();
    onTopicsChanged.push(renderPills);
  }

  const brand = document.getElementById('brand');
  if (brand) {
    let stats = '';
    if (libMode) {
      let nq = 0;
      g.forEachNode((id, a) => { if (a.entryId) nq++; });
      stats = ' · ' + nq + (nq === 1 ? ' question' : ' questions') + ' · ' + (g.order - nq) + ' sources';
    }
    brand.textContent = (snap.title || 'Knowledge graph') + stats + ' · CafresoHQ';
  }

  if (P('show_analytics', '0') === '1') {
    const el = document.getElementById('analytics');
    if (el) {
      // Use precomputed analytics if the snapshot carries them; otherwise
      // synthesize them client-side. The merged library graph ships none, so
      // without this the panel never rendered. Betweenness is O(V·E) — fine at
      // library scale (tens–hundreds of nodes), guarded above ~800 so a huge
      // graph doesn't hang the main thread on load.
      let m, topList;
      if (snap.analytics && snap.analytics.metrics) {
        m = snap.analytics.metrics;
        topList = (snap.analytics.topInfluential || []).slice(0, 6).map((t) => titleOf(t.id));
      } else {
        const N = g.order, E = g.size;
        let mod = 0;
        try { if (commOf) mod = modularity(g, { getNodeCommunity: (id) => commOf[id] }); } catch (_) { mod = N > 1 ? (2 * E) / (N * (N - 1)) : 0; }
        let influential = [];
        if (N > 1 && N <= 800) {
          let bc = {};
          try { bc = betweennessCentrality(g, { normalized: true }); } catch (_) { bc = {}; }
          influential = Object.keys(bc).sort((a, b) => bc[b] - bc[a]).slice(0, 6);
        } else {
          // Too large (or trivially small) for betweenness — degree is a cheap,
          // honest proxy for "what everything connects through".
          influential = g.nodes().sort((a, b) => g.degree(b) - g.degree(a)).slice(0, 6);
        }
        topList = influential.map((id) => fullLabel.get(id) || titleOf(id));
        m = {
          structure: commMeta ? (commMeta.size + ' topic clusters') : 'one web',
          nodes: N, edges: E,
          communityCount: commMeta ? commMeta.size : 1,
          modularity: mod,
        };
      }
      el.style.display = 'block';
      const top = topList.map((label) => '<div title="' + esc(label) + '">◆ ' + esc(label.length > 34 ? label.slice(0, 32).trimEnd() + '…' : label) + '</div>').join('');
      el.innerHTML =
        '<button id="gv-analytics-close" type="button" aria-label="Close graph analysis" title="Close">✕</button>' +
        '<div class="gv-panel-title">Graph analysis</div>' +
        '<div class="gv-pill">' + esc(m.structure || '') + '</div>' +
        '<div class="gv-muted" style="line-height:1.5">Notes <b>' + m.nodes + '</b> · Links <b>' + m.edges + '</b><br>Topics <b>' + m.communityCount + '</b> · Modularity <b>' + (m.modularity || 0).toFixed(2) + '</b></div>' +
        '<div class="gv-panel-title" style="margin:10px 0 4px">Most influential</div>' + top +
        '<div id="gv-gaps"></div>';
      // No way to dismiss it previously — on a library with several gap rows
      // the (unbounded-height, until the CSS fix above) panel sat on top of
      // the bottom pill bar and clipped tooltips with no way to get it out
      // of the way short of reloading without &show_analytics=1.
      const closeBtn = document.getElementById('gv-analytics-close');
      if (closeBtn) closeBtn.addEventListener('click', () => { el.style.display = 'none'; });

      /* ── structural gaps (the InfraNodus move) ──────────────────────────
         The pairs of big topic clusters with the FEWEST edges between them
         are where the library's blind spots live. Naming them is half the
         insight; the other half is the ⚡ button, which drops a bridging
         question straight into the network-search box — the same pipeline
         the gap cron feeds, but aimed by structure instead of guesswork.
         Rendered async so curated topic names can label the clusters. */
      function renderGaps() {
        const gapsEl = document.getElementById('gv-gaps');
        if (!gapsEl || !viewTopics.length || viewTopics.length < 2) return;
        const tops = viewTopics.slice(0, 6);
        // Count question-to-question relatedness across topics via shared
        // domain neighborhoods (relatedOf), plus direct edges — a domain node
        // sitting in both topics IS a connection.
        const edgeCount = new Map();   // 'i:j' -> n
        const idxOf = new Map();
        tops.forEach((t, i) => { for (const id of t.set) if (!idxOf.has(id)) idxOf.set(id, i); });
        g.forEachEdge((e, attrs, s, t2) => {
          const a = idxOf.get(s), b = idxOf.get(t2);
          if (a == null || b == null || a === b) return;
          const k = Math.min(a, b) + ':' + Math.max(a, b);
          edgeCount.set(k, (edgeCount.get(k) || 0) + 1);
        });
        const pairs = [];
        for (let i = 0; i < tops.length; i++) {
          for (let j = i + 1; j < tops.length; j++) {
            const n = edgeCount.get(i + ':' + j) || 0;
            pairs.push({ i, j, n, norm: n / Math.max(1, Math.min(tops[i].set.size, tops[j].set.size)) });
          }
        }
        pairs.sort((a, b) => a.norm - b.norm || a.n - b.n);
        const gaps = pairs.slice(0, 3);
        if (!gaps.length) return;
        const short = (s) => (s.length > 13 ? s.slice(0, 12).trimEnd() + '…' : s);
        gapsEl.innerHTML =
          '<div class="gv-panel-title" style="margin:10px 0 4px">Structural gaps</div>' +
          gaps.map((p, k) => (
            '<div class="gv-gap-row" title="' + esc(tops[p.i].label) + ' ↔ ' + esc(tops[p.j].label) + ' — ' + p.n + ' connecting link' + (p.n === 1 ? '' : 's') + '">' +
            '<span><span class="legend-swatch" style="background:' + esc(tops[p.i].color) + '"></span>' + esc(short(tops[p.i].label)) +
            ' <span class="gv-muted">✕</span> ' +
            '<span class="legend-swatch" style="background:' + esc(tops[p.j].color) + '"></span>' + esc(short(tops[p.j].label)) + '</span>' +
            (searchApiBase ? '<button class="gv-gap-bridge" data-gap="' + k + '" title="Research a question that bridges these two topics">⚡</button>' : '') +
            '</div>'
          )).join('');
        gapsEl.onclick = (ev) => {
          const btn = ev.target.closest('.gv-gap-bridge');
          if (!btn) return;
          const p = gaps[+btn.dataset.gap];
          if (!p) return;
          const q = 'How does ' + tops[p.i].label + ' relate to ' + tops[p.j].label + '?';
          const input = document.getElementById('gv-search-input');
          const wrap = document.getElementById('gv-search');
          if (input && wrap) {
            input.value = q;
            wrap.classList.add('gv-open', 'gv-has-q');
            input.focus();
            const st = document.getElementById('gv-search-status');
            if (st) { st.textContent = 'Bridge question ready — hit 🔍 to research it'; st.classList.add('gv-show'); setTimeout(() => st.classList.remove('gv-show'), 3500); }
          }
        };
      }
      renderGaps();
      onTopicsChanged.push(renderGaps);
    }
  }

  /* ── growth ──────────────────────────────────────────────────────────────
     A library that only ever grows should be able to say so. Diff the node ids
     against what was here last visit (keyed per graph URL, so the hero and a
     single entry keep separate memories) and let the new ones ignite.

     Two things this deliberately does NOT do: fire on a first visit, where
     "new since your last visit" would be a lie about every node; and fire when
     everything is new, which means the graph was swapped, not grown. Both
     cases would turn a real signal into decoration. */
  const SEEN_PREFIX = 'cafreso:gv:seen:';
  const SEEN_MAX_KEYS = 40;
  let fresh = [];
  try {
    const ids = g.nodes();
    let hsh = 0;
    const keySrc = src || 'inline';
    for (let i = 0; i < keySrc.length; i++) hsh = (hsh * 31 + keySrc.charCodeAt(i)) | 0;
    const key = SEEN_PREFIX + (hsh >>> 0).toString(36);
    const prev = JSON.parse(localStorage.getItem(key) || 'null');
    if (prev && Array.isArray(prev.ids) && prev.ids.length) {
      const seen = new Set(prev.ids);
      fresh = ids.filter((id) => !seen.has(id));
      if (fresh.length === ids.length) fresh = [];   // swapped, not grown
    }
    localStorage.setItem(key, JSON.stringify({ t: Date.now(), ids }));

    // Every entry graph ever opened leaves a key behind, and this library is
    // designed to grow without limit — so without a cap the memory of what
    // you've seen eventually eats the quota and starts throwing. Keep the most
    // recently visited graphs and forget the rest; the cost of forgetting is
    // one missed "+N new" badge on a graph you haven't opened in months.
    const keys = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith(SEEN_PREFIX)) {
        let t = 0;
        try { t = (JSON.parse(localStorage.getItem(k)) || {}).t || 0; } catch (_) {}
        keys.push([k, t]);
      }
    }
    if (keys.length > SEEN_MAX_KEYS) {
      keys.sort((a, b) => b[1] - a[1]);
      for (const [k] of keys.slice(SEEN_MAX_KEYS)) localStorage.removeItem(k);
    }
  } catch (_) { fresh = []; }   // private mode / quota — growth is a bonus, never a dependency

  if (fresh.length && signalsOn) {
    // Staggered, and started late enough that the web has taken its shape —
    // ignitions land on nodes that are already roughly where they'll stay.
    const now = performance.now();
    fresh.slice(0, 40).forEach((id, i) => rings.push({ node: id, at: now + 900 + i * 85, dur: 1500 }));
  }

  const newBadge = document.getElementById('gv-new');
  if (newBadge && fresh.length) {
    const n = fresh.length;
    newBadge.textContent = '+' + n + (n === 1 ? ' new node' : ' new nodes') + ' since your last visit';
    newBadge.style.display = 'block';
    requestAnimationFrame(() => newBadge.classList.add('gv-in'));
    // Click to walk the growth: each press flies to the next new node and
    // hovers it, so "what changed?" is one button rather than a hunt.
    let at = 0;
    newBadge.addEventListener('click', () => {
      const id = fresh[at++ % fresh.length];
      if (!g.hasNode(id)) return;
      const d = renderer.getNodeDisplayData(id);
      if (d) camera.animate({ x: d.x, y: d.y, ratio: 0.3 }, { duration: 420 });
      setHovered(id); showTip(id);
      if (hint) hint.classList.add('gv-hidden');
    });
    setTimeout(() => newBadge.classList.remove('gv-in'), 9000);
  }

  /** Frame the node cloud to fill the viewport, ignoring the handful of nodes
      physics flings to the fringe (p2..p98 trim) so the dense body — not one
      stray outlier — decides the zoom. Works in measured viewport pixels via
      graphToViewport, so it's independent of sigma's internal normalization,
      then converts the target center back through viewportToFramedGraph for
      the camera (whose x/y live in framed-graph space). */
  function fitToNodes(pad, duration) {
    try {
      const dims = renderer.getDimensions();
      const xs = [], ys = [];
      g.forEachNode((id) => { const p = vp(id); xs.push(p.x); ys.push(p.y); });
      if (xs.length < 3) return;
      xs.sort((a, b) => a - b); ys.sort((a, b) => a - b);
      const q = (a, t) => a[Math.floor(t * (a.length - 1))];
      const x0 = q(xs, 0.02), x1 = q(xs, 0.98), y0 = q(ys, 0.02), y1 = q(ys, 0.98);
      const bw = Math.max(1, x1 - x0), bh = Math.max(1, y1 - y0);
      const scale = Math.max(bw / ((1 - 2 * pad) * dims.width), bh / ((1 - 2 * pad) * dims.height));
      const targetRatio = camera.getBoundedRatio(camera.ratio * scale);
      const c = renderer.viewportToFramedGraph({ x: (x0 + x1) / 2, y: (y0 + y1) / 2 });
      camera.animate({ x: c.x, y: c.y, ratio: targetRatio, angle: 0 }, { duration: duration || 600 });
    } catch (_) { /* fit is best-effort; a missed frame just leaves the view as-is */ }
  }

  // Float, then calm: small graphs settle in ~1.5s, the biggest get ~5s.
  // Ring-seeded graphs hold the clean circle for a beat, then bloom (the
  // graph-engine intro). The bloom budget is deliberately SHORT of
  // equilibrium: run to convergence and the attraction folds the ring back
  // into the ball the ring exists to avoid — the readable state is mid-bloom,
  // same place graph-engine freezes. The fit afterwards frames wherever the
  // bloom actually landed so it fills the canvas instead of drifting high-left.
  if (!reduceMotion) {
    if (ringSeeded) {
      // 640 iterations — measured on the live snapshot: radial dispersion
      // (sd/meanR) reaches ~0.8 there, i.e. the ring has fully opened into a
      // cloud of islands; half that count freezes visibly annular. Spent in
      // iterations so every load of the same snapshot settles into the same
      // map (louvain is rng-pinned, the ring is deterministic, FA2 always was).
      setTimeout(() => {
        warmIters(640, () => {
          try { renderer.refresh(); } catch (_) {}
          fitToNodes(0.1, 600);
        });
      }, 700);
    } else {
      warm(Math.min(1500 + g.order * 8, 5000));
    }
  }
  // warm() is a no-op when the layout is off, but signals still need the loop.
  if (signalsOn) tick();

  /* ── deep-link focus (?focus=<nodeId>) ─────────────────────────────────────
     Fly to a node on load, pin it, open its tip — the target of the copy-link
     button, so a shared link lands where the sharer was looking. Fired once the
     layout has settled (getNodeDisplayData needs indexation, and flying before
     the web calms would leave the node drifting out from under the camera). */
  // A shared trail rebuilds the thread before the focus fly-in, so the link
  // opens as the sender's tour: thread drawn, camera on their last stop.
  const trailParam = P('trail', null);
  if (trailParam) {
    for (const id of String(trailParam).split('~')) {
      if (g.hasNode(id) && trail[trail.length - 1] !== id) trail.push(id);
    }
    updateTrailUi();
  }

  const focusId = P('focus', null);
  if (focusId && g.hasNode(focusId)) {
    const settleMs = reduceMotion || layoutOff ? 60 : Math.min(1500 + g.order * 8, 5000) + 120;
    setTimeout(() => {
      if (!g.hasNode(focusId)) return;
      const d = renderer.getNodeDisplayData(focusId);
      if (d) camera.animate({ x: d.x, y: d.y, ratio: 0.3 }, { duration: 500 });
      pinned = focusId;
      setHovered(focusId); showTip(focusId);
      if (hint) hint.classList.add('gv-hidden');
    }, settleMs);
  }
}
// main() is async, so anything it throws becomes an unhandled rejection that
// never reaches the console as an error — the viewer just half-renders and says
// nothing. Surface it.
main().catch((e) => { console.error('graph-viewer: failed to render —', e); });
