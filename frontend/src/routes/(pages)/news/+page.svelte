<script>
  /* THE NEWSROOM — the Ground.news-style river over the same on-chain
     library data as /library. This page owns the "what's happening, skim
     it fast" presentation (thumbnail cards, freshness badges, the weekly
     digest); /library is the calm, evergreen reference view of the exact
     same entries with none of the urgency framing. Deliberately a near-full
     duplicate of /library/+page.svelte rather than a shared component tree
     — the two pages' visual languages are different enough (skim-feed vs.
     reference-list) that forcing one parameterized component would fight
     itself on every future edit. Shared destinations both pages link to
     (the full entry page /library/<id>, the research vault) stay pointed
     at /library on purpose — those are canonical, not per-surface.

     Hero = the merged graph (graph-viewer iframe over /library/graph.json)
     with a live search box wired to the same library-first → network-queue
     pipeline as the search modal. Below: the entry stream (newest first)
     with provenance chips; clicking opens a URL-addressable drawer
     (?e=<id>) with the full answer, sources, and the entry's own
     micro-graph. Must render beautifully at 0 entries — that is its launch
     state. */
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import Icon from '$lib/components/Icon.svelte';
  import CommentThread from '$lib/components/CommentThread.svelte';
  import UpNext from '$lib/components/UpNext.svelte';
  import WeeklyDigest from '$lib/components/WeeklyDigest.svelte';
  import RelatedEntries from '$lib/components/RelatedEntries.svelte';
  import { loadUpNext, addQuestion, normQ } from '$lib/stores/upnext.js';
  import { relatedEntries, findSimilarEntry } from '$lib/utils/digest.js';
  import { trapFocus } from '$lib/actions/trapFocus.js';
  import { listComments, postComment } from '$lib/api/devlog.js';
  import { principalText } from '$lib/stores/auth.js';
  import { profile } from '$lib/stores/profile.js';
  import {
    libraryIndex, libraryEntry, networkHealth, findPublic, submitJob, awaitJob, libraryResearch
  } from '$lib/api/searchNetwork.js';
  import { libraryGraphViewerUrl, libraryEntryEnrichment, libraryCardVisual } from '$lib/api/library.js';
  import { fmtNsDate, fmtNsRelative, nsToDate } from '$lib/utils/time.js';

  let index = null;          // null = loading, {count, entries} after
  let health = null;
  let shown = 24;            // client-side paging over the (≤500) index

  // Masthead date line — computed client-side only (onMount) so SSR and the
  // browser never disagree on "today" and cause a hydration mismatch.
  let todayLabel = '';

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
  // The lead story's thumbnail is the biggest single image on the page
  // (a 21:9 hero, not a small card square) — a broken/hotlink-blocked Brave
  // thumbnail there would reserve a huge blank void instead of a subtle gap.
  // Only commit the space once the image has actually confirmed it loads.
  let leadThumbLoaded = {};   // entry id -> true once its image has loaded
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
  let queuedForLater = false;   // "added to Up Next" confirmation when the network's asleep
  let similarMatch = null;      // a likely-duplicate entry found before submitting — see runSearch()

  // A dead network shouldn't be a dead end — the question a visitor typed
  // still has somewhere useful to go: the personal shortlist, ready to send
  // the moment a worker's back online.
  function saveForLater() {
    if (!q.trim()) return;
    addQuestion(q);
    queuedForLater = true;
  }

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

  // The neural-web hero graph is Library's signature visual, not News' — a
  // force-directed graph of 300+ nodes is the opposite of "skim it fast."
  // News keeps the per-entry answer graph in the drawer (small, contextual,
  // opt-in) but drops the marquee full-network view entirely.

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

  function openEntry(id) { goto(`/news?e=${encodeURIComponent(id)}`, { noScroll: true }); }
  function closeDrawer() { goto('/news', { noScroll: true }); }
  function onKeydown(e) { if (e.key === 'Escape' && drawerId) closeDrawer(); }

  async function refresh() {
    const [ix, h] = await Promise.all([libraryIndex(), networkHealth()]);
    if (ix) index = ix;
    else if (index === null) index = { count: -1, entries: [] };   // unreachable → offline state
    if (h) health = h;
  }
  onMount(() => {
    todayLabel = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
    refresh();
    loadUpNext();   // hydrate the personal research shortlist (localStorage)
    const t = setInterval(refresh, 60_000);
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
    return () => { clearInterval(t); };
  });

  async function runSearch({ skipSimilarCheck = false } = {}) {
    const query = q.trim();
    if (!query || searchPhase === 'checking' || searchPhase === 'queued') return;
    const seq = ++searchSeq;
    searchPhase = 'checking';
    queuedForLater = false;
    similarMatch = null;
    const hit = await findPublic(query);
    if (seq !== searchSeq) return;
    if (hit && hit.id) { searchPhase = 'idle'; openEntry(hit.id); return; }
    // Catches paraphrases the canister's exact-normalized dedup can't see —
    // before spending a Brave query on a question that's likely answered
    // under different wording. Skippable: a real near-miss (rare, by design —
    // findSimilarEntry favors precision) shouldn't trap someone who really
    // does mean something new.
    if (!skipSimilarCheck && index?.entries) {
      const near = findSimilarEntry(query, index.entries);
      if (near) { similarMatch = near; searchPhase = 'similar'; return; }
    }
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

  // "Related in the library" for the drawer — the index is already in memory
  // here (unlike the standalone /library/[id] page, which fetches it itself).
  $: drawerRelated = drawerEntry && index?.entries ? relatedEntries(drawerEntry, index.entries) : [];

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
  // Day-bucket headers for the river — "TODAY" / "YESTERDAY" / a weekday —
  // so an infinite chronological list reads as dated editions instead of
  // one undifferentiated scroll. Only meaningful on the default newest-first
  // feed (see leadMode below); sorting by sources or filtering breaks the
  // chronological assumption a day header implies.
  function dayBucket(ns) {
    const d = nsToDate(ns);
    if (!d) return '';
    const startOf = (dt) => { const c = new Date(dt); c.setHours(0, 0, 0, 0); return c.getTime(); }
    const days = Math.round((startOf(new Date()) - startOf(d)) / 86_400_000);
    if (days <= 0) return 'Today';
    if (days === 1) return 'Yesterday';
    if (days < 7) return d.toLocaleDateString(undefined, { weekday: 'long' });
    return d.toLocaleDateString(undefined, { month: 'long', day: 'numeric' });
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
  <title>Newsroom — Ai Cafreso</title>
  <meta name="description" content="What the Cafreso search network is answering right now — a live, skimmable feed over the same permanent on-chain library." />
</svelte:head>

<svelte:window on:keydown={onKeydown} />

<section class="space-y-8">
  <!-- ── Masthead: the one thing a Library card grid could never look like ──
       A real newspaper nameplate — edition line, serif wordmark, hairline
       double rule — so /news reads as a distinct publication the instant it
       loads, before a single card renders. -->
  <div class="news-masthead">
    <div class="news-masthead-top">
      <span>Live Edition</span>
      <span class="news-masthead-date">{todayLabel || ' '}</span>
      <span>{index && index.count > 0 ? `Vol. ${index.count.toLocaleString()}` : ' '}</span>
    </div>
    <div class="news-nameplate">The Cafreso Newsroom</div>
    <div class="news-masthead-rule"></div>
  </div>

  <!-- ── Hero: editorial header + vitals, no graph ───────────────────────────
       The neural-web hero was Library's signature visual, borrowed wholesale —
       a 300+ node force graph is the opposite of "skim it fast." Dropped
       entirely: no iframe, no dark cosmic panel, no "explore the full graph"
       detour. What replaces it is what a reader actually wants at a glance —
       a headline, a way to ask something, and three numbers that say whether
       the network is alive right now. -->
  <div class="news-hero">
    <h1 class="news-hero-title">What the network is answering right now<span class="news-hero-dot">.</span></h1>
    <p class="news-hero-sub">
      A live feed over the permanent library — every answer here stays forever at
      <a href="/library" class="news-hero-link">the calm reference view</a>.
    </p>

    <form class="news-search" on:submit|preventDefault={runSearch}>
      <Icon name="magnifying-glass" size={18} style="color: hsl(var(--pg-fg-subtle)); flex-shrink: 0;" />
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

    {#if searchPhase === 'similar' && similarMatch}
      <div class="news-search-note">
        <Icon name="magnifying-glass" size={14} style="flex-shrink: 0;" />
        Looks like this may already be answered:
        <button class="news-hero-link" style="border: none; background: transparent; cursor: pointer; font: inherit; padding: 0;"
                on:click={() => { searchPhase = 'idle'; openEntry(similarMatch.id); }}>
          "{plain(similarMatch.query).slice(0, 70)}{plain(similarMatch.query).length > 70 ? '…' : ''}"
        </button>
        — view it, or
        <button class="news-hero-link" style="border: none; background: transparent; cursor: pointer; font: inherit; padding: 0;"
                on:click={() => runSearch({ skipSimilarCheck: true })}>
          search anyway
        </button>.
      </div>
    {:else if searchPhase === 'queued'}
      <div class="news-search-note">
        <span class="lib-pulse-dot"></span>
        {#if queueNote === 'slow'}
          Still working — this one's a slow one. The answer joins the library either way,
          so you can leave this page and find it here.
        {:else}
          The research network is on it — {queueNote}. Fresh answers usually land in a few seconds and join the web forever.
        {/if}
      </div>
    {:else if searchPhase === 'rejected'}
      <div class="news-search-note news-warn">
        {rejectReason === 'busy' ? 'The network is at capacity — try again in a minute.'
          : rejectReason === 'budget' ? "Today's research budget is spent — back tomorrow."
          : rejectReason === 'timeout' ? 'Still researching — your answer will appear in the stream below when it lands.'
          : "The network couldn't answer that one — try rephrasing."}
      </div>
    {:else if searchPhase === 'dark'}
      <div class="news-search-note news-warn">
        {#if queuedForLater}
          <Icon name="check-circle" size={14} style="flex-shrink: 0;" />
          Added to your Up Next shortlist below — send it the moment a worker's back online.
        {:else}
          The research network is asleep — no workers online.
          <button class="news-hero-link" style="border: none; background: transparent; cursor: pointer; font: inherit; padding: 0;"
                  on:click={saveForLater}>
            Add "{plain(q).slice(0, 40)}{plain(q).length > 40 ? '…' : ''}" to Up Next
          </button>
          instead, or <a href="/hq/search" class="news-hero-link">sign in to search with your own container</a>.
        {/if}
      </div>
    {/if}

    <!-- Vitals — the three numbers that answer "is this thing alive?" at a
         glance, replacing the graph as the hero's data payload. -->
    <div class="news-vitals" aria-live="polite">
      {#if index === null}
        <span class="lib-skel" style="width: 260px; height: 34px;"></span>
      {:else if index.count > 0}
        <div class="news-vital">
          <span class="news-vital-n">{index.count.toLocaleString()}</span>
          <span class="news-vital-label">Answered on-chain</span>
        </div>
        {#if health}
          <div class="news-vital">
            <span class="news-vital-n" class:news-vital-live={health.activeWorkers > 0}>
              {#if health.activeWorkers > 0}<span class="lib-pulse-dot" style="margin-right: 6px;"></span>{/if}{health.activeWorkers}
            </span>
            <span class="news-vital-label">{health.activeWorkers > 0 ? (health.activeWorkers === 1 ? 'Worker online' : 'Workers online') : 'Network asleep'}</span>
          </div>
          <div class="news-vital">
            <span class="news-vital-n">{health.answeredToday}</span>
            <span class="news-vital-label">Answered today</span>
          </div>
        {/if}
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
    <div class="lib-browse-head">
      <h2 class="lib-browse-title">Full coverage</h2>
      <p class="lib-browse-sub">Every question the network has answered — filter or sort below.</p>
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
      <!-- The river. This is the whole point of the redesign: no card grid,
           no rounded chips — a real front page. One big lead story (headline,
           dek, byline) earned only on the default newest/unfiltered feed,
           then every story after it as a numbered briefing row: red running
           number, serif headline, one quiet byline line, a small thumbnail
           if the entry has one. Filter or sort and the lead drops out —
           every row goes back to equal weight, the way a search result
           should. -->
      {@const leadMode = sortBy === 'newest' && modeFilter === 'all' && !filterText.trim()}
      {@const lead = leadMode ? filteredEntries[0] : null}
      {@const rest = lead ? filteredEntries.slice(1, shown) : filteredEntries.slice(0, shown)}

      {#if lead}
        {@const visual = cardVisuals[lead.id]}
        <button class="news-lead" on:click={() => openEntry(lead.id)}>
          {#if visual?.thumb}
            <img src={visual.thumb} alt="" class="news-thumb-probe"
                 on:load={() => (leadThumbLoaded = { ...leadThumbLoaded, [lead.id]: true })} />
            {#if leadThumbLoaded[lead.id]}
              <div class="news-lead-thumb" style="background-image:url('{visual.thumb}')" role="presentation"></div>
            {/if}
          {/if}
          <div class="news-lead-body">
            <div class="news-row-tags">
              {#if isFresh(lead.ts)}<span class="news-tag news-tag-live"><span class="news-tag-dot" aria-hidden="true"></span> Just In</span>{/if}
              {#if lead.mode === 'deep'}<span class="news-tag"><Icon name="tree-structure" size={10} /> Deep Research</span>{/if}
              {#if lead.askedBy === 'ai-gap'}<span class="news-tag" title="Nobody asked this one. Cafreso read the library, found a gap in what it covers, and asked to fill it.">✦ Asked by Cafreso</span>{/if}
            </div>
            <h2 class="news-lead-headline">{plain(lead.query)}</h2>
            {#if lead.snippet}<p class="news-lead-dek">{plain(lead.snippet)}</p>{/if}
            <div class="news-byline">
              <span>{relTime(lead.ts)}</span>
              <span class="news-byline-dot" aria-hidden="true">—</span>
              <span>{lead.sources} source{lead.sources === 1 ? '' : 's'}</span>
              <span class="news-byline-dot" aria-hidden="true">—</span>
              <span>{engineLabel(lead)}</span>
              <Icon name="arrow-right" size={12} class="news-row-go" />
            </div>
          </div>
        </button>
      {/if}

      <ol class="news-river">
        {#each rest as e, i (e.id)}
          {@const visual = cardVisuals[e.id]}
          {@const fresh = isFresh(e.ts)}
          {@const bucket = leadMode ? dayBucket(e.ts) : null}
          {@const prevBucket = leadMode && i > 0 ? dayBucket(rest[i - 1].ts) : (leadMode ? dayBucket(lead.ts) : null)}
          {#if bucket && bucket !== prevBucket}
            <li class="news-day-sep" aria-hidden="true"><span>{bucket}</span></li>
          {/if}
          <li>
            <button class="news-row" class:news-row-deep={e.mode === 'deep'} on:click={() => openEntry(e.id)}>
              <span class="news-row-n" aria-hidden="true">{String((lead ? i + 2 : i + 1)).padStart(2, '0')}</span>
              <div class="news-row-body">
                <div class="news-row-tags">
                  {#if fresh}<span class="news-tag news-tag-live"><span class="news-tag-dot" aria-hidden="true"></span> Just In</span>{/if}
                  {#if e.mode === 'deep'}<span class="news-tag"><Icon name="tree-structure" size={10} /> Deep Research</span>{/if}
                  {#if e.askedBy === 'ai-gap'}<span class="news-tag" title="Nobody asked this one. Cafreso read the library, found a gap in what it covers, and asked to fill it.">✦ Asked by Cafreso</span>{/if}
                </div>
                <h3>{plain(e.query)}</h3>
                <div class="news-byline">
                  <span>{relTime(e.ts)}</span>
                  <span class="news-byline-dot" aria-hidden="true">—</span>
                  <span>{e.sources} source{e.sources === 1 ? '' : 's'}</span>
                  <Icon name="arrow-right" size={12} class="news-row-go" />
                </div>
              </div>
              {#if visual?.thumb}
                <div class="news-row-thumb" style="background-image:url('{visual.thumb}')" role="presentation"></div>
              {/if}
            </button>
          </li>
        {/each}
      </ol>

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

      {#if drawerRelated.length}
        <div style="margin-top: 22px;">
          <RelatedEntries items={drawerRelated} {plain} onOpen={openEntry} />
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
            on:click={() => { try { navigator.clipboard.writeText(location.origin + '/news?e=' + drawerEntry.id); } catch {} }}>
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
  /* ── Masthead — a real nameplate, the fastest way to make this page not
       look like a re-skinned Library. Red is the one accent Library never
       uses (its whole palette is warm gold-on-cream/dark) — reserved here
       for the wire-service signals: live dot, running numbers, dek rule. */
  .news-masthead { text-align: center; padding: 4px 10px 0; }
  .news-masthead-top {
    display: flex; align-items: center; justify-content: center; gap: 14px;
    font: 700 10.5px/1 'JetBrains Mono', ui-monospace, monospace;
    letter-spacing: 0.08em; text-transform: uppercase;
    color: hsl(var(--pg-fg-muted));
    margin-bottom: 10px;
  }
  .news-masthead-date { color: hsl(355 65% 48%); }
  :global(.dark) .news-masthead-date { color: hsl(355 80% 68%); }
  .news-nameplate {
    font-family: 'Playfair Display', serif;
    font-weight: 900;
    font-size: clamp(2rem, 6vw, 3.4rem);
    letter-spacing: -0.01em;
    color: hsl(var(--pg-fg));
    line-height: 1;
  }
  .news-masthead-rule {
    height: 5px; margin: 14px auto 0; max-width: 100%;
    border-top: 3px solid hsl(var(--pg-fg));
    border-bottom: 1px solid hsl(var(--pg-fg));
  }

  /* Still used outside the hero — the drawer's section labels and inline links. */
  .lib-kicker {
    font-size: 11px; font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase;
    color: hsl(355 55% 45%);
  }
  :global(.dark) .lib-kicker { color: hsl(355 75% 68%); }
  .lib-link { color: hsl(355 60% 45%); font-weight: 600; text-decoration: none; display: inline-flex; align-items: center; gap: 3px; }
  :global(.dark) .lib-link { color: hsl(355 80% 70%); }

  /* ── Hero — plain paper, no graph. The masthead above already carries the
     "this is a different publication" signal; the hero's whole job now is
     legibility and three digestible numbers, not a backdrop. ──────────── */
  .news-hero { padding: 6px 4px 8px; max-width: 680px; margin: 0 auto; text-align: center; }
  .news-hero-title {
    font-family: 'Playfair Display', serif;
    font-size: clamp(1.7rem, 4vw, 2.6rem); font-weight: 700; line-height: 1.15;
    color: hsl(var(--pg-fg)); margin: 0 0 10px;
  }
  .news-hero-dot { color: hsl(355 60% 50%); }
  .news-hero-sub { font-size: 14.5px; line-height: 1.6; color: hsl(var(--pg-fg-muted)); margin: 0 auto 22px; max-width: 46ch; }
  .news-hero-link { color: hsl(355 60% 45%); font-weight: 600; text-decoration: underline; text-underline-offset: 2px; }
  :global(.dark) .news-hero-link { color: hsl(355 80% 70%); }

  .news-search {
    display: flex; align-items: center; gap: 10px;
    max-width: 560px; margin: 0 auto;
    background: hsl(var(--pg-surface));
    border: 1.5px solid hsl(var(--pg-border));
    border-radius: 16px;
    padding: 6px 8px 6px 16px;
    transition: border-color 0.15s;
  }
  .news-search:focus-within { border-color: hsl(355 55% 55%); }
  .news-search input {
    flex: 1; min-width: 0; border: none; background: transparent; outline: none;
    font: 500 16px/1.4 Inter, system-ui, sans-serif; color: hsl(var(--pg-fg)); padding: 8px 0;
  }
  .news-search input::placeholder { color: hsl(var(--pg-fg-subtle)); }
  .news-search button {
    border: none; border-radius: 11px; cursor: pointer;
    background: hsl(var(--pg-fg)); color: hsl(var(--pg-surface));
    font: 700 13.5px Inter, system-ui, sans-serif;
    padding: 10px 20px;
    transition: filter 0.15s;
  }
  .news-search button:hover:not(:disabled) { filter: brightness(1.2); }
  .news-search button:disabled { opacity: 0.45; cursor: default; }

  .news-search-note {
    display: flex; align-items: center; justify-content: center; gap: 8px;
    margin: 12px auto 0; font-size: 12.5px; color: hsl(var(--pg-fg-muted)); max-width: 560px; line-height: 1.5;
  }
  .news-search-note.news-warn { color: hsl(35 70% 42%); }
  :global(.dark) .news-search-note.news-warn { color: hsl(35 80% 68%); }

  /* Vitals — three numbers instead of a graph: is the network alive, right now. */
  .news-vitals {
    display: flex; align-items: flex-start; justify-content: center;
    gap: 36px; margin-top: 26px; padding-top: 22px;
    border-top: 1px solid hsl(var(--pg-border));
  }
  .news-vital { display: flex; flex-direction: column; align-items: center; gap: 3px; }
  .news-vital-n {
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    font-size: 22px; font-weight: 700; color: hsl(var(--pg-fg));
    display: inline-flex; align-items: center;
  }
  .news-vital-n.news-vital-live { color: hsl(150 60% 38%); }
  :global(.dark) .news-vital-n.news-vital-live { color: hsl(150 65% 62%); }
  .news-vital-label {
    font-size: 10.5px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
    color: hsl(var(--pg-fg-muted));
  }
  .lib-pulse-dot {
    width: 7px; height: 7px; border-radius: 50%; background: hsl(150 70% 45%);
    box-shadow: 0 0 8px hsl(150 70% 45% / 0.7);
    animation: lib-pulse 1.6s ease-in-out infinite;
    flex-shrink: 0; display: inline-block;
  }
  @keyframes lib-pulse { 50% { opacity: 0.35; } }
  @media (max-width: 560px) { .news-vitals { gap: 24px; } .news-vital-n { font-size: 19px; } }

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

  /* ── The river — flat editorial rows, not rounded cards ─────────────────
     This (plus the masthead) is the redesign: no lib-card grid, no pill
     chips, no drop shadows. A lead story, then a numbered list separated by
     hairlines — a wire feed, not a mood board. */
  .news-tag {
    display: inline-flex; align-items: center; gap: 4px;
    font: 700 10px/1 'JetBrains Mono', ui-monospace, monospace;
    letter-spacing: 0.04em; text-transform: uppercase;
    color: hsl(var(--pg-fg-muted));
  }
  .news-tag-live { color: hsl(355 65% 48%); }
  :global(.dark) .news-tag-live { color: hsl(355 80% 68%); }
  .news-tag-dot {
    width: 6px; height: 6px; border-radius: 50%; background: currentColor;
    box-shadow: 0 0 0 0 hsl(355 70% 50% / 0.6); animation: news-live-pulse 1.8s infinite;
  }
  @keyframes news-live-pulse {
    0% { box-shadow: 0 0 0 0 hsl(355 70% 50% / 0.5); }
    70% { box-shadow: 0 0 0 5px hsl(355 70% 50% / 0); }
    100% { box-shadow: 0 0 0 0 hsl(355 70% 50% / 0); }
  }
  .news-byline {
    display: flex; align-items: center; gap: 7px; flex-wrap: wrap;
    font: 500 11.5px/1 'JetBrains Mono', ui-monospace, monospace;
    color: hsl(var(--pg-fg-subtle)); margin-top: 8px;
  }
  .news-byline-dot { opacity: 0.5; }
  :global(.news-row-go) {
    margin-left: auto; color: hsl(355 60% 50%);
    opacity: 0; transform: translateX(-4px);
    transition: opacity .14s, transform .14s;
  }

  /* Lead story — the one thing above the fold. Flat, full-bleed, no card
     chrome; a hairline rule underneath is the only border it gets. */
  .news-lead {
    display: block; width: 100%; text-align: left; cursor: pointer;
    background: none; border: none; padding: 0 0 26px;
    border-bottom: 3px solid hsl(var(--pg-fg));
    font: inherit; color: inherit;
  }
  .news-thumb-probe { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
  .news-lead-thumb {
    width: 100%; aspect-ratio: 21 / 9; max-height: 420px; border-radius: 10px;
    background-size: cover; background-position: center;
    background-color: hsl(var(--pg-hover)); border: 1px solid hsl(var(--pg-border));
    margin-bottom: 18px;
  }
  .news-row-tags { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; }
  .news-lead-headline {
    font-family: 'Playfair Display', serif;
    font-size: clamp(1.5rem, 3.4vw, 2.5rem); font-weight: 800; line-height: 1.1;
    color: hsl(var(--pg-fg)); margin: 0 0 10px;
  }
  .news-lead-dek {
    font-family: 'Playfair Display', serif; font-style: italic;
    font-size: 16px; line-height: 1.55; color: hsl(var(--pg-fg-muted));
    max-width: 70ch; margin: 0;
  }
  .news-lead:hover .news-lead-headline { text-decoration: underline; text-decoration-color: hsl(355 60% 50% / 0.5); text-underline-offset: 4px; }
  .news-lead:hover :global(.news-row-go) { opacity: 1; transform: none; }

  .news-river { list-style: none; margin: 0; padding: 0; }
  .news-river li { border-bottom: 1px solid hsl(var(--pg-border)); }
  .news-river li:last-child { border-bottom: none; }
  /* Day-bucket header — turns an endless chronological scroll into dated
     editions a reader can actually orient inside. No bottom rule of its own;
     the row below it still gets the normal hairline. */
  .news-day-sep {
    border-bottom: none !important; padding: 22px 2px 8px;
  }
  .news-day-sep span {
    font: 800 11px/1 'JetBrains Mono', ui-monospace, monospace;
    letter-spacing: 0.1em; text-transform: uppercase;
    color: hsl(355 60% 50%);
  }
  .news-row {
    display: flex; align-items: flex-start; gap: 16px; width: 100%;
    text-align: left; cursor: pointer; background: none; border: none;
    padding: 18px 2px; font: inherit; color: inherit;
    transition: background .12s;
  }
  .news-row:hover { background: hsl(var(--pg-hover)); }
  .news-row-n {
    flex-shrink: 0; width: 28px; padding-top: 2px;
    font: 700 15px/1 'Playfair Display', serif; font-style: italic;
    color: hsl(355 60% 50%);
  }
  .news-row-body { flex: 1; min-width: 0; }
  .news-row h3 {
    font-family: 'Playfair Display', serif;
    font-size: 17px; font-weight: 700; line-height: 1.32;
    color: hsl(var(--pg-fg)); margin: 0;
  }
  .news-row:hover h3 { text-decoration: underline; text-decoration-color: hsl(355 60% 50% / 0.5); text-underline-offset: 3px; }
  .news-row:hover :global(.news-row-go) { opacity: 1; transform: none; }
  .news-row-thumb {
    flex-shrink: 0; width: 84px; height: 84px; border-radius: 8px;
    background-size: cover; background-position: center;
    background-color: hsl(var(--pg-hover));
  }
  .news-row-deep .news-row-n { color: hsl(266 55% 55%); }

  @media (max-width: 640px) {
    .news-lead-headline { font-size: 24px; }
    .news-lead-dek { font-size: 14px; }
    .news-row { gap: 12px; padding: 15px 0; }
    .news-row-thumb { width: 64px; height: 64px; }
    .news-masthead-top { gap: 8px; font-size: 9.5px; }
  }
  @media (prefers-reduced-motion: reduce) {
    .news-tag-dot { animation: none; }
  }

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
    .lib-drawer {
      top: auto; left: 0; right: 0; width: auto;
      max-height: 86dvh;
      border-left: none; border-top: 1px solid hsl(var(--pg-border));
      border-radius: 22px 22px 0 0;
      animation: lib-sheet-in 0.26s cubic-bezier(0.2, 0.8, 0.2, 1);
    }
    @keyframes lib-sheet-in { from { transform: translateY(40px); opacity: 0; } }

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
