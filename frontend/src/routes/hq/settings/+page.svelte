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
  import { workspacesApiUrl } from '$lib/stores/workspaces.js';
  import { navMode, setNavMode } from '$lib/stores/navMode.js';
  import { ociGet } from '$lib/api/ociClient.js';
  import { describeBrain } from '$lib/brain.js';
  import EndpointStatus from '$lib/components/EndpointStatus.svelte';
  import SearchNetworkCard from '$lib/components/SearchNetworkCard.svelte';
  import OperatorPanel from '$lib/components/OperatorPanel.svelte';

  // ── Your AI Brain — which model Hermes is actually calling right now ──
  let brainState = 'idle';   // idle | loading | ok | error
  let brain = null;          // {label, sublabel, managed, providerLabel}
  async function loadBrain() {
    if (!$endpointUrl) { brainState = 'idle'; brain = null; return; }
    brainState = 'loading';
    try {
      const info = await ociGet('/hermes/provider');
      brain = describeBrain(info);
      brainState = 'ok';
    } catch (_) {
      brainState = 'error';
      brain = null;
    }
  }
  $: if ($endpointHealth.state === 'ok' && brainState === 'idle') loadBrain();
  $: if (!$endpointUrl && brainState !== 'idle') { brainState = 'idle'; brain = null; }

  let fleetApiInput = $fleetApiUrl;
  let workspacesApiInput = $workspacesApiUrl;
  let fleetTokenInput = $fleetApiAuthToken;
  let fleetApiState = 'idle';
  let fleetApiData = null;
  let fleetApiError = '';

  // Separate probe state for the Workspaces API — it was previously silent:
  // Save only ever checked fleetHealth() (the regular Fleet API / OCI
  // gateway), so a broken or unset Workspaces API URL looked identical to a
  // working one — the "Fleet API: OK" result belonged to a different host
  // entirely. Confirmed live 2026-07-21.
  let wsApiState = 'idle';
  let wsApiData = null;
  let wsApiError = '';

  // NOTE: these are initialized once (above) and only updated explicitly in
  // saveAndProbeFleet(). A reactive `$: fleetApiInput = $fleetApiUrl` used to live
  // here — it re-clobbered the field from the store and fought the user's typing,
  // so the inputs couldn't hold an edit. Removed.

  async function probeWorkspacesApi(token) {
    // Read the just-saved values directly rather than the stores (Svelte
    // store updates via .set() are synchronous, but reading raw inputs here
    // avoids any ambiguity about ordering with the reactive $ subscriptions).
    const base = ((workspacesApiInput || fleetApiInput || '').trim()).replace(/\/+$/, '');
    if (!base) { wsApiState = 'idle'; wsApiData = null; return; }
    wsApiState = 'probing'; wsApiError = ''; wsApiData = null;
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 5_000);
      const headers = { Accept: 'application/json' };
      if (token) headers['X-Fleet-Auth'] = token;
      const r = await fetch(base + '/fleet/health', { headers, signal: ctrl.signal });
      clearTimeout(t);
      wsApiData = await r.json();
      wsApiState = r.ok ? 'ok' : 'err';
      if (!r.ok) wsApiError = `HTTP ${r.status}`;
    } catch (err) {
      wsApiError = String(err?.message || err);
      wsApiState = 'err';
    }
  }

  async function saveAndProbeFleet() {
    fleetApiUrl.set((fleetApiInput || '').trim().replace(/\/+$/, ''));
    workspacesApiUrl.set((workspacesApiInput || '').trim().replace(/\/+$/, ''));
    const tok = (fleetTokenInput || '').trim();
    fleetApiAuthToken.set(tok);
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
    // Independent of the Fleet API's result — a separate host, separate
    // success/failure.
    await probeWorkspacesApi(tok);
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
        alert('No Local Companion found on this machine. Start it locally, or paste your cloud container URL.');
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

<svelte:head>
  <title>Settings · CafresoHQ</title>
</svelte:head>

<section class="mx-auto max-w-5xl space-y-6">
  <header class="card p-6 sm:p-8">
    <div class="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <div class="page-kicker">Control Panel / Settings</div>
        <h1 class="page-title mt-4">Settings<span class="text-brand-500">.</span></h1>
        <p class="mt-4 max-w-2xl text-sm leading-6 text-ink-300">
          Connect CafresoHQ to your private container. Your data stays on your
          container; this app remains the polished command surface.
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
          URL of your CafresoHQ container: the Local Companion on this machine,
          a self-deployed cloud container, or one we run for you.
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

  {#if $endpointUrl}
    <div class="card p-6 space-y-4">
      <div>
        <div class="page-kicker">AI Brain</div>
        <h2 class="mt-2 text-xl font-semibold">What's answering your chats</h2>
      </div>

      {#if brainState === 'loading'}
        <div class="flex items-center gap-2 text-sm text-ink-400">
          <span class="glow-dot text-amber-400 animate-pulse"></span> Checking your HQ's brain…
        </div>
      {:else if brainState === 'ok' && brain}
        <div class="flex items-start gap-4">
          <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-500/20 text-xl">
            🧠
          </div>
          <div class="min-w-0">
            <p class="flex flex-wrap items-center gap-2 text-sm font-semibold text-ink-100">
              {brain.label}
              {#if brain.managed}
                <span class="pill-ok text-[10px]"><span class="glow-dot text-emerald-400"></span> Provided by Cafreso</span>
              {/if}
            </p>
            <p class="mt-0.5 text-xs text-ink-400">{brain.sublabel}</p>
          </div>
        </div>
        {#if !brain.managed}
          <p class="text-xs leading-5 text-ink-500">
            Prefer the included Gemma 4 brain instead? Re-provision without a custom key and
            your HQ falls back to it automatically.
          </p>
        {/if}
      {:else if brainState === 'error'}
        <p class="text-xs leading-5 text-ink-500">Couldn't check — your HQ may still be starting up.</p>
      {/if}
    </div>
  {/if}

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

  <!-- Navigation: tabs vs. a dedicated OS window per HQ surface -->
  <div class="card p-6 space-y-4">
    <div>
      <div class="page-kicker">Interface</div>
      <h2 class="mt-2 text-xl font-semibold">Navigation</h2>
      <p class="mt-1 text-sm leading-6 text-ink-400">
        How the header's Dashboard / HQ / Chat / Search / Vault / Plans / Settings links behave.
      </p>
    </div>

    <div class="inline-flex rounded-full border border-ink-600/60 p-1">
      <button
        type="button"
        class="rounded-full px-4 py-1.5 text-sm font-semibold transition-colors
               {$navMode === 'tabs' ? 'bg-ink-50 text-ink-900 shadow-sm' : 'text-ink-300 hover:text-ink-50'}"
        on:click={() => setNavMode('tabs')}
      >Tabs</button>
      <button
        type="button"
        class="rounded-full px-4 py-1.5 text-sm font-semibold transition-colors
               {$navMode === 'windows' ? 'bg-ink-50 text-ink-900 shadow-sm' : 'text-ink-300 hover:text-ink-50'}"
        on:click={() => setNavMode('windows')}
      >Windows</button>
    </div>

    <p class="text-xs leading-5 text-ink-400">
      {#if $navMode === 'windows'}
        Each surface opens in its own OS window — handy across multiple monitors. Clicking
        a link again refocuses that surface's window instead of opening another one.
        Cmd/Ctrl-click still opens a plain new tab. Each window unlocks the Vault
        independently — that's intentional, the vault key never leaves the window that
        derived it.
      {:else}
        Default. Every surface navigates in this one window, like any normal link.
      {/if}
    </p>
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
            Workspaces API URL <span class="normal-case tracking-normal">(optional — for VM streaming on a separate host)</span>
          </span>
          <input
            class="input mt-2"
            type="url"
            autocomplete="off"
            spellcheck="false"
            bind:value={workspacesApiInput}
            placeholder="Defaults to the Fleet API URL"
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
          <div class="text-xs uppercase tracking-[0.15em] text-ink-400">Fleet API result</div>
          <pre class="overflow-x-auto rounded-xl border border-ink-600/60 bg-[var(--code-bg)] px-4 py-3 font-mono text-xs text-ink-100">{JSON.stringify(fleetApiData, null, 2)}</pre>
        {:else if fleetApiState === 'err'}
          <div class="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-200">
            <div class="font-semibold">Fleet API probe failed</div>
            <div class="mt-1 font-mono text-xs">{fleetApiError}</div>
            <div class="mt-2 text-xs">Start it locally: <code class="font-mono">python oci-fleet/fleet-api.py</code></div>
          </div>
        {/if}

        <!-- Workspaces API — a SEPARATE host from the Fleet API above. Its
             own probe used to be silent; the Fleet API's "OK" pill could
             mislead you into thinking Workspaces was reachable when it
             wasn't (they're different services, different machines). -->
        {#if workspacesApiInput}
          <div class="flex items-center justify-between gap-3 border-t border-ink-700/30 pt-3">
            <div class="text-xs uppercase tracking-[0.22em] text-ink-400">Workspaces API</div>
            {#if wsApiState === 'ok'}
              <span class="pill-ok"><span class="glow-dot text-emerald-400"></span> Reachable</span>
            {:else if wsApiState === 'probing'}
              <span class="pill-warn"><span class="glow-dot text-amber-400 animate-pulse"></span> Probing</span>
            {:else if wsApiState === 'err'}
              <span class="pill-err"><span class="glow-dot text-rose-400"></span> Unreachable</span>
            {:else}
              <span class="pill-idle"><span class="glow-dot text-ink-400"></span> Idle</span>
            {/if}
          </div>
          {#if wsApiState === 'ok' && wsApiData}
            <pre class="overflow-x-auto rounded-xl border border-ink-600/60 bg-[var(--code-bg)] px-4 py-3 font-mono text-xs text-ink-100">{JSON.stringify(wsApiData, null, 2)}</pre>
          {:else if wsApiState === 'err'}
            <div class="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-200">
              <div class="font-semibold">Workspaces API probe failed</div>
              <div class="mt-1 font-mono text-xs">{wsApiError}</div>
              <div class="mt-2 text-xs">This must resolve on its own — the Fleet API above being reachable does not mean this one is.</div>
            </div>
          {/if}
        {/if}
      </div>
    {/if}
  </div>

  <OperatorPanel />

  <SearchNetworkCard />

  <div class="card p-6">
    <div class="page-kicker">Need a container?</div>
    <p class="mt-3 max-w-3xl text-sm leading-6 text-ink-300">
      Go to the <a href="/" class="font-semibold text-brand-600 underline dark:text-brand-300">dashboard</a>
      and click <strong>Provision my HQ</strong>. Your container will be spun up automatically
      and the endpoint will be set for you. Running the Local Companion on your own
      machine instead? Click "Detect local companion" above.
    </p>
  </div>
</section>
