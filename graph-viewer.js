/**
 * graph-viewer.js — standalone READ-ONLY public graph viewer (sigma + graphology).
 *
 * Bundled by esbuild into dist-ui/graph-viewer.js and paired with graph-viewer.html.
 * Renders a snapshot produced by graph-engine.js exportSnapshot() — positions,
 * community colors and betweenness sizes are precomputed, so this viewer ships
 * NEITHER the FA2 layout NOR the analytics worker (small bundle, canister-friendly).
 *
 * Mirrors the InfraNodus share-URL contract:
 *   ?g=<snapshot-url>  &background=dark|default  &most_influential=bc|bc2
 *   &maxnodes=N  &labelsize=proportional  &drawedges=true|false
 *   &selected=highlight  &dynamic=highlight  &show_analytics=1  &demo=1
 */
import Graph from 'graphology';
import Sigma from 'sigma';
import forceAtlas2 from 'graphology-layout-forceatlas2';

const COMMUNITY_COLORS = [
  '#E8A9A9', '#7DB5B5', '#C9B8E0', '#F0C674', '#A5C4A1', '#E0A47C',
  '#8FB7E0', '#D9A0C8', '#B7C97D', '#9C8FE0', '#E0C58F', '#7DC9B0',
];
const qs = new URLSearchParams(location.search);
const P = (k, d) => { const v = qs.get(k); return v == null ? d : v; };

function titleOf(id) { return String(id).split('/').pop().replace(/\.md$/, ''); }

async function main() {
  const container = document.getElementById('graph');
  const dark = !['default', 'light'].includes(P('background', 'dark'));
  document.body.style.background = dark ? '#171310' : '#f4efe6';

  const src = P('g', null) || P('graph', null);
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

  // Obsidian-style organic layout: settle the snapshot's seed positions with
  // a synchronous ForceAtlas2 pass (cheap at library scale; ?layout=none to
  // keep the raw snapshot geometry).
  if (P('layout', 'fa2') !== 'none' && g.order > 2 && g.order <= 600) {
    try {
      const settings = forceAtlas2.inferSettings(g);
      forceAtlas2.assign(g, {
        iterations: 220,
        settings: { ...settings, gravity: 0.06, scalingRatio: 24, slowDown: 4, adjustSizes: true },
      });
    } catch (_) { /* seed positions still render fine */ }
  }

  const drawEdges = P('drawedges', 'true') !== 'false';
  const highlight = P('selected', 'highlight') === 'highlight' || P('dynamic', '') === 'highlight';
  let hovered = null;
  const neighborhood = (n) => { const s = new Set([n]); g.forEachNeighbor(n, (x) => s.add(x)); return s; };

  const renderer = new Sigma(g, container, {
    allowInvalidContainer: true,
    renderLabels: true,
    renderEdges: drawEdges,
    labelColor: { color: dark ? '#e9e2d4' : '#2b2620' },
    labelFont: 'Inter, system-ui, sans-serif',
    labelRenderedSizeThreshold: 6,
    defaultEdgeColor: dark ? 'rgba(168,152,190,0.18)' : 'rgba(120,108,90,0.2)',
    minCameraRatio: 0.05, maxCameraRatio: 14, zIndex: true,
    nodeReducer: (id, d) => {
      const r = { ...d };
      if (highlight && hovered) {
        const nb = neighborhood(hovered);
        if (!nb.has(id)) { r.color = dark ? '#2a2733' : '#d8d0c4'; r.label = ''; r.zIndex = 0; }
        else { r.zIndex = 1; if (id === hovered) r.highlighted = true; }
      }
      return r;
    },
    edgeReducer: (id, d) => {
      const r = { ...d };
      if (highlight && hovered) {
        const s = g.source(id), t = g.target(id);
        if (s === hovered || t === hovered) { r.color = dark ? 'rgba(232,169,169,0.5)' : 'rgba(180,90,90,0.45)'; r.zIndex = 1; }
        else r.hidden = true;
      }
      return r;
    },
  });

  // Hover card — title, domain, and the worker LLM's one-line note for the
  // source under the cursor (Obsidian-style). Data comes from node attributes
  // written by the search worker's graph snapshot; nodes without extras just
  // highlight their neighborhood.
  const tip = document.getElementById('tip');
  const esc = (s) => String(s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  function showTip(node) {
    if (!tip) return;
    const a = g.getNodeAttributes(node);
    if (!a.note && !a.url && !a.domain) { tip.style.display = 'none'; return; }
    tip.innerHTML =
      '<div class="tip-title">' + esc(a.label) + '</div>' +
      (a.domain ? '<div class="tip-domain">' + esc(a.domain) + '</div>' : '') +
      (a.note ? '<div class="tip-note">' + esc(a.note) + '</div>' : '') +
      (a.url ? '<div class="tip-hint">click to open ↗</div>' : '');
    const p = renderer.graphToViewport({ x: a.x, y: a.y });
    tip.style.display = 'block';
    const r = tip.getBoundingClientRect();
    tip.style.left = Math.min(Math.max(8, p.x + 14), innerWidth - r.width - 8) + 'px';
    tip.style.top = Math.min(Math.max(8, p.y - r.height / 2), innerHeight - r.height - 8) + 'px';
  }
  function hideTip() { if (tip) tip.style.display = 'none'; }

  renderer.on('enterNode', ({ node }) => {
    if (highlight) { hovered = node; renderer.refresh({ skipIndexation: true }); }
    container.style.cursor = g.getNodeAttribute(node, 'url') ? 'pointer' : 'default';
    showTip(node);
  });
  renderer.on('leaveNode', () => {
    if (highlight) { hovered = null; renderer.refresh({ skipIndexation: true }); }
    container.style.cursor = 'default';
    hideTip();
  });
  renderer.on('clickNode', ({ node }) => {
    const url = g.getNodeAttribute(node, 'url');
    if (url && /^https?:\/\//i.test(url)) window.open(url, '_blank', 'noopener,noreferrer');
  });
  renderer.getCamera().on('updated', hideTip);
  // Repaint once the container is definitely laid out (handles 0-height-at-mount).
  requestAnimationFrame(() => { try { renderer.refresh(); } catch (_) {} });
  if (typeof ResizeObserver !== 'undefined') new ResizeObserver(() => { try { renderer.refresh(); } catch (_) {} }).observe(container);

  // Zoom / pan / reset — the graph was otherwise only discoverable via
  // sigma's default mouse-wheel zoom, with no on-screen affordance at all.
  const camera = renderer.getCamera();
  const zoomIn = document.getElementById('gv-zoom-in');
  const zoomOut = document.getElementById('gv-zoom-out');
  const resetBtn = document.getElementById('gv-reset');
  if (zoomIn) zoomIn.addEventListener('click', () => camera.animatedZoom({ duration: 200 }));
  if (zoomOut) zoomOut.addEventListener('click', () => camera.animatedUnzoom({ duration: 200 }));
  if (resetBtn) resetBtn.addEventListener('click', () => camera.animate({ x: 0.5, y: 0.5, ratio: 1, angle: 0 }, { duration: 250 }));

  // First-visit hint fades on the first real interaction, not on a timer —
  // someone still reading it shouldn't have it vanish underneath them.
  const hint = document.getElementById('hint');
  if (hint) {
    const dismissHint = () => { hint.classList.add('gv-hidden'); };
    container.addEventListener('wheel', dismissHint, { once: true, passive: true });
    container.addEventListener('mousedown', dismissHint, { once: true });
    container.addEventListener('touchstart', dismissHint, { once: true, passive: true });
  }

  // Domain-color legend — data-driven from what's actually rendered (the
  // search worker colors source nodes by domain hash; a generic knowledge
  // graph may have no 'domain' attribute at all, in which case there's
  // nothing meaningful to show and the toggle stays hidden).
  const legendToggle = document.getElementById('legend-toggle');
  const legend = document.getElementById('legend');
  if (legendToggle && legend) {
    const byDomain = new Map();   // domain -> {color, count}
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
          '<div class="legend-row"><span class="legend-swatch" style="background:' + v.color + '"></span>' + esc(d) + '</div>'
        )).join('') +
        (rest > 0 ? '<div class="legend-row" style="color:#8f8574">+' + rest + ' more</div>' : '');
      legendToggle.addEventListener('click', () => {
        legend.style.display = legend.style.display === 'block' ? 'none' : 'block';
      });
    } else {
      legendToggle.style.display = 'none';
    }
  }

  // Watermark + optional analytics panel.
  const brand = document.getElementById('brand');
  if (brand) brand.textContent = (snap.title || 'Knowledge graph') + ' · CafresoHQ';

  if (P('show_analytics', '0') === '1' && snap.analytics && snap.analytics.metrics) {
    const m = snap.analytics.metrics;
    const panel = document.getElementById('analytics');
    if (panel) {
      panel.style.display = 'block';
      const top = (snap.analytics.topInfluential || []).slice(0, 6).map((t) => '<div>◆ ' + titleOf(t.id) + '</div>').join('');
      panel.innerHTML =
        '<div style="font-weight:600;color:#F5D25D;margin-bottom:6px">Graph analysis</div>' +
        '<div style="display:inline-block;padding:2px 8px;border-radius:20px;background:rgba(245,210,93,.16);color:#F5D25D;text-transform:capitalize;margin-bottom:8px">' + (m.structure || '') + '</div>' +
        '<div style="color:#cabfa9;line-height:1.5">Notes <b>' + m.nodes + '</b> · Links <b>' + m.edges + '</b><br>Topics <b>' + m.communityCount + '</b> · Modularity <b>' + (m.modularity || 0).toFixed(2) + '</b></div>' +
        '<div style="font-weight:600;color:#F5D25D;margin:10px 0 4px">Most influential</div>' + top;
    }
  }
}
main();
