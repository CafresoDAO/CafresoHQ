import { CafresoHQClient } from '../claude-client.jsx';
import { hexToRgb } from './core.jsx';
const { useState: useSV, useMemo: useMV, useRef: useRV } = React;
const DEFAULT_SETTINGS = {
  centerForce:  0.0008,
  repelForce:   900,
  linkForce:    0.022,
  linkDistance: 150,
  layerForce:   0.003,
  // Color/style edges by their semantic type (cites, supports, contradicts,
  // child_of, etc) instead of all uniform. Off by default since the visual
  // change is significant; users opt-in via the gear panel. See
  // EDGE_TYPE_STYLE in this file for the palette.
  colorEdgesByType: false,
};

const GRAPH_PREFS_KEY = 'cafresohq:graph:prefs';

function loadGraphPrefs() {
  try {
    const raw = localStorage.getItem(GRAPH_PREFS_KEY);
    if (!raw) return null;
    const v = JSON.parse(raw);
    return (v && typeof v === 'object') ? v : null;
  } catch (_) { return null; }
}

function saveGraphPrefs(prefs) {
  try { localStorage.setItem(GRAPH_PREFS_KEY, JSON.stringify(prefs)); } catch (_) {}
}

/* Edge color from the typed-edge palette (shared with the legacy renderer's
   EDGE_TYPE_STYLE). Falls back to a soft theme default for plain links. */
function edgeColorForType(type, isDark) {
  const s = EDGE_TYPE_STYLE[type];
  if (s && s.color) return s.color;
  return isDark ? 'rgba(168,152,190,0.22)' : 'rgba(120,108,90,0.24)';
}

// Concept-map mode reads note bodies client-side; cap how many we pull so a big
// vault doesn't fire hundreds of fetches. Scoping to a folder keeps it focused.
const CONCEPT_NOTE_CAP = 120;

/* InfraNodus-grade WebGL graph view (sigma.js + graphology via
   window.CafresoGraphEngine). Replaces the legacy Canvas-2D renderer below.
   Keeps the external contract: props {onOpenNote, embedded, activePath,
   onMinimize, agents}, the window.CafresoHQGraph API, and the popout. Adds an
   analytics side panel (communities, betweenness, structure, gaps) and a second
   data source — a concept co-occurrence map (window.CafresoCooccur) — that drops
   into the same engine/analytics/publish path. */
function GraphView({ onOpenNote, embedded = false, activePath = null, onMinimize = null, agents = null }) {
  const containerRef = React.useRef(null);
  const engineRef = React.useRef(null);
  const rawRef = React.useRef({ byId: {}, maxInlinks: 0, mtimeRange: null });
  const persistedRef = React.useRef(null);
  if (persistedRef.current === null) persistedRef.current = loadGraphPrefs() || {};
  const persisted = persistedRef.current;

  const [colorMode, setColorMode] = useSV(persisted.colorMode || 'community');
  const [localMode, setLocalMode] = useSV(persisted.localMode || 'global');
  const [filter, setFilter] = useSV('');
  const [analytics, setAnalytics] = useSV(null);
  const [loading, setLoading] = useSV(true);
  const [panelOpen, setPanelOpen] = useSV(persisted.drawerOpen !== false);
  const [ctxMenu, setCtxMenu] = useSV(null); // { id, x, y }
  const [nodeCount, setNodeCount] = useSV(0);
  const [shareUrl, setShareUrl] = useSV(null);
  const [sharing, setSharing] = useSV(false);
  const [shareCopied, setShareCopied] = useSV(false);
  const [embedCopied, setEmbedCopied] = useSV(null); // null | true | false — real result of the last "Copy embed" click
  const [edgesHover, setEdgesHover] = useSV(!!persisted.edgesHover); // hide edges until hover
  const edgesHoverRef = React.useRef(edgesHover);
  edgesHoverRef.current = edgesHover;

  // Data source: 'links' = wikilink graph (/vault/graph); 'concepts' = co-occurrence map.
  const [source, setSource] = useSV(persisted.source === 'concepts' ? 'concepts' : 'links');
  const [scope, setScope] = useSV(persisted.scope || '__all__');   // folder prefix for concepts
  const [folders, setFolders] = useSV([]);
  const [conceptMeta, setConceptMeta] = useSV(null);
  // Refs keep the loader/mount helpers reading the latest values without re-binding.
  const sourceRef = React.useRef(source); sourceRef.current = source;
  const scopeRef = React.useRef(scope); scopeRef.current = scope;
  const filterRef = React.useRef(filter); filterRef.current = filter;
  const colorModeRef = React.useRef(colorMode); colorModeRef.current = colorMode;
  const localModeRef = React.useRef(localMode); localModeRef.current = localMode;
  const activePathRef = React.useRef(activePath); activePathRef.current = activePath;

  const isDark = typeof document !== 'undefined' && document.body.classList.contains('night');
  const titleFor = (id) => {
    const n = rawRef.current.byId[id];
    return (n && (n.title || n.label)) || String(id).split('/').pop().replace(/\.md$/, '');
  };

  // Color function for non-community modes — reuses the legacy colorForNode.
  const colorFor = React.useCallback((id, node) => {
    if (!node || colorMode === 'community') return null;
    const cs = (typeof getComputedStyle === 'function') ? getComputedStyle(document.documentElement) : null;
    return colorForNode(node, {
      colorMode,
      maxInlinks: rawRef.current.maxInlinks,
      mtimeRange: rawRef.current.mtimeRange,
      clusterColoring: false, clusters: null,
    }, isDark, cs);
  }, [colorMode, isDark]);

  const wireEngine = React.useCallback((eng) => {
    // Concept nodes are terms, not note paths — don't try to open them.
    eng.on('nodeClick', (id) => { if (sourceRef.current === 'links') onOpenNote && onOpenNote(id); });
    eng.on('nodeDoubleClick', (id) => { if (sourceRef.current === 'links') onOpenNote && onOpenNote(id); });
    eng.on('hover', () => { /* highlight handled inside the engine */ });
    eng.on('stageClick', () => setCtxMenu(null));
    eng.on('analytics', (a) => setAnalytics(a));
    eng.on('nodeRightClick', (id, evt) => {
      const ox = (evt && evt.original) ? evt.original.clientX : (evt && evt.x) || 0;
      const oy = (evt && evt.original) ? evt.original.clientY : (evt && evt.y) || 0;
      setCtxMenu({ id, x: ox, y: oy });
    });
  }, [onOpenNote]);

  const buildData = (g) => {
    rawRef.current.byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
    let maxIn = 0, mMin = Infinity, mMax = -Infinity;
    for (const n of g.nodes) {
      if ((n.inlinks || 0) > maxIn) maxIn = n.inlinks;
      if (n.mtime) { if (n.mtime < mMin) mMin = n.mtime; if (n.mtime > mMax) mMax = n.mtime; }
    }
    rawRef.current.maxInlinks = maxIn;
    rawRef.current.mtimeRange = mMin < mMax ? { min: mMin, max: mMax } : null;
    /* What the map is actually made of. `/vault/graph` returns the whole
       business — tasks, decisions, message threads, coworkers AND vault
       notes — so a single count cannot honestly be called any one of them
       (see the stats row below). */
    rawRef.current.byType = g.nodes.reduce((acc, n) => {
      const t = n.type || 'note';
      acc[t] = (acc[t] || 0) + 1;
      return acc;
    }, {});
    const edges = g.edges.map((e) => ({ ...e, color: edgeColorForType(e.type, isDark) }));
    return { nodes: g.nodes, edges };
  };

  // Pull note bodies for the concept map (scoped + capped to bound the fetches).
  const loadConceptDocs = async () => {
    const all = await CafresoHQClient.vaultList();
    let files = (all || []).filter((f) => /\.md$/i.test(f.path || ''));
    const sc = scopeRef.current;
    if (sc && sc !== '__all__') files = files.filter((f) => f.path === sc || f.path.startsWith(sc.replace(/\/$/, '') + '/'));
    files = files.sort((a, b) => (b.mtime || 0) - (a.mtime || 0)).slice(0, CONCEPT_NOTE_CAP);
    const docs = [];
    const CONC = 6;
    for (let i = 0; i < files.length; i += CONC) {
      const got = await Promise.all(files.slice(i, i + CONC).map(async (f) => {
        try { return { id: f.path, title: f.title || titleFor(f.path), text: await CafresoHQClient.vaultRead(f.path) }; }
        catch (_) { return null; }
      }));
      for (const d of got) if (d) docs.push(d);
    }
    return docs;
  };

  // Resolve the active data source into {nodes, edges} for the engine.
  const loadData = async () => {
    if (sourceRef.current === 'concepts') {
      if (!window.CafresoCooccur) throw new Error('concept builder unavailable');
      const docs = await loadConceptDocs();
      const built = window.CafresoCooccur.build(docs, { window: 4, maxNodes: 200 });
      setConceptMeta({ docs: docs.length, terms: built.nodes.length });
      return built;
    }
    setConceptMeta(null);
    return await CafresoHQClient.vaultGraph();
  };

  // (Re)mount the engine on fresh data, re-applying controls a remount drops.
  const mountData = (g) => {
    if (!containerRef.current || !window.CafresoGraphEngine) return null;
    try { engineRef.current && engineRef.current.destroy(); } catch (_) {}
    const eng = window.CafresoGraphEngine.mount(containerRef.current, buildData(g), {
      dark: isDark, colorMode: colorModeRef.current, colorFor, now: Date.now(),
      edgeMode: edgesHoverRef.current ? 'hover' : 'always',
    });
    engineRef.current = eng;
    wireEngine(eng);
    if (filterRef.current) eng.setFilter(filterRef.current);
    if (sourceRef.current === 'links' && activePathRef.current) {
      eng.setActivePath(activePathRef.current);
      if (localModeRef.current !== 'global') eng.setLocalMode(activePathRef.current, parseInt(localModeRef.current, 10));
    }
    setNodeCount(g.nodes.length);
    return eng;
  };

  // Load + mount on first render and whenever the source/scope changes.
  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const g = await loadData();
        if (cancelled || !containerRef.current) { setLoading(false); return; }
        const eng = mountData(g);
        setLoading(false);
        if (!eng) return;
        window.CafresoHQGraph = {
          _lastGraph: g,
          pulse: (id) => { try { engineRef.current && engineRef.current.focusNode(id); } catch (_) {} },
          refresh: async () => {
            try {
              const g2 = await loadData();
              if (!containerRef.current) return;
              const e2 = mountData(g2);
              if (e2) window.CafresoHQGraph._lastGraph = g2;
            } catch (_) {}
          },
        };
      } catch (e) { console.warn('graph load:', e); setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [source, scope]);

  // Folder list for the concept-map scope picker (cheap, once).
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const all = await CafresoHQClient.vaultList();
        if (cancelled) return;
        const set = new Set();
        for (const f of all || []) { const i = (f.path || '').indexOf('/'); if (i > 0) set.add(f.path.slice(0, i)); }
        setFolders([...set].sort());
      } catch (_) {}
    })();
    return () => { cancelled = true; };
  }, []);

  // Destroy the engine on unmount.
  React.useEffect(() => () => {
    try { engineRef.current && engineRef.current.destroy(); } catch (_) {}
    if (window.CafresoHQGraph) { try { delete window.CafresoHQGraph; } catch (_) {} }
  }, []);

  // Control → engine wiring.
  React.useEffect(() => { const e = engineRef.current; if (e) { e.setColorMode(colorMode); e.setColorFor(colorFor); } }, [colorMode, colorFor]);
  React.useEffect(() => { const e = engineRef.current; if (e) e.setFilter(filter); }, [filter]);
  React.useEffect(() => { const e = engineRef.current; if (e) e.setEdgeMode(edgesHover ? 'hover' : 'always'); }, [edgesHover]);
  React.useEffect(() => {
    const e = engineRef.current; if (!e) return;
    // Local depth is note-relative — only meaningful for the wikilink graph.
    if (source !== 'links' || localMode === 'global' || !activePath) e.setLocalMode(null, 0);
    else e.setLocalMode(activePath, parseInt(localMode, 10));
  }, [localMode, activePath, source]);
  React.useEffect(() => { const e = engineRef.current; if (e && source === 'links' && activePath) e.setActivePath(activePath); }, [activePath, source]);

  // Persist prefs.
  React.useEffect(() => {
    saveGraphPrefs({ ...persisted, colorMode, localMode, drawerOpen: panelOpen, edgesHover, source, scope });
  }, [colorMode, localMode, panelOpen, edgesHover, source, scope]);

  // Keep sigma sized to its container.
  React.useEffect(() => {
    const el = containerRef.current; if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => { const e = engineRef.current; if (e) e.resize(); });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Publish: export the laid-out snapshot to a shareable public graph URL.
  const publish = React.useCallback(async () => {
    const e = engineRef.current; if (!e) return;
    setSharing(true);
    setShareCopied(false);
    try {
      const snap = e.exportSnapshot();
      snap.title = sourceRef.current === 'concepts'
        ? ('Concept map' + (scopeRef.current && scopeRef.current !== '__all__' ? ' · ' + scopeRef.current : ''))
        : (activePath ? titleFor(activePath) : 'Library graph');
      const base = (typeof window !== 'undefined' && window._API_BASE != null) ? window._API_BASE : '';
      const res = await fetch(base + '/graph/publish', {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(snap),
      });
      const j = await res.json();
      if (j && j.viewerUrl) {
        const full = (base || (typeof location !== 'undefined' ? location.origin : '')) + j.viewerUrl;
        setShareUrl(full);
        try { await navigator.clipboard.writeText(full); setShareCopied(true); }
        catch (_) { setShareCopied(false); }
        // Onboarding: mark "publish your first graph" complete.
        try { localStorage.setItem('cafresohq_hq_v1:publishedGraph', '1'); window.dispatchEvent(new CustomEvent('cafresohq:graph-published')); } catch (_) {}
      }
    } catch (err) { console.warn('publish graph:', err); }
    finally { setSharing(false); }
  }, [activePath]);

  const m = analytics && analytics.metrics;
  const STRUCT_COPY = {
    biased: 'One dominant topic — add contrasting ideas.',
    /* Split out of `biased`, which used to cover the whole low-modularity
       band and said "One dominant topic" over a topic list whose biggest
       row read 39%. Low modularity is a claim about SEPARATION, not about
       dominance; this is the half of it where nothing dominates. Says what
       the number means and offers no advice, because there is nothing wrong
       here to act on — same as `diversified` below. */
    overlapping: 'Topics blur into each other — plenty of links cross between them.',
    focused: 'A clear main theme with some branches.',
    diversified: 'Several well-connected topics — healthy balance.',
    dispersed: 'Many scattered topics — consider bridging them.',
    /* The honest fifth state. Without it, an edgeless graph got NaN
       modularity, fell through every threshold in analytics.worker.js, and
       published "Dispersed — many scattered topics" over a cabinet with no
       notes in it — beside this panel's own "Topics: 1", which contradicted
       it in the same breath. Says nothing about shape, because there isn't
       one yet, and points at the thing that would create one. */
    unformed: 'Not enough here to read a shape yet — link a few notes and this fills in.',
  };
  const COLOR_MODES = [['community', 'Topics'], ['tags', 'Tags'], ['type', 'Type'], ['folder', 'Folder'], ['inlinks', 'Links'], ['modified', 'Recency']];

  const ctrlStyle = { background: 'rgba(20,18,12,0.55)', color: '#e9e2d4', border: '1px solid rgba(245,210,93,0.25)', borderRadius: 6, padding: '3px 7px', fontSize: 12, fontFamily: 'Inter, system-ui, sans-serif' };

  return React.createElement('div', { style: { position: 'relative', width: '100%', height: '100%', minHeight: 0, overflow: 'hidden', background: isDark ? '#171310' : '#f4efe6' } },
    // Sigma mounts here.
    React.createElement('div', { ref: containerRef, style: { position: 'absolute', inset: 0 } }),

    // Loading hint.
    loading && React.createElement('div', { style: { position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#bdb3a0', font: '13px Inter, sans-serif', pointerEvents: 'none' } }, source === 'concepts' ? 'Building concept map…' : 'Loading graph…'),

    // Top toolbar. zIndex above the analytics panel below: on a narrow
    // viewport this row's ~10 controls (filter, two selects, four buttons,
    // the analytics toggle, minimize) wrap onto a second line, and that
    // line lands inside the panel's own top:50 territory. Without this the
    // panel — which paints AFTER the toolbar in DOM order, so it wins
    // default stacking — sits visually and functionally on top of the
    // wrapped row. Confirmed live: `document.elementFromPoint()` at the
    // "Hide analytics ›" button's own center returned the panel's content
    // div, not the button, so the one control that closes the panel became
    // permanently unclickable the moment it opened on an ordinary window
    // width — not a rare narrow-viewport edge case, the default size this
    // was driven at.
    React.createElement('div', { style: { position: 'absolute', top: 10, left: 10, right: 10, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', pointerEvents: 'none', zIndex: 2 } },
      React.createElement('input', {
        value: filter, placeholder: source === 'concepts' ? 'Filter concepts' : 'Filter  (tag:x  type:y  -term)',
        onChange: (e) => setFilter(e.target.value),
        style: { ...ctrlStyle, width: 180, pointerEvents: 'auto' },
      }),
      // Data source: wikilink graph vs concept co-occurrence map.
      React.createElement('select', { value: source, onChange: (e) => setSource(e.target.value), title: 'Graph source', style: { ...ctrlStyle, pointerEvents: 'auto' } },
        React.createElement('option', { value: 'links' }, '🔗 Links'),
        React.createElement('option', { value: 'concepts' }, '🧠 Concepts')),
      React.createElement('select', { value: colorMode, onChange: (e) => setColorMode(e.target.value), title: 'Color by', style: { ...ctrlStyle, pointerEvents: 'auto' } },
        COLOR_MODES.map(([v, l]) => React.createElement('option', { key: v, value: v }, l))),
      // Concept mode → folder scope picker; link mode → local depth around the active note.
      source === 'concepts'
        ? React.createElement('select', { value: scope, onChange: (e) => setScope(e.target.value), title: 'Concept-map scope (folder)', style: { ...ctrlStyle, pointerEvents: 'auto', maxWidth: 150 } },
            React.createElement('option', { value: '__all__' }, 'All notes'),
            folders.map((f) => React.createElement('option', { key: f, value: f }, f + '/')))
        : React.createElement('select', { value: localMode, onChange: (e) => setLocalMode(e.target.value), title: 'Local depth around active note', style: { ...ctrlStyle, pointerEvents: 'auto' } },
            [['global', 'Whole graph'], ['1', '1 hop'], ['2', '2 hops'], ['3', '3 hops']].map(([v, l]) => React.createElement('option', { key: v, value: v }, l))),
      React.createElement('button', { onClick: () => setEdgesHover((v) => !v), title: edgesHover ? 'Edges appear on hover' : 'Edges always visible — click to calm', style: { ...ctrlStyle, cursor: 'pointer', pointerEvents: 'auto', ...(edgesHover ? { color: '#F5D25D', borderColor: 'rgba(245,210,93,0.55)' } : {}) } }, edgesHover ? 'Edges: hover' : 'Edges: on'),
      source === 'concepts'
        ? React.createElement('button', { onClick: () => { const a = window.CafresoHQGraph; if (a && a.refresh) a.refresh(); }, title: 'Re-read notes and rebuild the concept map', style: { ...ctrlStyle, cursor: 'pointer', pointerEvents: 'auto' } }, '↻ Rebuild')
        : React.createElement('button', { onClick: () => { const e = engineRef.current; if (e) e.refreshLayout(); }, title: 'Re-run layout', style: { ...ctrlStyle, cursor: 'pointer', pointerEvents: 'auto' } }, '↻ Layout'),
      React.createElement('button', { onClick: publish, title: 'Publish a shareable public graph', style: { ...ctrlStyle, cursor: 'pointer', pointerEvents: 'auto' } }, sharing ? 'Publishing…' : '⤴ Share'),
      React.createElement('div', { style: { flex: 1 } }),
      React.createElement('button', { onClick: () => setPanelOpen((v) => !v), style: { ...ctrlStyle, cursor: 'pointer', pointerEvents: 'auto' } }, panelOpen ? 'Hide analytics ›' : '‹ Analytics'),
      onMinimize && React.createElement('button', { onClick: onMinimize, style: { ...ctrlStyle, cursor: 'pointer', pointerEvents: 'auto' } }, '✕'),
    ),

    // Analytics side panel (InfraNodus-style).
    panelOpen && React.createElement('div', { style: { position: 'absolute', top: 50, right: 10, bottom: 10, width: 246, overflowY: 'auto', background: 'rgba(20,18,12,0.82)', backdropFilter: 'blur(6px)', border: '1px solid rgba(245,210,93,0.22)', borderRadius: 10, padding: '12px 13px', color: '#e9e2d4', font: '12px Inter, system-ui, sans-serif', zIndex: 1 } },
      React.createElement('div', { style: { fontWeight: 600, fontSize: 13, marginBottom: 8, color: '#F5D25D' } }, source === 'concepts' ? 'Concept analysis' : 'Graph analysis'),
      source === 'concepts' && conceptMeta && React.createElement('div', { style: { color: '#8f8676', fontSize: 11, marginBottom: 8 } }, 'Co-occurrence over ' + conceptMeta.docs + ' note' + (conceptMeta.docs === 1 ? '' : 's')),
      !m && React.createElement('div', { style: { color: '#9b938a' } }, 'Computing…'),
      m && React.createElement(React.Fragment, null,
        React.createElement('div', { style: { display: 'inline-block', padding: '3px 9px', borderRadius: 20, background: 'rgba(245,210,93,0.16)', color: '#F5D25D', fontWeight: 600, textTransform: 'capitalize', marginBottom: 6 } }, m.structure || '—'),
        React.createElement('div', { style: { color: '#cabfa9', marginBottom: 10, lineHeight: 1.4 } }, STRUCT_COPY[m.structure] || ''),
        React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 10px', marginBottom: 12 } },
          /* "Notes" was a lie on a business surface. `/vault/graph` returns
             the whole office — measured on a real session it was 19 message
             threads, 12 coworkers, 5 decisions and 2 tasks, and **zero**
             vault notes (the vault was empty) — all counted and labelled
             "Notes: 38". Concept mode really is concepts, so it keeps its
             word; the links map gets one that covers what it holds, with
             the actual mix spelled out below. */
          /* Modularity is GONE, and the two graph-theory words are
             translated. This panel already had the "Notes was a lie" fix
             below; the metrics row kept three terms a boss cannot act on.

             Modularity is the worst of them because it is redundant AND
             unreadable: analytics.worker.js decides the verdict chip from
             it (a low modularity picks between 'biased' and 'overlapping'),
             so the sentence directly above this row IS the modularity, said
             in words. Showing 0.25 as well adds a number with no visible
             scale, which is the same shape as the FUEL gauge that filled
             toward a budget nobody set.

             Components and avg degree are real and worth keeping; they just
             needed the names a boss would use. */
          [[source === 'concepts' ? 'Concepts' : 'On the map', m.nodes], ['Links', m.edges], ['Topics', m.communityCount], ['Separate clusters', m.components], ['Links per item', (m.avgDegree || 0).toFixed(1)]]
            .map(([k, v]) => React.createElement('div', { key: k }, React.createElement('span', { style: { color: '#8f8676' } }, k + ': '), React.createElement('b', null, v)))),

        /* The mix, in office words. Says nothing when a kind is absent, so
           an empty vault never claims notes it doesn't have. */
        source !== 'concepts' && (() => {
          const NAMES = {
            note: ['note', 'notes'], task: ['task', 'tasks'],
            decision: ['decision', 'decisions'], 'message-thread': ['conversation', 'conversations'],
            agent: ['coworker', 'coworkers'],
          };
          const by = (rawRef.current && rawRef.current.byType) || {};
          const parts = Object.keys(by)
            .sort((a, b) => by[b] - by[a])
            .map((t) => {
              const n = by[t];
              const nm = NAMES[t] || [t, t + 's'];
              return n + ' ' + (n === 1 ? nm[0] : nm[1]);
            });
          if (!parts.length) return null;
          return React.createElement('div', { style: { color: '#8f8676', fontSize: 11, marginTop: -6, marginBottom: 12, lineHeight: 1.45 } }, parts.join(' · '));
        })(),

        /* Top influential (betweenness brokers). The heading is conditional
           because nothing brokers on a small or disjoint graph — every
           betweenness is 0, the Jenks cutoff comes back Infinity, and the
           list is empty. A brand-new office was therefore shown a bold
           "Most influential" with a blank space under it, which reads as a
           surface that failed to load rather than one with nothing true to
           say yet. No answer is better rendered as no section. */
        (analytics.topInfluential || []).length > 0 && React.createElement(React.Fragment, null,
          React.createElement('div', { style: { fontWeight: 600, margin: '4px 0 5px', color: '#F5D25D' } }, 'Most influential'),
          (analytics.topInfluential || []).slice(0, 6).map((t) =>
            React.createElement('div', { key: t.id, onClick: () => { const e = engineRef.current; if (e) e.focusNode(t.id); }, title: 'Focus', style: { cursor: 'pointer', padding: '2px 0', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } },
              '◆ ' + titleFor(t.id)))),

        // Topical clusters. Conditional for the same reason as the heading
        // above: an empty vault was showing "Main topics" over blank space.
        (analytics.clusters || []).length > 0 && React.createElement(React.Fragment, null,
        React.createElement('div', { style: { fontWeight: 600, margin: '12px 0 5px', color: '#F5D25D' } }, 'Main topics'),
        (analytics.clusters || []).slice(0, 5).map((c) =>
          React.createElement('div', { key: c.community, style: { marginBottom: 6 } },
            React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 6 } },
              React.createElement('span', { style: { width: 9, height: 9, borderRadius: '50%', background: window.CafresoGraphEngine.communityColor(c.community), display: 'inline-block', flex: '0 0 auto' } }),
              React.createElement('b', null, Math.round(c.share * 100) + '%'),
              /* Same correction as the stat row above: a cluster mixes
                 conversations, coworkers, decisions and tasks, so "notes"
                 was wrong here too. "items" is true whatever it holds.
                 Singular when there is one of it: a lone note read "1 items",
                 and the counts here sit beside a percentage the boss is
                 already having to squint at. */
              React.createElement('span', { style: { color: '#8f8676' } },
                c.size + ' ' + (source === 'concepts'
                  ? (c.size === 1 ? 'concept' : 'concepts')
                  : (c.size === 1 ? 'item' : 'items')))),
            React.createElement('div', { style: { color: '#cabfa9', fontSize: 11, paddingLeft: 15, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } },
              /* Distinct NODES can share a display title — several messages
                 all render as "You → Sora" — so slicing to 3 before resolving
                 titles produced labels like "You → Sora, You → Sora, You →
                 Sora": one topic, repeated, dressed as three exemplars.
                 `topNodes` carries 5 candidates; dedupe on the resolved title
                 across all of them and take the first 3 that actually differ,
                 so a cluster with real variety shows it and a cluster that
                 genuinely is all one thing says so once. */
              (() => {
                const seen = new Set();
                const names = [];
                for (const id of (c.topNodes || [])) {
                  const t = titleFor(id);
                  if (!t || seen.has(t)) continue;
                  seen.add(t);
                  names.push(t);
                  if (names.length === 3) break;
                }
                return names.join(', ');
              })())))),

        // Structural gap.
        analytics.gap && React.createElement('div', { style: { marginTop: 12, padding: 8, borderRadius: 8, background: 'rgba(232,169,169,0.10)', border: '1px solid rgba(232,169,169,0.25)' } },
          React.createElement('div', { style: { fontWeight: 600, color: '#E8A9A9', marginBottom: 3 } }, 'Structural gap'),
          React.createElement('div', { style: { color: '#cabfa9', fontSize: 11, lineHeight: 1.4 } },
            'Weakly connected: ', React.createElement('b', null, titleFor(analytics.gap.aTop)), ' ⟷ ', React.createElement('b', null, titleFor(analytics.gap.bTop)))),
      ),
    ),

    // Node context menu.
    ctxMenu && React.createElement('div', { style: { position: 'fixed', left: Math.min(ctxMenu.x, (typeof window !== 'undefined' ? window.innerWidth : 9999) - 170), top: ctxMenu.y, zIndex: 50, background: 'rgba(28,24,16,0.97)', border: '1px solid rgba(245,210,93,0.3)', borderRadius: 8, padding: 4, minWidth: 150, font: '12px Inter, sans-serif', color: '#e9e2d4' },
      onMouseLeave: () => setCtxMenu(null) },
      [...(source === 'links' ? [['Open note', () => { onOpenNote && onOpenNote(ctxMenu.id); setCtxMenu(null); }]] : []),
       ['Focus', () => { const e = engineRef.current; if (e) e.focusNode(ctxMenu.id); setCtxMenu(null); }],
       ['Hide node', () => { const e = engineRef.current; if (e) { const s = new Set(e.hidden); s.add(ctxMenu.id); e.setHidden(s); } setCtxMenu(null); }]]
        .map(([label, fn]) => React.createElement('div', { key: label, onClick: fn, style: { padding: '6px 10px', cursor: 'pointer', borderRadius: 5 }, onMouseEnter: (ev) => ev.currentTarget.style.background = 'rgba(245,210,93,0.14)', onMouseLeave: (ev) => ev.currentTarget.style.background = 'transparent' }, label))),

    // Share modal.
    shareUrl && React.createElement('div', { style: { position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%,-50%)', zIndex: 60, width: 420, maxWidth: '90%', background: 'rgba(24,20,14,0.98)', border: '1px solid rgba(245,210,93,0.3)', borderRadius: 12, padding: 18, color: '#e9e2d4', font: '13px Inter, sans-serif', boxShadow: '0 18px 60px rgba(0,0,0,0.5)' } },
      React.createElement('div', { style: { fontWeight: 600, color: '#F5D25D', marginBottom: 8 } }, '⤴ Public graph published'),
      React.createElement('div', { style: { color: '#cabfa9', marginBottom: 10, lineHeight: 1.4 } },
        'Anyone with this link can view this graph (read-only). ' + (shareCopied ? 'Copied to your clipboard.' : 'Copy it below — your browser blocked the automatic copy.')),
      React.createElement('input', { readOnly: true, value: shareUrl, onFocus: (e) => e.target.select(), style: { width: '100%', boxSizing: 'border-box', ...ctrlStyle, marginBottom: 10 } }),
      React.createElement('div', { style: { display: 'flex', gap: 8 } },
        React.createElement('button', { onClick: () => window.open(shareUrl, '_blank'), style: { ...ctrlStyle, cursor: 'pointer' } }, 'Open ↗'),
        React.createElement('button', { onClick: async () => {
          const embed = '<iframe src="' + shareUrl + '" width="100%" height="600" style="border:0;border-radius:12px"></iframe>';
          try { await navigator.clipboard.writeText(embed); setEmbedCopied(true); }
          catch (_) { setEmbedCopied(false); }
          setTimeout(() => setEmbedCopied(null), 1500);
        }, style: { ...ctrlStyle, cursor: 'pointer' } }, embedCopied === true ? 'Copied ✓' : embedCopied === false ? 'Copy failed' : 'Copy embed'),
        React.createElement('div', { style: { flex: 1 } }),
        React.createElement('button', { onClick: () => setShareUrl(null), style: { ...ctrlStyle, cursor: 'pointer' } }, 'Close')),
    ),
  );
}

/* Connected-components labeling. Returns { id → componentIndex } and the
   total component count. Used for auto-cluster coloring. */
function connectedComponents(state) {
  const adj = graphAdjacency(state);
  const comp = {};
  let idx = 0;
  for (const n of state.nodes) {
    if (comp[n.id] != null) continue;
    const queue = [n.id]; comp[n.id] = idx;
    while (queue.length) {
      const cur = queue.shift();
      for (const nb of adj.get(cur) || []) {
        if (comp[nb] == null) { comp[nb] = idx; queue.push(nb); }
      }
    }
    idx++;
  }
  return { comp, count: idx };
}

/* BFS shortest path between two node ids. Returns array of ids inclusive,
   or null if unreachable. Treats edges as undirected. */
function shortestPathBetween(state, fromId, toId) {
  if (!fromId || !toId || fromId === toId) return fromId ? [fromId] : null;
  const adj = graphAdjacency(state);
  const prev = new Map(); prev.set(fromId, null);
  const queue = [fromId];
  while (queue.length) {
    const cur = queue.shift();
    if (cur === toId) {
      const path = []; let c = cur;
      while (c != null) { path.unshift(c); c = prev.get(c); }
      return path;
    }
    for (const nb of adj.get(cur) || []) {
      if (!prev.has(nb)) { prev.set(nb, cur); queue.push(nb); }
    }
  }
  return null;
}

/* Choose neighbor in roughly the given direction vector (dx,dy). Used by
   keyboard arrow navigation. */
function neighborInDirection(state, fromId, dx, dy) {
  const from = state.byId[fromId]; if (!from) return null;
  const targetAngle = Math.atan2(dy, dx);
  let best = null, bestScore = -Infinity;
  for (const e of state.edges) {
    const s = e.source.id || e.source, t = e.target.id || e.target;
    let other = null;
    if (s === fromId) other = state.byId[t];
    else if (t === fromId) other = state.byId[s];
    if (!other) continue;
    const a = Math.atan2(other.y - from.y, other.x - from.x);
    let diff = Math.abs(((a - targetAngle + Math.PI) % (Math.PI * 2)) - Math.PI);
    // Score: prefer aligned direction, secondarily prefer closer nodes.
    const dist = Math.hypot(other.x - from.x, other.y - from.y) || 1;
    const score = -diff * 4 - dist * 0.001;
    if (score > bestScore) { bestScore = score; best = other; }
  }
  return best;
}

/* In-browser semantic similarity using TF-IDF over a node's title tokens,
   tags, and folder path. Returns top-K candidate ghost edges between
   currently-unlinked node pairs. Cheap enough for vaults up to ~5k notes;
   beyond that we sample. */
function graphAdjacency(state) {
  if (!state) return new Map();
  if (state._adjEdgesRef === state.edges && state._adjacency) return state._adjacency;
  const adj = new Map();
  for (const n of (state.nodes || [])) adj.set(n.id, []);
  for (const e of (state.edges || [])) {
    const s = e.source && e.source.id ? e.source.id : e.source;
    const t = e.target && e.target.id ? e.target.id : e.target;
    if (adj.has(s) && adj.has(t)) { adj.get(s).push(t); adj.get(t).push(s); }
  }
  state._adjEdgesRef = state.edges;
  state._adjacency = adj;
  return adj;
}

function computeGhostEdges(state, opts = {}) {
  const TOPK       = opts.topK || 40;
  const MIN_SCORE  = opts.minScore || 0.18;
  const stop = new Set(['the','and','of','to','a','for','in','on','is','at','it','this','that','with','as','an','by','be','or','from','my','i']);

  const tokenize = (s) => (s || '').toLowerCase()
    .replace(/\.md$/, '')
    .replace(/[^\w\s-]/g, ' ')
    .split(/\s+/)
    .filter(t => t.length > 2 && !stop.has(t));

  const docs = state.nodes.map(n => {
    const titleToks = tokenize(n.title || n.id.split('/').pop());
    const folderToks = tokenize((n.id || '').split('/').slice(0, -1).join(' '));
    const tagToks    = (n.tags || []).map(t => t.replace(/^#/, '').toLowerCase());
    // Tags weighted 3x, folder 2x.
    const all = [...titleToks, ...folderToks, ...folderToks, ...tagToks, ...tagToks, ...tagToks];
    const tf = new Map();
    for (const t of all) tf.set(t, (tf.get(t) || 0) + 1);
    return { id: n.id, tf };
  });

  // IDF
  const df = new Map();
  for (const d of docs) for (const t of d.tf.keys()) df.set(t, (df.get(t) || 0) + 1);
  const N = docs.length;
  const idf = new Map();
  for (const [t, c] of df) idf.set(t, Math.log(1 + N / (1 + c)));

  // Build TF-IDF vectors as Maps; norm them.
  const vecs = docs.map(d => {
    const v = new Map();
    let normSq = 0;
    for (const [t, c] of d.tf) {
      const w = c * (idf.get(t) || 0);
      if (w > 0) { v.set(t, w); normSq += w * w; }
    }
    return { id: d.id, v, norm: Math.sqrt(normSq) || 1 };
  });

  // Existing-edge set so we skip pairs already linked.
  const linked = new Set();
  for (const e of state.edges) {
    const s = e.source.id || e.source, t = e.target.id || e.target;
    linked.add(s < t ? s + '\0' + t : t + '\0' + s);
  }

  // Pairwise — bail out early if vault is huge (sample 1500 nodes).
  const sample = vecs.length > 1500
    ? vecs.slice().sort(() => Math.random() - 0.5).slice(0, 1500)
    : vecs;

  const candidates = [];
  for (let i = 0; i < sample.length; i++) {
    const a = sample[i];
    for (let j = i + 1; j < sample.length; j++) {
      const b = sample[j];
      const key = a.id < b.id ? a.id + '\0' + b.id : b.id + '\0' + a.id;
      if (linked.has(key)) continue;
      // dot product over the smaller map for speed
      const [s1, s2] = a.v.size <= b.v.size ? [a.v, b.v] : [b.v, a.v];
      let dot = 0;
      for (const [t, w] of s1) {
        const w2 = s2.get(t);
        if (w2) dot += w * w2;
      }
      const score = dot / (a.norm * b.norm);
      if (score >= MIN_SCORE) candidates.push({ a: a.id, b: b.id, score });
    }
  }
  candidates.sort((x, y) => y.score - x.score);
  return candidates.slice(0, TOPK);
}

/* Cluster palette — 12 distinct hues spaced for maximum visual separation. */
const CLUSTER_HUES = [10, 35, 55, 95, 130, 175, 200, 230, 270, 300, 325, 350];
function clusterColor(idx, isDark) {
  const hue = CLUSTER_HUES[idx % CLUSTER_HUES.length];
  return `hsl(${hue}, ${isDark ? 60 : 50}%, ${isDark ? 65 : 58}%)`;
}

/* BFS from rootId out to maxDepth (inclusive). Returns the set of node ids
   reachable through the graph's edges in either direction. Used by Local mode. */
function bfsLocal(state, rootId, maxDepth) {
  if (!rootId || !state.byId[rootId]) return null;
  const adj = graphAdjacency(state);
  const visited = new Set([rootId]);
  let frontier = [rootId];
  for (let d = 0; d < maxDepth; d++) {
    const next = [];
    for (const id of frontier) {
      for (const nb of (adj.get(id) || [])) {
        if (!visited.has(nb)) { visited.add(nb); next.push(nb); }
      }
    }
    if (next.length === 0) break;
    frontier = next;
  }
  return visited;
}

function getNeighbors(state, nodeId) {
  if (!nodeId) return null;
  const neighbors = new Set([nodeId]);
  const adj = graphAdjacency(state);
  for (const nb of (adj.get(nodeId) || [])) neighbors.add(nb);
  return neighbors;
}

function simulate(s) {
  const cfg = s.settings || {};

  // Settling: freeze on the seed circle for state.freezeUntil ms, then ramp
  // forces in linearly between freezeUntil and warmupUntil. This produces a
  // smooth "circle pause → drift → settle" intro instead of an instant explosion.
  const now = Date.now();
  let warmth = 1;
  if (s.freezeUntil && now < s.freezeUntil) {
    warmth = 0;
  } else if (s.warmupUntil && now < s.warmupUntil) {
    const span = s.warmupUntil - (s.freezeUntil || s.warmupUntil);
    const t = span > 0 ? (now - (s.freezeUntil || 0)) / span : 1;
    // Ease-in-out cubic — slow start, gentle end. Feels like nodes "drift" into place.
    const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    warmth = e < 0 ? 0 : e > 1 ? 1 : e;
  }

  const REPULSE     = (cfg.repelForce    != null ? cfg.repelForce    : 900)   * warmth;
  const SPRING      = (cfg.linkForce     != null ? cfg.linkForce     : 0.022) * warmth;
  const SPRING_LEN  = cfg.linkDistance  != null ? cfg.linkDistance  : 150;
  const CENTER      = (cfg.centerForce   != null ? cfg.centerForce   : 0.0008) * warmth;
  const LAYER       = (cfg.layerForce    != null ? cfg.layerForce    : 0.003) * warmth;
  const DAMP        = 0.85;

  // Stability clamps — cap force per pair, velocity per step, displacement per step.
  // Without these the inverse-square repulsion explodes when two nodes overlap.
  // Velocity & step caps are scaled by warmth so the intro drift is gentle.
  const MIN_DIST2   = 100;
  const MAX_FORCE   = 12 * warmth;
  const MAX_VEL     = 4 + 14 * warmth;   // 4 px/frame at start of warmup → 18 at full
  const MAX_STEP    = 6 + 18 * warmth;   // 6 → 24

  const clamp = (v, lo, hi) => v < lo ? lo : v > hi ? hi : v;

  const { nodes, edges } = s;
  const D3 = !!s.is3D;

  // During the introductory freeze, keep repainting overlays/pulses but skip
  // the expensive O(n²) force pass. Previously we multiplied every force by 0
  // and still paid the full pairwise cost, causing the first seconds to hitch.
  if (warmth <= 0.0001) return;

  /* Repulsion — every pair pushes apart (Coulomb-like). */
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j];
      let dx = b.x - a.x, dy = b.y - a.y;
      let dz = D3 ? (b.z || 0) - (a.z || 0) : 0;
      let d2 = dx*dx + dy*dy + dz*dz;
      if (d2 < 0.01) {
        dx = (Math.random() - 0.5) * 2;
        dy = (Math.random() - 0.5) * 2;
        if (D3) dz = (Math.random() - 0.5) * 2;
        d2 = dx*dx + dy*dy + dz*dz;
      }
      if (d2 < MIN_DIST2) d2 = MIN_DIST2;
      const d = Math.sqrt(d2);
      const f = -REPULSE / d2;
      let fx = clamp(dx / d * f, -MAX_FORCE, MAX_FORCE);
      let fy = clamp(dy / d * f, -MAX_FORCE, MAX_FORCE);
      a.vx += fx; a.vy += fy;
      b.vx -= fx; b.vy -= fy;
      if (D3) {
        let fz = clamp(dz / d * f, -MAX_FORCE, MAX_FORCE);
        a.vz = (a.vz || 0) + fz; b.vz = (b.vz || 0) - fz;
      }
    }
  }

  /* Springs — linked nodes attract toward link distance. */
  for (const e of edges) {
    const a = e.source.id ? e.source : s.byId[e.source];
    const b = e.target.id ? e.target : s.byId[e.target];
    if (!a || !b) continue;
    const dx = b.x - a.x, dy = b.y - a.y;
    const dz = D3 ? (b.z || 0) - (a.z || 0) : 0;
    const d = Math.sqrt(dx*dx + dy*dy + dz*dz) || 1;
    const f = (d - SPRING_LEN) * SPRING;
    let fx = clamp(dx / d * f, -MAX_FORCE, MAX_FORCE);
    let fy = clamp(dy / d * f, -MAX_FORCE, MAX_FORCE);
    a.vx += fx; a.vy += fy;
    b.vx -= fx; b.vy -= fy;
    if (D3) {
      let fz = clamp(dz / d * f, -MAX_FORCE, MAX_FORCE);
      a.vz = (a.vz || 0) + fz; b.vz = (b.vz || 0) - fz;
    }
  }

  /* Integrate. */
  for (const n of nodes) {
    if (n.fx != null) { n.x = n.fx; n.y = n.fy; n.vx = 0; n.vy = 0; if (D3) n.vz = 0; continue; }

    n.vx += ((n.outlinks || 0) - (n.inlinks || 0)) * LAYER;
    n.vx -= n.x * CENTER;
    n.vy -= n.y * CENTER;
    n.vx *= DAMP; n.vy *= DAMP;
    n.vx = clamp(n.vx, -MAX_VEL, MAX_VEL);
    n.vy = clamp(n.vy, -MAX_VEL, MAX_VEL);
    n.x += clamp(n.vx, -MAX_STEP, MAX_STEP);
    n.y += clamp(n.vy, -MAX_STEP, MAX_STEP);

    if (D3) {
      n.z = n.z || 0;
      // Weaker z-centering so the cloud stays voluminous instead of
      // collapsing into a flat plane.
      n.vz = (n.vz || 0) - n.z * (CENTER * 0.25);
      n.vz *= DAMP;
      n.vz = clamp(n.vz, -MAX_VEL, MAX_VEL);
      n.z += clamp(n.vz, -MAX_STEP, MAX_STEP);
    }
  }
}

/* ---- Obsidian-style colour map for tagged notes -------------------------
   These are *fallbacks*. Each tag also reads a CSS variable
   (e.g. --tag-project) so styles.css can override per theme. */
const TAG_FALLBACKS = {
  '#project': '#7DB5B5',
  '#person':  '#C9B8E0',
  '#moc':     '#F0C674',
  '#idea':    '#E8A9A9',
  '#daily':   '#A5C4A1',
  '#archive': '#A39C8C',
};

function resolveTagColor(tag, computedStyle) {
  const varName = '--tag-' + tag.replace(/^#/, '');
  const v = computedStyle.getPropertyValue(varName).trim();
  return v || TAG_FALLBACKS[tag] || null;
}

/* ---- Color-by-mode helpers --------------------------------------------- */

/* Stable hash → 0..359 hue, bucketed into 12 evenly-spaced slots so similar
   folders are visually distinct rather than all "kinda blue". */
function folderHueFor(path) {
  const folder = (path || '').split('/').slice(0, -1).join('/') || '__root__';
  let h = 2166136261;
  for (let i = 0; i < folder.length; i++) {
    h ^= folder.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const slot = Math.abs(h) % 12;
  return slot * 30; // 0,30,60,…,330
}

function folderColor(path, isDark) {
  return `hsl(${folderHueFor(path)}, ${isDark ? 55 : 45}%, ${isDark ? 65 : 60}%)`;
}

/* Heat gradient — sharp recency-aware color. Returns vivid red/orange for
   "today", warm yellow for "this week", cool blue for "this month", dim
   gray for older. Tuned to feel like a thermal camera. */
function heatmapColor(daysOld, isDark) {
  if (daysOld == null || isNaN(daysOld)) return isDark ? '#5a5670' : '#cdbfa5';
  const d = Math.max(0, daysOld);
  // Hot zones with sharp transitions.
  if (d < 1)   return isDark ? '#ff6b6b' : '#e84d4d';   // today
  if (d < 3)   return isDark ? '#ff9a5a' : '#e87a3d';   // last 3 days
  if (d < 7)   return isDark ? '#ffcc66' : '#d9a040';   // this week
  if (d < 14)  return isDark ? '#e8cc7a' : '#bfa05a';   // this fortnight
  if (d < 30)  return isDark ? '#a8b5d9' : '#6a8aa8';   // this month
  if (d < 90)  return isDark ? '#7a8aa0' : '#8a9aa8';   // last 3 months
  return isDark ? '#5a5670' : '#9a948a';                // older
}

/* Map a number into a cool→warm gradient. v ∈ [0,1] */
function gradientCoolWarm(v, isDark) {
  v = v < 0 ? 0 : v > 1 ? 1 : v;
  // Stops: deep teal → sage → cream → peach → rose
  const stops = isDark
    ? [[80,170,170],[150,200,150],[230,210,160],[235,170,140],[230,140,140]]
    : [[110,180,180],[160,200,150],[230,210,160],[230,170,140],[210,130,130]];
  const i = Math.min(stops.length - 2, Math.floor(v * (stops.length - 1)));
  const t = (v * (stops.length - 1)) - i;
  const a = stops[i], b = stops[i + 1];
  const r = Math.round(a[0] + (b[0]-a[0])*t);
  const g = Math.round(a[1] + (b[1]-a[1])*t);
  const bl = Math.round(a[2] + (b[2]-a[2])*t);
  return `rgb(${r},${g},${bl})`;
}

/* Resolve final fill given the current colorMode. Returns null if mode is
   'tags' and no tag matched (caller falls back to inlink-shade). */
function typeColor(type, isDark) {
  const t = type || 'note';
  const colors = {
    research: isDark ? '#9fd3ff' : '#3d7fb8',
    project:  isDark ? '#7db5b5' : '#2d8b8b',
    task:     isDark ? '#f0c674' : '#a57400',
    agent:    isDark ? '#c9b8e0' : '#7d5bb5',
    decision: isDark ? '#e8a9a9' : '#b84a4a',
    proposal: isDark ? '#ffcf99' : '#bd6b19',
    memory:   isDark ? '#a5c4a1' : '#4f8a49',
    code_file:isDark ? '#b7c9ff' : '#526fb8',
    risk:     isDark ? '#ff9d9d' : '#b83333',
    // HQ-state ingestion adds these extra node types alongside the vault notes:
    mission:        isDark ? '#ffe19a' : '#c08a30',  // gold — running work
    receipt:        isDark ? '#cfcfcf' : '#7a7a7a',  // grey — audit trail / past actions
    'message-thread': isDark ? '#cfb8e8' : '#7d5bb5', // soft violet — comms threads
    note:     isDark ? '#d8c9a8' : '#9c8555',
  };
  return colors[t] || colors.note;
}

function colorForNode(n, state, isDark, computedStyle) {
  // Cluster coloring overrides colorMode when toggled on.
  if (state.clusterColoring && state.clusters) {
    const idx = state.clusters.comp[n.id];
    if (idx != null) return clusterColor(idx, isDark);
  }
  const mode = state.colorMode || 'tags';
  if (mode === 'folder') {
    return folderColor(n.id, isDark);
  }
  if (mode === 'type') {
    return typeColor(n.type, isDark);
  }
  if (mode === 'inlinks') {
    const max = state.maxInlinks || 1;
    return gradientCoolWarm((n.inlinks || 0) / max, isDark);
  }
  if (mode === 'modified') {
    const r = state.mtimeRange;
    if (!r || !n.mtime) return null;
    const v = (n.mtime - r.min) / Math.max(1, r.max - r.min);
    return gradientCoolWarm(v, isDark);
  }
  if (mode === 'heatmap') {
    if (!n.mtime) return null;
    const daysOld = (Date.now() - n.mtime) / 86400000;
    return heatmapColor(daysOld, isDark);
  }
  // 'tags' default
  for (const t of (n.tags || [])) {
    const c = resolveTagColor(t, computedStyle);
    if (c) return c;
  }
  return null;
}

function nodeMatchesFilter(n, filter) {
  if (!filter) return true;
  const raw = String(filter).trim();
  if (!raw) return true;
  const ageDays = n.mtime ? (Date.now() - n.mtime) / 86400000 : 0;
  const isOrphan = (n.inlinks || 0) === 0;
  const hay = [n.title, n.id, n.path, n.type, ...(n.tags || [])].join(' ').toLowerCase();
  const evalTerm = (term) => {
    term = term.trim();
    if (!term) return true;
    let neg = false;
    if (term.startsWith('-')) { neg = true; term = term.slice(1).trim(); }
    const low = term.toLowerCase().replace(/^"|"$/g, '');
    let ok;
    if (low.startsWith('type:')) ok = String(n.type || 'note').toLowerCase() === low.slice(5);
    else if (low.startsWith('path:')) ok = String(n.id || '').toLowerCase().includes(low.slice(5).replace(/^"|"$/g, ''));
    else if (low.startsWith('tag:')) ok = (n.tags || []).some(t => String(t).replace(/^#/,'').toLowerCase().includes(low.slice(4).replace(/^#/,'').replace(/^"|"$/g, '')));
    else if (low.startsWith('file:')) ok = String(n.title || n.id || '').toLowerCase().includes(low.slice(5).replace(/^"|"$/g, ''));
    else if (low === 'orphan') ok = isOrphan;
    else if (low === 'stale') ok = !!n.mtime && ageDays > 60;
    else ok = hay.includes(low);
    return neg ? !ok : ok;
  };
  return raw.split(/\s+OR\s+/i).some(part => part.split(/\s+AND\s+|\s+/i).every(evalTerm));
}

function nodeIsVisible(n, state) {
  if (state.hiddenIds && state.hiddenIds.has(n.id)) return false;
  if (state.filter && !nodeMatchesFilter(n, state.filter)) return false;
  if (state.localVisible && !state.localVisible.has(n.id)) return false;
  // Time scrubber: hide notes newer than the scrub timestamp.
  if (state.timeScrub && n.mtime && n.mtime > state.timeScrub) return false;
  return true;
}

/* Compute centroid + member count for each cluster, used for label placement. */
function clusterCentroids(state) {
  if (!state.clusters) return [];
  const acc = {}; // idx → {sx,sy,n,members[]}
  for (const node of state.nodes) {
    if (state.hiddenIds && state.hiddenIds.has(node.id)) continue;
    const idx = state.clusters.comp[node.id];
    if (idx == null) continue;
    if (!acc[idx]) acc[idx] = { sx: 0, sy: 0, n: 0, members: [] };
    acc[idx].sx += node.x; acc[idx].sy += node.y; acc[idx].n += 1;
    acc[idx].members.push(node);
  }
  return Object.entries(acc)
    .filter(([, v]) => v.n >= 3) // skip tiny clusters
    .map(([idx, v]) => ({ idx: Number(idx), x: v.sx / v.n, y: v.sy / v.n, n: v.n, members: v.members }));
}

function nodeRadius(n) {
  return 3.5 + Math.sqrt(n.inlinks || 0) * 2.2;
}

/* Project a 3D world point into 2D screen space (relative to the canvas's
   transform). Returns {sx, sy, scale, depth}. The canvas is already
   translated by pan & scaled by zoom, so the returned (sx,sy) are in
   pre-pan/zoom world coords — render3D applies pan/zoom outside. */
function project3D(x, y, z, rotX, rotY) {
  const cy = Math.cos(rotY), sy = Math.sin(rotY);
  // Yaw around the y-axis: (x, z) → (x', z')
  const x1 = x * cy - z * sy;
  const z1 = x * sy + z * cy;
  // Pitch around the x-axis: (y, z') → (y', z'')
  const cx = Math.cos(rotX), sx = Math.sin(rotX);
  const y2 = y * cx - z1 * sx;
  const z2 = y * sx + z1 * cx;
  // Perspective: a focal length of 800 gives a soft 3D feel — points near
  // the camera grow, points behind shrink. Values < -700 are clamped to
  // avoid the projection blowing up.
  const FOC = 800;
  const eyeZ = z2 + 600; // push the cloud away from the camera
  const persp = FOC / Math.max(60, eyeZ);
  return { sx: x1 * persp, sy: y2 * persp, scale: persp, depth: z2 };
}

/* Edge-type rendering palette. Keys must match the `type` field that
   serve.py's _classify_edge produces. Each entry: { color, dash, widthMul }.
   `widthMul` multiplies the base lineWidth (1/zoom). Dash is an array of
   user-space (pre-zoom) lengths or null for solid.

   The grouping is roughly:
     - structural: child_of/parent_of (blue), supersedes (orange-dashed)
     - epistemic: cites (amber), supports (green), contradicts (red-dashed)
     - workflow:  blocks (red), depends_on (violet-dashed), implements (teal)
     - agent:     assigned_to, created_by, edited_by, reviewed_by (cyan)
     - signal:    has_risk (red-dotted), has_task (cyan-dashed), decided (gold)
     - soft:      related_to, notes, mentions (default color, lower weight)
   The default case (`links_to` and unknown types) falls through to the
   theme's edgeColor so nothing regresses visually. */
const EDGE_TYPE_STYLE = {
  links_to:      { color: null,                      dash: null,    widthMul: 1.0 },
  cites:         { color: 'rgba(207, 154, 71, 0.95)',dash: null,    widthMul: 1.4 },
  related_to:    { color: null,                      dash: [3, 4],  widthMul: 0.95, alphaMul: 0.85 },
  child_of:      { color: 'rgba(102, 145, 209, 0.95)',dash: null,   widthMul: 1.5 },
  parent_of:     { color: 'rgba(102, 145, 209, 0.95)',dash: null,   widthMul: 1.5 },
  implements:    { color: 'rgba(110, 178, 168, 0.95)',dash: null,   widthMul: 1.4 },
  implemented_by:{ color: 'rgba(110, 178, 168, 0.95)',dash: null,   widthMul: 1.4 },
  supports:      { color: 'rgba(120, 178, 95, 0.95)',dash: null,    widthMul: 1.4 },
  contradicts:   { color: 'rgba(217, 87, 87, 0.95)', dash: [6, 4],  widthMul: 1.6 },
  derived_from:  { color: 'rgba(170, 122, 196, 0.95)',dash: null,   widthMul: 1.3 },
  supersedes:    { color: 'rgba(232, 145, 80, 0.95)',dash: [8, 4],  widthMul: 1.5 },
  superseded_by: { color: 'rgba(232, 145, 80, 0.6)', dash: [4, 6],  widthMul: 1.0 },
  blocks:        { color: 'rgba(217, 87, 87, 0.95)', dash: null,    widthMul: 1.5 },
  blocked_by:    { color: 'rgba(217, 87, 87, 0.7)',  dash: [3, 3],  widthMul: 1.2 },
  depends_on:    { color: 'rgba(155, 124, 199, 0.9)',dash: [5, 4],  widthMul: 1.2 },
  has_risk:      { color: 'rgba(217, 87, 87, 0.85)', dash: [1.5, 2.5], widthMul: 1.2 },
  decided:       { color: 'rgba(220, 178, 89, 0.95)',dash: null,    widthMul: 1.6 },
  has_task:      { color: 'rgba(110, 178, 200, 0.9)',dash: [4, 4],  widthMul: 1.1 },
  has_proposal:  { color: 'rgba(155, 178, 195, 0.9)',dash: [4, 4],  widthMul: 1.1 },
  created_by:    { color: 'rgba(125, 181, 181, 0.9)',dash: null,    widthMul: 1.2 },
  edited_by:     { color: 'rgba(125, 181, 181, 0.7)',dash: [2, 4],  widthMul: 1.0 },
  assigned_to:   { color: 'rgba(125, 181, 181, 0.95)',dash: null,   widthMul: 1.4 },
  reviewed_by:   { color: 'rgba(125, 181, 181, 0.85)',dash: [3, 3], widthMul: 1.1 },
  notes:         { color: null,                      dash: null,    widthMul: 0.85, alphaMul: 0.7 },
  mentions:      { color: null,                      dash: [2, 5],  widthMul: 0.85, alphaMul: 0.65 },
  exemplifies:   { color: 'rgba(120, 178, 95, 0.85)',dash: [4, 3],  widthMul: 1.1 },
  questions:     { color: 'rgba(220, 178, 89, 0.9)', dash: [3, 6],  widthMul: 1.1 },
  // HQ-state edges (task/mission/receipt → vault notes & agents)
  references:    { color: null,                      dash: [2, 3],  widthMul: 0.95, alphaMul: 0.85 },
  produces:      { color: 'rgba(86, 168, 124, 0.95)',dash: null,    widthMul: 1.5 },
  modified:      { color: 'rgba(168, 124, 86, 0.85)',dash: [3, 3],  widthMul: 1.1 },
  targets:       { color: 'rgba(110, 178, 200, 0.9)',dash: [5, 4],  widthMul: 1.2 },
  runs_as:       { color: 'rgba(125, 181, 181, 1.0)',dash: null,    widthMul: 1.6 },
  // Message-thread edges (agent ↔ thread)
  sent_to:       { color: 'rgba(155, 124, 199, 0.95)',dash: null,   widthMul: 1.4 },
  received:      { color: 'rgba(155, 124, 199, 0.7)',dash: [4, 3],  widthMul: 1.2 },
  // Org-chart: assistant → senior. Solid teal, slightly heavier so the
  // hierarchy stands out among the noisier message/thread edges.
  reports_to:    { color: 'rgba(86, 138, 178, 1.0)',  dash: null,   widthMul: 1.7 },
};

/* Group edges by render style and stroke each group in one batched path.
   Falls back to a single batched pass with `defaultColor` when colored-edges
   is disabled (or when state.colorEdgesByType is false). `getXY` returns
   [x,y] for a node id — lets the same helper work for 2D and 3D. */
function _drawEdgesByType(ctx, edges, getXY, opts) {
  const {
    defaultColor, baseAlpha, baseLineWidth,
    enabled, hidden, focusId, byId, focusedSkip,
  } = opts;
  // Bucket edges by style key. Default bucket = no special styling.
  const buckets = new Map();
  const fallback = { type: '__default__', style: { color: null, dash: null, widthMul: 1.0 }};
  for (const e of edges) {
    const aId = e.source.id || e.source;
    const bId = e.target.id || e.target;
    const a = byId[aId]; const b = byId[bId];
    if (!a || !b) continue;
    if (hidden && (hidden.has(aId) || hidden.has(bId))) continue;
    if (focusedSkip && focusId && (aId === focusId || bId === focusId)) continue;
    let key = '__default__';
    if (enabled) {
      const t = e.type;
      if (t && EDGE_TYPE_STYLE[t]) key = t;
    }
    let bucket = buckets.get(key);
    if (!bucket) {
      const style = key === '__default__' ? fallback.style : EDGE_TYPE_STYLE[key];
      bucket = { style, segs: [] };
      buckets.set(key, bucket);
    }
    bucket.segs.push([a, b, e.confidence == null ? 1 : e.confidence]);
  }
  // Render each bucket. Heaviest/most-styled last so they sit on top.
  const order = ['__default__','notes','mentions','related_to','links_to'];
  const ordered = [];
  for (const k of order) if (buckets.has(k)) ordered.push(k);
  for (const k of buckets.keys()) if (!ordered.includes(k)) ordered.push(k);
  for (const k of ordered) {
    const { style, segs } = buckets.get(k);
    if (!segs.length) continue;
    ctx.strokeStyle = style.color || defaultColor;
    ctx.lineWidth = baseLineWidth * (style.widthMul || 1);
    const alpha = baseAlpha * (style.alphaMul == null ? 1 : style.alphaMul);
    ctx.globalAlpha = alpha;
    if (style.dash) ctx.setLineDash(style.dash.map(v => v * baseLineWidth));
    else ctx.setLineDash([]);
    ctx.beginPath();
    for (const [a, b] of segs) {
      const A = getXY(a); const B = getXY(b);
      ctx.moveTo(A[0], A[1]); ctx.lineTo(B[0], B[1]);
    }
    ctx.stroke();
  }
  ctx.setLineDash([]);
  ctx.globalAlpha = 1;
}

/* 3D-mode render. Sibling to render(); same overlays apply but nodes/edges
   are drawn with perspective and back-to-front depth sorting. */
function render3D(canvas, state, hover, selected) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const { width, height } = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);
  }

  const style = getComputedStyle(canvas);
  const isDark = document.body.classList.contains('night');
  const edgeColor = isDark
    ? (style.getPropertyValue('--ink-3').trim() || '#a898be')
    : (style.getPropertyValue('--rule').trim() || '#cdbfa5');
  const labelColor = (style.getPropertyValue('--ink').trim() || '#3b2e2a');
  const labelRgb = hexToRgb(labelColor) || { r: 59, g: 46, b: 42 };
  const baseEdgeAlpha = isDark ? 0.55 : 0.40;
  const dimEdgeAlpha  = isDark ? 0.20 : 0.15;

  const { nodes, edges, pan, zoom } = state;
  const rotX = state.rot3D ? state.rot3D.rotX : 0;
  const rotY = state.rot3D ? state.rot3D.rotY : 0;
  const focusId  = selected || hover;
  const neighbors = getNeighbors(state, focusId);
  const focused = !!focusId;
  const filter = state.filter || '';
  const hidden = state.hiddenIds || new Set();

  ctx.clearRect(0, 0, width, height);
  ctx.save();
  ctx.translate(pan.x, pan.y);
  ctx.scale(zoom, zoom);

  // Project every visible node once and cache on the node so getNodeAt can read.
  const visList = [];
  for (const n of nodes) {
    if (hidden.has(n.id)) continue;
    if (state.timeScrub && n.mtime && n.mtime > state.timeScrub) continue;
    const p = project3D(n.x, n.y, n.z || 0, rotX, rotY);
    n._sx = p.sx; n._sy = p.sy; n._scale = p.scale; n._depth = p.depth;
    visList.push(n);
  }
  // Sort back-to-front so far edges/nodes render under near ones.
  visList.sort((a, b) => b._depth - a._depth);
  // Also build a lookup for edge endpoints.
  const projById = {};
  for (const n of visList) projById[n.id] = n;

  // ---- Edges (base + highlighted pass) ---------------------------------
  // 3D variant uses projected screen coords (_sx, _sy) instead of raw x,y;
  // hidden + focused-skip semantics are identical to the 2D path.
  const get3D = (n) => [n._sx, n._sy];
  _drawEdgesByType(ctx, edges, get3D, {
    defaultColor: edgeColor,
    baseAlpha: focused ? dimEdgeAlpha : baseEdgeAlpha,
    baseLineWidth: 1 / zoom,
    enabled: !!(state.settings && state.settings.colorEdgesByType),
    hidden,
    focusId,
    byId: projById,
    focusedSkip: focused,
  });
  ctx.lineWidth = 1 / zoom;
  ctx.globalAlpha = 1;
  if (focused) {
    ctx.strokeStyle = 'rgba(232, 169, 169, 0.9)';
    ctx.lineWidth = 1.6 / zoom;
    ctx.globalAlpha = 1;
    ctx.beginPath();
    for (const e of edges) {
      const a = projById[e.source.id || e.source];
      const b = projById[e.target.id || e.target];
      if (!a || !b) continue;
      if (!(a.id === focusId || b.id === focusId)) continue;
      ctx.moveTo(a._sx, a._sy);
      ctx.lineTo(b._sx, b._sy);
    }
    ctx.stroke();
  }

  // Ghost edges in 3D too.
  if (state.ghostEdges && state.ghostEdges.length) {
    ctx.save();
    ctx.setLineDash([4 / zoom, 4 / zoom]);
    ctx.lineWidth = 0.9 / zoom;
    for (const ge of state.ghostEdges) {
      const a = projById[ge.a]; const b = projById[ge.b];
      if (!a || !b) continue;
      ctx.globalAlpha = Math.min(0.5, ge.score * 0.9);
      ctx.strokeStyle = isDark ? 'rgba(201, 184, 224, 1)' : 'rgba(125, 181, 181, 1)';
      ctx.beginPath();
      ctx.moveTo(a._sx, a._sy);
      ctx.lineTo(b._sx, b._sy);
      ctx.stroke();
    }
    ctx.restore();
  }

  // Shortest-path emphasis edges.
  if (state.shortestPath && state.shortestPath.edges) {
    ctx.strokeStyle = 'rgba(240, 198, 116, 0.95)';
    ctx.lineWidth = 2.4 / zoom;
    ctx.globalAlpha = 1;
    ctx.beginPath();
    for (const e of edges) {
      const a = projById[e.source.id || e.source];
      const b = projById[e.target.id || e.target];
      if (!a || !b) continue;
      const key = a.id < b.id ? a.id + '\0' + b.id : b.id + '\0' + a.id;
      if (state.shortestPath.edges.has(key)) {
        ctx.moveTo(a._sx, a._sy);
        ctx.lineTo(b._sx, b._sy);
      }
    }
    ctx.stroke();
  }

  // ---- Nodes (depth-sorted back to front) -----------------------------
  for (const n of visList) {
    const inlinks = n.inlinks || 0;
    const r0 = nodeRadius(n);
    const r = r0 * n._scale; // perspective scaling
    const isFocus    = selected === n.id || hover === n.id;
    const isNeighbor = neighbors && neighbors.has(n.id);
    const visible    = nodeIsVisible(n, state);
    const inCompare  = state.compare ? (state.compare.a.has(n.id) || state.compare.b.has(n.id)) : true;
    const dim        = (focused && !isNeighbor) || !visible || (state.compare && !inCompare);

    // Glow halo for focus + neighbours.
    if (isFocus || (focused && isNeighbor)) {
      const g = ctx.createRadialGradient(n._sx, n._sy, 0, n._sx, n._sy, r * 4);
      const col = isFocus ? '232, 169, 169' : '201, 184, 224';
      g.addColorStop(0, `rgba(${col}, ${isFocus ? 0.55 : 0.35})`);
      g.addColorStop(1, `rgba(${col}, 0)`);
      ctx.fillStyle = g;
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(n._sx, n._sy, r * 4, 0, Math.PI * 2);
      ctx.fill();
    }

    // Color resolution (mirrors 2D path).
    const modeFill = colorForNode(n, state, isDark, style);
    let compareFill = null;
    if (state.compare) {
      const inA = state.compare.a.has(n.id), inB = state.compare.b.has(n.id);
      if (inA && inB) compareFill = '#f0c674';
      else if (inA)   compareFill = '#7db5b5';
      else if (inB)   compareFill = '#e8a9a9';
    }
    let fill;
    if (selected === n.id)              fill = '#e8a9a9';
    else if (state.activePath === n.id) fill = '#f0c674';
    else if (hover === n.id)            fill = '#c9b8e0';
    else if (compareFill)               fill = compareFill;
    else if (modeFill)                  fill = modeFill;
    else if (inlinks >= 6)              fill = '#7db5b5';
    else if (inlinks >= 1)              fill = '#bfa9d9';
    else                                fill = '#d8c9a8';

    ctx.globalAlpha = dim ? 0.18 : 1;
    ctx.beginPath();
    ctx.arc(n._sx, n._sy, r, 0, Math.PI * 2);
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = 'rgba(59, 46, 42, 0.45)';
    ctx.lineWidth = 1 / zoom;
    ctx.stroke();

    // Multi-select ring.
    if (state.selectedSet && state.selectedSet.has(n.id)) {
      ctx.strokeStyle = 'rgba(125, 181, 181, 0.95)';
      ctx.lineWidth = 2 / zoom;
      ctx.beginPath();
      ctx.arc(n._sx, n._sy, r + 5 / zoom, 0, Math.PI * 2);
      ctx.stroke();
    }
    // Agent activity halo.
    if (state.agentActivity && state.agentActivity.has(n.id)) {
      const act = state.agentActivity.get(n.id);
      const phase = ((Date.now() - (act.until - 5000)) % 1500) / 1500;
      const ringR = r + (4 + phase * 10) / zoom;
      ctx.save();
      ctx.globalAlpha = 0.55 * (1 - phase);
      ctx.strokeStyle = act.color || '#7db5b5';
      ctx.lineWidth = 2 / zoom;
      ctx.beginPath();
      ctx.arc(n._sx, n._sy, ringR, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }
    // Orphan ring.
    if (state.highlightOrphans) {
      const isOrphan  = (n.inlinks  || 0) === 0;
      const isDeadEnd = (n.outlinks || 0) === 0;
      if (isOrphan || isDeadEnd) {
        ctx.save();
        ctx.setLineDash([3 / zoom, 3 / zoom]);
        ctx.strokeStyle = isOrphan && isDeadEnd
          ? 'rgba(220, 90, 90, 0.85)'
          : isOrphan ? 'rgba(220, 130, 90, 0.75)' : 'rgba(220, 180, 80, 0.65)';
        ctx.lineWidth = 1.4 / zoom;
        ctx.beginPath();
        ctx.arc(n._sx, n._sy, r + 4 / zoom, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }
    }
  }

  // Pulses (interpolate along projected positions).
  if (state.pulses.size > 0) {
    const now = Date.now();
    ctx.fillStyle = 'rgba(232, 169, 169, 0.95)';
    ctx.globalAlpha = 1;
    for (const [key, p] of state.pulses.entries()) {
      const elapsed = (now - p.start) / 1000;
      if (elapsed > 1.2) { state.pulses.delete(key); continue; }
      const a = projById[p.edge.source.id || p.edge.source];
      const b = projById[p.edge.target.id || p.edge.target];
      if (!a || !b) continue;
      const t = elapsed / 1.2;
      const x = a._sx + (b._sx - a._sx) * t;
      const y = a._sy + (b._sy - a._sy) * t;
      ctx.beginPath();
      ctx.arc(x, y, 2.6 / zoom, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // Labels (hover + selected always; others honour showAllLabels / zoom).
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  const drawLabel = (n, alpha) => {
    const r = nodeRadius(n) * n._scale;
    const fontPx = (11 * n._scale) / zoom;
    ctx.font = `${Math.max(8, fontPx)}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
    ctx.globalAlpha = alpha;
    ctx.fillStyle = `rgba(${labelRgb.r}, ${labelRgb.g}, ${labelRgb.b}, 0.92)`;
    ctx.fillText(n.title || n.id, n._sx, n._sy + r + (4 / zoom));
  };
  if (state.showAllLabels) {
    for (const n of visList) drawLabel(n, 0.85);
  } else if (zoom > 1.4) {
    const a = Math.min(1, (zoom - 1.4) / 0.5);
    for (const n of visList) {
      if (focused && !neighbors.has(n.id)) continue;
      drawLabel(n, a);
    }
  } else if (focused && neighbors) {
    for (const id of neighbors) {
      const n = projById[id];
      if (n) drawLabel(n, n.id === selected || n.id === hover ? 1 : 0.7);
    }
  }
  if (hover && projById[hover]) drawLabel(projById[hover], 1);

  ctx.restore();

  // ---- Screen-space overlays (lasso, link drag) -----------------------
  if (state.lassoRect) {
    const r = state.lassoRect;
    const x = Math.min(r.x0, r.x1), y = Math.min(r.y0, r.y1);
    const w = Math.abs(r.x1 - r.x0), h = Math.abs(r.y1 - r.y0);
    ctx.save();
    ctx.fillStyle = 'rgba(125, 181, 181, 0.12)';
    ctx.strokeStyle = 'rgba(125, 181, 181, 0.85)';
    ctx.lineWidth = 1.2;
    ctx.setLineDash([4, 4]);
    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);
    ctx.restore();
  }
  if (state.linkDrag) {
    const ld = state.linkDrag;
    const fromNode = state.byId[ld.fromId];
    if (fromNode && fromNode._sx != null) {
      const sx = state.pan.x + fromNode._sx * state.zoom;
      const sy = state.pan.y + fromNode._sy * state.zoom;
      ctx.save();
      ctx.strokeStyle = 'rgba(232, 169, 169, 0.9)';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(sx, sy);
      ctx.lineTo(ld.endX, ld.endY);
      ctx.stroke();
      ctx.restore();
    }
  }

  // 3D camera indicator (small axes gizmo bottom-left).
  ctx.save();
  ctx.translate(36, height - 36);
  const drawAxis = (vec3, color, label) => {
    const p = project3D(vec3[0], vec3[1], vec3[2], rotX, rotY);
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(p.sx, p.sy);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(p.sx, p.sy, 2.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.font = '700 9px sans-serif';
    ctx.fillText(label, p.sx + 4, p.sy + 3);
  };
  drawAxis([22, 0, 0], '#e84d4d', 'X');
  drawAxis([0, 22, 0], '#5a9a5a', 'Y');
  drawAxis([0, 0, 22], '#5a8acf', 'Z');
  ctx.restore();
}

function render(canvas, state, hover, selected) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const { width, height } = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
    canvas.width  = width  * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);
  }

  // Theme-aware colours from CSS variables.
  // In night mode --rule is too dim against the dark paper, so use --ink-3
  // (which is tuned brighter) and bump alpha for connections.
  const style = getComputedStyle(canvas);
  const isDark = document.body.classList.contains('night');
  const edgeColor = isDark
    ? (style.getPropertyValue('--ink-3').trim() || '#a898be')
    : (style.getPropertyValue('--rule').trim() || '#cdbfa5');
  const labelColor = (style.getPropertyValue('--ink').trim() || '#3b2e2a');
  const labelRgb = hexToRgb(labelColor) || { r: 59, g: 46, b: 42 };
  const baseEdgeAlpha = isDark ? 0.7 : 0.45;
  const dimEdgeAlpha  = isDark ? 0.30 : 0.18;

  const { nodes, edges, pan, zoom } = state;
  const focusId  = selected || hover;
  const neighbors = getNeighbors(state, focusId);
  const filter = state.filter || '';
  const focused = !!focusId;

  ctx.clearRect(0, 0, width, height);
  ctx.save();
  ctx.translate(pan.x, pan.y);
  ctx.scale(zoom, zoom);

  // -------- Edges -------------------------------------------------------
  // Two passes: dim edges first, highlighted edges on top.
  // Pass 1 = bulk base edges, grouped by edge.type when colorEdgesByType is on
  // (off by default for backwards-compat — toggled in settings panel).
  const hidden = state.hiddenIds || new Set();
  const get2D = (n) => [n.x, n.y];
  _drawEdgesByType(ctx, edges, get2D, {
    defaultColor: edgeColor,
    baseAlpha: focused ? dimEdgeAlpha : baseEdgeAlpha,
    baseLineWidth: 1 / zoom,
    enabled: !!(state.settings && state.settings.colorEdgesByType),
    hidden,
    focusId,
    byId: state.byId,
    focusedSkip: focused, // skip focused edges here, redrawn in pass 2
  });
  ctx.lineWidth = 1 / zoom;
  ctx.globalAlpha = 1;

  // Pass 2 — highlighted edges (connected to focus)
  if (focused) {
    ctx.strokeStyle = 'rgba(232, 169, 169, 0.85)';
    ctx.lineWidth = 1.6 / zoom;
    ctx.globalAlpha = 1;
    ctx.beginPath();
    for (const e of edges) {
      const a = state.byId[e.source.id || e.source];
      const b = state.byId[e.target.id || e.target];
      if (!a || !b) continue;
      if (hidden.has(a.id) || hidden.has(b.id)) continue;
      if (!(a.id === focusId || b.id === focusId)) continue;
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
    }
    ctx.stroke();
    ctx.lineWidth = 1 / zoom;
  }

  // Ghost edges — dashed lines for high-similarity unlinked pairs.
  if (state.ghostEdges && state.ghostEdges.length) {
    ctx.save();
    ctx.setLineDash([4 / zoom, 4 / zoom]);
    ctx.lineWidth = 0.9 / zoom;
    for (const ge of state.ghostEdges) {
      const a = state.byId[ge.a]; const b = state.byId[ge.b];
      if (!a || !b) continue;
      if (state.hiddenIds && (state.hiddenIds.has(a.id) || state.hiddenIds.has(b.id))) continue;
      // Strength → opacity; cap at 0.5 so they always feel "ambient."
      ctx.globalAlpha = Math.min(0.5, ge.score * 0.9);
      ctx.strokeStyle = isDark ? 'rgba(201, 184, 224, 1)' : 'rgba(125, 181, 181, 1)';
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    ctx.restore();
  }

  // Pass 3 — shortest-path edges (thick, rose-gold) — only consecutive pairs.
  if (state.shortestPath && state.shortestPath.edges && state.shortestPath.edges.size > 0) {
    ctx.strokeStyle = 'rgba(240, 198, 116, 0.95)';
    ctx.lineWidth = 2.4 / zoom;
    ctx.globalAlpha = 1;
    ctx.beginPath();
    for (const e of edges) {
      const a = state.byId[e.source.id || e.source];
      const b = state.byId[e.target.id || e.target];
      if (!a || !b) continue;
      const key = a.id < b.id ? a.id + '\0' + b.id : b.id + '\0' + a.id;
      if (state.shortestPath.edges.has(key)) {
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
      }
    }
    ctx.stroke();
    ctx.lineWidth = 1 / zoom;
  }

  // -------- Pulses (animated dots travelling along edges) ---------------
  if (state.pulses.size > 0) {
    const now = Date.now();
    ctx.fillStyle = 'rgba(232, 169, 169, 0.95)';
    ctx.globalAlpha = 1;
    for (const [key, p] of state.pulses.entries()) {
      const elapsed = (now - p.start) / 1000;
      if (elapsed > 1.2) { state.pulses.delete(key); continue; }
      const a = state.byId[p.edge.source.id || p.edge.source];
      const b = state.byId[p.edge.target.id || p.edge.target];
      if (!a || !b) continue;
      const t = elapsed / 1.2;
      const x = a.x + (b.x - a.x) * t;
      const y = a.y + (b.y - a.y) * t;
      ctx.beginPath();
      ctx.arc(x, y, 2.6 / zoom, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // -------- Nodes (with soft glow for selected + neighbours) ------------
  for (const n of nodes) {
    if (state.hiddenIds && state.hiddenIds.has(n.id)) continue; // truly hidden
    const inlinks = n.inlinks || 0;
    const r = nodeRadius(n);
    const isFocus    = selected === n.id || hover === n.id;
    const isNeighbor = neighbors && neighbors.has(n.id);
    const visible    = nodeIsVisible(n, state);
    const inCompare  = state.compare ? (state.compare.a.has(n.id) || state.compare.b.has(n.id)) : true;
    const dim        = (focused && !isNeighbor) || !visible || (state.compare && !inCompare);

    // Soft glow underlay for the focused node and its neighbours.
    if (isFocus || (focused && isNeighbor)) {
      const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, r * 4);
      const col = isFocus ? '232, 169, 169' : '201, 184, 224';
      g.addColorStop(0, `rgba(${col}, ${isFocus ? 0.55 : 0.35})`);
      g.addColorStop(1, `rgba(${col}, 0)`);
      ctx.fillStyle = g;
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(n.x, n.y, r * 4, 0, Math.PI * 2);
      ctx.fill();
    }

    // Color resolution (selected/active/hover always win, then color-by-mode,
    // then inlink-based fallback shade).
    const modeFill = colorForNode(n, state, isDark, style);
    let fill;
    // Compare-mode wins over coloring schemes — left side teal, right side rose,
    // shared nodes gold, all others dim.
    let compareFill = null;
    let compareDim  = false;
    if (state.compare) {
      const inA = state.compare.a.has(n.id);
      const inB = state.compare.b.has(n.id);
      if (inA && inB)         compareFill = '#f0c674';
      else if (inA)           compareFill = '#7db5b5';
      else if (inB)           compareFill = '#e8a9a9';
      else                    compareDim  = true;
    }
    if (selected === n.id)              fill = '#e8a9a9';
    else if (state.activePath === n.id) fill = '#f0c674';
    else if (hover === n.id)            fill = '#c9b8e0';
    else if (compareFill)               fill = compareFill;
    else if (modeFill)                  fill = modeFill;
    else if (inlinks >= 6)              fill = '#7db5b5';
    else if (inlinks >= 1)              fill = '#bfa9d9';
    else                                fill = '#d8c9a8';

    ctx.globalAlpha = dim ? 0.18 : 1;
    ctx.beginPath();
    ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = 'rgba(59, 46, 42, 0.45)';
    ctx.lineWidth = 1 / zoom;
    ctx.stroke();

    // Orphan / dead-end ring (notes with no incoming or no outgoing links).
    if (state.highlightOrphans) {
      const isOrphan  = (n.inlinks  || 0) === 0;
      const isDeadEnd = (n.outlinks || 0) === 0;
      if (isOrphan || isDeadEnd) {
        ctx.save();
        ctx.setLineDash([3 / zoom, 3 / zoom]);
        ctx.strokeStyle = isOrphan && isDeadEnd
          ? 'rgba(220, 90, 90, 0.85)'
          : isOrphan ? 'rgba(220, 130, 90, 0.75)' : 'rgba(220, 180, 80, 0.65)';
        ctx.lineWidth = 1.4 / zoom;
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 4 / zoom, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }
    }

    // Multi-select ring (lasso pick).
    if (state.selectedSet && state.selectedSet.has(n.id)) {
      ctx.save();
      ctx.strokeStyle = 'rgba(125, 181, 181, 0.95)';
      ctx.lineWidth = 2 / zoom;
      ctx.beginPath();
      ctx.arc(n.x, n.y, r + 5 / zoom, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    // Live agent activity halo — pulse a ring at the agent's color when the
    // agent is currently reading/writing this note.
    if (state.agentActivity && state.agentActivity.has(n.id)) {
      const act = state.agentActivity.get(n.id);
      const phase = ((Date.now() - (act.until - 5000)) % 1500) / 1500;
      const ringR = r + (4 + phase * 10) / zoom;
      ctx.save();
      ctx.globalAlpha = 0.55 * (1 - phase);
      ctx.strokeStyle = act.color || '#7db5b5';
      ctx.lineWidth = 2 / zoom;
      ctx.beginPath();
      ctx.arc(n.x, n.y, ringR, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    // Shortest-path glow.
    if (state.shortestPath && state.shortestPath.nodes && state.shortestPath.nodes.has(n.id)) {
      ctx.save();
      const grd = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, r * 4);
      grd.addColorStop(0, 'rgba(240, 198, 116, 0.7)');
      grd.addColorStop(1, 'rgba(240, 198, 116, 0)');
      ctx.globalAlpha = 1;
      ctx.fillStyle = grd;
      ctx.beginPath();
      ctx.arc(n.x, n.y, r * 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }

  // -------- Labels ------------------------------------------------------
  // Always draw the hovered label. Otherwise draw zoomed-in labels or all-on.
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';

  const drawLabel = (n, alpha) => {
    const r = nodeRadius(n);
    const fontPx = 11 / zoom;
    ctx.font = `${fontPx}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
    ctx.globalAlpha = alpha;
    ctx.fillStyle = `rgba(${labelRgb.r}, ${labelRgb.g}, ${labelRgb.b}, 0.92)`;
    ctx.fillText(n.title || n.id, n.x, n.y + r + (4 / zoom));
  };

  if (state.showAllLabels) {
    for (const n of nodes) {
      if (!nodeIsVisible(n, state)) continue;
      drawLabel(n, 0.85);
    }
  } else if (zoom > 1.4) {
    const a = Math.min(1, (zoom - 1.4) / 0.5);
    for (const n of nodes) {
      if (!nodeIsVisible(n, state)) continue;
      if (focused && !neighbors.has(n.id)) continue;
      drawLabel(n, a);
    }
  } else if (focused && neighbors) {
    // Show labels for the focused node + neighbours
    for (const id of neighbors) {
      const n = state.byId[id];
      if (n) drawLabel(n, n.id === selected || n.id === hover ? 1 : 0.7);
    }
  }

  // Hover label is always rendered prominently.
  if (hover && state.byId[hover]) {
    drawLabel(state.byId[hover], 1);
  }

  // -------- Cluster labels (overlay text at cluster centroids) ----------
  if (state.clusterColoring && state.clusters && state.clusterLabels) {
    const centroids = clusterCentroids(state);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (const c of centroids) {
      const label = state.clusterLabels[c.idx];
      if (!label) continue;
      const fontPx = Math.max(14, Math.min(28, 10 + Math.sqrt(c.n) * 2)) / zoom;
      ctx.font = `700 ${fontPx}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
      // Pillow background
      const metrics = ctx.measureText(label);
      const w = metrics.width + 16 / zoom;
      const h = fontPx + 8 / zoom;
      ctx.globalAlpha = 0.85;
      ctx.fillStyle = `rgba(${labelRgb.r}, ${labelRgb.g}, ${labelRgb.b}, 0.10)`;
      ctx.beginPath();
      const rad = 4 / zoom;
      ctx.roundRect ? ctx.roundRect(c.x - w/2, c.y - h/2, w, h, rad) : ctx.rect(c.x - w/2, c.y - h/2, w, h);
      ctx.fill();
      ctx.globalAlpha = 0.92;
      ctx.fillStyle = `rgba(${labelRgb.r}, ${labelRgb.g}, ${labelRgb.b}, 0.92)`;
      ctx.fillText(label, c.x, c.y);
    }
  }

  ctx.restore();

  // -------- Screen-space overlays: lasso rect + link-drag rubber band ---
  // (Drawn after restore so they're in unscaled screen coords.)
  if (state.lassoRect) {
    const r = state.lassoRect;
    const x = Math.min(r.x0, r.x1), y = Math.min(r.y0, r.y1);
    const w = Math.abs(r.x1 - r.x0), h = Math.abs(r.y1 - r.y0);
    ctx.save();
    ctx.fillStyle = 'rgba(125, 181, 181, 0.12)';
    ctx.strokeStyle = 'rgba(125, 181, 181, 0.85)';
    ctx.lineWidth = 1.2;
    ctx.setLineDash([4, 4]);
    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);
    ctx.restore();
  }
  if (state.linkDrag) {
    const ld = state.linkDrag;
    const fromNode = state.byId[ld.fromId];
    if (fromNode) {
      const sx = state.pan.x + fromNode.x * state.zoom;
      const sy = state.pan.y + fromNode.y * state.zoom;
      ctx.save();
      ctx.strokeStyle = 'rgba(232, 169, 169, 0.9)';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(sx, sy);
      ctx.lineTo(ld.endX, ld.endY);
      ctx.stroke();
      ctx.fillStyle = 'rgba(232, 169, 169, 1)';
      ctx.beginPath();
      ctx.arc(ld.endX, ld.endY, 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }
}


/* ================================================================
   Missing components — reconstructed after external file corruption
   ================================================================ */

/* ---------------- Custom Markdown renderer (no marked.js) ---------------- */

export { GraphView, simulate };
