<script>
  import { onMount } from 'svelte';
  import { isAuthenticated, principalText } from '$lib/stores/auth.js';
  import { setEndpoint } from '$lib/stores/endpoint.js';
  import { lookup, provisionAndWait, fleetHealth, FleetApiError, fleetApiUrl }
    from '$lib/api/fleetClient.js';

  let state = 'unknown';
  let phase = '';
  let error = '';
  let endpoint = '';
  let apiOk = null;

  $: principal = $principalText;

  async function checkApi() {
    apiOk = null;
    try {
      await fleetHealth();
      apiOk = true;
    } catch (err) {
      apiOk = false;
    }
  }

  function pickEndpoint(r) {
    return r?.gateway_url || r?.endpoint || null;
  }

  async function autoLookup() {
    if (!$isAuthenticated || !principal) return;
    state = 'checking';
    phase = '';
    error = '';
    await checkApi();
    if (!apiOk) {
      state = 'no-api';
      return;
    }
    try {
      const r = await lookup(principal);
      const ep = pickEndpoint(r);
      if (ep) {
        setEndpoint(ep);
        endpoint = ep;
        state = 'existing';
      } else {
        state = 'no-container';
      }
    } catch (err) {
      error = describe(err);
      state = 'error';
    }
  }

  async function startProvision() {
    state = 'provisioning';
    phase = 'starting';
    error = '';
    try {
      const job = await provisionAndWait(principal, {
        onUpdate: (j) => {
          phase = j.phase || j.status || 'working';
        },
        pollMs: 5000,
        maxWaitMs: 600000
      });
      const ep = pickEndpoint(job);
      if (ep) {
        setEndpoint(ep);
        endpoint = ep;
        state = 'ready';
        phase = 'ready';
      } else {
        throw new Error('no endpoint in job result');
      }
    } catch (err) {
      error = describe(err);
      state = 'error';
    }
  }

  function describe(err) {
    if (err instanceof FleetApiError) {
      const detail = err.body?.error || err.message;
      return `${detail} (HTTP ${err.status || '?'})`;
    }
    return String(err?.message || err);
  }

  $: if ($isAuthenticated && principal && state === 'unknown') autoLookup();
  $: if (!$isAuthenticated && state !== 'unknown') {
    state = 'unknown';
    phase = '';
    error = '';
    endpoint = '';
  }

  onMount(() => {
    if ($isAuthenticated && principal) autoLookup();
  });
</script>

<div class="card p-5">
  <div class="flex items-start justify-between gap-3">
    <div>
      <div class="page-kicker">Your CafresoAI HQ</div>
      <div class="mt-2 text-xl font-semibold">
        {#if state === 'checking'}
          Checking the fleet...
        {:else if state === 'existing' || state === 'ready'}
          Container ready
        {:else if state === 'provisioning'}
          Provisioning your HQ...
        {:else if state === 'no-container'}
          No container yet
        {:else if state === 'no-api'}
          Fleet API unreachable
        {:else if state === 'error'}
          Couldn't check fleet
        {:else}
          Sign in to check
        {/if}
      </div>
    </div>
    {#if state === 'existing' || state === 'ready'}
      <span class="pill-ok"><span class="glow-dot text-emerald-400"></span> Live</span>
    {:else if state === 'provisioning' || state === 'checking'}
      <span class="pill-warn"><span class="glow-dot text-amber-400 animate-pulse"></span> Working</span>
    {:else if state === 'no-container'}
      <span class="pill-idle"><span class="glow-dot text-ink-400"></span> Idle</span>
    {:else if state === 'error' || state === 'no-api'}
      <span class="pill-err"><span class="glow-dot text-rose-400"></span> Error</span>
    {/if}
  </div>

  {#if state === 'checking'}
    <p class="mt-3 text-sm leading-6 text-ink-300">Asking the fleet API if your principal already has an HQ...</p>
  {:else if state === 'no-api'}
    <p class="mt-3 text-sm leading-6 text-ink-300">
      Can't reach the fleet API at <code class="font-mono text-brand-600 dark:text-brand-300">{$fleetApiUrl}</code>.
    </p>
    <p class="mt-1 text-xs leading-5 text-ink-400">
      Start it locally with <code class="font-mono">python oci-fleet/fleet-api.py</code>,
      or update the URL in
      <a href="/hq/settings" class="font-semibold text-brand-600 underline dark:text-brand-300">Settings</a>.
    </p>
    <button class="btn-ghost btn-sm mt-3" on:click={autoLookup}>Retry</button>
  {:else if state === 'no-container'}
    <p class="mt-3 text-sm leading-6 text-ink-300">
      Your principal doesn't have a CafresoAI HQ yet. Provisioning takes about a minute.
      We'll spin up a private OCI container in Ashburn with 1 OCPU, 6 GB, and ARM64.
    </p>
    <button class="btn-primary mt-4" on:click={startProvision}>
      Provision my HQ
    </button>
  {:else if state === 'provisioning'}
    <p class="mt-3 text-sm leading-6 text-ink-300">
      Building your HQ. This can take 60 to 90 seconds while OCI pulls the image
      and starts the container.
    </p>
    <div class="mt-4 space-y-2">
      <div class="flex items-center gap-2 text-sm">
        <span class="glow-dot text-amber-400 animate-pulse"></span>
        <span class="font-mono text-ink-200">{phase || 'working'}</span>
      </div>
      <div class="h-1.5 w-full overflow-hidden rounded-full bg-ink-800/70">
        <div class="h-full w-1/3 animate-pulse rounded-full bg-brand-500"></div>
      </div>
    </div>
  {:else if state === 'existing'}
    <p class="mt-3 text-sm leading-6 text-ink-300">
      Your HQ is live. Endpoint adopted, and the rest of the app is already pointed at it.
    </p>
    <code class="mt-2 block break-all rounded-xl border border-ink-600/60 bg-[var(--code-bg)] px-3 py-3 font-mono text-xs text-ink-100">{endpoint}</code>
    <a href="/hq/app" class="btn-primary btn-sm mt-3">Launch HQ</a>
  {:else if state === 'ready'}
    <p class="mt-3 text-sm leading-6 text-ink-300">
      Your CafresoAI HQ is online. Welcome.
    </p>
    <code class="mt-2 block break-all rounded-xl border border-ink-600/60 bg-[var(--code-bg)] px-3 py-3 font-mono text-xs text-ink-100">{endpoint}</code>
    <a href="/hq/app" class="btn-primary btn-sm mt-3">Launch HQ</a>
  {:else if state === 'error'}
    <p class="mt-3 text-sm text-rose-700 dark:text-rose-300">{error}</p>
    <div class="mt-3 flex gap-2">
      <button class="btn-ghost btn-sm" on:click={autoLookup}>Retry lookup</button>
      <button class="btn-ghost btn-sm" on:click={startProvision} disabled={!apiOk}>
        Try provision
      </button>
    </div>
  {:else}
    <p class="mt-3 text-sm leading-6 text-ink-300">Sign in with Internet Identity to check your HQ.</p>
  {/if}
</div>
