<script>
  /* THE LIBRARY — the public face of Ai Cafreso Search.
     Anonymous-first: every question ever answered on-chain, explorable as one
     growing neural web. Hero = the merged graph (graph-viewer iframe over
     /library/graph.json) with a live search box wired to the same
     library-first → network-queue pipeline as the search modal. Below: the
     entry stream (newest first) with provenance chips; clicking opens a
     URL-addressable drawer (?e=<id>) with the full answer, sources, and the
     entry's own micro-graph. Must render beautifully at 0 entries — that is
     its launch state. */
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import Icon from '$lib/components/Icon.svelte';
  import CommentThread from '$lib/components/CommentThread.svelte';
  import UpNext from '$lib/components/UpNext.svelte';
  import WeeklyDigest from '$lib/components/WeeklyDigest.svelte';
  import { loadUpNext, normQ } from '$lib/stores/upnext.js';
  import { trapFocus } from '$lib/actions/trapFocus.js';
  import { listComments, postComment } from '$lib/api/devlog.js';
  import { principalText } from '$lib/stores/auth.js';
  import { profile } from '$lib/stores/profile.js';
  import {
    libraryIndex, libraryEntry, networkHealth, findPublic, submitJob, awaitJob, libraryResearch
  } from '$lib/api/searchNetwork.js';
  import { libraryGraphViewerUrl, libraryMergedGraphViewerUrl, libraryFullGraphViewerUrl, libraryReplayGraphViewerUrl, libraryEntryEnrichment, libraryCardVisual, graphViewerOrigin } from '$lib/api/library.js';
  import { fmtNsDate, fmtNsRelative, nsToDate } from '$lib/utils/time.js';

  let index = null;          // null = loading, {count, entries} after
  let health = null;
  let shown = 24;            // client-side paging over the (≤500) index

  // Filter/sort the already-fetched index client-side — no extra fetch, the
  // whole (≤500-entry) index is already local by the time this page renders.
  let filterText = '';
  let sortBy = 'newest';     // 'newest' | 'sources' — index arrives newest-first
  let modeFilter = 'all';    // 'all' | 'deep' — Deep Research has its own section
  $: deepCount = index && index.entries ? index.entries.filter((e) => e.mode === 'deep').length : 0;
  $: filteredEntries = index && index.entries
    ? (() => {
        const needle = filterText.trim().toLowerCase();
        let out = modeFilter === 'deep' ? index.entries.filter((e) => e.mode === 'deep') : index.entries;
        if (needle) out = out.filter((e) => plain(e.query).toLowerCase().includes(needle));
        return sortBy === 'sources' ? [...out].sort((a, b) => b.sources - a.sources) : out;
      })()
    : [];
  function onFilterChange() { shown = 24; }   // fresh "Show more" once the set changes
  function setMode(m) { modeFilter = m; onFilterChange(); }

  // A digest theme chip jumps straight into the existing text filter — no new
  // filtering mechanism, just points the one that already exists at a word.
  function jumpToTheme(word) {
    filterText = word;
    modeFilter = 'all';
    onFilterChange();
    document.querySelector('.lib-browse-head')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // Ground.news-style cards: a hero thumbnail + favicon row per card, pulled
  // from each entry's own graph.json. Bounded to what's actually on screen
  // (the current page of `shown` cards) rather than all ≤500 index entries —
  // requestedIds guards against re-fetching on every unrelated reactive tick
  // while a request is still in flight (cardVisuals only gains the key once
  // the fetch resolves, which would otherwise look identical to "not yet asked").
  let cardVisuals = {};   // id -> null (no enrichment) | {thumb, favicons}
  const requestedIds = new Set();
  $: {
    for (const e of filteredEntries.slice(0, shown)) {
      if (!requestedIds.has(e.id)) {
        requestedIds.add(e.id);
        libraryCardVisual(e.id).then((v) => { cardVisuals = { ...cardVisuals, [e.id]: v }; });
      }
    }
  }

  // Hero search — same pipeline as the modal, rendered inline.
  let q = '';
  let searchPhase = 'idle';  // idle | checking | queued | rejected | dark
  const SLOW_AFTER_MS = 45_000;   // past this, name the slowness instead of just spinning
  let queueNote = '';
  let rejectReason = '';
  let searchSeq = 0;

  // Drawer (URL-addressable: /library?e=<id>)
  let drawerId = null;
  let drawerEntry = null;    // null while loading
  let drawerMissing = false;
  let drawerResearch = null; // deep entries: {pages:[…]} note pages, lazily fetched
  let openPageId = null;     // which note page is expanded in the drawer
  let drawerEnrich = null;   // {byUrl, suggests} from the entry graph, lazily fetched
  let drawerComments = [];   // devlog-backed comment thread, keyed by libCommentSlug(id)
  let commentErr = null;
  // Own namespace ('library-' not the forums' 'f-') so a library entry id can
  // never collide with a blog/forum slug in the shared devlog comment keyspace.
  const libCommentSlug = (id) => `library-${id}`;

  const mergedGraphUrl = libraryMergedGraphViewerUrl();
  const fullGraphUrl = libraryFullGraphViewerUrl();   // full interactive viewer (topic filter, search, analytics)
  const replayGraphUrl = libraryReplayGraphViewerUrl();  // same viewer, growth replay auto-playing
  let heroIframe;   // bound to the hero graph iframe; used to gate postMessage

  $: {
    const e = $page.url.searchParams.get('e');
    if (e !== drawerId) { drawerId = e; loadDrawer(e); }
  }

  async function loadDrawer(id) {
    drawerEntry = null;
    drawerMissing = false;
    drawerResearch = null;
    drawerEnrich = null;
    drawerComments = [];
    commentErr = null;
    openPageId = null;
    if (!id) return;
    const e = await libraryEntry(id);
    if (id !== drawerId) return;
    if (e && e.id) {
      drawerEntry = e;
      // The entry graph carries the Brave-harvest enrichment (source dates,
      // "people also ask") that the flat entry JSON doesn't — pull it in
      // parallel so the sources list can show dates and the drawer can offer
      // the follow-up questions as one-tap searches.
      libraryEntryEnrichment(id).then((en) => { if (id === drawerId) drawerEnrich = en; });
      // The library curates like a blog post already (a permanent, sourced
      // answer) — comments reuse the exact same devlog-backed thread the blog
      // and forums use, just under their own slug namespace.
      listComments(libCommentSlug(id)).then((c) => { if (id === drawerId) drawerComments = c || []; });
      // Deep entries carry a browsable set of note pages — load them so the
      // drawer can show the research as pages, not just one synthesized answer.
      if (e.mode === 'deep') {
        const r = await libraryResearch(id);
        if (id === drawerId && r && r.pages) drawerResearch = r;
      }
    } else drawerMissing = true;
  }
  async function postDrawerComment(text) {
    if (!drawerId) return;
    commentErr = null;
    const author = {
      name: $profile?.name || ($principalText ? `${$principalText.slice(0, 5)}…${$principalText.slice(-3)}` : 'Guest'),
      role: $profile?.bio ? 'Member' : 'Community',
      hue: 24
    };
    const res = await postComment(libCommentSlug(drawerId), author, text);
    if (res?.err) { commentErr = res.err; return; }
    drawerComments = await listComments(libCommentSlug(drawerId));
  }
  // Svelte's legacy-mode dependency scan works per-block: it only picks up a
  // dependency an {#each} block's OWN template expressions reference by name.
  // A wrapper function (srcAge(url) reading srcAges via closure) doesn't
  // count — the each block never sees "srcAges" in its own markup, so it
  // never got a dirty bit when the async enrichment fetch resolved and the
  // dates silently never rendered. Reading srcAges directly via {@const} in
  // the each block (see the sources list below) is what actually fixes it;
  // this derived map only needs to exist, not be read from here.
  $: srcAges = drawerEnrich && drawerEnrich.byUrl ? drawerEnrich.byUrl : new Map();
  // Oldest dated source — one glance at how far back the evidence reaches,
  // the Ground.news "Coverage Details" idea adapted to what we actually have.
  $: oldestSourceAge = (() => {
    let oldest = null;
    for (const v of srcAges.values()) {
      if (v.age && /^\d{4}-\d{2}-\d{2}/.test(v.age) && (!oldest || v.age < oldest)) oldest = v.age;
    }
    return oldest;
  })();
  function togglePage(pid) { openPageId = openPageId === pid ? null : pid; }

  function openEntry(id) { goto(`/library?e=${encodeURIComponent(id)}`, { noScroll: true }); }
  function closeDrawer() { goto('/library', { noScroll: true }); }
  function onKeydown(e) { if (e.key === 'Escape' && drawerId) closeDrawer(); }

  async function refresh() {
    const [ix, h] = await Promise.all([libraryIndex(), networkHealth()]);
    if (ix) index = ix;
    else if (index === null) index = { count: -1, entries: [] };   // unreachable → offline state
    if (h) health = h;
  }
  // The hero graph iframe (embed=post) posts a message when a question node is
  // clicked; open the in-page drawer instead of letting it navigate a new tab.
  // Strict checks: only the viewer origin, only OUR iframe's window, only the
  // one message shape — never trust postMessage blind.
  function onGraphMessage(ev) {
    if (ev.origin !== graphViewerOrigin()) return;
    if (heroIframe && ev.source !== heroIframe.contentWindow) return;
    const d = ev.data;
    if (!d || d.type !== 'cafreso:openEntry' || !d.entryId) return;
    openEntry(String(d.entryId));
  }
  onMount(() => {
    refresh();
    loadUpNext();   // hydrate the personal research shortlist (localStorage)
    const t = setInterval(refresh, 60_000);
    window.addEventListener('message', onGraphMessage);
    // ?ask=<question> — the landing target for the graph viewer's ghost
    // "people also wonder" nodes: arrive with the question PRE-FILLED, not
    // auto-run. A URL that runs a paid search job on load with no user
    // action is a CSRF-shaped hole (any page can iframe/link ?ask=... and
    // spend the network's Brave quota + mint a permanent entry with
    // attacker-chosen text) — the visitor still has to press Search.
    // Only the `ask` param is stripped, via URLSearchParams, so any other
    // param (e.g. a future ?e= alongside it) survives the replace.
    const ask = $page.url.searchParams.get('ask');
    if (ask && ask.trim()) {
      q = ask.trim().slice(0, 400);
      const u = new URL($page.url);
      u.searchParams.delete('ask');
      goto(u.pathname + u.search, { replaceState: true, noScroll: true });
    }
    return () => { clearInterval(t); window.removeEventListener('message', onGraphMessage); };
  });

  async function runSearch() {
    const query = q.trim();
    if (!query || searchPhase === 'checking' || searchPhase === 'queued') return;
    const seq = ++searchSeq;
    searchPhase = 'checking';
    const hit = await findPublic(query);
    if (seq !== searchSeq) return;
    if (hit && hit.id) { searchPhase = 'idle'; openEntry(hit.id); return; }
    const h = await networkHealth();
    if (seq !== searchSeq) return;
    if (!h || !h.activeWorkers) { searchPhase = 'dark'; return; }
    const sub = await submitJob(query);
    if (seq !== searchSeq) return;
    if (!sub) { searchPhase = 'dark'; return; }
    if (sub.status === 'hit' && sub.entry) { searchPhase = 'idle'; openEntry(sub.entry.id); return; }
    if (sub.status === 'rejected') { rejectReason = sub.reason; searchPhase = 'rejected'; return; }
    searchPhase = 'queued';
    queueNote = h.activeWorkers === 1 ? '1 worker researching' : `${h.activeWorkers} workers online`;
    const done = await awaitJob(sub.jobId, {
      onTick: (st, elapsedMs) => {
        if (seq !== searchSeq) return;
        // Past ~45s a slow box is still healthy — say so rather than spin.
        // 'slow' is a sentinel: the template swaps the whole sentence, since the
        // default one promises "~10–30s" and would contradict itself here.
        if (elapsedMs > SLOW_AFTER_MS) queueNote = 'slow';
        else if (st === 'claimed') queueNote = 'a worker picked it up…';
      }
    });
    if (seq !== searchSeq) return;
    if (done.status === 'done' && done.entry) {
      searchPhase = 'idle';
      refresh();                      // the web just grew
      openEntry(done.entry.id);
    } else {
      rejectReason = done.status;
      searchPhase = 'rejected';
    }
  }

  // ── "Up Next" shortlist glue ───────────────────────────────────────────────
  // Graduation: a queued question that now exists in the library (answered by
  // anyone) flips to a "read it" row. Loose client-side normalized match — the
  // authoritative check is findPublic() when the question is actually sent.
  $: answeredMap = (() => {
    const m = new Map();
    if (index && index.entries) for (const e of index.entries) m.set(normQ(plain(e.query)), e.id);
    return m;
  })();
  // Reactive so its identity changes when answeredMap does — the UpNext
  // template re-evaluates graduation as the index refreshes.
  $: findAnswered = (q) => answeredMap.get(normQ(q)) || null;

  // Send one shortlisted question through the real network pipeline (same
  // library-first → queue → await path as the hero search). Returns a status
  // the UpNext component reflects; on success refresh() lets the item graduate.
  async function sendQueued(question) {
    const query = String(question || '').trim();
    if (!query) return { status: 'idle' };
    const hit = await findPublic(query);
    if (hit && hit.id) { refresh(); return { status: 'hit', id: hit.id }; }
    const h = await networkHealth();
    if (!h || !h.activeWorkers) return { status: 'dark' };
    const sub = await submitJob(query);
    if (!sub) return { status: 'dark' };
    if (sub.status === 'hit' && sub.entry) { refresh(); return { status: 'hit', id: sub.entry.id }; }
    if (sub.status === 'rejected') return { status: 'rejected', reason: sub.reason };
    const done = await awaitJob(sub.jobId);
    if (done.status === 'done' && done.entry) { refresh(); return { status: 'done', id: done.entry.id }; }
    return { status: 'rejected', reason: done.status };
  }

  function plain(t) { return String(t || '').replace(/<[^>]+>/g, ''); }
  const fmtDate = (ns) => fmtNsDate(ns, 'short');
  // News feeds live on recency: "3h ago" reads as a live wire, "Jul 22, 2026"
  // reads as an archive. Cards use the relative form; the drawer keeps the
  // absolute date (a permanent record wants an exact stamp).
  const relTime = (ns) => fmtNsRelative(ns) || fmtNsDate(ns, 'short');
  // "Just in" — answered in the last 24h. The one editorial signal that turns
  // a static library into an incoming-news feed you check back on.
  function isFresh(ns) {
    const d = nsToDate(ns);
    return d ? (Date.now() - d.getTime()) < 86_400_000 : false;
  }
  function shortPrincipal(p) {
    if (!p) return '';
    return p.length > 12 ? p.slice(0, 5) + '…' + p.slice(-3) : p;
  }
  function domain(url) {
    try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; }
  }
  // Sources are worker-authored (any approved network worker can write this
  // field) — treat like any other untrusted URL before it becomes an href.
  // graph-viewer.js already scheme-gates url/img/favicon the same way.
  function safeHref(url) { return /^https?:\/\//i.test(url || '') ? url : '#'; }
  /* Who asked this question — a person, or the library noticing its own gap?
     The worker marks gap questions by appending 'ai-gap' to the engine field
     (the canister entry has no askedBy; adding one is a canister upgrade).
     Read it here rather than rendering the raw marker at the user. */
  function askedByAi(entry) {
    return /\bai-gap\b/.test(String(entry?.engine || ''));
  }
  function engineLabel(entry) {
    return String(entry?.engine || '').replace(/\s*·?\s*\bai-gap\b/, '').trim() || 'brave';
  }
</script>

<svelte:head>
  <title>The Library — Ai Cafreso</title>
  <meta name="description" content="Every question answered on-chain lives here forever — a public research web grown by the Cafreso search network." />
</svelte:head>

<svelte:window on:keydown={onKeydown} />

<section class="space-y-8">
  <!-- ── Hero: the neural web ─────────────────────────────────────────────── -->
  <div class="lib-hero">
    {#if mergedGraphUrl && index && index.count > 0}
      <iframe
        bind:this={heroIframe}
        src={mergedGraphUrl}
        title="The library as a graph — every question and source, one web"
        class="lib-hero-graph"
        loading="lazy"
      ></iframe>
    {:else}
      <div class="lib-hero-stars" aria-hidden="true"></div>
    {/if}
    <div class="lib-hero-veil" aria-hidden="true"></div>

    <div class="lib-hero-content">
      <div class="lib-kicker">The Cafreso Library</div>
      <h1 class="lib-title">Every answer, one growing web<span class="text-brand-400">.</span></h1>
      <p class="lib-sub">
        Questions answered on-chain live here forever — searched once, free for everyone after.
      </p>

      <form class="lib-search" on:submit|preventDefault={runSearch}>
        <Icon name="magnifying-glass" size={18} style="color: hsl(40 30% 65%); flex-shrink: 0;" />
        <input
          type="search"
          bind:value={q}
          placeholder="Ask the library anything…"
          aria-label="Search the library"
          disabled={searchPhase === 'checking' || searchPhase === 'queued'}
        />
        <button type="submit" disabled={!q.trim() || searchPhase === 'checking' || searchPhase === 'queued'}>
          {searchPhase === 'checking' ? 'Checking…' : searchPhase === 'queued' ? 'Researching…' : 'Search'}
        </button>
      </form>

      {#if fullGraphUrl && index && index.count > 0}
        <div class="lib-explore-row">
          <a class="lib-explore" href={fullGraphUrl} target="_blank" rel="noopener">
            <Icon name="graph" size={15} style="flex-shrink:0;" />
            Explore the full graph — filter by topic, search &amp; trace connections
            <span class="lib-explore-arrow" aria-hidden="true">→</span>
          </a>
          {#if replayGraphUrl && index.count >= 10}
            <a class="lib-explore lib-replay" href={replayGraphUrl} target="_blank" rel="noopener"
               title="Replay every question in the order it was asked — the web growing in fast-forward">
              <span aria-hidden="true">▶</span>
              Watch it grow
            </a>
          {/if}
        </div>
      {/if}

      {#if searchPhase === 'queued'}
        <div class="lib-search-note">
          <span class="lib-pulse-dot"></span>
          {#if queueNote === 'slow'}
            Still working — this one's a slow one. The answer joins the library either way,
            so you can leave this page and find it here.
          {:else}
            The research network is on it — {queueNote}. Fresh answers usually land in a few seconds and join the web forever.
          {/if}
        </div>
      {:else if searchPhase === 'rejected'}
        <div class="lib-search-note lib-warn">
          {rejectReason === 'busy' ? 'The network is at capacity — try again in a minute.'
            : rejectReason === 'budget' ? "Today's research budget is spent — back tomorrow."
            : rejectReason === 'timeout' ? 'Still researching — your answer will appear in the stream below when it lands.'
            : "The network couldn't answer that one — try rephrasing."}
        </div>
      {:else if searchPhase === 'dark'}
        <div class="lib-search-note lib-warn">
          The research network is asleep — no workers online. Browse everything already answered below,
          or <a href="/hq/search" class="lib-link">sign in to search with your own container</a>.
        </div>
      {/if}

      <div class="lib-pulse" aria-live="polite">
        {#if index === null}
          <span class="lib-skel" style="width: 220px;"></span>
        {:else if index.count > 0}
          <span>{index.count.toLocaleString()} question{index.count === 1 ? '' : 's'} answered on-chain</span>
          {#if health}
            <span class="lib-dot">·</span>
            {#if health.activeWorkers > 0}
              <span class="lib-live"><span class="lib-pulse-dot"></span>{health.activeWorkers} worker{health.activeWorkers === 1 ? '' : 's'} online</span>
            {:else}
              <span>network asleep</span>
            {/if}
            <span class="lib-dot">·</span>
            <span>{health.answeredToday} answered today</span>
          {/if}
        {/if}
      </div>

      {#if fullGraphUrl && index && index.count > 0}
        <a class="lib-graph-open" href={fullGraphUrl} target="_blank" rel="noopener noreferrer">
          Explore the full web <Icon name="arrow-up-right" size={12} />
        </a>
      {/if}
    </div>
  </div>

  <!-- ── This week in the library: what got answered ──────────────────────── -->
  {#if index && index.entries}
    <WeeklyDigest entries={index.entries} onOpen={openEntry} onTheme={jumpToTheme} />
  {/if}

  <!-- ── Up Next: personal research shortlist ─────────────────────────────── -->
  {#if index !== null}
    <UpNext {findAnswered} onOpen={openEntry} onSend={sendQueued} workersOnline={!!(health && health.activeWorkers)} />
  {/if}

  <!-- ── Entry stream ─────────────────────────────────────────────────────── -->
  {#if index === null}
    <div class="lib-grid">
      {#each Array(6) as _}
        <div class="lib-card">
          <div class="lib-skel" style="width: 80%; height: 16px; margin-bottom: 12px;"></div>
          <div class="lib-skel" style="width: 100%; height: 11px; margin-bottom: 7px;"></div>
          <div class="lib-skel" style="width: 92%; height: 11px; margin-bottom: 7px;"></div>
          <div class="lib-skel" style="width: 60%; height: 11px; margin-bottom: 16px;"></div>
          <div class="lib-skel" style="width: 40%; height: 11px;"></div>
        </div>
      {/each}
    </div>
  {:else if index.count === 0}
    <div class="lib-empty">
      <div class="lib-empty-glyph" aria-hidden="true">◍</div>
      <h2>The library is being born</h2>
      <p>
        Every question answered on-chain lives here forever — permanent, sourced, and free for the
        next person who wonders the same thing. Ask the first one above.
      </p>
    </div>
  {:else if index.count === -1}
    <div class="lib-empty">
      <div class="lib-empty-glyph" aria-hidden="true">◌</div>
      <h2>The library is unreachable</h2>
      <p>The on-chain library didn't answer — it may not be deployed on this network yet. Try again shortly.</p>
    </div>
  {:else}
    <!-- The graph hero above is the primary way to explore; this list is the
         browse/search fallback. Framing it as such keeps the "one growing web"
         idea front-and-centre rather than letting the flat list read as the
         whole library. -->
    <div class="lib-browse-head">
      <h2 class="lib-browse-title">Browse every answer</h2>
      <p class="lib-browse-sub">
        The whole web as a list — filter or sort below, or
        <a href={fullGraphUrl} target="_blank" rel="noopener noreferrer" class="lib-link">explore it visually in the graph ↑</a>
      </p>
    </div>

    {#if deepCount > 0}
      <div class="lib-modebar" role="group" aria-label="Filter by research depth">
        <button class="lib-modetab" class:on={modeFilter === 'all'} on:click={() => setMode('all')}>
          All questions
        </button>
        <button class="lib-modetab lib-modetab-deep" class:on={modeFilter === 'deep'} on:click={() => setMode('deep')}>
          <Icon name="tree-structure" size={14} /> Deep Research
          <span class="lib-modecount">{deepCount}</span>
        </button>
      </div>
      {#if modeFilter === 'deep'}
        <p class="lib-modehint">
          Multi-angle research queries — each broke a question into several searches and note pages you can walk as a tree.
        </p>
      {/if}
    {/if}

    <div class="lib-filterbar">
      <div class="lib-filter-input">
        <Icon name="funnel" size={14} style="color: hsl(var(--pg-fg-muted)); flex-shrink: 0;" />
        <input
          type="text"
          placeholder="Filter {index.entries.length} entries…"
          bind:value={filterText}
          on:input={onFilterChange}
          aria-label="Filter library entries"
        />
        {#if filterText}
          <button class="lib-filter-clear" on:click={() => { filterText = ''; onFilterChange(); }} aria-label="Clear filter">
            <Icon name="x" size={12} />
          </button>
        {/if}
      </div>
      <select class="lib-sort-select" bind:value={sortBy} on:change={onFilterChange} aria-label="Sort entries">
        <option value="newest">Newest first</option>
        <option value="sources">Most sources</option>
      </select>
    </div>

    {#if filteredEntries.length === 0}
      <div class="lib-empty">
        <div class="lib-empty-glyph" aria-hidden="true">◌</div>
        <h2>No entries match "{filterText}"</h2>
        <p>Try a shorter word, or <button class="lib-filter-reset-link" on:click={() => { filterText = ''; onFilterChange(); }}>clear the filter</button> to browse everything.</p>
      </div>
    {:else}
      <!-- The feed. On desktop this is the Ground.news-style card grid; on
           mobile it collapses to a news river — the first card is the lead
           story (big thumbnail), every card after it becomes a compact
           headline row (small thumbnail, 2-line headline, one quiet meta
           line). A giant slab per screen doesn't scan; a river does. The
           lead only earns its size on the default newest feed — once you
           filter or sort, every row is equal weight. -->
      {@const leadMode = sortBy === 'newest' && modeFilter === 'all' && !filterText.trim()}
      <div class="lib-grid lib-feed">
        {#each filteredEntries.slice(0, shown) as e, i (e.id)}
          {@const visual = cardVisuals[e.id]}
          {@const fresh = isFresh(e.ts)}
          <button class="lib-card lib-card-btn" class:lib-card-deep={e.mode === 'deep'}
                  class:lib-card-visual={visual?.thumb} class:lib-lead={leadMode && i === 0}
                  on:click={() => openEntry(e.id)}>
            {#if visual?.thumb}
              <div class="lib-card-thumb" style="background-image:url('{visual.thumb}')" role="presentation">
                {#if fresh}<span class="lib-fresh-tag">Just in</span>{/if}
              </div>
            {/if}
            <div class="lib-card-body">
              {#if e.mode === 'deep' || e.askedBy === 'ai-gap' || (fresh && !visual?.thumb)}
                <div class="lib-card-top">
                  {#if fresh && !visual?.thumb}
                    <span class="lib-chip lib-chip-fresh"><span class="lib-fresh-dot" aria-hidden="true"></span> Just in</span>
                  {/if}
                  {#if e.mode === 'deep'}
                    <span class="lib-chip lib-chip-deep"><Icon name="tree-structure" size={11} /> Deep research</span>
                  {/if}
                  {#if e.askedBy === 'ai-gap'}
                    <span class="lib-chip lib-chip-ai" title="Nobody asked this one. Cafreso read the library, found a gap in what it covers, and asked to fill it.">✦ Asked by Cafreso</span>
                  {/if}
                </div>
              {/if}
              <h3>{plain(e.query)}</h3>
              {#if e.snippet}
                <p class="lib-card-snippet">{plain(e.snippet)}</p>
              {/if}
              <div class="lib-card-meta">
                {#if visual?.favicons?.length}
                  <span class="lib-card-favs" aria-hidden="true">
                    {#each visual.favicons as f}
                      <img src={f} alt="" loading="lazy" on:error={(ev) => { ev.target.style.visibility = 'hidden'; }} />
                    {/each}
                  </span>
                {/if}
                <span>{relTime(e.ts)}</span>
                <span class="lib-meta-dot" aria-hidden="true">·</span>
                <span>{e.sources} source{e.sources === 1 ? '' : 's'}</span>
                <Icon name="arrow-right" size={13} class="lib-card-go" />
              </div>
            </div>
          </button>
        {/each}
      </div>
      {#if filteredEntries.length > shown}
        <div style="text-align: center;">
          <button class="lib-more" on:click={() => (shown += 24)}>
            Show more ({filteredEntries.length - shown} remaining)
          </button>
        </div>
      {/if}
    {/if}
  {/if}
</section>

<!-- ── Entry drawer (?e=<id>) ──────────────────────────────────────────────── -->
{#if drawerId}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="lib-drawer-backdrop" on:click={closeDrawer}></div>
  <aside class="lib-drawer" use:trapFocus role="dialog" aria-modal="true" aria-label="Library entry">
    <button class="lib-drawer-close" on:click={closeDrawer} aria-label="Close entry">
      <Icon name="x" size={16} />
    </button>
    {#if drawerEntry}
      <div class="lib-kicker" style="display: flex; align-items: center; justify-content: space-between; gap: 10px;">
        <span>Library entry · {drawerEntry.id}</span>
        <a class="lib-link" href="/library/{drawerEntry.id}" style="flex-shrink: 0;">
          Open full entry <Icon name="arrow-up-right" size={11} />
        </a>
      </div>
      <h2 class="lib-drawer-q">{plain(drawerEntry.query)}</h2>
      <div class="lib-chips" style="margin-bottom: 18px;">
        {#if drawerEntry.mode === 'deep'}
          <span class="lib-chip lib-chip-deep"><Icon name="tree-structure" size={11} /> Deep research</span>
        {/if}
        {#if askedByAi(drawerEntry)}
          <span class="lib-chip lib-chip-ai"
                title="Nobody asked this one. Cafreso read the library, found a gap in what it covers, and asked to fill it.">
            ✦ Asked by Cafreso to fill a gap
          </span>
        {/if}
        {#if drawerEntry.model}<span class="lib-chip">🤖 {drawerEntry.model}</span>{/if}
        {#if drawerEntry.engine}<span class="lib-chip">🔎 {engineLabel(drawerEntry)}</span>{/if}
        <span class="lib-chip">📅 {fmtDate(drawerEntry.answeredAt || drawerEntry.ts)}</span>
        {#if drawerEntry.worker}<span class="lib-chip" title={drawerEntry.worker}>⚙ {shortPrincipal(drawerEntry.worker)}</span>{/if}
      </div>

      {#if drawerEntry.sources?.length}
        <div class="lib-coverage">
          <div class="lib-coverage-stat">
            <span class="lib-coverage-n">{drawerEntry.sources.length}</span>
            <span class="lib-coverage-label">source{drawerEntry.sources.length === 1 ? '' : 's'}</span>
          </div>
          {#if oldestSourceAge}
            <div class="lib-coverage-stat">
              <span class="lib-coverage-n">{oldestSourceAge}</span>
              <span class="lib-coverage-label">oldest source</span>
            </div>
          {/if}
          {#if drawerEnrich?.favicons?.length}
            <div class="lib-coverage-favs" title="Sites cited in this answer">
              {#each drawerEnrich.favicons.slice(0, 8) as f}
                <img src={f} alt="" loading="lazy" on:error={(ev) => { ev.target.style.visibility = 'hidden'; }} />
              {/each}
            </div>
          {/if}
        </div>
      {/if}

      {#if drawerEntry.answer}
        <p class="lib-drawer-answer">{plain(drawerEntry.answer)}</p>
      {:else}
        <p class="lib-drawer-answer lib-muted">Sources were collected for this question, but no summary was written yet.</p>
      {/if}

      {#if drawerEntry.sources?.length}
        <div class="lib-kicker" style="margin-top: 22px;">Sources</div>
        <ol class="lib-sources">
          {#each drawerEntry.sources as s, i}
            {@const age = srcAges.get(s.url)?.age}
            <li>
              <a href={safeHref(s.url)} target="_blank" rel="noopener noreferrer">
                <span class="lib-src-n">[{i + 1}]</span>
                <span class="lib-src-t">{plain(s.title)}</span>
                {#if age}<span class="lib-src-age">{age}</span>{/if}
                <span class="lib-src-d">{domain(s.url)}</span>
              </a>
            </li>
          {/each}
        </ol>
      {/if}

      {#if drawerEnrich?.suggests?.length}
        <div class="lib-kicker" style="margin-top: 22px;">People also wonder</div>
        <p class="lib-ask-lede">Questions the web raised alongside this one — ask any to send it to the research network.</p>
        <div class="lib-ask-chips">
          {#each drawerEnrich.suggests.slice(0, 6) as sug}
            <button class="lib-ask-chip" on:click={() => { closeDrawer(); q = sug.q; runSearch(); }} title={sug.a || sug.q}>
              <span aria-hidden="true">✦</span> {plain(sug.q)}
            </button>
          {/each}
        </div>
      {/if}

      {#if drawerEntry.mode === 'deep' && drawerResearch?.pages?.length}
        <div class="lib-kicker" style="margin-top: 24px;">The research tree · {drawerResearch.pages.length} note pages</div>
        <p class="lib-deep-lede">
          This question was researched from several angles. Open a page to read the note, browse the whole
          thing as a vault of linked markdown files, or explore the tree in the graph below.
        </p>
        <a class="lib-vault-btn" href="/library/vault?e={drawerEntry.id}">
          <Icon name="vault" size={15} />
          <span class="lib-vault-btn-t">
            <strong>Browse Research</strong>
            <small>File tree · wikilinks · download as .md for Obsidian</small>
          </span>
          <Icon name="arrow-right" size={14} />
        </a>
        <div class="lib-pages">
          {#each drawerResearch.pages as p, i}
            <div class="lib-page" class:open={openPageId === p.id}>
              <button class="lib-page-head" on:click={() => togglePage(p.id)} aria-expanded={openPageId === p.id}>
                <span class="lib-page-n">{i + 1}</span>
                <span class="lib-page-title">
                  <span class="lib-page-t">{plain(p.title)}</span>
                  {#if p.question}<span class="lib-page-q">{plain(p.question)}</span>{/if}
                </span>
                <Icon name={openPageId === p.id ? 'caret-up' : 'caret-down'} size={14} style="flex-shrink: 0; color: hsl(var(--pg-fg-muted));" />
              </button>
              {#if openPageId === p.id}
                <div class="lib-page-body">
                  <p class="lib-page-note">{plain(p.body)}</p>
                  {#if p.sources?.length}
                    <ol class="lib-sources" style="margin-top: 12px;">
                      {#each p.sources as s, si}
                        <li>
                          <a href={safeHref(s.url)} target="_blank" rel="noopener noreferrer">
                            <span class="lib-src-n">[{si + 1}]</span>
                            <span class="lib-src-t">{plain(s.title)}</span>
                            <span class="lib-src-d">{domain(s.url)}</span>
                          </a>
                        </li>
                      {/each}
                    </ol>
                  {/if}
                </div>
              {/if}
            </div>
          {/each}
        </div>
      {/if}

      {#if libraryGraphViewerUrl(drawerEntry.id)}
        {@const deepEntry = drawerEntry.mode === 'deep'}
        {@const gvUrl = libraryGraphViewerUrl(drawerEntry.id, { deep: deepEntry })}
        <div class="lib-kicker" style="margin-top: 22px;">{deepEntry ? 'The research tree, explorable' : 'This answer as a graph'}</div>
        <iframe
          src={gvUrl}
          title={deepEntry ? 'The research tree — click a topic to read its note' : 'Graph of this answer'}
          class="lib-drawer-graph"
          loading="lazy"
        ></iframe>
        <div class="lib-drawer-actions">
          <a class="lib-link" href={gvUrl} target="_blank" rel="noopener noreferrer">
            {deepEntry ? 'Open the research tree' : 'Open graph'} <Icon name="arrow-up-right" size={12} />
          </a>
          <button class="lib-link" style="border: none; background: transparent; cursor: pointer; font: inherit; padding: 0;"
            on:click={() => { try { navigator.clipboard.writeText(location.origin + '/library?e=' + drawerEntry.id); } catch {} }}>
            Copy link
          </button>
        </div>
      {/if}

      <!-- The library curates like a blog: a permanent, sourced answer worth
           discussing. Same devlog-backed thread as the blog/forums, own slug
           namespace (library-<id>) so it can never collide with theirs. -->
      {#if commentErr}
        <p class="lib-comment-err">{commentErr}</p>
      {/if}
      <CommentThread comments={drawerComments} onPost={postDrawerComment} modSlug={libCommentSlug(drawerEntry.id)} />
    {:else if drawerMissing}
      <div class="lib-empty" style="padding: 60px 10px;">
        <h2>Entry not found</h2>
        <p>It may have been withdrawn by its author.</p>
      </div>
    {:else}
      <div class="lib-skel" style="width: 40%; height: 12px; margin: 8px 0 16px;"></div>
      <div class="lib-skel" style="width: 90%; height: 26px; margin-bottom: 18px;"></div>
      <div class="lib-skel" style="width: 100%; height: 12px; margin-bottom: 8px;"></div>
      <div class="lib-skel" style="width: 95%; height: 12px; margin-bottom: 8px;"></div>
      <div class="lib-skel" style="width: 70%; height: 12px;"></div>
    {/if}
  </aside>
{/if}

<style>
  /* ── Hero — the one deliberately dark surface on the warm Pages theme ──── */
  .lib-hero {
    position: relative;
    border-radius: 1.75rem;
    overflow: hidden;
    background:
      radial-gradient(ellipse at 30% 20%, hsl(255 45% 16%) 0%, transparent 55%),
      radial-gradient(ellipse at 75% 75%, hsl(24 55% 12%) 0%, transparent 60%),
      hsl(250 30% 7%);
    min-height: 440px;
    display: flex;
    align-items: flex-end;
    box-shadow: 0 30px 80px -30px hsl(250 40% 6% / 0.7);
  }
  .lib-hero-graph {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    border: 0;
    opacity: 0.85;
  }
  /* Zero-entry night sky: pure CSS star field so the launch state still feels alive. */
  .lib-hero-stars {
    position: absolute; inset: 0;
    background-image:
      radial-gradient(1.5px 1.5px at 12% 30%, hsl(45 90% 80% / 0.9), transparent 100%),
      radial-gradient(1px 1px at 28% 68%, hsl(0 0% 100% / 0.7), transparent 100%),
      radial-gradient(2px 2px at 45% 22%, hsl(265 80% 82% / 0.8), transparent 100%),
      radial-gradient(1px 1px at 58% 55%, hsl(0 0% 100% / 0.6), transparent 100%),
      radial-gradient(1.5px 1.5px at 71% 33%, hsl(160 70% 78% / 0.8), transparent 100%),
      radial-gradient(1px 1px at 83% 70%, hsl(0 0% 100% / 0.7), transparent 100%),
      radial-gradient(2px 2px at 91% 18%, hsl(45 90% 78% / 0.75), transparent 100%),
      radial-gradient(1px 1px at 8% 82%, hsl(0 0% 100% / 0.55), transparent 100%);
  }
  /* Legibility veil: the graph stays explorable up top, text sits on the fade. */
  .lib-hero-veil {
    position: absolute; inset: 0;
    background: linear-gradient(180deg, transparent 0%, hsl(250 30% 7% / 0.35) 45%, hsl(250 30% 7% / 0.92) 78%);
    pointer-events: none;
  }
  .lib-hero-content {
    position: relative;
    z-index: 1;
    width: 100%;
    padding: 200px 28px 30px;
    pointer-events: none;   /* let the graph receive drag/zoom… */
  }
  .lib-hero-content > * { pointer-events: auto; }  /* …but keep controls clickable */

  .lib-kicker {
    font-size: 11px; font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase;
    color: hsl(45 85% 62%);
  }
  .lib-title {
    font-family: 'Playfair Display', serif;
    font-size: clamp(1.9rem, 4.5vw, 3.1rem);
    font-weight: 700;
    color: hsl(40 50% 96%);
    margin: 10px 0 8px;
    line-height: 1.08;
  }
  .lib-sub { font-size: 14.5px; line-height: 1.6; color: hsl(40 25% 78%); max-width: 46ch; margin: 0 0 18px; }

  .lib-search {
    display: flex; align-items: center; gap: 10px;
    max-width: 620px;
    background: hsl(250 25% 12% / 0.85);
    border: 1.5px solid hsl(255 30% 30%);
    border-radius: 16px;
    padding: 6px 8px 6px 16px;
    backdrop-filter: blur(10px);
    transition: border-color 0.15s;
  }
  .lib-search:focus-within { border-color: hsl(45 85% 55%); }
  .lib-search input {
    flex: 1; min-width: 0; border: none; background: transparent; outline: none;
    font: 500 16px/1.4 Inter, system-ui, sans-serif; color: hsl(40 50% 96%); padding: 8px 0;
  }
  .lib-search input::placeholder { color: hsl(40 15% 55%); }
  .lib-search button {
    border: none; border-radius: 11px; cursor: pointer;
    background: hsl(45 90% 58%); color: hsl(24 48% 12%);
    font: 700 13.5px Inter, system-ui, sans-serif;
    padding: 10px 20px;
    transition: filter 0.15s;
  }
  .lib-search button:hover:not(:disabled) { filter: brightness(1.08); }
  .lib-search button:disabled { opacity: 0.55; cursor: default; }

  .lib-search-note {
    display: flex; align-items: center; gap: 8px;
    margin-top: 12px; font-size: 12.5px; color: hsl(40 25% 78%); max-width: 600px; line-height: 1.5;
  }
  .lib-search-note.lib-warn { color: hsl(35 80% 72%); }
  .lib-link { color: hsl(45 85% 62%); font-weight: 600; text-decoration: none; display: inline-flex; align-items: center; gap: 3px; }

  .lib-explore-row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 14px; }
  .lib-explore-row .lib-explore { margin-top: 0; }
  /* "Watch it grow" — same pill family, warmer fill so it reads as the play
     button it is rather than a second navigation link. */
  .lib-replay { color: hsl(150 65% 70%); background: hsl(150 40% 12% / 0.55); border-color: hsl(150 50% 40% / 0.4); }
  .lib-replay:hover { border-color: hsl(150 65% 50% / 0.75); background: hsl(150 45% 14% / 0.7); }
  .lib-explore {
    display: inline-flex; align-items: center; gap: 8px;
    margin-top: 14px; padding: 8px 14px;
    font-size: 12.5px; font-weight: 600; color: hsl(45 85% 66%);
    background: hsl(45 40% 12% / 0.55); border: 1px solid hsl(45 60% 45% / 0.35);
    border-radius: 999px; text-decoration: none; line-height: 1;
    backdrop-filter: blur(6px); transition: border-color .15s, background .15s, transform .15s;
  }
  .lib-explore:hover { border-color: hsl(45 85% 55% / 0.7); background: hsl(45 45% 14% / 0.7); transform: translateY(-1px); }
  .lib-explore-arrow { transition: transform .15s; }
  .lib-explore:hover .lib-explore-arrow { transform: translateX(3px); }
  @media (max-width: 560px) { .lib-explore { font-size: 12px; } }

  .lib-pulse {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    margin-top: 16px; font-size: 12px; color: hsl(40 20% 62%);
    font-family: 'JetBrains Mono', ui-monospace, monospace;
  }
  .lib-dot { opacity: 0.5; }
  .lib-live { display: inline-flex; align-items: center; gap: 6px; color: hsl(150 60% 65%); }
  .lib-pulse-dot {
    width: 7px; height: 7px; border-radius: 50%; background: hsl(150 70% 55%);
    box-shadow: 0 0 8px hsl(150 70% 55% / 0.8);
    animation: lib-pulse 1.6s ease-in-out infinite;
    flex-shrink: 0;
  }
  @keyframes lib-pulse { 50% { opacity: 0.35; } }

  .lib-graph-open {
    position: absolute; top: 18px; right: 20px;
    display: inline-flex; align-items: center; gap: 5px;
    font-size: 12px; font-weight: 600; color: hsl(40 30% 80%); text-decoration: none;
    background: hsl(250 25% 12% / 0.7); border: 1px solid hsl(255 30% 28%);
    padding: 7px 13px; border-radius: 999px; backdrop-filter: blur(8px);
    transition: border-color 0.15s;
  }
  .lib-graph-open:hover { border-color: hsl(45 85% 55%); }

  /* ── Entry stream ──────────────────────────────────────────────────────── */
  .lib-filterbar {
    display: flex; gap: 10px; align-items: center; margin-bottom: 16px;
  }
  .lib-filter-input {
    flex: 1; min-width: 0; display: flex; align-items: center; gap: 8px;
    background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border)); border-radius: 999px;
    padding: 8px 14px; transition: border-color 0.14s;
  }
  .lib-filter-input:focus-within { border-color: hsl(45 75% 60%); }
  .lib-filter-input input {
    flex: 1; min-width: 0; border: none; outline: none; background: none;
    font: 14px Inter, system-ui, sans-serif; color: hsl(var(--pg-fg));
  }
  .lib-filter-input input::placeholder { color: hsl(40 15% 60%); }
  .lib-filter-clear {
    display: flex; align-items: center; justify-content: center;
    width: 18px; height: 18px; border-radius: 50%; border: none; cursor: pointer;
    background: hsl(var(--pg-border)); color: hsl(var(--pg-fg-muted)); flex-shrink: 0; padding: 0;
  }
  .lib-filter-clear:hover { background: hsl(var(--pg-border)); }
  .lib-sort-select {
    border: 1px solid hsl(var(--pg-border)); background: hsl(var(--pg-elevated)); border-radius: 999px;
    padding: 8px 14px; font: 600 12.5px Inter, system-ui, sans-serif;
    color: hsl(var(--pg-fg)); cursor: pointer; flex-shrink: 0;
  }
  .lib-filter-reset-link {
    background: none; border: none; padding: 0; margin: 0; cursor: pointer;
    font: inherit; color: hsl(45 70% 40%); text-decoration: underline;
  }
  /* Section header framing the list as the secondary browse surface. */
  .lib-browse-head { margin-bottom: 16px; }
  .lib-browse-title {
    font-family: 'Playfair Display', serif; font-size: 22px; font-weight: 700;
    color: hsl(var(--pg-fg)); margin: 0 0 4px;
  }
  .lib-browse-sub { font-size: 13px; line-height: 1.55; color: hsl(var(--pg-fg-muted)); margin: 0; }

  /* Wider tracks than before — cards now carry an answer snippet, which needs
     room to read. Auto-fill still collapses to 1-up on narrow screens. */
  .lib-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 14px;
  }
  .lib-card {
    background: hsl(var(--pg-surface));
    border: 1px solid hsl(var(--pg-border));
    border-radius: 18px;
    padding: 18px 20px;
    box-shadow: 0 4px 18px -10px hsl(24 35% 15% / 0.15);
  }
  /* Flex column so the meta line pins to the bottom and cards in a row stay the
     same height regardless of question/snippet length — kills the ragged grid. */
  .lib-card-btn {
    display: flex; flex-direction: column; height: 100%;
    text-align: left; cursor: pointer; font: inherit;
    transition: transform 0.14s, border-color 0.14s, box-shadow 0.14s;
  }
  .lib-card-btn:hover {
    transform: translateY(-2px);
    border-color: hsl(45 75% 60%);
    box-shadow: 0 12px 28px -12px hsl(24 35% 15% / 0.25);
  }
  /* Ground.news-style visual card: a hero thumbnail pulled from the entry's
     own Brave-harvested source images, when one exists. Only entries the
     enriched worker answered carry this — older entries render exactly as
     before (plain text card), so the grid is intentionally a visual mix
     rather than everything re-templated at once. */
  .lib-card-visual { padding: 0; overflow: hidden; }
  .lib-card-thumb {
    width: 100%; aspect-ratio: 16 / 9; flex-shrink: 0;
    background-size: cover; background-position: center;
    background-color: hsl(var(--pg-hover));
  }
  .lib-card-body { display: flex; flex-direction: column; flex: 1; min-height: 0; }
  .lib-card-visual .lib-card-body { padding: 14px 18px 18px; }
  .lib-card-top { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
  /* The question is now the card's eyebrow/title — smaller and clamped tighter,
     because the answer snippet is what a browser actually reads. */
  .lib-card h3 {
    font-family: 'Playfair Display', serif;
    font-size: 16px; font-weight: 600; line-height: 1.3;
    color: hsl(var(--pg-fg));
    margin: 0 0 8px;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .lib-card-snippet {
    font-size: 13px; line-height: 1.55; color: hsl(var(--pg-fg-muted));
    margin: 0 0 14px;
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
  }
  /* Meta pinned to the bottom (margin-top:auto), one quiet line instead of the
     old row of four pills. The universal "on-chain" chip is gone — everything
     here is on-chain, so it discriminated nothing; on-chain provenance now
     lives once, in the drawer. */
  .lib-card-meta {
    margin-top: auto; display: flex; align-items: center; gap: 7px;
    font-size: 11.5px; color: hsl(var(--pg-fg-subtle));
    font-family: 'JetBrains Mono', ui-monospace, monospace;
  }
  .lib-meta-dot { opacity: 0.5; }
  /* Overlapping favicon strip — Ground.news' "who's covering this" row,
     built from the same domain favicons the graph viewer draws on nodes. */
  .lib-card-favs { display: inline-flex; align-items: center; flex-shrink: 0; }
  .lib-card-favs img {
    width: 14px; height: 14px; border-radius: 50%; margin-left: -5px;
    border: 1.5px solid hsl(var(--pg-surface)); background: hsl(var(--pg-hover));
    object-fit: cover;
  }
  .lib-card-favs img:first-child { margin-left: 0; }
  :global(.lib-card-go) {
    margin-left: auto; color: hsl(var(--pg-fg-subtle));
    opacity: 0; transform: translateX(-4px);
    transition: opacity .14s, transform .14s;
  }
  .lib-card-btn:hover :global(.lib-card-go) { opacity: 1; transform: none; }

  .lib-chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .lib-chip {
    font-size: 10.5px; font-weight: 600; color: hsl(var(--pg-fg-muted));
    background: hsl(var(--pg-hover)); border-radius: 999px; padding: 3px 9px;
  }
  .lib-chip-chain { background: hsl(45 80% 88%); color: hsl(38 65% 30%); }
  .lib-chip-deep {
    display: inline-flex; align-items: center; gap: 4px;
    background: hsl(266 70% 94%); color: hsl(266 60% 42%); border: 1px solid hsl(266 55% 86%);
  }
  /* "Just in" — the incoming-news signal. On a thumbnail it's an overlay tag;
     on a plain card it's a chip with a live pulse dot. */
  .lib-chip-fresh {
    display: inline-flex; align-items: center; gap: 5px;
    background: hsl(150 60% 92%); color: hsl(150 70% 26%); border: 1px solid hsl(150 50% 78%);
  }
  .lib-fresh-dot {
    width: 6px; height: 6px; border-radius: 50%; background: hsl(150 70% 40%);
    box-shadow: 0 0 0 0 hsl(150 70% 40% / 0.6); animation: lib-fresh-pulse 2s infinite;
  }
  @keyframes lib-fresh-pulse {
    0% { box-shadow: 0 0 0 0 hsl(150 70% 40% / 0.5); }
    70% { box-shadow: 0 0 0 6px hsl(150 70% 40% / 0); }
    100% { box-shadow: 0 0 0 0 hsl(150 70% 40% / 0); }
  }
  .lib-fresh-tag {
    position: absolute; top: 10px; left: 10px; z-index: 1;
    font-size: 10.5px; font-weight: 700; letter-spacing: .03em;
    padding: 3px 9px; border-radius: 999px;
    background: hsl(150 70% 32%); color: hsl(150 60% 96%);
    box-shadow: 0 2px 8px -2px hsl(150 40% 15% / 0.5);
  }
  .lib-card-thumb { position: relative; }
  :global(.dark) .lib-chip-fresh {
    background: hsl(150 55% 22% / 0.5); color: hsl(150 70% 78%); border-color: hsl(150 45% 40%);
  }

  /* Deep Research section toggle — a distinct tab pair above the filter bar. */
  .lib-modebar { display: flex; gap: 8px; margin-bottom: 14px; }
  .lib-modetab {
    display: inline-flex; align-items: center; gap: 6px;
    border: 1px solid hsl(var(--pg-border)); background: hsl(var(--pg-elevated));
    border-radius: 999px; padding: 8px 16px; cursor: pointer;
    font: 600 13px Inter, system-ui, sans-serif; color: hsl(var(--pg-fg-muted));
    transition: border-color .14s, color .14s, background .14s;
  }
  .lib-modetab.on { color: hsl(var(--pg-fg)); border-color: hsl(45 75% 60%); background: hsl(var(--pg-surface)); }
  .lib-modetab-deep.on {
    color: hsl(266 60% 42%); border-color: hsl(266 60% 70%);
    background: hsl(266 70% 96%);
  }
  .lib-modecount {
    font-size: 10.5px; font-weight: 700; padding: 1px 7px; border-radius: 999px;
    background: hsl(266 60% 88%); color: hsl(266 55% 38%);
  }
  .lib-modehint { font-size: 12.5px; line-height: 1.55; color: hsl(var(--pg-fg-muted)); margin: -4px 0 16px; max-width: 60ch; }

  /* Deep card accent — a soft violet edge so a deep entry reads as richer. */
  .lib-card-deep { border-color: hsl(266 55% 84%); }
  .lib-card-deep:hover { border-color: hsl(266 60% 66%); }

  /* Vault CTA — the flagship way into a deep entry. */
  .lib-vault-btn {
    display: flex; align-items: center; gap: 12px; text-decoration: none;
    border: 1px solid hsl(266 55% 78%); border-radius: 13px; padding: 12px 14px;
    background: linear-gradient(120deg, hsl(266 70% 96%), hsl(266 60% 98%));
    color: hsl(266 60% 40%); margin: 0 0 14px;
    transition: border-color .14s, transform .14s;
  }
  .lib-vault-btn:hover { border-color: hsl(266 60% 58%); transform: translateY(-1px); }
  .lib-vault-btn-t { flex: 1; display: flex; flex-direction: column; gap: 1px; }
  .lib-vault-btn-t strong { font-size: 13.5px; }
  .lib-vault-btn-t small { font-size: 11px; color: hsl(266 30% 52%); }
  :global(.dark) .lib-vault-btn {
    background: linear-gradient(120deg, hsl(266 55% 30% / 0.35), hsl(266 55% 24% / 0.2));
    border-color: hsl(266 45% 48%); color: hsl(266 85% 85%);
  }
  :global(.dark) .lib-vault-btn-t small { color: hsl(266 40% 70%); }

  /* Drawer note pages — the research as a small notebook. */
  .lib-deep-lede { font-size: 13px; line-height: 1.6; color: hsl(var(--pg-fg-muted)); margin: 6px 0 12px; }
  .lib-pages { display: flex; flex-direction: column; gap: 8px; }
  .lib-page { border: 1px solid hsl(var(--pg-border)); border-radius: 12px; overflow: hidden; background: hsl(var(--pg-surface)); }
  .lib-page.open { border-color: hsl(266 55% 72%); }
  .lib-page-head {
    display: flex; align-items: center; gap: 11px; width: 100%; text-align: left;
    padding: 12px 14px; border: none; background: transparent; cursor: pointer; font: inherit;
  }
  .lib-page-n {
    flex-shrink: 0; width: 22px; height: 22px; border-radius: 7px;
    display: grid; place-items: center; font-size: 11px; font-weight: 700;
    background: hsl(266 60% 92%); color: hsl(266 55% 42%);
  }
  .lib-page-title { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .lib-page-t { font-size: 13.5px; font-weight: 600; color: hsl(var(--pg-fg)); }
  .lib-page-q {
    font-size: 11.5px; color: hsl(var(--pg-fg-muted)); overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap;
  }
  .lib-page-body { padding: 0 14px 14px 47px; }
  .lib-page-note { font-size: 13.5px; line-height: 1.68; color: hsl(var(--pg-fg)); margin: 0; white-space: pre-wrap; }
  /* Louder than the other chips on purpose: "a machine chose to ask this" is
     the one thing on this card a reader would want to know unprompted, and it
     should never be mistaken for a neutral metadata pill. */
  .lib-chip-ai {
    background: hsl(266 70% 95%); color: hsl(266 55% 40%);
    border: 1px solid hsl(266 55% 85%); cursor: help;
  }

  .lib-more {
    border: 1px solid hsl(var(--pg-border)); background: hsl(var(--pg-elevated)); border-radius: 999px;
    padding: 10px 22px; font: 600 13px Inter, system-ui, sans-serif;
    color: hsl(var(--pg-fg)); cursor: pointer;
  }

  .lib-empty {
    text-align: center; padding: 70px 20px;
    background: hsl(var(--pg-surface)); border: 1px dashed hsl(var(--pg-border)); border-radius: 1.75rem;
  }
  .lib-empty-glyph { font-size: 40px; color: hsl(45 80% 55%); margin-bottom: 12px; }
  .lib-empty h2 { font-family: 'Playfair Display', serif; font-size: 24px; margin: 0 0 8px; color: hsl(var(--pg-fg)); }
  .lib-empty p { font-size: 14px; line-height: 1.65; color: hsl(var(--pg-fg-muted)); max-width: 48ch; margin: 0 auto; }

  .lib-skel {
    display: inline-block; height: 14px; border-radius: 6px;
    background: linear-gradient(90deg, hsl(var(--pg-hover)) 25%, hsl(var(--pg-border)) 50%, hsl(var(--pg-hover)) 75%);
    background-size: 200% 100%;
    animation: lib-shimmer 1.4s ease-in-out infinite;
  }
  @keyframes lib-shimmer { to { background-position: -200% 0; } }

  /* ── Drawer ────────────────────────────────────────────────────────────── */
  .lib-drawer-backdrop {
    position: fixed; inset: 0; z-index: 60;
    background: hsl(24 48% 8% / 0.5);
    backdrop-filter: blur(4px);
  }
  .lib-drawer {
    position: fixed; z-index: 61;
    top: 0; right: 0; bottom: 0;
    width: min(520px, 94vw);
    background: hsl(var(--pg-surface));
    border-left: 1px solid hsl(var(--pg-border));
    box-shadow: -24px 0 60px -20px hsl(24 40% 8% / 0.4);
    padding: 26px 26px calc(26px + env(safe-area-inset-bottom, 0px));
    overflow-y: auto;
    animation: lib-drawer-in 0.24s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  @keyframes lib-drawer-in { from { transform: translateX(30px); opacity: 0; } }
  .lib-drawer-close {
    position: absolute; top: 16px; right: 16px;
    width: 32px; height: 32px; border: none; border-radius: 9px;
    background: hsl(var(--pg-hover)); color: hsl(var(--pg-fg-muted));
    cursor: pointer; display: grid; place-items: center;
  }
  /* The drawer becomes a bottom sheet on touch, where 32px is too small to
     hit reliably — and dismissing is the one thing that must always work. */
  @media (pointer: coarse) {
    .lib-drawer-close { width: 40px; height: 40px; }
  }
  .lib-drawer-q {
    font-family: 'Playfair Display', serif;
    font-size: 24px; font-weight: 700; line-height: 1.25;
    color: hsl(var(--pg-fg)); margin: 8px 0 12px;
  }
  /* "Coverage Details" strip — Ground.news' sidebar stat box, adapted to a
     single-column drawer: source count, how far back the evidence reaches,
     and a favicon row of who's cited. Only renders what enrichment provides,
     so a plain (pre-harvest) entry shows just the source count. */
  .lib-coverage {
    display: flex; align-items: center; flex-wrap: wrap; gap: 16px;
    margin: 4px 0 18px; padding: 12px 14px;
    background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border)); border-radius: 12px;
  }
  .lib-coverage-stat { display: flex; flex-direction: column; gap: 1px; }
  .lib-coverage-n { font-size: 15px; font-weight: 700; color: hsl(var(--pg-fg)); font-family: 'JetBrains Mono', ui-monospace, monospace; }
  .lib-coverage-label { font-size: 10.5px; text-transform: uppercase; letter-spacing: .05em; color: hsl(var(--pg-fg-muted)); }
  .lib-coverage-favs { display: inline-flex; align-items: center; margin-left: auto; }
  .lib-coverage-favs img {
    width: 20px; height: 20px; border-radius: 50%; margin-left: -6px;
    border: 2px solid hsl(var(--pg-elevated)); background: hsl(var(--pg-hover)); object-fit: cover;
  }
  .lib-coverage-favs img:first-child { margin-left: 0; }
  .lib-drawer-answer { font-size: 14.5px; line-height: 1.7; color: hsl(var(--pg-fg)); margin: 0; }
  .lib-muted { color: hsl(var(--pg-fg-muted)); font-style: italic; }
  .lib-sources { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
  .lib-sources a {
    display: flex; align-items: baseline; gap: 8px; text-decoration: none;
    font-size: 13px; color: hsl(var(--pg-fg));
  }
  .lib-src-n { color: hsl(var(--pg-fg-muted)); font-size: 11px; flex-shrink: 0; }
  .lib-src-t { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .lib-src-d { color: hsl(var(--pg-fg-muted)); font-size: 11px; font-family: 'JetBrains Mono', monospace; flex-shrink: 0; }
  /* Publish date from the Brave harvest (only when the entry graph carried it). */
  .lib-src-age {
    color: hsl(45 60% 45%); font-size: 10.5px; font-family: 'JetBrains Mono', monospace;
    flex-shrink: 0; white-space: nowrap;
  }
  :global(.dark) .lib-src-age { color: hsl(45 70% 60%); }

  /* "People also wonder" — follow-up questions the web raised, each a one-tap
     search. The graph's ghost nodes, surfaced for readers who never open it. */
  .lib-ask-lede { font-size: 12.5px; line-height: 1.55; color: hsl(var(--pg-fg-muted)); margin: 4px 0 10px; }
  .lib-ask-chips { display: flex; flex-direction: column; gap: 7px; }
  .lib-ask-chip {
    display: flex; align-items: flex-start; gap: 7px; text-align: left; width: 100%;
    border: 1px solid hsl(266 40% 82%); border-radius: 11px; padding: 9px 12px;
    background: hsl(266 60% 97%); color: hsl(266 45% 38%); cursor: pointer;
    font: 500 13px Inter, system-ui, sans-serif; line-height: 1.4;
    transition: border-color .14s, transform .14s, background .14s;
  }
  .lib-ask-chip:hover { border-color: hsl(266 55% 62%); background: hsl(266 65% 95%); transform: translateY(-1px); }
  .lib-ask-chip span { color: hsl(45 75% 50%); }
  :global(.dark) .lib-ask-chip {
    background: hsl(266 45% 26% / 0.35); border-color: hsl(266 40% 46%); color: hsl(266 80% 84%);
  }
  :global(.dark) .lib-ask-chip:hover { background: hsl(266 45% 30% / 0.5); border-color: hsl(266 55% 60%); }
  .lib-drawer-graph {
    width: 100%; height: 260px; border: 1px solid hsl(var(--pg-border)); border-radius: 14px;
    background: hsl(250 30% 7%); margin-top: 8px;
  }
  .lib-drawer-actions { display: flex; gap: 16px; margin-top: 10px; font-size: 12.5px; }
  .lib-comment-err {
    margin: 24px 0 -8px; padding: 8px 12px; font-size: 12.5px;
    background: hsl(0 60% 96%); color: hsl(0 55% 38%); border: 1px solid hsl(0 55% 85%); border-radius: 8px;
  }
  :global(.dark) .lib-comment-err { background: hsl(0 45% 22% / 0.4); color: hsl(0 70% 82%); border-color: hsl(0 45% 40%); }
  .lib-drawer-actions .lib-link { color: hsl(38 65% 35%); }

  /* ── Mobile: the feed becomes a news river ────────────────────────────── */
  @media (max-width: 640px) {
    .lib-hero { min-height: 360px; }
    .lib-hero-content { padding: 130px 18px 22px; }
    .lib-drawer {
      top: auto; left: 0; right: 0; width: auto;
      max-height: 86dvh;
      border-left: none; border-top: 1px solid hsl(var(--pg-border));
      border-radius: 22px 22px 0 0;
      animation: lib-sheet-in 0.26s cubic-bezier(0.2, 0.8, 0.2, 1);
    }
    @keyframes lib-sheet-in { from { transform: translateY(40px); opacity: 0; } }
    .lib-graph-open { top: 12px; right: 12px; }

    /* The river: no per-card gap, hairline dividers instead — a scannable
       list, not a stack of full-screen slabs. */
    .lib-feed { gap: 0; }

    /* Lead story keeps the big treatment: full-width thumbnail, large
       headline — the one story the editor put above the fold. */
    .lib-feed .lib-lead h3 { font-size: 21px; -webkit-line-clamp: 3; }
    .lib-feed .lib-lead .lib-card-thumb { aspect-ratio: 16 / 10; }
    .lib-feed .lib-lead { margin-bottom: 4px; }

    /* Every card after the lead collapses to a compact headline row:
       flat (no card chrome), a small square thumbnail on the right, a
       2–3 line headline and one quiet meta line on the left. */
    .lib-feed .lib-card:not(.lib-lead) {
      border: none; border-radius: 0; box-shadow: none; background: transparent;
      border-bottom: 1px solid hsl(var(--pg-border));
      padding: 15px 2px;
    }
    .lib-feed .lib-card:not(.lib-lead).lib-card-visual {
      overflow: visible;
      flex-direction: row-reverse; align-items: flex-start; gap: 13px;
    }
    .lib-feed .lib-card:not(.lib-lead) .lib-card-thumb {
      width: 92px; min-width: 92px; aspect-ratio: 1;
      border-radius: 12px; align-self: flex-start;
    }
    .lib-feed .lib-card:not(.lib-lead).lib-card-visual .lib-card-body { padding: 0; }
    .lib-feed .lib-card:not(.lib-lead) h3 {
      font-size: 16px; line-height: 1.32; -webkit-line-clamp: 3; margin-bottom: 7px;
    }
    /* One line of context is enough on a row; three would rebuild the slab. */
    .lib-feed .lib-card:not(.lib-lead) .lib-card-snippet { display: none; }
    .lib-feed .lib-card:not(.lib-lead) .lib-fresh-tag {
      top: 5px; left: 5px; font-size: 9px; padding: 2px 6px;
    }
    /* Touch has no hover — kill the lift so rows sit flat and calm. */
    .lib-feed .lib-card:not(.lib-lead):hover {
      transform: none; box-shadow: none; border-color: transparent;
      border-bottom-color: hsl(var(--pg-border));
    }
    :global(.lib-card-go) { display: none; }
    .lib-feed .lib-card:not(.lib-lead):active { background: hsl(var(--pg-hover)); }

    /* Section controls stop stacking into a tall wall: the sort dropdown
       sits inline with a shrinking filter field. */
    .lib-browse-title { font-size: 19px; }
    .lib-filterbar { gap: 8px; }
    .lib-sort-select { font-size: 12px; padding: 8px 10px; }
  }

  @media (prefers-reduced-motion: reduce) {
    .lib-pulse-dot, .lib-skel { animation: none; }
    .lib-drawer { animation: none; }
    .lib-card-btn { transition: none; }
  }

  /* Dark-mode text/fills for the branded pills + gold links. Their light
     values (pale-gold / pale-purple washes with dark ink) would read as loud
     bright chips on the dark cards, so flip to translucent fills + light ink.
     Everything else flips automatically via the --pg-* tokens above. */
  :global(.dark) .lib-chip-chain {
    background: hsl(45 85% 55% / 0.16);
    color: hsl(45 88% 72%);
  }
  :global(.dark) .lib-chip-ai {
    background: hsl(266 55% 32% / 0.4);
    color: hsl(266 85% 85%);
    border-color: hsl(266 45% 48%);
  }
  :global(.dark) .lib-filter-reset-link { color: hsl(45 85% 64%); }
  :global(.dark) .lib-drawer-actions .lib-link { color: hsl(45 85% 66%); }
  :global(.dark) .lib-chip-deep {
    background: hsl(266 55% 32% / 0.4); color: hsl(266 85% 85%); border-color: hsl(266 45% 48%);
  }
  :global(.dark) .lib-modetab-deep.on {
    background: hsl(266 55% 30% / 0.35); color: hsl(266 85% 84%); border-color: hsl(266 50% 52%);
  }
  :global(.dark) .lib-modecount { background: hsl(266 55% 40% / 0.5); color: hsl(266 85% 86%); }
  :global(.dark) .lib-card-deep { border-color: hsl(266 45% 40% / 0.6); }
  :global(.dark) .lib-card-deep:hover { border-color: hsl(266 55% 58%); }
  :global(.dark) .lib-page.open { border-color: hsl(266 50% 52%); }
  :global(.dark) .lib-page-n { background: hsl(266 55% 38% / 0.5); color: hsl(266 85% 85%); }
</style>
