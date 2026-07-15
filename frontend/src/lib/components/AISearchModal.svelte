<script>
  /* Ai Cafreso Search — the anonymous quick-search sheet. Pipeline:
       1. on-chain library (instant, free)  →  2. the research network queue
       (community workers answer in ~10-30s) →  3. honest fallbacks.
     Every answer shown here is a public, permanent library entry with
     provenance. Nothing a visitor types is stored unless the network answers
     it — and then it's the ANSWER that's public, never the visitor. */
  import { aiSearchOpen, aiSearchPrefill } from '$lib/stores/blog.js';
  import { bankingBraveOrigin } from '$lib/links.js';
  import { goto } from '$app/navigation';
  import Icon from './Icon.svelte';
  import { trapFocus } from '$lib/actions/trapFocus.js';
  import { findPublic, networkHealth, submitJob, awaitJob } from '$lib/api/searchNetwork.js';
  import { libraryGraphViewerUrl } from '$lib/api/library.js';
  import { get } from 'svelte/store';
  import { operatorConfig, refreshOperatorConfig, searchPaused, gpuNodeDown, gpuDownMessage } from '$lib/stores/operator.js';

  const CACHE_TTL = 5 * 60 * 1000; // 5 min — library hits only (queue results change state)
  const SLOW_AFTER_MS = 45_000;    // past this, tell the user it's slow rather than just spinning

  let inputEl;
  let query = '';
  let phase = 'idle'; // idle | checking | queued | result | rejected | dark
  let entry = null;   // library entry JSON {id, query, answer, sources, model, engine, answeredAt}
  let fromLibrary = false;
  let queueNote = '';
  let rejectReason = '';
  let recentSearches = [];
  let searchSeq = 0;  // stale-response guard
  let darkMessage = '';  // operator-set pause / GPU-down message for the dark state

  $: if ($aiSearchOpen) {
    phase = 'idle';
    query = '';
    entry = null;
    try { recentSearches = JSON.parse(localStorage.getItem('cafreso:ai-recent') || '[]'); } catch { recentSearches = []; }
    refreshOperatorConfig();
    // A query handed in from elsewhere (e.g. the homepage box) — run it, then clear.
    const seed = get(aiSearchPrefill);
    if (seed) {
      aiSearchPrefill.set('');
      setTimeout(() => runSearch(seed), 40);
    } else {
      setTimeout(() => inputEl?.focus(), 60);
    }
  }

  function close() { aiSearchOpen.set(false); }
  function onKeydown(e) { if (e.key === 'Escape') close(); }

  function plain(t) { return String(t || '').replace(/<[^>]+>/g, ''); }
  function domain(url) {
    try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; }
  }
  function provLine(e) {
    const bits = [];
    if (e.model) bits.push('answered by ' + e.model);
    if (e.engine) bits.push('via ' + e.engine);
    if (e.answeredAt) {
      try { bits.push(new Date(Number(e.answeredAt) / 1e6).toLocaleDateString()); } catch {}
    }
    return bits.join(' · ');
  }

  async function runSearch(q) {
    q = q.trim();
    if (!q) return;
    query = q;
    const seq = ++searchSeq;

    const cacheKey = 'cafreso:ai-cache:' + q;
    try {
      const cached = JSON.parse(sessionStorage.getItem(cacheKey) || 'null');
      if (cached && Date.now() - cached.ts < CACHE_TTL) {
        entry = cached.entry; fromLibrary = true; phase = 'result';
        return;
      }
    } catch {}
    try {
      const updated = [q, ...recentSearches.filter((r) => r !== q)].slice(0, 6);
      recentSearches = updated;
      localStorage.setItem('cafreso:ai-recent', JSON.stringify(updated));
    } catch {}

    phase = 'checking';
    entry = null;
    darkMessage = '';

    // 1. Library first — instant and free. Still works even when the operator
    //    has paused the network (reads aren't gated — only NEW queries are).
    const hit = await findPublic(q);
    if (seq !== searchSeq) return;
    if (hit && hit.id) {
      entry = hit; fromLibrary = true; phase = 'result';
      try { sessionStorage.setItem(cacheKey, JSON.stringify({ ts: Date.now(), entry: hit })); } catch {}
      return;
    }

    // 2. Miss → operator pause / node-down beats everything.
    const opc = get(operatorConfig);
    if (searchPaused(opc)) {
      darkMessage = 'Search is paused by the operator right now — browse everything already answered below.';
      phase = 'dark'; return;
    }
    const health = await networkHealth();
    if (seq !== searchSeq) return;
    if (!health || !health.activeWorkers) {
      if (gpuNodeDown(opc)) darkMessage = gpuDownMessage(opc);
      phase = 'dark'; return;
    }

    const sub = await submitJob(q);
    if (seq !== searchSeq) return;
    if (!sub) { phase = 'dark'; return; }
    if (sub.status === 'hit' && sub.entry) {
      entry = sub.entry; fromLibrary = true; phase = 'result';
      return;
    }
    if (sub.status === 'rejected') {
      rejectReason = sub.reason || 'busy';
      phase = 'rejected';
      return;
    }

    // 3. Queued — a worker is on it.
    phase = 'queued';
    queueNote = health.activeWorkers === 1
      ? '1 worker online' : `${health.activeWorkers} workers online`;
    const done = await awaitJob(sub.jobId, {
      onTick: (st, elapsedMs) => {
        if (seq !== searchSeq) return;
        // A slow box can legitimately take most of the worker's 200s budget.
        // Past ~45s say so plainly instead of leaving a spinner implying
        // something is wrong — the answer joins the library either way.
        if (elapsedMs > SLOW_AFTER_MS) queueNote = 'slow';
        else if (st === 'claimed') queueNote = 'a worker picked it up…';
      }
    });
    if (seq !== searchSeq) return;
    if (done.status === 'done' && done.entry) {
      entry = done.entry; fromLibrary = false; phase = 'result';
    } else {
      rejectReason = done.status;   // failed | expired | timeout
      phase = 'rejected';
    }
  }

  function onSubmit(e) { e.preventDefault(); runSearch(query); }
  function fallbackToLocal() { close(); goto(`/search?q=${encodeURIComponent(query.trim())}`); }
  function openLibrary() { close(); goto('/library' + (entry ? `?e=${entry.id}` : '')); }
</script>

<svelte:window on:keydown={onKeydown} />

{#if $aiSearchOpen}
  <!-- Backdrop -->
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    on:click={close}
    style="
      position: fixed; inset: 0; z-index: 55;
      background: hsl(24 48% 8% / 0.55);
      backdrop-filter: blur(6px);
      -webkit-backdrop-filter: blur(6px);
    "
  ></div>

  <!-- Panel -->
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div
    role="dialog"
    aria-modal="true"
    aria-label="Ai Cafreso Search"
    use:trapFocus
    on:click|stopPropagation
    style="
      position: fixed; left: 12px; right: 12px;
      bottom: calc(82px + env(safe-area-inset-bottom, 0px));
      z-index: 56;
      background: hsl(26 45% 98% / 0.97);
      backdrop-filter: blur(24px) saturate(160%);
      -webkit-backdrop-filter: blur(24px) saturate(160%);
      border: 1px solid hsl(26 30% 85%);
      border-radius: 20px;
      box-shadow: 0 24px 60px -16px hsl(24 40% 10% / 0.45), 0 2px 0 hsl(26 40% 98% / 0.5) inset;
      padding: 18px 16px 20px;
      max-height: calc(100dvh - 120px);
      overflow-y: auto;
      animation: modalUp .22s cubic-bezier(.2,.8,.2,1);
    "
  >
    <!-- Header row -->
    <div style="display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 14px;">
      <div>
        <div style="font-size: 15px; font-weight: 700; color: hsl(222 47% 11%); display: flex; align-items: center; gap: 6px;">
          <Icon name="brain" size={16} style="color: hsl(260 70% 50%);" />
          Ai Cafreso Search
        </div>
        <div style="font-size: 10.5px; color: hsl(215 16% 47%); margin-top: 2px;">
          Answered on-chain · every answer joins the public library
        </div>
      </div>
      <button
        type="button"
        on:click={close}
        aria-label="Close AI Search"
        style="
          width: 30px; height: 30px; border: none; background: transparent;
          border-radius: 8px; cursor: pointer; color: hsl(215 16% 47%);
          display: flex; align-items: center; justify-content: center;
          flex-shrink: 0; margin-top: -2px;
        "
      >
        <Icon name="x" size={16} />
      </button>
    </div>

    <!-- Search input -->
    <form on:submit={onSubmit} style="margin-bottom: 16px;">
      <div style="position: relative;">
        <Icon name="magnifying-glass" size={16} style="
          position: absolute; left: 13px; top: 50%; transform: translateY(-50%);
          color: hsl(215 16% 47%); pointer-events: none;
        " />
        <input
          bind:this={inputEl}
          data-autofocus
          bind:value={query}
          type="search"
          placeholder="Ask anything…"
          style="
            width: 100%; padding: 12px 14px 12px 38px; border-radius: 12px;
            border: 1.5px solid hsl(26 30% 82%); font-size: 15px; font-family: inherit;
            background: white; color: hsl(222 47% 11%); outline: none;
            box-sizing: border-box;
            box-shadow: 0 1px 4px hsl(24 20% 20% / 0.06);
            transition: border-color .15s, box-shadow .15s;
          "
          on:focus={(e) => {
            e.currentTarget.style.borderColor = 'hsl(260 70% 62%)';
            e.currentTarget.style.boxShadow = '0 0 0 3px hsl(260 70% 62% / 0.15), 0 1px 4px hsl(24 20% 20% / 0.06)';
          }}
          on:blur={(e) => {
            e.currentTarget.style.borderColor = 'hsl(26 30% 82%)';
            e.currentTarget.style.boxShadow = '0 1px 4px hsl(24 20% 20% / 0.06)';
          }}
        />
      </div>
    </form>

    <!-- Phase: idle -->
    {#if phase === 'idle'}
      {#if recentSearches.length > 0}
        <div style="margin-bottom: 14px;">
          <div style="
            font-size: 10.5px; font-weight: 700; text-transform: uppercase;
            letter-spacing: 0.08em; color: hsl(215 16% 47%); margin-bottom: 7px;
          ">Recent</div>
          <div style="display: flex; flex-wrap: wrap; gap: 6px;">
            {#each recentSearches as r}
              <button
                type="button"
                on:click={() => runSearch(r)}
                style="
                  padding: 5px 11px; border-radius: 999px;
                  border: 1px solid hsl(26 30% 85%); background: white;
                  font-family: inherit; font-size: 12.5px; font-weight: 500;
                  color: hsl(222 47% 11%); cursor: pointer;
                  transition: border-color .12s;
                "
              >{r}</button>
            {/each}
          </div>
        </div>
      {/if}

      <!-- Quick-link grid -->
      <div style="margin-bottom: 4px;">
        <div style="
          font-size: 10.5px; font-weight: 700; text-transform: uppercase;
          letter-spacing: 0.08em; color: hsl(215 16% 47%); margin-bottom: 7px;
        ">Quick access</div>
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px;">
          <a
            href="/library"
            on:click={close}
            style="
              display: flex; flex-direction: column; align-items: center; gap: 5px;
              padding: 12px 6px; border-radius: 12px; text-decoration: none;
              border: 1px solid hsl(26 30% 88%); background: white; text-align: center;
              transition: border-color .12s;
            "
          >
            <Icon name="books" size={20} style="color: hsl(45 85% 45%);" />
            <span style="font-size: 11px; font-weight: 600; color: hsl(222 47% 11%);">Library</span>
          </a>
          <a
            href="/governance"
            on:click={close}
            style="
              display: flex; flex-direction: column; align-items: center; gap: 5px;
              padding: 12px 6px; border-radius: 12px; text-decoration: none;
              border: 1px solid hsl(26 30% 88%); background: white; text-align: center;
              transition: border-color .12s;
            "
          >
            <Icon name="gavel" size={20} style="color: hsl(260 70% 62%);" />
            <span style="font-size: 11px; font-weight: 600; color: hsl(222 47% 11%);">DAO</span>
          </a>
          <a
            href={bankingBraveOrigin}
            data-sveltekit-reload="on"
            rel="noopener"
            on:click={close}
            style="
              display: flex; flex-direction: column; align-items: center; gap: 5px;
              padding: 12px 6px; border-radius: 12px; text-decoration: none;
              border: 1px solid hsl(26 30% 88%); background: white; text-align: center;
              transition: border-color .12s;
            "
          >
            <Icon name="bank" size={20} style="color: hsl(220 78% 44%);" />
            <span style="font-size: 11px; font-weight: 600; color: hsl(222 47% 11%);">Banking</span>
          </a>
        </div>
      </div>
    {/if}

    <!-- Phase: checking / queued -->
    {#if phase === 'checking' || phase === 'queued'}
      <div style="text-align: center; padding: 28px 0 24px;">
        <div
          class="spin"
          style="
            display: inline-block;
            width: 34px; height: 34px;
            border: 3px solid hsl(26 30% 85%);
            border-top-color: hsl(260 70% 55%);
            border-radius: 50%;
            margin-bottom: 14px;
          "
        ></div>
        {#if phase === 'checking'}
          <div style="font-size: 13px; color: hsl(215 16% 47%);">Checking the on-chain library…</div>
        {:else if queueNote === 'slow'}
          <div style="font-size: 13px; font-weight: 600; color: hsl(222 47% 11%);">Still working — this one's a slow one</div>
          <div style="font-size: 11.5px; color: hsl(215 16% 55%); margin-top: 4px;">
            The answer joins <a href="/library" on:click={close} style="color: hsl(260 70% 55%);">the library</a>
            either way — you can close this and find it there.
          </div>
        {:else}
          <div style="font-size: 13px; font-weight: 600; color: hsl(222 47% 11%);">The research network is on it</div>
          <div style="font-size: 11.5px; color: hsl(215 16% 55%); margin-top: 4px;">
            {queueNote} · fresh answers take ~10–30s and join the library forever
          </div>
        {/if}
      </div>
    {/if}

    <!-- Phase: result -->
    {#if phase === 'result' && entry}
      <div>
        <div style="margin-bottom: 10px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
          <span style="
            font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
            padding: 2px 7px; border-radius: 5px;
            background: {fromLibrary ? 'hsl(112 43% 90%)' : 'hsl(260 60% 92%)'};
            color: {fromLibrary ? 'hsl(112 43% 28%)' : 'hsl(260 60% 35%)'};
          ">
            {fromLibrary ? 'On-chain library' : 'Fresh from the network'}
          </span>
          {#if provLine(entry)}
            <span style="font-size: 10.5px; color: hsl(215 16% 55%);">{provLine(entry)}</span>
          {/if}
        </div>
        {#if entry.answer}
          <p style="font-size: 14px; line-height: 1.65; color: hsl(222 47% 11%); margin: 0 0 12px;">{plain(entry.answer)}</p>
        {:else}
          <p style="font-size: 13px; line-height: 1.6; color: hsl(215 16% 40%); margin: 0 0 12px;">
            Sources collected — no summary was generated for this one yet.
          </p>
        {/if}
        {#if entry.sources && entry.sources.length}
          <div style="display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px;">
            {#each entry.sources.slice(0, 3) as s, i}
              <a href={s.url} target="_blank" rel="noopener noreferrer" style="
                display: flex; align-items: baseline; gap: 7px; text-decoration: none;
                font-size: 12.5px; color: hsl(222 47% 11%);
              ">
                <span style="color: hsl(215 16% 55%); font-size: 11px; flex-shrink: 0;">[{i + 1}]</span>
                <span style="font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{plain(s.title)}</span>
                <span style="color: hsl(215 16% 55%); font-size: 11px; flex-shrink: 0;">{domain(s.url)}</span>
              </a>
            {/each}
          </div>
        {/if}
        <div style="display: flex; gap: 14px; flex-wrap: wrap;">
          <button type="button" on:click={openLibrary} style="
            display: inline-flex; align-items: center; gap: 5px; border: none; background: transparent;
            padding: 0; font-family: inherit; font-size: 12.5px; font-weight: 600; color: hsl(260 70% 50%);
            cursor: pointer;
          ">
            Explore in the library
            <Icon name="arrow-up-right" size={12} />
          </button>
          {#if entry.id && libraryGraphViewerUrl(entry.id)}
            <a href={libraryGraphViewerUrl(entry.id)} target="_blank" rel="noopener noreferrer" style="
              display: inline-flex; align-items: center; gap: 5px;
              font-size: 12.5px; font-weight: 600; color: hsl(215 16% 40%); text-decoration: none;
            ">
              Graph view
              <Icon name="arrow-up-right" size={12} />
            </a>
          {/if}
        </div>
      </div>
    {/if}

    <!-- Phase: rejected (busy / budget / failed / timeout) -->
    {#if phase === 'rejected'}
      <div style="text-align: center; padding: 20px 0 16px;">
        <Icon name="warning-circle" size={28} style="color: hsl(32 72% 50%); display: block; margin: 0 auto 10px;" />
        <div style="font-size: 14px; font-weight: 600; color: hsl(222 47% 11%); margin-bottom: 4px;">
          {rejectReason === 'busy' ? 'The network is at capacity'
            : rejectReason === 'budget' ? "Today's research budget is spent"
            : rejectReason === 'timeout' ? 'Still researching — check the library shortly'
            : "The network couldn't answer this one"}
        </div>
        <div style="font-size: 12.5px; color: hsl(215 16% 47%); margin-bottom: 16px;">
          {rejectReason === 'timeout'
            ? 'Your question stays queued; the answer lands in the public library when a worker finishes.'
            : 'You can search with your own container instead — or try again in a bit.'}
        </div>
        <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
          <a href="/hq/search?q={encodeURIComponent(query)}" on:click={close} style="
            display: inline-flex; align-items: center; gap: 6px; padding: 9px 16px; border-radius: 10px;
            background: hsl(24 48% 12%); color: white; font-size: 13px; font-weight: 600; text-decoration: none;
          ">Sign in &amp; search</a>
          <button type="button" on:click={fallbackToLocal} style="
            display: inline-flex; align-items: center; gap: 6px; padding: 9px 16px; border-radius: 10px;
            border: 1px solid hsl(26 30% 82%); background: white; font-family: inherit;
            font-size: 13px; font-weight: 600; color: hsl(222 47% 11%); cursor: pointer;
          ">Search this site</button>
        </div>
      </div>
    {/if}

    <!-- Phase: network dark -->
    {#if phase === 'dark'}
      <div style="text-align: center; padding: 20px 0 16px;">
        <Icon name="moon" size={28} style="color: hsl(260 40% 55%); display: block; margin: 0 auto 10px;" />
        <div style="font-size: 14px; font-weight: 600; color: hsl(222 47% 11%); margin-bottom: 4px;">
          {darkMessage ? 'Heads up' : 'The research network is asleep'}
        </div>
        <div style="font-size: 12.5px; color: hsl(215 16% 47%); margin-bottom: 16px;">
          {darkMessage || 'No workers are online right now. Sign in to search with your own container — or browse everything already answered.'}
        </div>
        <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
          <a href="/hq/search?q={encodeURIComponent(query)}" on:click={close} style="
            display: inline-flex; align-items: center; gap: 6px; padding: 9px 16px; border-radius: 10px;
            background: hsl(24 48% 12%); color: white; font-size: 13px; font-weight: 600; text-decoration: none;
          ">Sign in &amp; search</a>
          <a href="/library" on:click={close} style="
            display: inline-flex; align-items: center; gap: 6px; padding: 9px 16px; border-radius: 10px;
            border: 1px solid hsl(26 30% 82%); background: white;
            font-size: 13px; font-weight: 600; color: hsl(222 47% 11%); text-decoration: none;
          ">Explore the library</a>
        </div>
      </div>
    {/if}

    <!-- Persistent library link -->
    {#if phase === 'idle' || phase === 'result'}
      <div style="margin-top: 14px; padding-top: 12px; border-top: 1px dashed hsl(26 25% 82%); text-align: center;">
        <a href="/library" on:click={close} style="
          font-size: 12px; font-weight: 600; color: hsl(215 16% 47%); text-decoration: none;
        ">Explore the library — every answer, one growing web →</a>
      </div>
    {/if}
  </div>
{/if}

<style>
  @keyframes modalUp {
    from { opacity: 0; transform: translateY(12px) scale(0.97); }
    to   { opacity: 1; transform: translateY(0) scale(1); }
  }
</style>
