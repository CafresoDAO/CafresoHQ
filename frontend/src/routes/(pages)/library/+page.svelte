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
    libraryIndex, libraryEntry, networkHealth, findPublic, submitJob, awaitJob
  } from '$lib/api/searchNetwork.js';
  import { libraryGraphViewerUrl, libraryMergedGraphViewerUrl } from '$lib/api/library.js';

  let index = null;          // null = loading, {count, entries} after
  let health = null;
  let shown = 24;            // client-side paging over the (≤500) index

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

  const mergedGraphUrl = libraryMergedGraphViewerUrl();

  $: {
    const e = $page.url.searchParams.get('e');
    if (e !== drawerId) { drawerId = e; loadDrawer(e); }
  }

  async function loadDrawer(id) {
    drawerEntry = null;
    drawerMissing = false;
    if (!id) return;
    const e = await libraryEntry(id);
    if (id !== drawerId) return;
    if (e && e.id) drawerEntry = e; else drawerMissing = true;
  }

  function openEntry(id) { goto(`/library?e=${encodeURIComponent(id)}`, { noScroll: true }); }
  function closeDrawer() { goto('/library', { noScroll: true }); }
  function onKeydown(e) { if (e.key === 'Escape' && drawerId) closeDrawer(); }

  async function refresh() {
    const [ix, h] = await Promise.all([libraryIndex(), networkHealth()]);
    if (ix) index = ix;
    else if (index === null) index = { count: -1, entries: [] };   // unreachable → offline state
    if (h) health = h;
  }
  onMount(() => {
    refresh();
    const t = setInterval(refresh, 60_000);
    return () => clearInterval(t);
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
  function fmtDate(ns) {
    try { return new Date(Number(ns) / 1e6).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }); }
    catch { return ''; }
  }
  function shortPrincipal(p) {
    if (!p) return '';
    return p.length > 12 ? p.slice(0, 5) + '…' + p.slice(-3) : p;
  }
  function domain(url) {
    try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; }
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
          <div class="lib-skel" style="width: 85%; height: 20px; margin-bottom: 10px;"></div>
          <div class="lib-skel" style="width: 55%; height: 12px; margin-bottom: 16px;"></div>
          <div class="lib-skel" style="width: 40%; height: 12px;"></div>
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
    <div class="lib-grid">
      {#each index.entries.slice(0, shown) as e (e.id)}
        <button class="lib-card lib-card-btn" on:click={() => openEntry(e.id)}>
          <h3>{plain(e.query)}</h3>
          <div class="lib-chips">
            <span class="lib-chip">{fmtDate(e.ts)}</span>
            <span class="lib-chip">{e.sources} source{e.sources === 1 ? '' : 's'}</span>
            <span class="lib-chip lib-chip-chain">on-chain</span>
          </div>
        </button>
      {/each}
    </div>
    {#if index.entries.length > shown}
      <div style="text-align: center;">
        <button class="lib-more" on:click={() => (shown += 24)}>
          Show more ({index.entries.length - shown} remaining)
        </button>
      </div>
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
        {#if drawerEntry.model}<span class="lib-chip">🤖 {drawerEntry.model}</span>{/if}
        {#if drawerEntry.engine}<span class="lib-chip">🔎 {drawerEntry.engine}</span>{/if}
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

      {#if libraryGraphViewerUrl(drawerEntry.id)}
        <div class="lib-kicker" style="margin-top: 22px;">This answer as a graph</div>
        <iframe
          src={libraryGraphViewerUrl(drawerEntry.id)}
          title="Graph of this answer"
          class="lib-drawer-graph"
          loading="lazy"
        ></iframe>
        <div class="lib-drawer-actions">
          <a class="lib-link" href={libraryGraphViewerUrl(drawerEntry.id)} target="_blank" rel="noopener noreferrer">
            Open graph <Icon name="arrow-up-right" size={12} />
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
  .lib-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
    gap: 14px;
  }
  .lib-card {
    background: hsl(26 45% 98%);
    border: 1px solid hsl(26 30% 87%);
    border-radius: 18px;
    padding: 20px;
    box-shadow: 0 4px 18px -10px hsl(24 35% 15% / 0.15);
  }
  .lib-card-btn {
    text-align: left; cursor: pointer; font: inherit;
    transition: transform 0.14s, border-color 0.14s, box-shadow 0.14s;
  }
  .lib-card-btn:hover {
    transform: translateY(-2px);
    border-color: hsl(45 75% 60%);
    box-shadow: 0 12px 28px -12px hsl(24 35% 15% / 0.25);
  }
  .lib-card h3 {
    font-family: 'Playfair Display', serif;
    font-size: 17.5px; font-weight: 600; line-height: 1.35;
    color: hsl(222 47% 11%);
    margin: 0 0 12px;
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
  }
  .lib-chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .lib-chip {
    font-size: 10.5px; font-weight: 600; color: hsl(215 16% 40%);
    background: hsl(26 35% 93%); border-radius: 999px; padding: 3px 9px;
  }
  .lib-chip-chain { background: hsl(45 80% 88%); color: hsl(38 65% 30%); }

  .lib-more {
    border: 1px solid hsl(26 30% 82%); background: white; border-radius: 999px;
    padding: 10px 22px; font: 600 13px Inter, system-ui, sans-serif;
    color: hsl(222 47% 11%); cursor: pointer;
  }

  .lib-empty {
    text-align: center; padding: 70px 20px;
    background: hsl(26 45% 98%); border: 1px dashed hsl(26 30% 82%); border-radius: 1.75rem;
  }
  .lib-empty-glyph { font-size: 40px; color: hsl(45 80% 55%); margin-bottom: 12px; }
  .lib-empty h2 { font-family: 'Playfair Display', serif; font-size: 24px; margin: 0 0 8px; color: hsl(222 47% 11%); }
  .lib-empty p { font-size: 14px; line-height: 1.65; color: hsl(215 16% 45%); max-width: 48ch; margin: 0 auto; }

  .lib-skel {
    display: inline-block; height: 14px; border-radius: 6px;
    background: linear-gradient(90deg, hsl(26 30% 90%) 25%, hsl(26 35% 95%) 50%, hsl(26 30% 90%) 75%);
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
    background: hsl(26 45% 98%);
    border-left: 1px solid hsl(26 30% 85%);
    box-shadow: -24px 0 60px -20px hsl(24 40% 8% / 0.4);
    padding: 26px 26px calc(26px + env(safe-area-inset-bottom, 0px));
    overflow-y: auto;
    animation: lib-drawer-in 0.24s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  @keyframes lib-drawer-in { from { transform: translateX(30px); opacity: 0; } }
  .lib-drawer-close {
    position: absolute; top: 16px; right: 16px;
    width: 32px; height: 32px; border: none; border-radius: 9px;
    background: hsl(26 35% 93%); color: hsl(215 16% 40%);
    cursor: pointer; display: grid; place-items: center;
  }
  .lib-drawer-q {
    font-family: 'Playfair Display', serif;
    font-size: 24px; font-weight: 700; line-height: 1.25;
    color: hsl(222 47% 11%); margin: 8px 0 12px;
  }
  .lib-drawer-answer { font-size: 14.5px; line-height: 1.7; color: hsl(222 30% 18%); margin: 0; }
  .lib-muted { color: hsl(215 16% 50%); font-style: italic; }
  .lib-sources { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
  .lib-sources a {
    display: flex; align-items: baseline; gap: 8px; text-decoration: none;
    font-size: 13px; color: hsl(222 47% 11%);
  }
  .lib-src-n { color: hsl(215 16% 55%); font-size: 11px; flex-shrink: 0; }
  .lib-src-t { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .lib-src-d { color: hsl(215 16% 55%); font-size: 11px; font-family: 'JetBrains Mono', monospace; flex-shrink: 0; }
  .lib-drawer-graph {
    width: 100%; height: 260px; border: 1px solid hsl(26 30% 85%); border-radius: 14px;
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
      border-left: none; border-top: 1px solid hsl(26 30% 85%);
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
</style>
