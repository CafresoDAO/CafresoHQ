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
  import { trapFocus } from '$lib/actions/trapFocus.js';
  import {
    libraryIndex, libraryEntry, networkHealth, findPublic, submitJob, awaitJob, libraryResearch
  } from '$lib/api/searchNetwork.js';
  import { libraryGraphViewerUrl, libraryMergedGraphViewerUrl, graphViewerOrigin } from '$lib/api/library.js';
  import { fmtNsDate } from '$lib/utils/time.js';

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

  const mergedGraphUrl = libraryMergedGraphViewerUrl();
  let heroIframe;   // bound to the hero graph iframe; used to gate postMessage

  $: {
    const e = $page.url.searchParams.get('e');
    if (e !== drawerId) { drawerId = e; loadDrawer(e); }
  }

  async function loadDrawer(id) {
    drawerEntry = null;
    drawerMissing = false;
    drawerResearch = null;
    openPageId = null;
    if (!id) return;
    const e = await libraryEntry(id);
    if (id !== drawerId) return;
    if (e && e.id) {
      drawerEntry = e;
      // Deep entries carry a browsable set of note pages — load them so the
      // drawer can show the research as pages, not just one synthesized answer.
      if (e.mode === 'deep') {
        const r = await libraryResearch(id);
        if (id === drawerId && r && r.pages) drawerResearch = r;
      }
    } else drawerMissing = true;
  }
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
    const t = setInterval(refresh, 60_000);
    window.addEventListener('message', onGraphMessage);
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

  function plain(t) { return String(t || '').replace(/<[^>]+>/g, ''); }
  const fmtDate = (ns) => fmtNsDate(ns, 'short');
  function shortPrincipal(p) {
    if (!p) return '';
    return p.length > 12 ? p.slice(0, 5) + '…' + p.slice(-3) : p;
  }
  function domain(url) {
    try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; }
  }
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

      {#if mergedGraphUrl && index && index.count > 0}
        <a class="lib-graph-open" href={mergedGraphUrl} target="_blank" rel="noopener noreferrer">
          Explore the full web <Icon name="arrow-up-right" size={12} />
        </a>
      {/if}
    </div>
  </div>

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
        <a href={mergedGraphUrl} target="_blank" rel="noopener noreferrer" class="lib-link">explore it visually in the graph ↑</a>
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
      <div class="lib-grid">
        {#each filteredEntries.slice(0, shown) as e (e.id)}
          <button class="lib-card lib-card-btn" class:lib-card-deep={e.mode === 'deep'} on:click={() => openEntry(e.id)}>
            {#if e.mode === 'deep' || e.askedBy === 'ai-gap'}
              <div class="lib-card-top">
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
              <span>{fmtDate(e.ts)}</span>
              <span class="lib-meta-dot" aria-hidden="true">·</span>
              <span>{e.sources} source{e.sources === 1 ? '' : 's'}</span>
              <Icon name="arrow-right" size={13} class="lib-card-go" />
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
      <div class="lib-kicker">Library entry · {drawerEntry.id}</div>
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

      {#if drawerEntry.answer}
        <p class="lib-drawer-answer">{plain(drawerEntry.answer)}</p>
      {:else}
        <p class="lib-drawer-answer lib-muted">Sources were collected for this question, but no summary was written yet.</p>
      {/if}

      {#if drawerEntry.sources?.length}
        <div class="lib-kicker" style="margin-top: 22px;">Sources</div>
        <ol class="lib-sources">
          {#each drawerEntry.sources as s, i}
            <li>
              <a href={s.url} target="_blank" rel="noopener noreferrer">
                <span class="lib-src-n">[{i + 1}]</span>
                <span class="lib-src-t">{plain(s.title)}</span>
                <span class="lib-src-d">{domain(s.url)}</span>
              </a>
            </li>
          {/each}
        </ol>
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
                          <a href={s.url} target="_blank" rel="noopener noreferrer">
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
  .lib-drawer-graph {
    width: 100%; height: 260px; border: 1px solid hsl(var(--pg-border)); border-radius: 14px;
    background: hsl(250 30% 7%); margin-top: 8px;
  }
  .lib-drawer-actions { display: flex; gap: 16px; margin-top: 10px; font-size: 12.5px; }
  .lib-drawer-actions .lib-link { color: hsl(38 65% 35%); }

  /* ── Mobile: drawer becomes a bottom sheet; hero tightens ─────────────── */
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
