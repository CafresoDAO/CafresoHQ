import { CafresoHQClient } from '../claude-client.jsx';
import { hexToRgb } from './core.jsx';
import { officeCause } from '../app/floor.jsx';
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

/* Accent-folded copy of `s`: NFD-decompose each code point, drop the
   combining marks (U+0300-U+036F), lowercase. Same algorithm as
   serve.py's _fold_accents and views/vault.jsx's _foldAccents (module-
   local rather than imported — vault.jsx already imports FROM this
   file, so importing back would be circular), applied here so
   nodeMatchesFilter (the graph's own search/filter box) doesn't miss
   the accented notes the vault's two search paths already find:
   'unicas' has to find a node titled '...investigación...' or the
   graph quietly splits by keyboard layout, same as vault search used
   to before it was fixed. No index-map here — this filter only needs
   a match/no-match verdict, never a snippet back into the original
   text. */
const _foldAccents = (s) => String(s || '')
  .normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

/* The engine's own filter is a raw substring `includes` over the whole
   query string — but the filter box right above it advertises the legacy
   renderer's grammar ("tag:x  type:y  -term", plus OR / orphan / stale and
   the accent folding directly above). Typing the placeholder's own example
   into the WebGL view therefore blanked the graph: "tag:project" was
   searched as the literal text "tag:project", "-daily" hid everything
   instead of excluding, and "planning meeting" missed a note titled
   "meeting planning". One matcher already speaks that grammar —
   nodeMatchesFilter below — so wrap it as the predicate the engine's
   setFilter now accepts, rather than teaching graph-engine.js a second
   copy of the syntax. Empty text returns '' so the engine clears cleanly. */
const filterMatcher = (text) => (text ? (n) => nodeMatchesFilter(n, text) : '');

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
   window.CafresoGraphEngine). Replaced the legacy Canvas-2D renderer; its
   force simulation and path helpers came out in #425 once nothing called them.
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
  /* The analytics panel's `top` used to be a hardcoded 50 — the height of
     the toolbar when it fits on ONE line. On a phone the toolbar wraps to
     three lines (~190px), and the panel painted straight through the
     wrapped controls (zIndex kept them clickable, not readable). Track the
     toolbar's real bottom edge instead of assuming its height. */
  const toolbarRef = React.useRef(null);
  const [panelTop, setPanelTop] = useSV(50);
  React.useEffect(() => {
    const el = toolbarRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const measure = () => setPanelTop(el.offsetTop + el.offsetHeight + 6);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const [ctxMenu, setCtxMenu] = useSV(null); // { id, x, y }
  const [shareUrl, setShareUrl] = useSV(null);
  const [sharing, setSharing] = useSV(false);
  const [shareCopied, setShareCopied] = useSV(false);
  const [shareError, setShareError] = useSV(null);
  /* The LOAD half of the same silence `shareError` was added for. The publish
     catch twelve lines below it stopped swallowing failure into console.warn;
     the catch that runs when the map itself cannot be built kept doing exactly
     that, in this same file. `loadError` is its twin, rendered by the same card
     shape, so a map that failed to build says so instead of showing a boss the
     empty box a brand-new office also shows. */
  const [loadError, setLoadError] = useSV(null);
  /* Bumped by the error card's "Try again", which is the whole reason the card
     is worth more than a line of text: the office coming back up is by far the
     commonest cure for this failure, and without this the only retry available
     was a full page reload. */
  const [reloadTick, setReloadTick] = useSV(0);
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
  /* #414 — the canvas is ONE slot and `mountData` DESTROYS whatever engine is
     on it before mounting the next, so "the map you are looking at" is decided
     by which `loadData` LANDS last, not by which rebuild was asked for last.
     Three things start a rebuild and none of them freeze the other two: the
     source/scope effect below, the ↻ Rebuild button, and
     `window.CafresoHQGraph.refresh()` — which views/vault.jsx:450 fires after
     EVERY note write and agent_runner.jsx fires from four places, none of them
     a DOM click, so no overlay is anywhere in their path. Same sequence-number
     shape as `openSeqRef` in views/projects.jsx (#409) and views/vault.jsx
     (#404): claimed before the first suspend, re-checked after it. */
  const mountSeqRef = React.useRef(0);

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
    if (filterRef.current) eng.setFilter(filterMatcher(filterRef.current));
    if (sourceRef.current === 'links' && activePathRef.current) {
      eng.setActivePath(activePathRef.current);
      if (localModeRef.current !== 'global') eng.setLocalMode(activePathRef.current, parseInt(localModeRef.current, 10));
    }
    return eng;
  };

  // Load + mount on first render and whenever the source/scope changes.
  React.useEffect(() => {
    let cancelled = false;
    /* Claimed before the first suspend. `cancelled` alone only covers ONE
       direction — this effect being torn down — and the race that was live
       runs the other way: a `refresh()` fired while this load is in flight
       lands first, mounts, and then THIS older load mounts on top of it.
       Measured pre-fix (#414). */
    const seq = ++mountSeqRef.current;
    setLoading(true);
    setLoadError(null);
    (async () => {
      try {
        const g = await loadData();
        if (cancelled || mountSeqRef.current !== seq || !containerRef.current) { setLoading(false); return; }
        const eng = mountData(g);
        setLoading(false);
        /* `mountData` returns null when `window.CafresoGraphEngine` is not
           there — the engine is a SEPARATE <script> (ui_manifest.py emits it
           only `if manifest.get('graphEngine')`), so a build that shipped
           without it, or a bundle that 404s, lands here having thrown
           nothing. The load "succeeded"; the map was never drawn. That is the
           one path in this component where everything reports success and the
           work did not happen, and it used to be a bare `return`. */
        if (!eng) { setLoadError('the graph engine did not load — reload the page, and if it keeps happening the office is serving an incomplete build'); return; }
        window.CafresoHQGraph = {
          _lastGraph: g,
          pulse: (id) => { try { engineRef.current && engineRef.current.focusNode(id); } catch (_) {} },
          refresh: async () => {
            /* #414 — claimed before the read, re-checked after it. Two
               refreshes in flight used to end on whichever `loadData` LANDED
               last: measured pre-fix through
               scripts/harness_await_tail_two.mjs, a boss who wrote note A and
               then note B was left looking at the library WITHOUT note B
               (`mountedAfterBoth: "/a.md"`, with only note A on it) — and `_lastGraph` was
               left
               holding that same stale shape, which is not a picture: it is
               what views/vault.jsx:1408 counts to tell the boss which notes
               will lose a link if they delete this one, so the delete confirm
               under-reported the damage — `deadLinksNamedByTheConfirm: []`
               where the live library had one, i.e. the plain "This cannot be
               undone" instead of the sentence that names the note about to
               lose its link. A rebuild started under the OLD
               source/scope also used to land on the NEW one, painting the
               wikilink graph onto a canvas whose toolbar said Concept map
               (`mountedSource: "links"` under `source: "concepts"`). */
            const seq2 = ++mountSeqRef.current;
            try {
              const g2 = await loadData();
              if (mountSeqRef.current !== seq2 || !containerRef.current) return;
              const e2 = mountData(g2);
              // The unmount effect below does `delete window.CafresoHQGraph`,
              // so a refresh still in flight when the panel closes must not
              // assume the API object is still there.
              const api = window.CafresoHQGraph;
              if (e2 && api) api._lastGraph = g2;
            } catch (e) {
              // A refusal belongs to the rebuild it came from — a superseded
              // one must not paint its card over the map that did mount.
              if (mountSeqRef.current !== seq2) return;
              /* A refresh is fired by views/vault.jsx after a note write. It
                 failing silently left the map showing a shape the library no
                 longer has, with nothing saying it was stale. */
              console.warn('graph refresh:', e);
              setLoadError(officeCause((e && e.message) || String(e)));
            }
          },
        };
      } catch (e) {
        console.warn('graph load:', e);
        setLoading(false);
        /* Same voice, same classifier and the same card as the publish
           failure below — the boss is told the map could not be built rather
           than being handed an empty canvas that reads as an empty library. */
        setLoadError(officeCause((e && e.message) || String(e)));
      }
    })();
    return () => { cancelled = true; };
  }, [source, scope, reloadTick]);

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
  React.useEffect(() => { const e = engineRef.current; if (e) e.setFilter(filterMatcher(filter)); }, [filter]);
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
    setShareError(null);
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
      if (!res.ok) {
        let msg = `HTTP ${res.status}`;
        try { const j = await res.json(); if (j && j.error) msg = j.error; } catch (_e) {}
        throw new Error(msg);
      }
      const j = await res.json();
      if (j && j.viewerUrl) {
        const full = (base || (typeof location !== 'undefined' ? location.origin : '')) + j.viewerUrl;
        setShareUrl(full);
        try { await navigator.clipboard.writeText(full); setShareCopied(true); }
        catch (_) { setShareCopied(false); }
        // Onboarding: mark "publish your first graph" complete.
        try { localStorage.setItem('cafresohq_hq_v1:publishedGraph', '1'); window.dispatchEvent(new CustomEvent('cafresohq:graph-published')); } catch (_) {}
      } else {
        throw new Error('the office did not hand back a link to share');
      }
    } catch (err) {
      console.warn('publish graph:', err);
      setShareError(officeCause((err && err.message) || String(err)));
    }
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
    React.createElement('div', { ref: toolbarRef, style: { position: 'absolute', top: 10, left: 10, right: 10, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', pointerEvents: 'none', zIndex: 2 } },
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
      onMinimize && React.createElement('button', { onClick: onMinimize, 'aria-label': 'Minimize graph', title: 'Minimize graph', style: { ...ctrlStyle, cursor: 'pointer', pointerEvents: 'auto' } }, '✕'),
    ),

    // Analytics side panel (InfraNodus-style).
    panelOpen && React.createElement('div', { style: { position: 'absolute', top: panelTop, right: 10, bottom: 10, width: 246, overflowY: 'auto', background: 'rgba(20,18,12,0.82)', backdropFilter: 'blur(6px)', border: '1px solid rgba(245,210,93,0.22)', borderRadius: 10, padding: '12px 13px', color: '#e9e2d4', font: '12px Inter, system-ui, sans-serif', zIndex: 1 } },
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
            React.createElement('div', { key: t.id, role: 'button', tabIndex: 0,
              onClick: () => { const e = engineRef.current; if (e) e.focusNode(t.id); },
              onKeyDown: (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); const e = engineRef.current; if (e) e.focusNode(t.id); } },
              title: 'Focus', style: { cursor: 'pointer', padding: '2px 0', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } },
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
    ctxMenu && React.createElement('div', { role: 'menu', 'aria-label': 'Node actions', style: { position: 'fixed', left: Math.min(ctxMenu.x, (typeof window !== 'undefined' ? window.innerWidth : 9999) - 170), top: ctxMenu.y, zIndex: 50, background: 'rgba(28,24,16,0.97)', border: '1px solid rgba(245,210,93,0.3)', borderRadius: 8, padding: 4, minWidth: 150, font: '12px Inter, sans-serif', color: '#e9e2d4' },
      onMouseLeave: () => setCtxMenu(null) },
      /* Only a node that IS a Library file gets the open item. The links
         graph draws office nodes too (task:, agent:, receipt: — path '')
         and offering "Open note" on one was a menu item that silently did
         nothing: the Library-side guard (openGraphNode) refuses ids its
         file list doesn't hold. The node record itself says which it is,
         and a filed deck opens as a file, not a "note". */
      [...(source === 'links' && (rawRef.current.byId[ctxMenu.id] || {}).path
          ? [[/\.(md|markdown)$/i.test(rawRef.current.byId[ctxMenu.id].path) ? 'Open note' : 'Open file',
              () => { onOpenNote && onOpenNote(ctxMenu.id); setCtxMenu(null); }]] : []),
       ['Focus', () => { const e = engineRef.current; if (e) e.focusNode(ctxMenu.id); setCtxMenu(null); }],
       ['Hide node', () => { const e = engineRef.current; if (e) { const s = new Set(e.hidden); s.add(ctxMenu.id); e.setHidden(s); } setCtxMenu(null); }]]
        .map(([label, fn]) => React.createElement('div', { key: label, role: 'menuitem', tabIndex: 0, onClick: fn,
          onKeyDown: (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); fn(); } },
          style: { padding: '6px 10px', cursor: 'pointer', borderRadius: 5 }, onMouseEnter: (ev) => ev.currentTarget.style.background = 'rgba(245,210,93,0.14)', onMouseLeave: (ev) => ev.currentTarget.style.background = 'transparent' }, label))),

    /* Load failure — the twin of the publish card below, and swallowed to
       console.warn for exactly as long as that one was. Without it the only
       thing this view does on a failed load is stop saying "Loading graph…",
       which on a black canvas is indistinguishable from an empty library. */
    loadError && React.createElement('div', { style: { position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%,-50%)', zIndex: 60, width: 380, maxWidth: '90%', background: 'rgba(24,20,14,0.98)', border: '1px solid rgba(220,90,90,0.4)', borderRadius: 12, padding: 18, color: '#e9e2d4', font: '13px Inter, sans-serif', boxShadow: '0 18px 60px rgba(0,0,0,0.5)' } },
      React.createElement('div', { style: { fontWeight: 600, color: '#e08080', marginBottom: 8 } }, source === 'concepts' ? '⚠ Concept map failed' : '⚠ Graph failed to load'),
      React.createElement('div', { style: { color: '#cabfa9', marginBottom: 12, lineHeight: 1.4 } }, loadError),
      React.createElement('div', { style: { display: 'flex', gap: 8 } },
        React.createElement('button', { onClick: () => setReloadTick(n => n + 1), style: { ...ctrlStyle, cursor: 'pointer' } }, 'Try again'),
        React.createElement('button', { onClick: () => setLoadError(null), style: { ...ctrlStyle, cursor: 'pointer' } }, 'Close')),
    ),

    // Publish failure — was silently swallowed to console.warn before.
    shareError && React.createElement('div', { style: { position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%,-50%)', zIndex: 60, width: 380, maxWidth: '90%', background: 'rgba(24,20,14,0.98)', border: '1px solid rgba(220,90,90,0.4)', borderRadius: 12, padding: 18, color: '#e9e2d4', font: '13px Inter, sans-serif', boxShadow: '0 18px 60px rgba(0,0,0,0.5)' } },
      React.createElement('div', { style: { fontWeight: 600, color: '#e08080', marginBottom: 8 } }, '⚠ Publish failed'),
      React.createElement('div', { style: { color: '#cabfa9', marginBottom: 12, lineHeight: 1.4 } }, shareError),
      React.createElement('button', { onClick: () => setShareError(null), style: { ...ctrlStyle, cursor: 'pointer' } }, 'Close'),
    ),

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

/* In-browser semantic similarity using TF-IDF over a node's title tokens,
   tags, and folder path. Returns top-K candidate ghost edges between
   currently-unlinked node pairs. Cheap enough for vaults up to ~5k notes;
   beyond that we sample. */




/* Cluster palette — 12 distinct hues spaced for maximum visual separation. */


/* BFS from rootId out to maxDepth (inclusive). Returns the set of node ids
   reachable through the graph's edges in either direction. Used by Local mode. */




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
    artifact: isDark ? '#9db8c9' : '#4a7089',  // slate — filed decks/PDFs/images
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
  /* Accent-folded twin of `hay`, for the bare-term fallback below only —
     'unicas' has to find a node titled '...investigación...' the same
     way vault search (both arms — see _foldAccents in vault.jsx) already
     does. Left the `type:`/`path:`/`tag:`/`file:` operators alone: those
     compare against their own already-lowercased (unfolded) values, and
     folding just the query side there would silently stop matching an
     accented path/tag verbatim instead of adding a capability. */
  const foldedHay = _foldAccents(hay);
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
    else ok = foldedHay.includes(_foldAccents(low));
    return neg ? !ok : ok;
  };
  return raw.split(/\s+OR\s+/i).some(part => part.split(/\s+AND\s+|\s+/i).every(evalTerm));
}



/* Compute centroid + member count for each cluster, used for label placement. */




/* Project a 3D world point into 2D screen space (relative to the canvas's
   transform). Returns {sx, sy, scale, depth}. The canvas is already
   translated by pan & scaled by zoom, so the returned (sx,sy) are in
   pre-pan/zoom world coords — render3D applies pan/zoom outside. */


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
  links_to: { color: null },
  cites: { color: 'rgba(207, 154, 71, 0.95)' },
  related_to: { color: null },
  child_of: { color: 'rgba(102, 145, 209, 0.95)' },
  parent_of: { color: 'rgba(102, 145, 209, 0.95)' },
  implements: { color: 'rgba(110, 178, 168, 0.95)' },
  implemented_by: { color: 'rgba(110, 178, 168, 0.95)' },
  supports: { color: 'rgba(120, 178, 95, 0.95)' },
  contradicts: { color: 'rgba(217, 87, 87, 0.95)' },
  derived_from: { color: 'rgba(170, 122, 196, 0.95)' },
  supersedes: { color: 'rgba(232, 145, 80, 0.95)' },
  superseded_by: { color: 'rgba(232, 145, 80, 0.6)' },
  blocks: { color: 'rgba(217, 87, 87, 0.95)' },
  blocked_by: { color: 'rgba(217, 87, 87, 0.7)' },
  depends_on: { color: 'rgba(155, 124, 199, 0.9)' },
  has_risk: { color: 'rgba(217, 87, 87, 0.85)' },
  decided: { color: 'rgba(220, 178, 89, 0.95)' },
  has_task: { color: 'rgba(110, 178, 200, 0.9)' },
  has_proposal: { color: 'rgba(155, 178, 195, 0.9)' },
  created_by: { color: 'rgba(125, 181, 181, 0.9)' },
  edited_by: { color: 'rgba(125, 181, 181, 0.7)' },
  assigned_to: { color: 'rgba(125, 181, 181, 0.95)' },
  reviewed_by: { color: 'rgba(125, 181, 181, 0.85)' },
  /* Obsidian ![[embeds]] — the note SHOWS this artifact (kg_builder
     types them at 0.95). Warm attachment tint, no dash, heavier than a
     plain link: the artifact is part of the note, not a mention. */
  embeds: { color: 'rgba(196, 149, 106, 0.95)' },
  notes: { color: null },
  mentions: { color: null },
  exemplifies: { color: 'rgba(120, 178, 95, 0.85)' },
  questions: { color: 'rgba(220, 178, 89, 0.9)' },
  // HQ-state edges (task/mission/receipt → vault notes & agents)
  references: { color: null },
  produces: { color: 'rgba(86, 168, 124, 0.95)' },
  modified: { color: 'rgba(168, 124, 86, 0.85)' },
  targets: { color: 'rgba(110, 178, 200, 0.9)' },
  runs_as: { color: 'rgba(125, 181, 181, 1.0)' },
  // Message-thread edges (agent ↔ thread)
  sent_to: { color: 'rgba(155, 124, 199, 0.95)' },
  received: { color: 'rgba(155, 124, 199, 0.7)' },
  // Org-chart: assistant → senior. Solid teal, slightly heavier so the
  // hierarchy stands out among the noisier message/thread edges.
  reports_to: { color: 'rgba(86, 138, 178, 1.0)' },
};

/* Group edges by render style and stroke each group in one batched path.
   Falls back to a single batched pass with `defaultColor` when colored-edges
   is disabled (or when state.colorEdgesByType is false). `getXY` returns
   [x,y] for a node id — lets the same helper work for 2D and 3D. */


/* 3D-mode render. Sibling to render(); same overlays apply but nodes/edges
   are drawn with perspective and back-to-front depth sorting. */







export { GraphView };
