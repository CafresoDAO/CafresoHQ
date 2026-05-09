<script>
  import { onMount, onDestroy } from 'svelte';
  import { endpointUrl, endpointHealth, endpointReady, probeHealth } from '$lib/stores/endpoint.js';
  import { isAuthenticated, principalText } from '$lib/stores/auth.js';
  import ProvisionPanel from '$lib/components/ProvisionPanel.svelte';

  // If we land here with a saved endpoint but the probe never ran in this
  // tab (idle state), kick one off. Prevents the "Connecting to your
  // container…" spinner from hanging forever when the user navigates
  // straight to /app from a fresh tab.
  $: if ($endpointUrl && $endpointHealth.state === 'idle') {
    probeHealth().catch(() => { /* surfaces via endpointHealth.state */ });
  }

  // Path inside the container to the full CafresoAI React SPA
  const APP_PATH = '/hq.html';

  $: appUrl = $endpointUrl ? $endpointUrl + APP_PATH : '';

  // Mixed-content detection: a page served over HTTPS cannot iframe an HTTP URL
  // (browser blocks). Localhost is exempt — "potentially trustworthy".
  $: shellIsHttps   = typeof window !== 'undefined' && window.location?.protocol === 'https:';
  $: endpointIsHttp = $endpointUrl?.startsWith('http://');
  $: isLocalhost    = $endpointUrl && /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test($endpointUrl);
  $: mixedContent   = shellIsHttps && endpointIsHttp && !isLocalhost;

  // True when the iframe should take the whole viewport — i.e. signed in,
  // endpoint healthy, no mixed-content block. The shell chrome (header,
  // padding, dashboard cards) only appears in setup states; once HQ is
  // running it gets the full page.
  $: fullscreenIframe = $isAuthenticated
                     && $endpointReady
                     && !mixedContent
                     && !!appUrl;

  let iframe;
  let loaded = false;
  let controlsCollapsed = false;   // user can tuck the floating controls away

  function reload() {
    loaded = false;
    if (iframe) iframe.src = appUrl + '?_t=' + Date.now();
  }

  function popout() {
    if (appUrl) window.open(appUrl, '_blank', 'noopener,noreferrer');
  }

  // Esc collapses/expands the floating controls (helpful when controls cover
  // a button in the iframe). Doesn't exit the page — Browser back / "Dashboard"
  // button do that.
  function onKey(e) {
    if (e.key === 'Escape' && fullscreenIframe) controlsCollapsed = !controlsCollapsed;
  }
  onMount(() => {
    if (typeof window !== 'undefined') window.addEventListener('keydown', onKey);
  });
  onDestroy(() => {
    if (typeof window !== 'undefined') window.removeEventListener('keydown', onKey);
  });
</script>

{#if fullscreenIframe}
  <!-- ── Full-screen iframe (z-40 puts it above the header z-30) ─────── -->
  <div class="fixed inset-0 z-40 bg-ink-900">
    {#if !loaded}
      <div class="absolute inset-0 grid place-items-center text-sm text-ink-400 z-10
                  bg-ink-900/60 backdrop-blur-sm pointer-events-none">
        <div class="flex items-center gap-2">
          <span class="glow-dot text-brand-400 animate-pulse"></span>
          Loading HQ from your container…
        </div>
      </div>
    {/if}

    <iframe
      bind:this={iframe}
      src={appUrl}
      title="CafresoAI HQ"
      on:load={() => loaded = true}
      class="block h-full w-full bg-ink-900 border-0"
      allow="clipboard-write *; clipboard-read *; fullscreen *">
    </iframe>

    <!-- Floating controls — tuck behind a button when collapsed -->
    {#if controlsCollapsed}
      <button
        class="absolute top-3 right-3 z-50 grid h-8 w-8 place-items-center rounded-full
               border border-ink-600/40 bg-ink-900/80 backdrop-blur-md text-ink-200
               hover:bg-ink-800/80 hover:text-ink-50 transition-colors"
        title="Show controls (Esc)"
        on:click={() => controlsCollapsed = false}>
        ⋯
      </button>
    {:else}
      <div class="absolute top-3 right-3 z-50 flex items-center gap-1
                  rounded-full border border-ink-600/40 bg-ink-900/80
                  backdrop-blur-md p-1 shadow-lg">
        <a href="/" class="rounded-full px-3 py-1 text-xs text-ink-200
                            hover:bg-ink-800/80 hover:text-ink-50 transition-colors"
           title="Back to dashboard">
          ← Dashboard
        </a>
        <span class="h-4 w-px bg-ink-600/40"></span>
        <button
          class="rounded-full px-3 py-1 text-xs text-ink-200
                 hover:bg-ink-800/80 hover:text-ink-50 transition-colors"
          on:click={reload} title="Hard reload the iframe">
          ⟳
        </button>
        <button
          class="rounded-full px-3 py-1 text-xs text-ink-200
                 hover:bg-ink-800/80 hover:text-ink-50 transition-colors"
          on:click={popout} title="Open in new tab">
          ↗
        </button>
        <button
          class="rounded-full px-3 py-1 text-xs text-ink-200
                 hover:bg-ink-800/80 hover:text-ink-50 transition-colors"
          on:click={() => controlsCollapsed = true}
          title="Hide controls (Esc)">
          ✕
        </button>
      </div>
    {/if}
  </div>
{:else}
  <!-- ── Setup / error states — render in the regular shell layout ───── -->
  <section class="space-y-3">
    <header class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">CafresoAI HQ</h1>
        <p class="text-sm text-ink-400">
          The full agent command center, running in your private OCI container.
        </p>
      </div>
    </header>

    {#if !$isAuthenticated}
      <div class="card p-5 text-sm text-ink-200">
        Sign in to launch HQ. Your principal scopes vault and agent state.
      </div>
    {:else if $endpointHealth.state === 'idle' || $endpointHealth.state === 'probing'}
      <div class="card p-5 text-sm text-ink-200 flex items-center gap-3">
        <span class="glow-dot text-brand-400 animate-pulse"></span>
        Connecting to your container…
      </div>
    {:else if !$endpointUrl || $endpointHealth.state === 'error'}
      <ProvisionPanel />
    {:else if mixedContent}
      <div class="card p-6 space-y-3">
        <div class="flex items-center gap-2">
          <span class="glow-dot text-amber-400"></span>
          <h2 class="text-lg font-semibold">Embedding blocked: mixed content</h2>
        </div>
        <p class="text-sm text-ink-200">
          This shell is served over <code class="font-mono text-brand-300">https://</code>,
          but your container endpoint is plain <code class="font-mono text-brand-300">http://</code>.
          Browsers block iframing an HTTP page from an HTTPS origin.
        </p>
        <p class="text-sm text-ink-200">
          Production fix is the OCI Caddy gateway at
          <code class="font-mono text-brand-300">hq.cafreso.com/u/&lt;principal-slug&gt;/*</code>
          with managed Let's Encrypt — re-point your endpoint there.
        </p>
        <div class="flex flex-wrap gap-2 pt-1">
          <button class="btn-primary" on:click={popout}>Open HQ in new tab ↗</button>
          <a href="/settings" class="btn-ghost">Update endpoint</a>
        </div>
        <p class="text-xs text-ink-400 pt-1">
          Endpoint: <code class="font-mono">{$endpointUrl}</code>
        </p>
      </div>
    {/if}
  </section>
{/if}
