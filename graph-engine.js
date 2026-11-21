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
const EDGE_SIZE = 0.6;        // Obsidian-thin links
const EDGE_SIZE_FOCUS = 1.4;  // a focused node's own links

/* Obsidian's graph look, one palette per theme: grey nodes on a flat ground,
   hairline links, and one accent (the purple) for whatever has your attention.
   Colours are solid, mixed against the ground: sigma's WebGL blending treats a
   translucent colour as premultiplied, so rgba(255,255,255,0.13) drew as solid
   white on the dark ground. */
const THEMES = {
  dark: {
    bg: '#1e1e1e', node: '#9a9a9a', attachment: '#b9a46c', office: '#6f8aa3',
    dim: '#353535', edge: '#3d3d3d', edgeDim: '#262626',
    accent: '#a88bfa', label: '#dcdcdc', labelDim: '#8a8a8a',
  },
  light: {
    bg: '#ffffff', node: '#8c8c8c', attachment: '#b08a35', office: '#5b7c99',
    dim: '#e4e4e4', edge: '#d6d6d6', edgeDim: '#f3f3f3',
    accent: '#7f6df2', label: '#222222', labelDim: '#9a9a9a',
  },
};
const OFFICE_TYPES = new Set(['task', 'agent', 'decision', 'message-thread', 'mission', 'receipt', 'proposal', 'risk', 'memory']);

/* Labels and hover in Obsidian's manner: plain text under the dot, no boxes.
   (Sigma's default hover paints a white card behind the label.) */
function drawLabel(context, data, settings) {
  if (!data.label) return;
  const size = settings.labelSize;
  context.font = `${settings.labelWeight} ${size}px ${settings.labelFont}`;
  context.fillStyle = data.labelColor || settings.labelColor.color;
  context.textAlign = 'center';
  context.textBaseline = 'top';
  context.fillText(data.label, data.x, data.y + data.size + 3);
  context.textAlign = 'left';
  context.textBaseline = 'alphabetic';
}
function drawHover(context, data, settings) {
  const size = settings.labelSize;
  context.beginPath();
  context.arc(data.x, data.y, data.size + 2.5, 0, Math.PI * 2);
  context.strokeStyle = data.ringColor || '#a88bfa';
  context.lineWidth = 1.5;
  context.stroke();
  if (!data.label) return;
  // Same place and weight as drawLabel, so the label layer's copy sits exactly under it.
  context.font = `${settings.labelWeight} ${size}px ${settings.labelFont}`;
  context.fillStyle = data.labelColor || settings.labelColor.color;
  context.textAlign = 'center';
  context.textBaseline = 'top';
  context.fillText(data.label, data.x, data.y + data.size + 3);
  context.textAlign = 'left';
  context.textBaseline = 'alphabetic';
}

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
    this.colorMode = opts.colorMode || 'plain';
    this.t = THEMES[this.dark ? 'dark' : 'light'];
    this.colorFor = opts.colorFor || null;       // (id, node) => hex  (tags/folder/type modes)
    this.edgeMode = opts.edgeMode || 'always';   // 'always' (calm/faint) | 'hover' (hidden until hover)
    this._holdMs = opts.holdMs != null ? opts.holdMs : 700;  // hold the seed circle, then bloom
    this.hovered = null;
    this.selected = null;
    this.hidden = new Set();
    this.filterText = '';
    this.filterFn = null;                          // predicate over the raw node record (see setFilter)
    this.localSet = null;                          // Set of ids when in local mode, else null
    this.analytics = null;
    this._analyticsSeq = 0;
    this._listeners = {};
    this._raw = data;

    try { container.style.background = this.t.bg; } catch (_) {}
    this.graph = new DirectedGraph({ allowSelfLoops: false });
    this._build(data);
    this._sizeByLinks();
    seedPositions(this.graph);

    this.renderer = new Sigma(this.graph, container, {
      allowInvalidContainer: true,                 // tolerate transient 0-height; resize() repaints
      renderLabels: true,
      labelDensity: 0.55,
      labelGridCellSize: 90,
      labelRenderedSizeThreshold: 7,       // labels fade in as you zoom, like Obsidian
      labelSize: 11,
      labelWeight: '400',
      labelColor: { color: this.t.label },
      labelFont: 'Inter, system-ui, -apple-system, sans-serif',
      defaultDrawNodeLabel: drawLabel,
      defaultDrawNodeHover: drawHover,
      defaultNodeColor: this.t.node,
      defaultEdgeColor: this.t.edge,
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

  /* Obsidian sizes a dot by how many links it has, so hubs read at a glance. */
  _sizeByLinks() {
    let max = 1;
    this.graph.forEachNode((id) => { max = Math.max(max, this.graph.degree(id)); });
    this.graph.forEachNode((id) => {
      this.graph.setNodeAttribute(id, 'size', 2.6 + Math.sqrt(this.graph.degree(id) / max) * 7.5);
    });
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
    this.graph.forEachNode((id) => {
      const na = attrs[id];
      const bc = na ? na.betweenness : 0;
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
    if (this.colorMode === 'plain') {
      if (d._type === 'artifact' || (d._node && d._node.isBinary)) return this.t.attachment;
      if (OFFICE_TYPES.has(d._type)) return this.t.office;
      return this.t.node;
    }
    if (this.colorMode !== 'community' && this.colorFor) {
      const c = this.colorFor(id, d._node);
      if (c) return c;
    }
    return communityColor(d._community != null ? d._community : 0);
  }

  // Default neuron-link color — visible synapse web, still calmer than the nodes.
  _edgeBase() { return this.t.edge; }

  // ── Reducers (hover/selection/filter/local — no graph mutation) ───────
  _visible(id, d) {
    if (this.hidden.has(id)) return false;
    if (this.localSet && !this.localSet.has(id)) return false;
    if (this.filterFn) {
      // The shell's grammar-aware matcher (nodeMatchesFilter) gets the raw
      // backend record; fall back to the display attrs for nodes built
      // without one so a bad record can never blank the whole graph.
      if (!this.filterFn(d._node || { id, title: d.label, type: d._type, tags: d._tags })) return false;
    } else if (this.filterText) {
      const q = this.filterText;
      const hay = ((d.label || '') + ' ' + (d._path || '') + ' ' + (d._type || '') + ' ' + (d._tags || []).join(' ')).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  }

  _focusId() {
    // A hovered/selected node that has since been filtered out, hidden, or
    // pushed outside local mode is no longer on the canvas — it must stop
    // acting as a focus, or every other node/edge gets dimmed (or, for
    // edges, hidden outright) around a phantom that nothing points at.
    const f = this.hovered || this.selected;
    if (f == null) return f;
    if (!this.graph.hasNode(f) || !this._visible(f, this.graph.getNodeAttributes(f))) return null;
    return f;
  }

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
    res.ringColor = this.t.accent;
    // The note you have open keeps the accent, as Obsidian marks the active file.
    if (id === this.active) { res.color = this.t.accent; res.forceLabel = true; res.zIndex = 2; }
    if (focus) {
      const nbrs = this._nbrCache || (this._nbrCache = this._neighborhood(focus));
      if (nbrs && !nbrs.has(id)) {
        res.color = this.t.dim;
        res.label = '';
        res.zIndex = 0;
      } else {
        res.zIndex = 1;
        res.forceLabel = true;             // the hovered note and its neighbours are named
        if (id === focus) { res.highlighted = true; res.color = this.t.accent; res.zIndex = 2; }
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
        res.color = this.colorEdgesTyped && data._typeColor && data._typeColor !== this.t.edge ? data._typeColor : this.t.accent;
        res.size = EDGE_SIZE_FOCUS; res.zIndex = 1;
      } else { res.color = this.t.edgeDim; res.zIndex = 0; }
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

    // Node Dragging Implementation
    let draggedNode = null;
    let isDragging = false;
    
    r.on('downNode', (e) => {
      isDragging = true;
      draggedNode = e.node;
      r.getCamera().disable();
    });
    
    r.getMouseCaptor().on('mousemovebody', (e) => {
      if (!isDragging || !draggedNode) return;
      const pos = r.viewportToGraph(e);
      this.graph.setNodeAttribute(draggedNode, 'x', pos.x);
      this.graph.setNodeAttribute(draggedNode, 'y', pos.y);
      e.preventSigmaDefault();
      if (e.original && e.original.preventDefault) e.original.preventDefault();
      if (e.original && e.original.stopPropagation) e.original.stopPropagation();
    });
    // Mobile Touch Polish
    r.getMouseCaptor().on('touchmovebody', (e) => {
      if (!isDragging || !draggedNode) return;
      const pos = r.viewportToGraph(e);
      this.graph.setNodeAttribute(draggedNode, 'x', pos.x);
      this.graph.setNodeAttribute(draggedNode, 'y', pos.y);
      e.preventSigmaDefault();
      if (e.original && e.original.preventDefault) e.original.preventDefault();
      if (e.original && e.original.stopPropagation) e.original.stopPropagation();
    });

    
    const handleUp = () => {
      if (isDragging || draggedNode) {
        isDragging = false;
        draggedNode = null;
        r.getCamera().enable();
      }
    };
    
    r.getMouseCaptor().on('mouseup', handleUp);
    r.getMouseCaptor().on('dragleave', handleUp);
    r.getMouseCaptor().on('touchend', handleUp);
  }

  on(ev, cb) { (this._listeners[ev] = this._listeners[ev] || []).push(cb); return this; }
  _emit(ev, ...args) { (this._listeners[ev] || []).forEach((cb) => { try { cb(...args); } catch (_) {} }); }

  // ── Public imperative API ─────────────────────────────────────────────
  setColorMode(mode) { this.colorMode = mode; this._recolor(); }
  setEdgeMode(mode) { this.edgeMode = mode || 'always'; this._refreshReducers(); }
  setColorFor(fn) { this.colorFor = fn; if (this.colorMode !== 'community') this._recolor(); }
  /* Accepts either a predicate over the RAW node record, or a plain string.
     The React shell passes nodeMatchesFilter wrapped in a closure, so the
     filter box's advertised syntax (tag:x, type:y, -term, OR, orphan/stale,
     accent folding) works on this renderer instead of being matched as one
     literal substring. The string path stays as the grammarless fallback. */
  setFilter(f) {
    if (typeof f === 'function') { this.filterFn = f; this.filterText = ''; }
    else { this.filterFn = null; this.filterText = (f || '').toLowerCase().trim(); }
    this._refreshReducers();
  }
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

  setActivePath(path) {
    // Marks and centres the open note without dimming the rest: only hover dims.
    this.active = path || null;
    if (path && this.graph.hasNode(path)) {
      try {
        const disp = this.renderer.getNodeDisplayData(path);
        if (disp) this.renderer.getCamera().animate({ x: disp.x, y: disp.y }, { duration: 420 });
      } catch (_) {}
    }
    this._refreshReducers();
  }
  getAnalytics() { return this.analytics; }
  getGraph() { return this.graph; }

  // Snapshot for public sharing (Phase 2): positions + community + bc baked in.
  exportSnapshot() {
    const exp = this.graph.export();
    /* Publish only what the boss is LOOKING at. A node dropped via "Hide
       node", excluded by the filter box, or outside the local-depth set is
       invisible on the canvas — but graph.export() carries the whole graph,
       so every one of them (title, path, tags, the raw backend record in
       `_node`) rode along into the snapshot JSON, which /graph/snapshot
       serves WITHOUT the API key by design. Anyone handed the share link
       could read the very notes the boss had just excluded from view.
       Prune those nodes, every edge touching them, and their analytics
       traces (nodeAttrs keys, top-influential rows, cluster exemplars,
       the gap's endpoint notes) before the payload leaves the office. */
    const dropped = new Set();
    exp.nodes = (exp.nodes || []).filter((n) => {
      if (this._visible(n.key, n.attributes || {})) return true;
      dropped.add(n.key);
      return false;
    });
    let analytics = this.analytics;
    if (dropped.size) {
      exp.edges = (exp.edges || []).filter((e) => !dropped.has(e.source) && !dropped.has(e.target));
      if (analytics) {
        const nodeAttrs = {};
        for (const id in (analytics.nodeAttrs || {})) { if (!dropped.has(id)) nodeAttrs[id] = analytics.nodeAttrs[id]; }
        analytics = {
          ...analytics,
          nodeAttrs,
          topInfluential: (analytics.topInfluential || []).filter((t) => t && !dropped.has(t.id)),
          clusters: (analytics.clusters || []).map((c) => (c ? { ...c, topNodes: (c.topNodes || []).filter((id) => !dropped.has(id)) } : c)),
          gap: (analytics.gap && (dropped.has(analytics.gap.aTop) || dropped.has(analytics.gap.bTop))) ? null : analytics.gap,
        };
      }
    }
    return { graph: exp, analytics, ts: this.opts.now || 0 };
  }

  resize() { try { this.renderer.refresh(); this.renderer.getCamera().setState(this.renderer.getCamera().getState()); } catch (_) {} }
  setDark(dark) {
    this.dark = dark; this.t = THEMES[dark ? 'dark' : 'light'];
    try { this.container.style.background = this.t.bg; } catch (_) {}
    try { this.renderer.setSetting('labelColor', { color: this.t.label }); } catch (_) {}
    this._recolor();
  }
  zoom(by) { try { const c = this.renderer.getCamera(); by > 0 ? c.animatedZoom({ duration: 200 }) : c.animatedUnzoom({ duration: 200 }); } catch (_) {} }
  fit() { try { this.renderer.getCamera().animatedReset({ duration: 300 }); } catch (_) {} }

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
