<script>
  import { SEARCH_API_BASE } from '$lib/config.js';

  let query = '';
  let results = [];
  let summary = '';
  let source = '';
  let responseMs = null;
  let vaultSize = null;
  let loading = false;
  let error = '';
  let searched = false;

  async function doSearch() {
    const q = query.trim();
    if (!q) return;

    loading = true;
    error = '';
    results = [];
    summary = '';
    source = '';
    searched = true;

    try {
      const url = `${SEARCH_API_BASE}/api/search?q=${encodeURIComponent(q)}`;
      const res = await fetch(url);

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      results = data.results || [];
      summary = data.summary || '';
      source = data.source || '';
      responseMs = data.response_time_ms ?? null;

      fetch(`${SEARCH_API_BASE}/api/stats`)
        .then((r) => r.json())
        .then((s) => { vaultSize = s.vault_size; })
        .catch(() => {});
    } catch (err) {
      error = err.message || 'Search failed. Is the search server running?';
    } finally {
      loading = false;
    }
  }

  function handleKeydown(e) {
    if (e.key === 'Enter') doSearch();
  }

  function reset() {
    query = '';
    results = [];
    summary = '';
    source = '';
    error = '';
    searched = false;
    responseMs = null;
  }

  function domain(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, '');
    } catch {
      return url;
    }
  }
</script>

<svelte:head>
  <title>CafresoPages Search - CafresoHQ</title>
</svelte:head>

<section class="space-y-6">
  <header class="card p-6 sm:p-8">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <div class="page-kicker">CafresoHQ / Search</div>
        <h1 class="page-title mt-4">CafresoPages<span class="text-brand-500">.</span></h1>
        <p class="mt-4 max-w-2xl text-sm leading-6 text-ink-300">
          Semantic search powered by the local AI vault. Results get smarter with every query.
        </p>
      </div>
      {#if vaultSize !== null}
        <span class="pill-ok">{vaultSize.toLocaleString()} in vault</span>
      {/if}
    </div>
  </header>

  <div class="card p-4">
    <div class="flex flex-col gap-2 sm:flex-row">
      <input
        class="input flex-1"
        type="text"
        placeholder="Search anything..."
        bind:value={query}
        on:keydown={handleKeydown}
        disabled={loading}
      />
      <button class="btn-primary px-6" on:click={doSearch} disabled={loading || !query.trim()}>
        {#if loading}
          <span class="animate-pulse">Searching...</span>
        {:else}
          Search
        {/if}
      </button>
      {#if searched}
        <button class="btn-ghost px-3" on:click={reset} title="Clear">Clear</button>
      {/if}
    </div>
  </div>

  {#if loading}
    <div class="space-y-3">
      {#each Array(4) as _}
        <div class="card space-y-2 p-4 animate-pulse">
          <div class="h-4 w-2/3 rounded bg-ink-700/70"></div>
          <div class="h-3 w-1/4 rounded bg-ink-800/70"></div>
          <div class="h-3 w-full rounded bg-ink-800/70"></div>
          <div class="h-3 w-5/6 rounded bg-ink-800/70"></div>
        </div>
      {/each}
    </div>
  {/if}

  {#if error}
    <div class="card border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-700 dark:text-rose-200">
      <strong>Error:</strong> {error}
      <div class="mt-2 text-xs leading-5">
        Make sure the CafresoPages server is running at
        <code class="font-mono">{SEARCH_API_BASE}</code>.
      </div>
      <button
        class="btn-ghost mt-3 text-xs"
        on:click={doSearch}
        disabled={loading || !query.trim()}
      >
        {loading ? 'Retrying…' : 'Retry search'}
      </button>
    </div>
  {/if}

  {#if !loading && searched && results.length > 0}
    <div class="flex flex-wrap items-center gap-3 text-xs text-ink-400">
      {#if source === 'vault'}
        <span class="pill-ok">Vault hit</span>
      {:else if source === 'brave'}
        <span class="pill-warn">Web search</span>
      {/if}
      {#if responseMs !== null}
        <span>{responseMs} ms</span>
      {/if}
      <span>{results.length} result{results.length !== 1 ? 's' : ''}</span>
    </div>

    {#if summary}
      <div class="card border-brand-500/40 bg-brand-500/10 p-4">
        <div class="mb-2 flex items-center gap-2">
          <span class="page-kicker">AI Summary</span>
          <span class="text-xs text-ink-500">Mistral 7B / local inference</span>
        </div>
        <p class="text-sm leading-7 text-ink-100">{summary}</p>
      </div>
    {/if}

    <div class="space-y-3">
      {#each results as result, i}
        <div class="card p-4 transition-colors group hover:border-brand-500/50">
          <a href={result.url} target="_blank" rel="noopener noreferrer" class="block space-y-1">
            <div class="flex items-start justify-between gap-2">
              <h3 class="text-sm font-semibold leading-snug text-brand-600 transition-colors group-hover:text-brand-700 dark:text-brand-300 dark:group-hover:text-brand-200">
                {result.title}
              </h3>
              <span class="shrink-0 text-xs text-ink-500">{i + 1}</span>
            </div>
            <div class="font-mono text-xs text-ink-500">{domain(result.url)}</div>
            {#if result.description}
              <p class="text-xs leading-6 text-ink-300">{result.description}</p>
            {/if}
          </a>
        </div>
      {/each}
    </div>
  {:else if !loading && searched && !error}
    <div class="card p-8 text-center text-sm text-ink-400">
      No results found for <em class="text-ink-200">"{query}"</em>
    </div>
  {/if}

  {#if !searched && !loading}
    <div class="card p-10 text-center">
      <div class="page-kicker">Search Vault</div>
      <p class="mx-auto mt-3 max-w-md text-sm leading-6 text-ink-400">
        Start searching to build the vault. Every result is learned, so future searches
        become instant.
      </p>
      <div class="flex flex-wrap justify-center gap-2 pt-5">
        {#each ['AI inference GPUs 2025', 'ICP canister development', 'Qdrant vector search', 'Ollama local models'] as suggestion}
          <button
            class="btn-ghost px-3 py-1 text-xs"
            on:click={() => { query = suggestion; doSearch(); }}
          >
            {suggestion}
          </button>
        {/each}
      </div>
    </div>
  {/if}
</section>
