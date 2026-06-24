<script>
  import {
    endpointUrl,
    endpointHealth,
    setEndpoint,
    clearEndpoint,
    probeHealth,
    detectLocalCompanion
  } from '$lib/stores/endpoint.js';
  import {
    principalText,
    isAuthenticated
  } from '$lib/stores/auth.js';
  import { fleetApiUrl, fleetApiAuthToken, fleetHealth } from '$lib/api/fleetClient.js';
  import EndpointStatus from '$lib/components/EndpointStatus.svelte';

  let fleetApiInput = $fleetApiUrl;
  let fleetTokenInput = $fleetApiAuthToken;
  let fleetApiState = 'idle';
  let fleetApiData = null;
  let fleetApiError = '';

  $: fleetApiInput = $fleetApiUrl;
  $: fleetTokenInput = $fleetApiAuthToken;

  async function saveAndProbeFleet() {
    fleetApiUrl.set((fleetApiInput || '').trim().replace(/\/+$/, ''));
    fleetApiAuthToken.set((fleetTokenInput || '').trim());
    fleetApiState = 'probing';
    fleetApiError = '';
    fleetApiData = null;
    try {
      fleetApiData = await fleetHealth();
      fleetApiState = 'ok';
    } catch (err) {
      fleetApiError = String(err?.message || err);
      fleetApiState = 'err';
    }
  }

  let inputValue = $endpointUrl;
  let probing = false;
  let detecting = false;

  $: inputValue = $endpointUrl;
  $: shellIsHttps = typeof window !== 'undefined' && window.location?.protocol === 'https:';
  $: endpointIsHttp = $endpointUrl?.startsWith('http://');
  $: isLocalhost = $endpointUrl && /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test($endpointUrl);
  $: showMixedWarning = shellIsHttps && endpointIsHttp && !isLocalhost;

  async function save() {
    const normalized = setEndpoint(inputValue);
    inputValue = normalized;
    await testProbe();
  }

  async function testProbe() {
    probing = true;
    try {
      await probeHealth();
    } catch (_) {
      // shown in the card
    }
    probing = false;
  }

  async function detect() {
    detecting = true;
    try {
      const url = await detectLocalCompanion();
      if (url) {
        setEndpoint(url);
        await testProbe();
      } else {
        alert('No Local Companion found on http://localhost:8787. Start serve.py or paste your OCI URL.');
      }
    } finally {
      detecting = false;
    }
  }

  function reset() {
    if (confirm('Forget the configured endpoint?')) {
      clearEndpoint();
      inputValue = '';
    }
  }

  let showAdvanced = false;
  let showHealthJson = false;
</script>

<section class="mx-auto max-w-5xl space-y-6">
  <header class="card p-6 sm:p-8">
    <div class="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <div class="page-kicker">Control Panel / Settings</div>
        <h1 class="page-title mt-4">Settings<span class="text-brand-500">.</span></h1>
        <p class="mt-4 max-w-2xl text-sm leading-6 text-ink-300">
          Connect CafresoHQ to your private serve.py instance. Your data stays
          on your container; this app remains the polished command surface.
        </p>
      </div>
      <EndpointStatus />
    </div>
  </header>

  <div class="card p-6 space-y-5">
    <div class="flex items-start justify-between gap-3">
      <div>
        <div class="page-kicker">Cloud Endpoint</div>
        <h2 class="mt-2 text-xl font-semibold">Container connection</h2>
        <p class="mt-1 text-sm leading-6 text-ink-400">
          URL of your CafresoHQ serve.py instance: Local Companion, OCI self-deploy,
          or OCI Fleet container.
        </p>
      </div>
      <EndpointStatus />
    </div>

    <label class="block">
      <span class="text-xs uppercase tracking-[0.22em] text-ink-400">Endpoint URL</span>
      <input
        class="input mt-2"
        type="url"
        placeholder="http://132.145.133.139:8787"
        bind:value={inputValue}
        autocomplete="off"
        spellcheck="false"
      />
    </label>

    <div class="flex flex-wrap gap-2">
      <button class="btn-primary" on:click={save} disabled={!inputValue || probing}>
        {probing ? 'Saving + probing...' : 'Save & probe'}
      </button>
      <button class="btn-ghost" on:click={testProbe} disabled={!$endpointUrl || probing}>
        Probe /health
      </button>
      <button class="btn-ghost" on:click={detect} disabled={detecting}>
        {detecting ? 'Detecting...' : 'Detect local companion'}
      </button>
      <button class="btn-ghost sm:ml-auto" on:click={reset} disabled={!$endpointUrl}>
        Forget endpoint
      </button>
    </div>

    {#if showMixedWarning}
      <div class="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 dark:text-amber-200">
        <div class="font-semibold">Mixed-content warning</div>
        <div class="mt-1 text-xs leading-5">
          The shell is HTTPS but this endpoint is HTTP. The browser will block
          fetches and the iframe at <code class="font-mono">/app</code>. Use a localhost
          companion, or put TLS in front of the container.
        </div>
      </div>
    {/if}

    {#if $endpointHealth.state === 'error'}
      <div class="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-200">
        <div class="font-semibold">Probe failed</div>
        <div class="mt-1 font-mono text-xs">{$endpointHealth.error}</div>
        <div class="mt-2 text-xs leading-5">
          Common causes: typo in URL, container stopped, missing CORS headers,
          or browser blocking HTTP to HTTPS mixed content.
        </div>
      </div>
    {/if}

    {#if $endpointHealth.state === 'ok' && $endpointHealth.data}
      {@const d = $endpointHealth.data}
      <button
        class="flex items-center gap-2 text-xs text-ink-400 hover:text-ink-200 transition-colors"
        on:click={() => showHealthJson = !showHealthJson}
      >
        <span class="font-mono">{showHealthJson ? '▾' : '▸'}</span>
        {showHealthJson ? 'Hide' : 'Show'} connection details
      </button>
      {#if showHealthJson}
        <pre class="overflow-x-auto rounded-xl border border-ink-600/60 bg-[var(--code-bg)] px-4 py-3 font-mono text-xs text-ink-100">{JSON.stringify(d, null, 2)}</pre>
      {/if}
    {/if}
  </div>

  <div class="card p-6 space-y-4">
    <div>
      <div class="page-kicker">Ecosystem Identity</div>
      <h2 class="mt-2 text-xl font-semibold">Your account</h2>
    </div>

    {#if $isAuthenticated}
      <div class="flex items-start gap-4">
        <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-500/20 text-xl">
          🪪
        </div>
        <div class="min-w-0">
          <p class="text-sm font-semibold text-ink-100">Signed in via Internet Identity</p>
          <p class="mt-0.5 text-xs text-ink-400">
            Your identity is shared seamlessly across the Cafreso ecosystem —
            Banking.Brave, Cafreso Pages, Minegold.defi, and CafresoHQ all
            recognize the same account.
          </p>
        </div>
      </div>
      <div>
        <span class="text-xs uppercase tracking-[0.22em] text-ink-400">Principal ID</span>
        <code class="mt-2 block break-all rounded-xl border border-ink-600/60 bg-[var(--code-bg)] px-3 py-3 font-mono text-xs text-ink-100">{$principalText}</code>
      </div>
    {:else}
      <div class="flex items-center gap-3 rounded-xl border border-ink-600/40 bg-ink-800/40 px-4 py-4">
        <span class="text-xl">🔒</span>
        <p class="text-sm text-ink-300">
          Sign in with Internet Identity (button in the header) to see your account details.
        </p>
      </div>
    {/if}
  </div>

  <!-- Advanced / developer settings -->
  <div class="card overflow-hidden">
    <button
      class="flex w-full items-center justify-between px-6 py-4 text-left hover:bg-ink-700/30 transition-colors"
      on:click={() => showAdvanced = !showAdvanced}
    >
      <div>
        <span class="text-xs uppercase tracking-[0.22em] text-ink-400">Developer</span>
        <h2 class="mt-1 text-base font-semibold">Advanced settings</h2>
      </div>
      <span class="text-ink-400 text-lg font-mono">{showAdvanced ? '▾' : '▸'}</span>
    </button>

    {#if showAdvanced}
      <div class="border-t border-ink-600/40 p-6 space-y-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="text-xs uppercase tracking-[0.22em] text-ink-400">Fleet API</div>
            <h3 class="mt-1 text-base font-semibold">Provisioning service</h3>
            <p class="mt-1 text-sm leading-6 text-ink-400">
              Service that provisions OCI containers per principal. Only change this if you're self-hosting the fleet layer.
            </p>
          </div>
          {#if fleetApiState === 'ok'}
            <span class="pill-ok"><span class="glow-dot text-emerald-400"></span> Reachable</span>
          {:else if fleetApiState === 'probing'}
            <span class="pill-warn"><span class="glow-dot text-amber-400 animate-pulse"></span> Probing</span>
          {:else if fleetApiState === 'err'}
            <span class="pill-err"><span class="glow-dot text-rose-400"></span> Unreachable</span>
          {:else}
            <span class="pill-idle"><span class="glow-dot text-ink-400"></span> Idle</span>
          {/if}
        </div>

        <label class="block">
          <span class="text-xs uppercase tracking-[0.22em] text-ink-400">Fleet API URL</span>
          <input
            class="input mt-2"
            type="url"
            autocomplete="off"
            spellcheck="false"
            bind:value={fleetApiInput}
            placeholder="http://localhost:8080"
          />
        </label>

        <label class="block">
          <span class="text-xs uppercase tracking-[0.22em] text-ink-400">
            Auth token <span class="normal-case tracking-normal">(optional in dev)</span>
          </span>
          <input
            class="input mt-2"
            type="password"
            autocomplete="off"
            bind:value={fleetTokenInput}
            placeholder="X-Fleet-Auth header value"
          />
        </label>

        <button class="btn-primary" on:click={saveAndProbeFleet} disabled={!fleetApiInput || fleetApiState === 'probing'}>
          {fleetApiState === 'probing' ? 'Probing...' : 'Save & probe'}
        </button>

        {#if fleetApiState === 'ok' && fleetApiData}
          <pre class="overflow-x-auto rounded-xl border border-ink-600/60 bg-[var(--code-bg)] px-4 py-3 font-mono text-xs text-ink-100">{JSON.stringify(fleetApiData, null, 2)}</pre>
        {:else if fleetApiState === 'err'}
          <div class="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-200">
            <div class="font-semibold">Probe failed</div>
            <div class="mt-1 font-mono text-xs">{fleetApiError}</div>
            <div class="mt-2 text-xs">Start it locally: <code class="font-mono">python oci-fleet/fleet-api.py</code></div>
          </div>
        {/if}
      </div>
    {/if}
  </div>

  <div class="card p-6">
    <div class="page-kicker">Need a container?</div>
    <p class="mt-3 max-w-3xl text-sm leading-6 text-ink-300">
      Go to the <a href="/" class="font-semibold text-brand-600 underline dark:text-brand-300">dashboard</a>
      and click <strong>Provision my HQ</strong>. Your container will be spun up automatically
      and the endpoint will be set for you. To run a local dev server instead, start
      <code class="font-mono text-brand-600 dark:text-brand-300">serve.py</code> and click
      "Detect local companion" above.
    </p>
  </div>
</section>
