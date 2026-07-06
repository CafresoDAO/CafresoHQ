<script>
  import { aiSearchOpen } from '$lib/stores/blog.js';
  import { aiCafresoOrigin, bankingBraveOrigin } from '$lib/links.js';
  import { goto } from '$app/navigation';
  import Icon from './Icon.svelte';
  import { trapFocus } from '$lib/actions/trapFocus.js';

  const CACHE_TTL = 5 * 60 * 1000; // 5 min

  let inputEl;
  let query = '';
  let phase = 'idle'; // 'idle' | 'loading' | 'result' | 'error'
  let result = null;  // { summary: string, source: 'vault' | 'web' }
  let errorMsg = '';
  let recentSearches = [];

  $: if ($aiSearchOpen) {
    phase = 'idle';
    query = '';
    result = null;
    errorMsg = '';
    try { recentSearches = JSON.parse(localStorage.getItem('cafreso:ai-recent') || '[]'); } catch { recentSearches = []; }
    setTimeout(() => inputEl?.focus(), 60);
  }

  function close() { aiSearchOpen.set(false); }

  function onKeydown(e) {
    if (e.key === 'Escape') close();
  }

  async function runSearch(q) {
    q = q.trim();
    if (!q) return;
    query = q;

    // Check session cache
    const cacheKey = 'cafreso:ai-cache:' + q;
    try {
      const cached = JSON.parse(sessionStorage.getItem(cacheKey) || 'null');
      if (cached && Date.now() - cached.ts < CACHE_TTL) {
        result = cached.data;
        phase = 'result';
        return;
      }
    } catch {}

    // Persist to recent searches
    try {
      const updated = [q, ...recentSearches.filter(r => r !== q)].slice(0, 6);
      recentSearches = updated;
      localStorage.setItem('cafreso:ai-recent', JSON.stringify(updated));
    } catch {}

    phase = 'loading';
    result = null;
    errorMsg = '';

    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 15000);
      const resp = await fetch(
        `${aiCafresoOrigin}/api/search?q=${encodeURIComponent(q)}`,
        { signal: ctrl.signal }
      );
      clearTimeout(t);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json(); // expects { summary: string, source: 'vault'|'web' }
      result = data;
      try { sessionStorage.setItem(cacheKey, JSON.stringify({ ts: Date.now(), data })); } catch {}
      phase = 'result';
    } catch (err) {
      errorMsg = err.name === 'AbortError'
        ? 'Request timed out after 15 seconds.'
        : 'ai.cafreso.com is unreachable right now.';
      phase = 'error';
    }
  }

  function onSubmit(e) {
    e.preventDefault();
    runSearch(query);
  }

  function fallbackToLocal() {
    close();
    goto(`/search?q=${encodeURIComponent(query.trim())}`);
  }
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
    aria-label="AI Search"
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
          AI Search
        </div>
        <div style="font-size: 10.5px; color: hsl(215 16% 47%); margin-top: 2px;">
          Powered by CafresoDAO Library · ai.cafreso.com
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
          placeholder="Ask anything about CafresoDAO…"
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
            href="/blog"
            on:click={close}
            style="
              display: flex; flex-direction: column; align-items: center; gap: 5px;
              padding: 12px 6px; border-radius: 12px; text-decoration: none;
              border: 1px solid hsl(26 30% 88%); background: white; text-align: center;
              transition: border-color .12s;
            "
          >
            <Icon name="article" size={20} style="color: hsl(32 72% 50%);" />
            <span style="font-size: 11px; font-weight: 600; color: hsl(222 47% 11%);">Dev Log</span>
          </a>
        </div>
      </div>
    {/if}

    <!-- Phase: loading -->
    {#if phase === 'loading'}
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
        <div style="font-size: 13px; color: hsl(215 16% 47%);">Querying vault…</div>
        <div style="font-size: 11px; color: hsl(215 16% 60%); margin-top: 4px;">ai.cafreso.com</div>
      </div>
    {/if}

    <!-- Phase: result -->
    {#if phase === 'result' && result}
      <div>
        <div style="margin-bottom: 10px;">
          <span style="
            font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
            padding: 2px 7px; border-radius: 5px;
            background: {result.source === 'vault' ? 'hsl(112 43% 90%)' : 'hsl(26 50% 90%)'};
            color: {result.source === 'vault' ? 'hsl(112 43% 28%)' : 'hsl(24 48% 30%)'};
          ">
            {result.source === 'vault' ? 'Vault hit' : 'Web search'}
          </span>
        </div>
        <p style="
          font-size: 14px; line-height: 1.65; color: hsl(222 47% 11%);
          margin: 0 0 14px;
        ">{result.summary}</p>
        <a
          href="{aiCafresoOrigin}?q={encodeURIComponent(query)}"
          data-sveltekit-reload="on"
          rel="noopener"
          on:click={close}
          style="
            display: inline-flex; align-items: center; gap: 5px;
            font-size: 12.5px; font-weight: 600; color: hsl(260 70% 50%);
            text-decoration: none;
          "
        >
          Open full answer in ai.cafreso.com
          <Icon name="arrow-up-right" size={12} />
        </a>
      </div>
    {/if}

    <!-- Phase: error -->
    {#if phase === 'error'}
      <div style="text-align: center; padding: 20px 0 16px;">
        <Icon name="warning-circle" size={28} style="color: hsl(32 72% 50%); display: block; margin: 0 auto 10px;" />
        <div style="font-size: 14px; font-weight: 600; color: hsl(222 47% 11%); margin-bottom: 4px;">
          Couldn't reach ai.cafreso.com
        </div>
        <div style="font-size: 12.5px; color: hsl(215 16% 47%); margin-bottom: 16px;">{errorMsg}</div>
        <button
          type="button"
          on:click={fallbackToLocal}
          style="
            display: inline-flex; align-items: center; gap: 6px;
            padding: 9px 16px; border-radius: 10px;
            border: 1px solid hsl(26 30% 82%); background: white;
            font-family: inherit; font-size: 13px; font-weight: 600;
            color: hsl(222 47% 11%); cursor: pointer;
            transition: background .15s;
          "
        >
          <Icon name="magnifying-glass" size={14} />
          Search locally instead
        </button>
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
