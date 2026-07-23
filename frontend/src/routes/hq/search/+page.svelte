<script>
  /* Ai Cafreso Search — look anything up, get a quick AI answer, and keep the
     result as a graph. Pipeline per query:
       1. LIBRARY FIRST — exact hit in the public on-chain library answers
          instantly (and costs nothing).
       2. Brave web search through the user's own container (/brave/ proxy,
          session cookie) — the container's BRAVE_API_KEY pays, per user.
       3. Quick answer via the user's own Anthropic key from the on-chain
          keychain (BYOK; skipped gracefully when no key is set).
       4. The result set becomes a graph snapshot (query → results → domains),
          published to the container's graph store and rendered inline.
       5. OPT-IN "Add to public library" writes {query, answer, sources, graph}
          to cafresohq_state — searching alone never publishes anything. */
  import { endpointUrl, endpointHealth, endpointReady, probeHealth } from '$lib/stores/endpoint.js';
  import { isAuthenticated, login } from '$lib/stores/auth.js';
  import { ensureHqSession, hqSessionReady, endpointNeedsSession } from '$lib/api/hqSession.js';
  import { getKeychain } from '$lib/api/keychain.js';
  import { findInLibrary, publishToLibrary, libraryGraphViewerUrl, pendingCount } from '$lib/api/library.js';
  import { aiSearchOpen, aiSearchPrefill } from '$lib/stores/blog.js';

  // Signed-out lane: hand the query to the shared anonymous search modal
  // (public library + community worker network — no account, no container).
  let publicQuery = '';
  function openPublicSearch() {
    const q = publicQuery.trim();
    if (q) aiSearchPrefill.set(q);
    aiSearchOpen.set(true);
    publicQuery = '';
  }

  let query = '';
  let loading = false;
  let searched = false;
  let error = '';
  let results = [];              // [{title, url, description}]
  let answer = '';
  let answerState = 'idle';      // idle | working | done | nokey | failed
  let libraryHit = null;         // LibraryEntry when the library answered
  let graphViewer = '';          // inline viewer URL (container-published)
  let publishState = 'idle';     // idle | working | ok | existing | queued | error
  let publishInfo = null;        // { viewerUrl, publicUrl }
  let queuedTotal = 0;

  $: if ($endpointUrl && $endpointHealth.state === 'idle') { probeHealth().catch(() => {}); }
  $: needsSession = endpointNeedsSession($endpointUrl);
  $: if ($isAuthenticated && needsSession && $endpointReady && !$hqSessionReady) {
    ensureHqSession().catch(() => {});
  }

  function domain(url) {
    try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; }
  }

  /* ── Graph snapshot: query hub → result nodes → domain ring ─────────────── */
  const PALETTE = ['#7DC9B0', '#C9B8E0', '#E8A9A9', '#F0C987', '#9BC0E8', '#B8E09A', '#E0A47C', '#D89BE0'];
  function colorFor(name) {
    let h = 0;
    for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
    return PALETTE[h % PALETTE.length];
  }
  function buildGraphSnapshot(q, res) {
    const nodes = [{ key: 'q', attributes: { label: q, size: 18, x: 0, y: 0, color: '#F5D25D' } }];
    const edges = [];
    const domains = new Map();
    res.forEach((r, i) => {
      const a = (i / res.length) * Math.PI * 2;
      nodes.push({ key: 'r' + i, attributes: {
        label: r.title.slice(0, 60), size: 8,
        x: Math.cos(a) * 10, y: Math.sin(a) * 10, color: colorFor(domain(r.url))
      }});
      edges.push({ key: 'eq' + i, source: 'q', target: 'r' + i, attributes: {} });
      const d = domain(r.url);
      if (!domains.has(d)) domains.set(d, []);
      domains.get(d).push(i);
    });
    let di = 0;
    for (const [d, ixs] of domains) {
      const a = (di / domains.size) * Math.PI * 2 + 0.35;
      nodes.push({ key: 'd:' + d, attributes: {
        label: d, size: 5 + ixs.length, x: Math.cos(a) * 17, y: Math.sin(a) * 17, color: colorFor(d)
      }});
      for (const i of ixs) edges.push({ key: 'ed' + di + '_' + i, source: 'r' + i, target: 'd:' + d, attributes: {} });
      di++;
    }
    return {
      graph: { options: { type: 'mixed', multi: false, allowSelfLoops: true }, attributes: {}, nodes, edges },
      title: 'Search: ' + q,
      ts: Date.now()
    };
  }
  let snapshot = null;

  // Bumped on every runSearch() call. quickAnswer()/publishInlineGraph() are
  // fired without awaiting (so a second search isn't blocked on the first's
  // answer/graph calls) — without this guard, re-searching before the first
  // call resolves lets its stale response land AFTER the second search's
  // results are already showing, silently overwriting them with mismatched
  // content.
  let _searchGen = 0;

  /* ── Quick answer (BYOK Anthropic key from the on-chain keychain) ────────── */
  async function quickAnswer(q, res, gen) {
    answerState = 'working';
    try {
      const { keys } = await getKeychain();
      const key = keys && keys.anthropic;
      if (!key) { if (gen === _searchGen) answerState = 'nokey'; return; }
      const src = res.slice(0, 8).map((r, i) =>
        `[${i + 1}] ${r.title}\n${r.url}\n${r.description || ''}`).join('\n\n');
      const resp = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-api-key': key,
          'anthropic-version': '2023-06-01',
          'anthropic-dangerous-direct-browser-access': 'true'
        },
        body: JSON.stringify({
          model: 'claude-haiku-4-5-20251001',
          max_tokens: 400,
          messages: [{ role: 'user', content:
            `Answer this search query in 2-4 sentences using ONLY the sources below. Cite with [n]. If the sources don't answer it, say what they do cover.\n\nQuery: ${q}\n\nSources:\n${src}` }]
        })
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      if (gen !== _searchGen) return; // a newer search superseded this one
      answer = (data.content && data.content[0] && data.content[0].text || '').trim();
      answerState = answer ? 'done' : 'failed';
    } catch (_e) {
      if (gen === _searchGen) answerState = 'failed';
    }
  }

  /* ── Inline graph via the container's existing publish/viewer plumbing ──── */
  async function publishInlineGraph(snap, gen) {
    try {
      const r = await fetch(`${$endpointUrl}/graph/publish`, {
        method: 'POST', credentials: 'include',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(snap)
      });
      const j = await r.json();
      if (gen !== _searchGen) return; // a newer search superseded this one
      if (j && j.viewerUrl) graphViewer = `${$endpointUrl}${j.viewerUrl}`;
    } catch (_e) { /* graph pane just stays hidden */ }
  }

  async function runSearch() {
    const q = query.trim();
    if (!q || loading) return;
    const gen = ++_searchGen;
    loading = true; searched = true; error = '';
    results = []; answer = ''; answerState = 'idle';
    libraryHit = null; graphViewer = ''; snapshot = null;
    publishState = 'idle'; publishInfo = null;

    try {
      // 1. Library first — instant, free, public.
      const hit = await findInLibrary(q);
      if (gen !== _searchGen) return; // a newer search superseded this one
      if (hit) {
        libraryHit = hit;
        results = (hit.sources || []).map((s) => ({ title: s.title, url: s.url, description: '' }));
        answer = hit.answer || '';
        answerState = answer ? 'done' : 'idle';
        graphViewer = hit.graphJson && hit.graphJson.length ? libraryGraphViewerUrl(hit.id) : '';
        return;
      }
      // 2. Brave, through your container.
      if (!$endpointReady) throw new Error('Your container isn’t reachable — open the HQ dashboard to wake it, then retry.');
      const r = await fetch(`${$endpointUrl}/brave/search?q=${encodeURIComponent(q)}&count=8`, { credentials: 'include' });
      if (r.status === 401) throw new Error('Search needs your container session — open HQ once, then retry.');
      if (!r.ok) {
        const b = await r.json().catch(() => ({}));
        throw new Error(b.error || `Search failed (HTTP ${r.status})`);
      }
      const data = await r.json();
      if (gen !== _searchGen) return; // a newer search superseded this one
      results = ((data.web && data.web.results) || []).map((x) => ({
        title: x.title || x.url, url: x.url, description: x.description || ''
      }));
      if (!results.length) return;
      // 3 + 4 in parallel: answer and graph don't wait on each other.
      snapshot = buildGraphSnapshot(q, results);
      quickAnswer(q, results, gen);
      publishInlineGraph(snapshot, gen);
    } catch (e) {
      if (gen === _searchGen) error = e.message || String(e);
    } finally {
      if (gen === _searchGen) loading = false;
    }
  }

  /* ── Opt-in: publish this result to the public on-chain library ─────────── */
  async function addToLibrary() {
    if (!snapshot || publishState === 'working') return;
    publishState = 'working';
    const res = await publishToLibrary({
      q: query.trim(),
      answer: answerState === 'done' ? answer : '',
      sources: results.map((r) => ({ title: r.title, url: r.url })),
      graphJson: JSON.stringify(snapshot),
      model: answerState === 'done' ? 'claude-haiku-4-5' : '',
      searchEngine: 'brave'
    });
    if (res.status === 'ok') {
      publishState = res.existing ? 'existing' : 'ok';
      publishInfo = res;
    } else if (res.status === 'queued') {
      publishState = 'queued';
      queuedTotal = pendingCount();
    } else {
      publishState = 'error';
      error = res.error || 'publish failed';
    }
  }

  function handleKeydown(e) {
    // isComposing/keyCode 229 = an IME (CJK/Japanese/Korean) is mid-conversion;
    // the Enter that confirms the conversion must not also fire a search.
    if (e.key === 'Enter' && !e.isComposing && e.keyCode !== 229) runSearch();
  }
</script>

<svelte:head>
  <title>Ai Cafreso Search</title>
</svelte:head>

<section class="space-y-5">
  <header class="card p-6 sm:p-8">
    <div class="page-kicker">CafresoHQ / Search</div>
    <h1 class="page-title mt-4">Ai Cafreso Search<span class="text-brand-500">.</span></h1>
    <p class="mt-4 max-w-2xl text-sm leading-6 text-ink-300">
      Look anything up. Every search returns real sources, a quick AI answer, and a graph of what
      you found — and any answer you choose to share joins the public on-chain library, so the
      next person's search is instant.
    </p>
  </header>

  {#if !$isAuthenticated}
    <!-- No sign-in wall: the public lane works for everyone. Signing in adds
         the private lane (your container, your keys), it doesn't gate search. -->
    <div class="card p-4">
      <form class="flex flex-col gap-2 sm:flex-row" on:submit|preventDefault={openPublicSearch}>
        <input
          class="input flex-1"
          type="text"
          placeholder="Ask the on-chain library anything…"
          bind:value={publicQuery}
        />
        <button class="btn-primary px-6" type="submit">Search</button>
      </form>
      <p class="mt-3 text-xs leading-5 text-ink-400">
        Public search — answered from the on-chain library or by community workers, with
        sources. No account needed, and Deep Research is one toggle away.
      </p>
    </div>

    <div class="card flex flex-wrap items-center gap-3 p-5 text-sm leading-6 text-ink-300">
      <p class="min-w-0 flex-1">
        <span class="font-semibold text-ink-100">Want a private lane?</span>
        Sign in and searches can also run through your own container and your own
        keys — results stay yours unless you choose to share them.
      </p>
      <button class="btn-ghost btn-sm" on:click={login}>Sign in with Internet Identity</button>
    </div>
  {:else}
    <div class="card p-4">
      <div class="flex flex-col gap-2 sm:flex-row">
        <input
          class="input flex-1"
          type="text"
          placeholder="Search anything…"
          bind:value={query}
          on:keydown={handleKeydown}
          disabled={loading}
        />
        <button class="btn-primary px-6" on:click={runSearch} disabled={loading || !query.trim()}>
          {loading ? 'Searching…' : 'Search'}
        </button>
      </div>
    </div>

    {#if error}
      <div class="card border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-700 dark:text-rose-200">
        {error}
        <a href="/hq" class="btn-ghost ml-2 text-xs">Open HQ dashboard</a>
      </div>
    {/if}

    {#if loading}
      <div class="space-y-3">
        {#each Array(4) as _}
          <div class="card animate-pulse space-y-2 p-4">
            <div class="h-4 w-2/3 rounded bg-ink-700/70"></div>
            <div class="h-3 w-1/4 rounded bg-ink-800/70"></div>
            <div class="h-3 w-full rounded bg-ink-800/70"></div>
          </div>
        {/each}
      </div>
    {/if}

    {#if !loading && searched && (results.length || libraryHit)}
      <div class="flex flex-wrap items-center gap-2 text-xs text-ink-400">
        {#if libraryHit}
          <span class="pill-ok">Library hit — answered on-chain, no web search needed</span>
        {:else}
          <span class="pill-warn">Web search</span>
        {/if}
        <span>{results.length} source{results.length === 1 ? '' : 's'}</span>
      </div>

      {#if answerState === 'working'}
        <div class="card flex items-center gap-3 p-4 text-sm text-ink-300">
          <span class="glow-dot text-brand-400 animate-pulse"></span> Writing a quick answer…
        </div>
      {:else if answerState === 'done'}
        <div class="card border-brand-500/40 bg-brand-500/10 p-4">
          <div class="page-kicker mb-2">Quick answer</div>
          <p class="text-sm leading-7 text-ink-100">{answer}</p>
        </div>
      {:else if answerState === 'nokey'}
        <div class="card p-4 text-xs leading-5 text-ink-400">
          Add an Anthropic key in HQ → Settings → Keys to get an AI quick answer with your searches.
        </div>
      {/if}

      {#if graphViewer}
        <div class="card overflow-hidden p-0">
          <div class="flex items-center justify-between px-4 py-2">
            <span class="page-kicker">Graph view</span>
            <a class="btn-ghost text-xs" href={graphViewer} target="_blank" rel="noopener noreferrer">Open ↗</a>
          </div>
          <iframe src={graphViewer} title="Search graph" class="block h-[380px] w-full border-0"></iframe>
        </div>
      {/if}

      {#if !libraryHit && results.length}
        <div class="card flex flex-wrap items-center gap-3 p-4 text-sm">
          {#if publishState === 'idle' || publishState === 'working'}
            <span class="text-ink-300">Share this answer? It becomes a public library entry (query, answer, sources, graph) — your identity is never shown.</span>
            <button class="btn-primary text-xs" on:click={addToLibrary} disabled={publishState === 'working'}>
              {publishState === 'working' ? 'Publishing…' : '+ Add to public library'}
            </button>
          {:else if publishState === 'ok'}
            <span class="pill-ok">In the library</span>
            <a class="btn-ghost text-xs" href={publishInfo.viewerUrl} target="_blank" rel="noopener noreferrer">Public graph ↗</a>
            <a class="btn-ghost text-xs" href={publishInfo.publicUrl} target="_blank" rel="noopener noreferrer">Entry JSON ↗</a>
          {:else if publishState === 'existing'}
            <span class="pill-ok">Already in the library</span>
            <a class="btn-ghost text-xs" href={publishInfo.viewerUrl} target="_blank" rel="noopener noreferrer">Public graph ↗</a>
          {:else if publishState === 'queued'}
            <span class="pill-warn">Saved locally ({queuedTotal} queued)</span>
            <span class="text-xs text-ink-400">The library goes live with the next state-canister upgrade; queued entries publish then.</span>
          {/if}
        </div>
      {/if}

      <div class="space-y-3">
        {#each results as result, i}
          <div class="card group p-4 transition-colors hover:border-brand-500/50">
            <a href={result.url} target="_blank" rel="noopener noreferrer" class="block space-y-1">
              <div class="flex items-start justify-between gap-2">
                <h3 class="text-sm font-semibold leading-snug text-brand-600 transition-colors group-hover:text-brand-700 dark:text-brand-300 dark:group-hover:text-brand-200">
                  {result.title}
                </h3>
                <span class="shrink-0 text-xs text-ink-500">[{i + 1}]</span>
              </div>
              <div class="font-mono text-xs text-ink-500">{domain(result.url)}</div>
              {#if result.description}
                <!-- Brave descriptions embed <strong> markup — strip to plain text, never @html -->
                <p class="text-xs leading-6 text-ink-300">{result.description.replace(/<[^>]+>/g, '')}</p>
              {/if}
            </a>
          </div>
        {/each}
      </div>
    {:else if !loading && searched && !error}
      <div class="card p-8 text-center text-sm text-ink-400">
        No results for <em class="text-ink-200">"{query}"</em>
      </div>
    {/if}

    {#if !searched && !loading}
      <div class="card p-10 text-center">
        <div class="page-kicker">The library learns</div>
        <p class="mx-auto mt-3 max-w-md text-sm leading-6 text-ink-400">
          Shared answers live on-chain and answer repeat searches instantly — every query you
          publish makes the next person's search free.
        </p>
        <div class="flex flex-wrap justify-center gap-2 pt-5">
          {#each ['What is an ICP canister?', 'Best local LLM 2026', 'ICRC-2 approve flow', 'Pixel art office games'] as suggestion}
            <button class="btn-ghost px-3 py-1 text-xs" on:click={() => { query = suggestion; runSearch(); }}>
              {suggestion}
            </button>
          {/each}
        </div>
      </div>
    {/if}
  {/if}
</section>
