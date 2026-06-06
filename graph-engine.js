/**
 * graph-engine.js — WebGL knowledge-graph engine (sigma.js v3 + graphology).
 *
 * Bundled by esbuild into bundle/graph-engine-<hash>.js (with sigma/graphology
 * inlined) and exposed as window.CafresoGraphEngine. Replaces the old custom
 * Canvas-2D force renderer in views.jsx GraphView. Responsibilities:
 *   - build a graphology graph from the backend /vault/graph {nodes, edges}
 *   - ForceAtlas2 layout in a Web Worker (UI never blocks)
 *   - sigma WebGL rendering with hover/selection highlight via reducers
 *   - InfraNodus-style analytics (Louvain communities, betweenness, bc2, structure,
 *     gaps) computed in analytics.worker.js; betweenness → node/label size,
 *     community → color
 *   - imperative API for the React shell (color modes, filter, local mode, focus,
 *     snapshot export for public sharing)
 *
 * Cross-file contract: window.CafresoGraphEngine.mount(container, data, opts) -> instance.
 */
import { DirectedGraph } from 'graphology';
import Sigma from 'sigma';
import FA2Layout from 'graphology-layout-forceatlas2/worker';
import forceAtlas2 from 'graphology-layout-forceatlas2';

// Distinct, theme-friendly community palette (warm + cool spread).
const COMMUNITY_COLORS = [
  '#E8A9A9', '#7DB5B5', '#C9B8E0', '#F0C674', '#A5C4A1', '#E0A47C',
  '#8FB7E0', '#D9A0C8', '#B7C97D', '#9C8FE0', '#E0C58F', '#7DC9B0',
];
const DIM = '#2a2733';
const DIM_LIGHT = '#d8d0c4';
const EDGE_SIZE = 0.9;        // default neuron-link thickness (calm but visible)
const EDGE_SIZE_FOCUS = 1.8;  // a focused node's own links

function communityColor(c) {
  if (c == null) return '#9b93a8';
  return COMMUNITY_COLORS[((c % COMMUNITY_COLORS.length) + COMMUNITY_COLORS.length) % COMMUNITY_COLORS.length];
}

// Clean, evenly-spaced seed ring (with a touch of deterministic jitter so FA2 can
// break symmetry and bloom outward). The intro holds this circle briefly, then
// ForceAtlas2 blooms it into formation.
function seedPositions(graph) {
  const n = graph.order;
  const R = 10 + Math.sqrt(n) * 1.5;
  let i = 0;
  graph.forEachNode((node) => {
    const a = (i / Math.max(1, n)) * Math.PI * 2;
    graph.setNodeAttribute(node, 'x', Math.cos(a) * R + (((i * 37) % 11) - 5) * 0.15);
    graph.setNodeAttribute(node, 'y', Math.sin(a) * R + (((i * 53) % 13) - 6) * 0.15);
    i++;
  });
}

class GraphEngine {
  constructor(container, data, opts = {}) {
    this.container = container;
    this.opts = opts;
    this.dark = opts.dark !== false;
    this.colorMode = opts.colorMode || 'community';
    this.colorFor = opts.colorFor || null;       // (id, node) => hex  (tags/folder/type modes)
    this.edgeMode = opts.edgeMode || 'always';   // 'always' (calm/faint) | 'hover' (hidden until hover)
    this._holdMs = opts.holdMs != null ? opts.holdMs : 700;  // hold the seed circle, then bloom
    this.hovered = null;
    this.selected = null;
    this.hidden = new Set();
    this.filterText = '';
    this.localSet = null;                          // Set of ids when in local mode, else null
    this.analytics = null;
    this._analyticsSeq = 0;
    this._listeners = {};
    this._raw = data;

    this.graph = new DirectedGraph({ allowSelfLoops: false });
    this._build(data);
    seedPositions(this.graph);

    this.renderer = new Sigma(this.graph, container, {
      allowInvalidContainer: true,                 // tolerate transient 0-height; resize() repaints
      renderLabels: true,
      labelDensity: 0.7,
      labelGridCellSize: 70,
      labelRenderedSizeThreshold: 6,
      labelColor: { color: this.dark ? '#e9e2d4' : '#2b2620' },
      labelFont: 'Inter, system-ui, sans-serif',
      defaultNodeColor: '#9b93a8',
      defaultEdgeColor: this.dark ? 'rgba(176,158,214,0.22)' : 'rgba(120,108,90,0.24)',
      minCameraRatio: 0.05,
      maxCameraRatio: 14,
      zIndex: true,
      nodeReducer: (id, d) => this._nodeReducer(id, d),
      edgeReducer: (id, d) => this._edgeReducer(id, d),
    });

    this._wireEvents();
    this._startLayout();
    this._runAnalytics();
  }

  // ── Graph construction ────────────────────────────────────────────────
  _build(data) {
    const g = this.graph;
    const nodes = (data && data.nodes) || [];
    const edges = (data && data.edges) || [];
    for (const n of nodes) {
      if (!n || n.id == null || g.hasNode(n.id)) continue;
      g.addNode(n.id, {
        label: n.title || n.label || String(n.id).split('/').pop(),
        size: 4,
        color: '#9b93a8',
        _node: n,                                  // carry the raw record for color modes
        _type: n.type || 'note',
        _tags: n.tags || [],
        _path: n.id,
        _inlinks: n.inlinks || 0,
        _mtime: n.mtime || 0,
        x: 0, y: 0,
      });
    }
    for (const e of edges) {
      if (!e) continue;
      const s = e.source, t = e.target;
      if (s == null || t == null || s === t || !g.hasNode(s) || !g.hasNode(t)) continue;
      if (g.hasDirectedEdge(s, t)) {
        g.updateDirectedEdgeAttribute(s, t, 'weight', (w) => (w || 1) + 1);
      } else {
        g.addDirectedEdge(s, t, {
          weight: 1,
          _type: e.type || 'links_to',
          _typeColor: e.color || this._edgeBase(),   // shown brighter on focus/hover
          color: this._edgeBase(),                   // visible neuron-link by default
          size: EDGE_SIZE,
        });
      }
    }
  }

  // ── Layout (ForceAtlas2 in a worker) ──────────────────────────────────
  _startLayout() {
    try {
      const settings = forceAtlas2.inferSettings(this.graph);
      settings.barnesHutOptimize = this.graph.order > 800;
      settings.slowDown = 1 + Math.log(Math.max(2, this.graph.order));
      settings.gravity = 0.8;
      settings.scalingRatio = 8;
      settings.adjustSizes = true;
      this.fa2 = new FA2Layout(this.graph, { settings });
      // Hold the seed circle briefly, then bloom into the force layout. Settle then
      // stop so it freezes (re-startable via refreshLayout()).
      const runMs = Math.min(6000, 1500 + this.graph.order * 2);
      this._fa2StartTimer = setTimeout(() => {
        try { this.fa2 && this.fa2.start(); } catch (_) {}
        this._fa2Timer = setTimeout(() => { try { this.fa2 && this.fa2.stop(); } catch (_) {} }, runMs);
      }, this._holdMs);
    } catch (_) { /* layout is best-effort */ }
  }

  refreshLayout() {
    if (!this.fa2) return this._startLayout();
    try {
      if (this.fa2.isRunning()) return;
      this.fa2.start();
      clearTimeout(this._fa2Timer);
      const ms = Math.min(6000, 1500 + this.graph.order * 2);
      this._fa2Timer = setTimeout(() => { try { this.fa2.stop(); } catch (_) {} }, ms);
    } catch (_) {}
  }

  // ── Analytics worker ──────────────────────────────────────────────────
  _runAnalytics() {
    const url = (window.__CAFRESO_BUNDLE__ && window.__CAFRESO_BUNDLE__.analyticsWorker) || null;
    const payload = {
      id: ++this._analyticsSeq,
      nodes: this.graph.mapNodes((id) => ({ id })),
      edges: this.graph.mapEdges((e, attr, s, t) => ({ source: s, target: t })),
    };
    const apply = (res) => {
      if (!res || !res.ok) return;
      this.analytics = { metrics: res.metrics, clusters: res.clusters, topInfluential: res.topInfluential, gap: res.gap, nodeAttrs: res.nodeAttrs };
      this._applyAnalytics();
      this._emit('analytics', this.analytics);
    };
    if (url && typeof Worker !== 'undefined') {
      try {
        const w = new Worker(url);
        this._worker = w;
        w.onmessage = (ev) => { if (ev.data && ev.data.id === payload.id) apply(ev.data); };
        w.postMessage(payload);
        return;
      } catch (_) { /* fall through to inline */ }
    }
    // No worker URL (e.g. dev before injection) — skip; sizes/colors stay default.
  }

  _applyAnalytics() {
    const a = this.analytics;
    if (!a) return;
    const attrs = a.nodeAttrs || {};
    // Size by betweenness (sqrt for area perception); min floor so leaves stay visible.
    let maxBc = 0;
    for (const id in attrs) maxBc = Math.max(maxBc, attrs[id].betweenness || 0);
    this.graph.forEachNode((id) => {
      const na = attrs[id];
      const bc = na ? na.betweenness : 0;
      const size = 3 + (maxBc > 0 ? Math.sqrt(bc / maxBc) * 13 : 0);
      this.graph.setNodeAttribute(id, 'size', size);
      this.graph.setNodeAttribute(id, '_community', na ? na.community : 0);
      this.graph.setNodeAttribute(id, '_bc', bc);
    });
    this._recolor();
  }

  // ── Coloring ──────────────────────────────────────────────────────────
  _recolor() {
    this.graph.forEachNode((id, d) => {
      this.graph.setNodeAttribute(id, 'color', this._baseColor(id, d));
    });
    if (this.renderer) this.renderer.refresh();
  }

  _baseColor(id, d) {
    if (this.colorMode !== 'community' && this.colorFor) {
      const c = this.colorFor(id, d._node);
      if (c) return c;
    }
    return communityColor(d._community != null ? d._community : 0);
  }

  // Default neuron-link color — visible synapse web, still calmer than the nodes.
  _edgeBase() { return this.dark ? 'rgba(176,158,214,0.22)' : 'rgba(120,108,90,0.24)'; }

  // ── Reducers (hover/selection/filter/local — no graph mutation) ───────
  _visible(id, d) {
    if (this.hidden.has(id)) return false;
    if (this.localSet && !this.localSet.has(id)) return false;
    if (this.filterText) {
      const q = this.filterText;
      const hay = ((d.label || '') + ' ' + (d._path || '') + ' ' + (d._type || '') + ' ' + (d._tags || []).join(' ')).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  }

  _focusId() { return this.hovered || this.selected; }

  _neighborhood(focus) {
    if (!focus || !this.graph.hasNode(focus)) return null;
    const set = new Set([focus]);
    this.graph.forEachNeighbor(focus, (nb) => set.add(nb));
    return set;
  }

  _nodeReducer(id, data) {
    const res = { ...data };
    if (!this._visible(id, data)) { res.hidden = true; return res; }
    const focus = this._focusId();
    if (focus) {
      const nbrs = this._nbrCache || (this._nbrCache = this._neighborhood(focus));
      if (nbrs && !nbrs.has(id)) {
        res.color = this.dark ? DIM : DIM_LIGHT;
        res.label = '';
        res.zIndex = 0;
      } else {
        res.zIndex = 1;
        if (id === focus) { res.highlighted = true; res.forceLabel = true; }
      }
    }
    return res;
  }

  _edgeReducer(id, data) {
    const res = { ...data };
    const s = this.graph.source(id), t = this.graph.target(id);
    if (!this._visible(s, this.graph.getNodeAttributes(s)) || !this._visible(t, this.graph.getNodeAttributes(t))) {
      res.hidden = true; return res;
    }
    const focus = this._focusId();
    if (focus) {
      // Reveal only the focused node's edges — in their typed color, brighter + bolder.
      if (s === focus || t === focus) {
        res.color = data._typeColor || (this.dark ? 'rgba(232,169,169,0.7)' : 'rgba(180,90,90,0.6)');
        res.size = EDGE_SIZE_FOCUS; res.zIndex = 1;
      } else { res.hidden = true; }
    } else if (this.edgeMode === 'hover') {
      res.hidden = true;                 // declutter: edges stay hidden until a node is hovered
    } else {
      res.color = this._edgeBase(); res.size = EDGE_SIZE; res.zIndex = 0;
    }
    return res;
  }

  _refreshReducers() {
    this._nbrCache = null;
    if (this.renderer) this.renderer.refresh({ skipIndexation: true });
  }

  // ── Events ────────────────────────────────────────────────────────────
  _wireEvents() {
    const r = this.renderer;
    r.on('enterNode', ({ node }) => { this.hovered = node; this._nbrCache = null; this._refreshReducers(); this._emit('hover', node); });
    r.on('leaveNode', () => { this.hovered = null; this._nbrCache = null; this._refreshReducers(); this._emit('hover', null); });
    r.on('clickNode', ({ node }) => { this.selected = node; this._nbrCache = null; this._refreshReducers(); this._emit('nodeClick', node); });
    r.on('rightClickNode', (e) => { if (e.event && e.event.original) e.event.original.preventDefault(); this._emit('nodeRightClick', e.node, e.event); });
    r.on('doubleClickNode', ({ node }) => this._emit('nodeDoubleClick', node));
    r.on('clickStage', () => { this.selected = null; this._nbrCache = null; this._refreshReducers(); this._emit('stageClick'); });
  }

  on(ev, cb) { (this._listeners[ev] = this._listeners[ev] || []).push(cb); return this; }
  _emit(ev, ...args) { (this._listeners[ev] || []).forEach((cb) => { try { cb(...args); } catch (_) {} }); }

  // ── Public imperative API ─────────────────────────────────────────────
  setColorMode(mode) { this.colorMode = mode; this._recolor(); }
  setEdgeMode(mode) { this.edgeMode = mode || 'always'; this._refreshReducers(); }
  setColorFor(fn) { this.colorFor = fn; if (this.colorMode !== 'community') this._recolor(); }
  setFilter(text) { this.filterText = (text || '').toLowerCase().trim(); this._refreshReducers(); }
  setHidden(idSet) { this.hidden = idSet instanceof Set ? idSet : new Set(idSet || []); this._refreshReducers(); }
  setLocalMode(rootId, depth) {
    if (!rootId || !depth) { this.localSet = null; this._refreshReducers(); return; }
    const set = new Set([rootId]);
    let frontier = [rootId];
    for (let d = 0; d < depth; d++) {
      const next = [];
      for (const nd of frontier) this.graph.forEachNeighbor(nd, (nb) => { if (!set.has(nb)) { set.add(nb); next.push(nb); } });
      frontier = next;
    }
    this.localSet = set; this._refreshReducers();
  }

  focusNode(id) {
    if (!this.graph.hasNode(id)) return;
    this.selected = id; this._nbrCache = null;
    try {
      const disp = this.renderer.getNodeDisplayData(id);
      if (disp) this.renderer.getCamera().animate({ x: disp.x, y: disp.y, ratio: 0.35 }, { duration: 420 });
    } catch (_) {}
    this._refreshReducers();
  }

  setActivePath(path) { if (path) this.focusNode(path); }
  getAnalytics() { return this.analytics; }
  getGraph() { return this.graph; }

  // Snapshot for public sharing (Phase 2): positions + community + bc baked in.
  exportSnapshot() {
    const exp = this.graph.export();
    return { graph: exp, analytics: this.analytics, ts: this.opts.now || 0 };
  }

  resize() { try { this.renderer.refresh(); this.renderer.getCamera().setState(this.renderer.getCamera().getState()); } catch (_) {} }
  setDark(dark) { this.dark = dark; this._recolor(); }

  destroy() {
    clearTimeout(this._fa2Timer);
    clearTimeout(this._fa2StartTimer);
    try { this.fa2 && this.fa2.kill(); } catch (_) {}
    try { this._worker && this._worker.terminate(); } catch (_) {}
    try { this.renderer && this.renderer.kill(); } catch (_) {}
    this.graph && this.graph.clear();
    this._listeners = {};
  }
}

window.CafresoGraphEngine = {
  version: 1,
  mount(container, data, opts) { return new GraphEngine(container, data, opts || {}); },
  communityColor,
};
