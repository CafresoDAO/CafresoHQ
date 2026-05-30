<script>
  import { isAuthenticated, principalText, login } from '$lib/stores/auth.js';
  import { endpointUrl, endpointHealth, probeHealth } from '$lib/stores/endpoint.js';
  import EndpointStatus from '$lib/components/EndpointStatus.svelte';
  import ProvisionPanel from '$lib/components/ProvisionPanel.svelte';

  function fmtUptime(seconds) {
    if (seconds == null) return '-';
    const m = Math.floor(seconds / 60);
    const h = Math.floor(m / 60);
    if (h > 0) return `${h}h ${m % 60}m`;
    if (m > 0) return `${m}m ${seconds % 60}s`;
    return `${seconds}s`;
  }
</script>

<section class="space-y-6">
  <header class="card overflow-hidden p-6 sm:p-8">
    <div class="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
      <div class="max-w-3xl">
        <div class="page-kicker">CafresoAI / Control Plane</div>
        <h1 class="page-title mt-5">Command Center<span class="text-brand-500">.</span></h1>
        <p class="mt-5 max-w-2xl text-base leading-7 text-ink-300">
          Your private OCI container, encrypted vault, and ecosystem-shared Internet
          Identity principal in one warm, glassy workspace.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <EndpointStatus />
        {#if $isAuthenticated}
          <span class="pill-ok"><span class="glow-dot text-emerald-400"></span> II connected</span>
        {:else}
          <span class="pill-idle"><span class="glow-dot text-ink-400"></span> Anonymous</span>
        {/if}
      </div>
    </div>
  </header>

  <div class="grid gap-4 lg:grid-cols-2">
    <div class="card p-5">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="page-kicker">Identity</div>
          <div class="mt-2 text-xl font-semibold">
            {#if $isAuthenticated}
              Signed in as principal
            {:else}
              Not signed in
            {/if}
          </div>
        </div>
        {#if $isAuthenticated}
          <span class="pill-ok"><span class="glow-dot text-emerald-400"></span> Authenticated</span>
        {:else}
          <span class="pill-idle"><span class="glow-dot text-ink-400"></span> Idle</span>
        {/if}
      </div>

      {#if $isAuthenticated}
        <div class="mt-5 space-y-2">
          <div class="text-xs uppercase tracking-[0.22em] text-ink-400">Ecosystem principal</div>
          <code class="block break-all rounded-xl border border-ink-600/60 bg-[var(--code-bg)] px-3 py-3 font-mono text-xs text-ink-100">
            {$principalText}
          </code>
          <div class="text-xs text-ink-400">
            Same principal as Banking.Brave, Cafreso, and Minegold.
          </div>
        </div>
      {:else}
        <p class="mt-4 text-sm leading-6 text-ink-300">
          Sign in with Internet Identity to derive your ecosystem principal and
          unlock your CafresoAI container.
        </p>
        <button class="btn-primary mt-5" on:click={login}>
          Sign in with Internet Identity
        </button>
      {/if}
    </div>

    <div class="card p-5">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="page-kicker">OCI Container</div>
          <div class="mt-2 truncate text-xl font-semibold">
            {$endpointUrl || 'No endpoint configured'}
          </div>
        </div>
        <EndpointStatus />
      </div>

      {#if $endpointHealth.state === 'ok' && $endpointHealth.data}
        {@const d = $endpointHealth.data}
        <dl class="mt-5 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
          <dt class="text-ink-400">Mode</dt>
          <dd class="font-mono text-ink-100">{d.mode}</dd>

          <dt class="text-ink-400">Vault backend</dt>
          <dd class="font-mono text-ink-100">{d.vault_backend}</dd>

          <dt class="text-ink-400">Uptime</dt>
          <dd class="font-mono text-ink-100">{fmtUptime(d.uptime_seconds)}</dd>

          <dt class="text-ink-400">Platform</dt>
          <dd class="font-mono text-ink-100">{d.platform}</dd>

          <dt class="text-ink-400">Claude Code CLI</dt>
          <dd>{d.claude_code ? 'available' : 'not installed'}</dd>

          <dt class="text-ink-400">Codex CLI</dt>
          <dd>{d.codex ? 'available' : 'not installed'}</dd>

          <dt class="text-ink-400">OCI vault ready</dt>
          <dd>{d.oci_vault_ready ? 'ready' : 'not ready'}</dd>
        </dl>
        <div class="mt-5 flex flex-wrap gap-2">
          <a href="/hq/app" class="btn-primary btn-sm">Launch HQ</a>
          <button class="btn-ghost btn-sm" on:click={() => probeHealth()}>
            Re-check
          </button>
        </div>
      {:else if $endpointHealth.state === 'error'}
        <p class="mt-4 text-sm text-rose-700 dark:text-rose-300">
          Couldn't reach this endpoint: {$endpointHealth.error}
        </p>
        <a href="/hq/settings" class="btn-ghost btn-sm mt-4">Update endpoint</a>
      {:else if !$endpointUrl}
        <p class="mt-4 text-sm leading-6 text-ink-300">
          Configure the URL of your OCI Container Instance to connect.
        </p>
        <a href="/hq/settings" class="btn-primary btn-sm mt-4">Configure endpoint</a>
      {/if}
    </div>
  </div>

  {#if $isAuthenticated}
    <ProvisionPanel />
  {/if}

  <div class="grid gap-4 sm:grid-cols-3">
    <a href="/hq/chat" class="card p-5 transition-colors hover:border-brand-500/50 group">
      <div class="page-kicker">Action</div>
      <div class="mt-2 text-lg font-semibold transition-colors group-hover:text-brand-500">Chat</div>
      <p class="mt-2 text-sm leading-6 text-ink-300">Talk to Claude through your private container.</p>
    </a>
    <a href="/hq/vault" class="card p-5 transition-colors hover:border-brand-500/50 group">
      <div class="page-kicker">Action</div>
      <div class="mt-2 text-lg font-semibold transition-colors group-hover:text-brand-500">Vault</div>
      <p class="mt-2 text-sm leading-6 text-ink-300">Browse encrypted files of any type, zero-knowledge.</p>
    </a>
    <a href="/hq/settings" class="card p-5 transition-colors hover:border-brand-500/50 group">
      <div class="page-kicker">Action</div>
      <div class="mt-2 text-lg font-semibold transition-colors group-hover:text-brand-500">Settings</div>
      <p class="mt-2 text-sm leading-6 text-ink-300">Endpoint URL, deployment mode, and identity controls.</p>
    </a>
  </div>
</section>
