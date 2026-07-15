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
    edge: [201, 191, 169, 0.18], edgeDim: [201, 191, 169, 0.03], edgeHot: [245, 210, 93, 0.7],
    nodeDim: [38, 33, 25], label: [220, 211, 192], ring: 'rgba(245,210,93,0.9)',
    pulse: [245, 210, 93], spark: [255, 243, 208],
  },
  light: {
    bg: '#F6F1E7',
    edge: [92, 82, 64, 0.2], edgeDim: [92, 82, 64, 0.04], edgeHot: [158, 112, 20, 0.7],
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
  const dimOf = new Map();     // node -> 0..1, written by nodeReducer, read by drawLabel

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
    if (searchSet && !searchSet.has(id)) return 1;
    if (highlight && hops) {
      const k = hops.get(id);
      return (k === undefined ? HOP_FAR : HOP_DIM[k]) * h;
    }
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
      else if (hops && hops.has(id)) r.zIndex = 1;
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
  const fa2 = { ...forceAtlas2.inferSettings(g), gravity: 0.06, scalingRatio: 24, slowDown: 4, adjustSizes: true };
  const layoutOff = P('layout', 'fa2') === 'none' || g.order <= 2 || g.order > 600;
  let animateOn = !layoutOff && !reduceMotion;
  // Budget is measured in frames actually rendered, not wall-clock: a graph
  // opened in a background tab gets no rAF at all, and a deadline would expire
  // unspent and leave it frozen at its seed positions forever. Spending only on
  // real frames also means the browser's own rAF pause IS the battery guard.
  let simBudget = 0, raf = 0, last = 0, lastFx = 0;

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

  // Float, then calm: small graphs settle in ~1.5s, the biggest get ~5s.
  if (!reduceMotion) warm(Math.min(1500 + g.order * 8, 5000));
  // warm() is a no-op when the layout is off, but signals still need the loop.
  if (signalsOn) tick();
}
// main() is async, so anything it throws becomes an unhandled rejection that
// never reaches the console as an error — the viewer just half-renders and says
// nothing. Surface it.
main().catch((e) => { console.error('graph-viewer: failed to render —', e); });
