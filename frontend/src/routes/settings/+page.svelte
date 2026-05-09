<script>
  import {
    endpointUrl, endpointHealth, setEndpoint, clearEndpoint,
    probeHealth, detectLocalCompanion, normalizeUrl
  } from '$lib/stores/endpoint.js';
  import { ECOSYSTEM_DERIVATION_ORIGIN, principalText, isAuthenticated,
           useEcosystemPrincipal } from '$lib/stores/auth.js';
  import {
    fleetApiUrl, fleetApiAuthToken, fleetHealth
  } from '$lib/api/fleetClient.js';
  import EndpointStatus from '$lib/components/EndpointStatus.svelte';

  // Fleet API config (separate from container endpoint)
  let fleetApiInput   = $fleetApiUrl;
  let fleetTokenInput = $fleetApiAuthToken;
  let fleetApiState   = 'idle'; // idle | probing | ok | err
  let fleetApiData    = null;
  let fleetApiError   = '';

  $: fleetApiInput   = $fleetApiUrl;
  $: fleetTokenInput = $fleetApiAuthToken;

  async function saveAndProbeFleet() {
    fleetApiUrl.set((fleetApiInput || '').trim().replace(/\/+$/, ''));
    fleetApiAuthToken.set((fleetTokenInput || '').trim());
    fleetApiState = 'probing';
    fleetApiError = ''; fleetApiData = null;
    try {
      fleetApiData  = await fleetHealth();
      fleetApiState = 'ok';
    } catch (err) {
      fleetApiError = String(err?.message || err);
      fleetApiState = 'err';
    }
  }

  let inputValue = $endpointUrl;
  let probing    = false;
  let detecting  = false;

  // keep the input in sync with the store (e.g. when auto-detect fires)
  $: inputValue = $endpointUrl;

  // Mixed-content warning (matches /app route logic)
  $: shellIsHttps   = typeof window !== 'undefined' && window.location?.protocol === 'https:';
  $: endpointIsHttp = $endpointUrl?.startsWith('http://');
  $: isLocalhost    = $endpointUrl && /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test($endpointUrl);
  $: showMixedWarning = shellIsHttps && endpointIsHttp && !isLocalhost;

  async function save() {
    const n = setEndpoint(inputValue);
    inputValue = n;
    await testProbe();
  }

  async function testProbe() {
    probing = true;
    try { await probeHealth(); } catch (_) { /* shown in card */ }
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
    } finally { detecting = false; }
  }

  function reset() {
    if (confirm('Forget the configured endpoint?')) {
      clearEndpoint();
      inputValue = '';
    }
  }
</script>

<section class="space-y-6 max-w-3xl">
  <header class="space-y-1">
    <h1 class="text-2xl font-semibold tracking-tight">Settings</h1>
    <p class="text-sm text-ink-400">
      Connect CafresoAI to your private serve.py instance.
      Your data stays on your container — this app is just the UI.
    </p>
  </header>

  <!-- ── Endpoint configuration ────────────────────────────────────────── -->
  <div class="card p-6 space-y-5">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h2 class="text-lg font-semibold">Cloud endpoint</h2>
        <p class="mt-1 text-sm text-ink-400">
          URL of your CafresoAI serve.py — Local Companion, OCI self-deploy, or OCI Fleet container.
        </p>
      </div>
      <EndpointStatus />
    </div>

    <label class="block">
      <span class="text-xs uppercase tracking-wider text-ink-400">Endpoint URL</span>
      <input class="input mt-1.5"
             type="url"
             placeholder="http://132.145.133.139:8787"
             bind:value={inputValue}
             autocomplete="off"
             spellcheck="false" />
    </label>

    <div class="flex flex-wrap gap-2">
      <button class="btn-primary" on:click={save} disabled={!inputValue || probing}>
        {probing ? 'Saving + probing…' : 'Save & probe'}
      </button>
      <button class="btn-ghost" on:click={testProbe}
              disabled={!$endpointUrl || probing}>
        Probe /health
      </button>
      <button class="btn-ghost" on:click={detect} disabled={detecting}>
        {detecting ? 'Detecting…' : 'Detect local companion'}
      </button>
      <button class="btn-ghost ml-auto" on:click={reset} disabled={!$endpointUrl}>
        Forget endpoint
      </button>
    </div>

    {#if showMixedWarning}
      <div class="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
        <div class="font-medium">Mixed-content warning</div>
        <div class="mt-1 text-xs text-amber-100/90">
          The shell is HTTPS but this endpoint is HTTP. The browser will block
          fetches and the iframe at <code class="font-mono">/app</code>. Use a localhost
          companion, or put TLS in front of the container (planned: API Gateway at
          <code class="font-mono">hq.cafreso.com</code>).
        </div>
      </div>
    {/if}

    {#if $endpointHealth.state === 'error'}
      <div class="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
        <div class="font-medium">Probe failed</div>
        <div class="mt-1 font-mono text-xs">{$endpointHealth.error}</div>
        <div class="mt-2 text-xs text-rose-300/80">
          Common causes: typo in URL, container stopped, missing CORS headers,
          or browser blocking http→https mixed content. Check
          <code>fleet-manager.py status &lt;principal&gt;</code> from your CLI.
        </div>
      </div>
    {/if}

    {#if $endpointHealth.state === 'ok' && $endpointHealth.data}
      {@const d = $endpointHealth.data}
      <pre class="rounded-lg border border-ink-600/40 bg-[var(--code-bg)] px-4 py-3 text-xs
                  font-mono text-ink-100 overflow-x-auto"
      >{JSON.stringify(d, null, 2)}</pre>
    {/if}
  </div>

  <!-- ── Identity card ─────────────────────────────────────────────────── -->
  <div class="card p-6 space-y-3">
    <h2 class="text-lg font-semibold">Ecosystem identity</h2>
    {#if $isAuthenticated}
      <div class="text-sm text-ink-200">Signed in. Your principal:</div>
      <code class="block font-mono text-xs break-all bg-[var(--code-bg)]
                   border border-ink-600/40 rounded-md px-3 py-2">{$principalText}</code>
    {:else}
      <p class="text-sm text-ink-200">Sign in from the header to see your principal.</p>
    {/if}
    <dl class="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs pt-2">
      <dt class="text-ink-400">II provider</dt>
      <dd class="sm:col-span-2 font-mono">https://identity.ic0.app</dd>
      <dt class="text-ink-400">Derivation origin</dt>
      <dd class="sm:col-span-2 font-mono break-all">
        {$useEcosystemPrincipal ? ECOSYSTEM_DERIVATION_ORIGIN : '(use this canister\'s URL)'}
      </dd>
      <dt class="text-ink-400">Sister dapps</dt>
      <dd class="sm:col-span-2">Banking.Brave · Cafreso · Minegold.defi</dd>
    </dl>

    <label class="flex items-start gap-3 pt-3 cursor-pointer">
      <input type="checkbox" class="mt-1 accent-brand-500 h-4 w-4"
             bind:checked={$useEcosystemPrincipal} />
      <span class="block text-sm">
        <span class="text-ink-50 font-medium">Use ecosystem-shared principal</span>
        <span class="block text-xs text-ink-400 mt-0.5">
          Pass <code class="font-mono">derivationOrigin</code> to II so the same anchor produces the same
          principal across Banking.Brave, Cafreso Pages, Minegold.defi, and CafresoAI.
          Banking.Brave's <code class="font-mono">/.well-known/ii-alternative-origins</code> must list this dapp's URL.
          Disable to test on a non-whitelisted host (you'll get a different principal).
        </span>
      </span>
    </label>
  </div>

  <!-- ── Fleet API ─────────────────────────────────────────────────────── -->
  <div class="card p-6 space-y-4">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h2 class="text-lg font-semibold">Fleet API</h2>
        <p class="mt-1 text-sm text-ink-400">
          Service that provisions OCI containers per principal.
          Defaults to <code class="font-mono">http://localhost:8080</code>.
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
      <span class="text-xs uppercase tracking-wider text-ink-400">Fleet API URL</span>
      <input class="input mt-1.5" type="url" autocomplete="off" spellcheck="false"
             bind:value={fleetApiInput}
             placeholder="http://localhost:8080" />
    </label>

    <label class="block">
      <span class="text-xs uppercase tracking-wider text-ink-400">
        Auth token <span class="text-ink-400 normal-case">(optional in dev)</span>
      </span>
      <input class="input mt-1.5" type="password" autocomplete="off"
             bind:value={fleetTokenInput}
             placeholder="X-Fleet-Auth header value (FLEET_API_SECRET on the server)" />
    </label>

    <div class="flex gap-2">
      <button class="btn-primary" on:click={saveAndProbeFleet}
              disabled={!fleetApiInput || fleetApiState === 'probing'}>
        {fleetApiState === 'probing' ? 'Probing…' : 'Save & probe'}
      </button>
    </div>

    {#if fleetApiState === 'ok' && fleetApiData}
      <pre class="rounded-lg border border-ink-600/40 bg-[var(--code-bg)] px-4 py-3
                  text-xs font-mono text-ink-100 overflow-x-auto"
      >{JSON.stringify(fleetApiData, null, 2)}</pre>
    {:else if fleetApiState === 'err'}
      <div class="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
        <div class="font-medium">Probe failed</div>
        <div class="mt-1 font-mono text-xs">{fleetApiError}</div>
        <div class="mt-2 text-xs text-rose-300/80">
          Start it locally: <code class="font-mono">python oci-fleet/fleet-api.py</code>
        </div>
      </div>
    {/if}
  </div>

  <!-- ── Help card ─────────────────────────────────────────────────────── -->
  <div class="card p-6 space-y-3">
    <h2 class="text-lg font-semibold">Need a container?</h2>
    <p class="text-sm text-ink-200">
      Run <code class="font-mono text-brand-300">python oci-fleet/fleet-manager.py provision &lt;principal&gt;</code>
      from this repo to spin up your OCI Container Instance, then paste the public IP
      (with <code class="font-mono">:8787</code>) into the endpoint field above.
    </p>
    <p class="text-sm text-ink-200">
      Or run the local Electron app and click "Detect local companion" above —
      CafresoAI will auto-bind to <code class="font-mono">http://localhost:8787</code>.
    </p>
  </div>
</section>
