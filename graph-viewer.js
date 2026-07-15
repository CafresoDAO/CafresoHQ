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
 */
import Graph from 'graphology';
import Sigma from 'sigma';
import forceAtlas2 from 'graphology-layout-forceatlas2';

const qs = new URLSearchParams(location.search);
const P = (k, d) => { const v = qs.get(k); return v == null ? d : v; };

function titleOf(id) { return String(id).split('/').pop().replace(/\.md$/, ''); }

/* Node identity stays in the snapshot's colors; gold is reserved as the single
   "attention" channel (hover, halo, adjacent edges) so the two never compete.
   Edge alphas are tuned against premultiplied blending (see glRgba) — at rest
   they land a hairline just above the plane, ~rgb(53,48,42) on dark. */
const THEME = {
  dark: {
    bg: '#14110E',
    edge: [201, 191, 169, 0.18], edgeDim: [201, 191, 169, 0.03], edgeHot: [245, 210, 93, 0.7],
    nodeDim: [38, 33, 25], label: [220, 211, 192], ring: 'rgba(245,210,93,0.9)',
  },
  light: {
    bg: '#F6F1E7',
    edge: [92, 82, 64, 0.2], edgeDim: [92, 82, 64, 0.04], edgeHot: [158, 112, 20, 0.7],
    nodeDim: [230, 222, 206], label: [58, 52, 43], ring: 'rgba(158,112,20,0.9)',
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
  const baseRgb = new Map();   // node -> [r,g,b] as authored (dim lerps from this)
  const baseSize = new Map();
  const minSize = compact() ? 3 : 2.5;
  g.forEachNode((id, a) => {
    const degSize = 2 + Math.sqrt(g.degree(id)) * 1.6;
    const snapSize = typeof a.size === 'number' ? a.size : 4;
    const size = clamp(0.45 * snapSize + 0.55 * degSize, minSize, 14);
    g.setNodeAttribute(id, 'size', size);
    baseSize.set(id, size);
    baseRgb.set(id, parseColor(a.color));
  });

  const drawEdges = P('drawedges', 'true') !== 'false';
  const highlight = P('selected', 'highlight') === 'highlight' || P('dynamic', '') === 'highlight';
  const proportional = P('labelsize', '') === 'proportional';
  const reduceMotion = (() => { try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (_) { return false; } })();
  const coarse = (() => { try { return matchMedia('(pointer: coarse)').matches; } catch (_) { return false; } })();

  /* ── hover / search state ────────────────────────────────────────────────
     `h` is the animated hover intensity (0..1). Everything dim-related reads
     it, so sliding from one node to the next swaps the neighborhood set while
     h stays high — no fade-out-and-back-in flicker. */
  let hovered = null, nbrs = null, h = 0, hTarget = 0;
  let searchSet = null;
  const dimOf = new Map();     // node -> 0..1, written by nodeReducer, read by drawLabel

  function setHovered(node) {
    hovered = node;
    nbrs = null;
    if (node && g.hasNode(node)) {
      const s = new Set([node]);
      g.forEachNeighbor(node, (x) => s.add(x));
      nbrs = s;
    }
    hTarget = node ? 1 : 0;
    tick();
  }

  // How dimmed a node currently is: search misses dim hard and immediately,
  // hover dims everything outside the hovered neighborhood as `h` ramps in.
  function dimFactor(id) {
    if (searchSet && !searchSet.has(id)) return 1;
    if (highlight && nbrs && !nbrs.has(id)) return 0.9 * h;
    return 0;
  }

  let fadeStart = parseFloat(P('textfade', '6')) || 6;

  const renderer = new Sigma(g, container, {
    allowInvalidContainer: true,
    renderLabels: true,
    labelFont: 'Inter, system-ui, sans-serif',
    labelSize: 11,
    labelWeight: '500',
    // The alpha ramp in drawNodeLabel is the real gate; sigma's own threshold
    // would pop labels in and out on top of it.
    labelRenderedSizeThreshold: 0,
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
      ctx.font = (proportional ? 9 + data.size * 0.35 : 11) + "px 'Inter', system-ui, sans-serif";
      ctx.fillStyle = rgbaCss(T.label, alpha.toFixed(3));
      ctx.fillText(data.label, data.x + data.size + 4, data.y + 4);
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
      const dim = dimFactor(id);
      dimOf.set(id, dim);
      if (dim > 0.001) {
        r.color = rgbCss(lerpRgb(baseRgb.get(id) || [202, 191, 169], T.nodeDim, dim));
        r.zIndex = 0;
      } else if (id === hovered) r.zIndex = 2;
      else if (nbrs && nbrs.has(id)) r.zIndex = 1;
      // Sigma treats `highlighted` as "draw the hover layer"; we drive it
      // ourselves so the halo only ever tracks the real hovered node.
      r.highlighted = id === hovered && h > 0.01;
      return r;
    },
    edgeReducer: (id, d) => {
      const r = { ...d };
      if (!drawEdges) { r.hidden = true; return r; }
      const s = g.source(id), t = g.target(id);
      const sd = dimOf.has(s) ? dimOf.get(s) : dimFactor(s);
      const td = dimOf.has(t) ? dimOf.get(t) : dimFactor(t);
      const adjacent = highlight && hovered && (s === hovered || t === hovered);
      if (adjacent) {
        r.color = glRgba(T.edgeHot, +lerp(T.edge[3], T.edgeHot[3], h).toFixed(3));
        r.size = lerp(0.6, 1.1, h);
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

  /* ── physics ─────────────────────────────────────────────────────────────
     One rAF ticker drives both the layout burst and the hover tween, so the
     page settles to zero CPU the moment neither has anything left to do. */
  const fa2 = { ...forceAtlas2.inferSettings(g), gravity: 0.06, scalingRatio: 24, slowDown: 4, adjustSizes: true };
  const layoutOff = P('layout', 'fa2') === 'none' || g.order <= 2 || g.order > 600;
  let animateOn = !layoutOff && !reduceMotion;
  // Budget is measured in frames actually rendered, not wall-clock: a graph
  // opened in a background tab gets no rAF at all, and a deadline would expire
  // unspent and leave it frozen at its seed positions forever. Spending only on
  // real frames also means the browser's own rAF pause IS the battery guard.
  let simBudget = 0, raf = 0, last = 0;

  function warm(ms) {
    if (!animateOn) return;
    simBudget = Math.max(simBudget, ms);
    tick();
  }
  function tick() { if (!raf) raf = requestAnimationFrame(frame); }

  function frame(ts) {
    raf = 0;
    const dt = last ? Math.min(ts - last, 64) : 16;
    last = ts;

    const simming = animateOn && simBudget > 0;
    if (simming) simBudget -= dt;
    if (simming) {
      // Pin before and after: assign() writes every node's position back from
      // its own matrix, so the dragged node has to be re-stated on both sides
      // of the burst to stay exactly under the cursor.
      if (dragged && dragPos) { g.setNodeAttribute(dragged, 'x', dragPos.x); g.setNodeAttribute(dragged, 'y', dragPos.y); }
      try { forceAtlas2.assign(g, { iterations: 2, settings: fa2 }); } catch (_) { simBudget = 0; }
      if (dragged && dragPos) { g.setNodeAttribute(dragged, 'x', dragPos.x); g.setNodeAttribute(dragged, 'y', dragPos.y); }
    }

    // ~95% of the way in ~210ms — an ease-out that retargets cleanly mid-slide.
    const tweening = Math.abs(hTarget - h) > 0.005;
    if (tweening) h += (hTarget - h) * (1 - Math.exp(-dt / 70));
    else h = hTarget;

    if (simming || tweening || h !== 0) {
      renderer.refresh({ skipIndexation: !simming });
      if (hovered) showTip(hovered);
    }
    if (simming || tweening) tick(); else last = 0;
  }

  /* ── hover card ──────────────────────────────────────────────────────────
     Title, domain, and the worker LLM's one-line note for the source under the
     cursor. Nodes without extras just highlight their neighborhood. */
  const tip = document.getElementById('tip');
  const esc = (s) => String(s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  function showTip(node) {
    if (!tip || !g.hasNode(node)) return;
    const a = g.getNodeAttributes(node);
    if (!a.note && !a.url && !a.domain) { tip.style.display = 'none'; return; }
    if (tip.dataset.node !== node) {
      tip.dataset.node = node;
      tip.innerHTML =
        '<div class="tip-title">' + esc(a.label) + '</div>' +
        (a.domain ? '<div class="tip-domain">' + esc(a.domain) + '</div>' : '') +
        (a.note ? '<div class="tip-note">' + esc(a.note) + '</div>' : '') +
        (a.url ? '<div class="tip-hint">' + (coarse ? 'tap again to open ↗' : 'click to open ↗') + '</div>' : '');
    }
    const p = renderer.graphToViewport({ x: a.x, y: a.y });
    tip.style.display = 'block';
    const r = tip.getBoundingClientRect();
    tip.style.left = Math.min(Math.max(8, p.x + 14), innerWidth - r.width - 8) + 'px';
    tip.style.top = Math.min(Math.max(8, p.y - r.height / 2), innerHeight - r.height - 8) + 'px';
  }
  function hideTip() { if (tip) { tip.style.display = 'none'; tip.dataset.node = ''; } }

  renderer.on('enterNode', ({ node }) => {
    setHovered(node);
    container.style.cursor = g.getNodeAttribute(node, 'url') ? 'pointer' : 'grab';
    showTip(node);
  });
  renderer.on('leaveNode', () => {
    if (dragged) return;
    setHovered(null);
    container.style.cursor = 'default';
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
    if (hovered && !nbrs) setHovered(null);
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

  /* Click opens the source. On touch there is no hover, so the first tap
     stands in for it and a second tap on the same node opens. */
  let tapped = null, tapAt = 0;
  renderer.on('clickNode', ({ node }) => {
    if (didDrag) { didDrag = false; return; }
    const url = g.getNodeAttribute(node, 'url');
    if (!url || !/^https?:\/\//i.test(url)) return;
    if (coarse) {
      const now = Date.now();
      if (tapped === node && now - tapAt < 4000) { window.open(url, '_blank', 'noopener,noreferrer'); tapped = null; return; }
      tapped = node; tapAt = now;
      setHovered(node); showTip(node);
      return;
    }
    window.open(url, '_blank', 'noopener,noreferrer');
  });
  renderer.on('clickStage', () => { if (coarse) { tapped = null; setHovered(null); hideTip(); } });
  renderer.on('doubleClickNode', (e) => {
    e.preventSigmaDefault();
    const d = renderer.getNodeDisplayData(e.node);
    if (d) camera.animate({ x: d.x, y: d.y, ratio: Math.max(camera.ratio / 1.7, 0.08) }, { duration: 350 });
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
    camera.animate({ x: 0.5, y: 0.5, ratio: 1, angle: 0 }, { duration: 250 });
    warm(900);
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

  /* ── search ──────────────────────────────────────────────────────────────
     Dims everything that doesn't match as you type; Enter flies to the best
     hit. Keys are bound to the input only — an embedding page keeps its own. */
  const searchWrap = document.getElementById('gv-search');
  const searchInput = document.getElementById('gv-search-input');
  const searchBtn = document.getElementById('gv-search-toggle');
  if (searchInput && searchWrap) {
    let debounce = 0;
    const apply = () => {
      const q = searchInput.value.trim().toLowerCase();
      if (!q) searchSet = null;
      else {
        searchSet = new Set();
        g.forEachNode((id, a) => { if (String(a.label || '').toLowerCase().includes(q)) searchSet.add(id); });
      }
      searchWrap.classList.toggle('gv-has-q', !!q);
      renderer.refresh({ skipIndexation: true });
    };
    searchInput.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(apply, 80); });
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        searchInput.value = ''; apply(); searchInput.blur();
        if (searchBtn) searchWrap.classList.remove('gv-open');
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const q = searchInput.value.trim().toLowerCase();
        if (!q || !searchSet || !searchSet.size) return;
        // Prefix hits win, then the biggest node — "icp" should land on the
        // hub named ICP, not on the first source that mentions it.
        let best = null, bestScore = -1;
        for (const id of searchSet) {
          const label = String(g.getNodeAttribute(id, 'label') || '').toLowerCase();
          const score = (label.startsWith(q) ? 1000 : 0) + (baseSize.get(id) || 0);
          if (score > bestScore) { bestScore = score; best = id; }
        }
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
    } else {
      legendToggle.style.display = 'none';
    }
  }

  const brand = document.getElementById('brand');
  if (brand) brand.textContent = (snap.title || 'Knowledge graph') + ' · CafresoHQ';

  if (P('show_analytics', '0') === '1' && snap.analytics && snap.analytics.metrics) {
    const m = snap.analytics.metrics;
    const el = document.getElementById('analytics');
    if (el) {
      el.style.display = 'block';
      const top = (snap.analytics.topInfluential || []).slice(0, 6).map((t) => '<div>◆ ' + esc(titleOf(t.id)) + '</div>').join('');
      el.innerHTML =
        '<div class="gv-panel-title">Graph analysis</div>' +
        '<div class="gv-pill">' + esc(m.structure || '') + '</div>' +
        '<div class="gv-muted" style="line-height:1.5">Notes <b>' + m.nodes + '</b> · Links <b>' + m.edges + '</b><br>Topics <b>' + m.communityCount + '</b> · Modularity <b>' + (m.modularity || 0).toFixed(2) + '</b></div>' +
        '<div class="gv-panel-title" style="margin:10px 0 4px">Most influential</div>' + top;
    }
  }

  // Float, then calm: small graphs settle in ~1.5s, the biggest get ~5s.
  if (!reduceMotion) warm(Math.min(1500 + g.order * 8, 5000));
}
main();
