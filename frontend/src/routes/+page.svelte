<script>
  import { isAuthenticated, principalText, login } from '$lib/stores/auth.js';
  import { endpointUrl, endpointHealth, probeHealth } from '$lib/stores/endpoint.js';
  import EndpointStatus from '$lib/components/EndpointStatus.svelte';
  import ProvisionPanel from '$lib/components/ProvisionPanel.svelte';

  function fmtUptime(seconds) {
    if (seconds == null) return '—';
    const m = Math.floor(seconds / 60);
    const h = Math.floor(m / 60);
    if (h > 0)      return `${h}h ${m % 60}m`;
    if (m > 0)      return `${m}m ${seconds % 60}s`;
    return `${seconds}s`;
  }
</script>

<section class="space-y-6">
  <header class="space-y-1">
    <h1 class="text-2xl font-semibold tracking-tight">Command Center</h1>
    <p class="text-sm text-ink-400">
      Your CafresoAI environment, served from a private OCI container —
      authenticated by your ecosystem-shared Internet Identity principal.
    </p>
  </header>

  <!-- ── Auth + Endpoint summary cards ───────────────────────────────────── -->
  <div class="grid gap-4 md:grid-cols-2">
    <!-- Identity card -->
    <div class="card p-5">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="text-xs uppercase tracking-wider text-ink-400">Identity</div>
          <div class="mt-1 font-semibold">
            {#if $isAuthenticated}
              Signed in
            {:else}
              Not signed in
            {/if}
          </div>
        </div>
        {#if $isAuthenticated}
          <span class="pill-ok">
            <span class="glow-dot text-emerald-400"></span>
            Authenticated
          </span>
        {:else}
          <span class="pill-idle">
            <span class="glow-dot text-ink-400"></span>
            Anonymous
          </span>
        {/if}
      </div>

      {#if $isAuthenticated}
        <div class="mt-4 space-y-2">
          <div class="text-xs text-ink-400">Ecosystem principal</div>
          <code class="block font-mono text-xs text-ink-100 break-all bg-[var(--code-bg)]
                       border border-ink-600/40 rounded-md px-3 py-2">
            {$principalText}
          </code>
          <div class="text-xs text-ink-400">
            Same principal as Banking.Brave, Cafreso, and Minegold.
          </div>
        </div>
      {:else}
        <p class="mt-3 text-sm text-ink-200">
          Sign in with Internet Identity to derive your ecosystem principal and
          unlock your CafresoAI container.
        </p>
        <button class="btn-primary mt-4" on:click={login}>
          Sign in with Internet Identity
        </button>
      {/if}
    </div>

    <!-- Container card -->
    <div class="card p-5">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="text-xs uppercase tracking-wider text-ink-400">OCI Container</div>
          <div class="mt-1 font-semibold">
            {$endpointUrl || 'No endpoint configured'}
          </div>
        </div>
        <EndpointStatus />
      </div>

      {#if $endpointHealth.state === 'ok' && $endpointHealth.data}
        {@const d = $endpointHealth.data}
        <dl class="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <dt class="text-ink-400">Mode</dt>
          <dd class="font-mono text-ink-100">{d.mode}</dd>

          <dt class="text-ink-400">Vault backend</dt>
          <dd class="font-mono text-ink-100">{d.vault_backend}</dd>

          <dt class="text-ink-400">Uptime</dt>
          <dd class="font-mono text-ink-100">{fmtUptime(d.uptime_seconds)}</dd>

          <dt class="text-ink-400">Platform</dt>
          <dd class="font-mono text-ink-100">{d.platform}</dd>

          <dt class="text-ink-400">Claude Code CLI</dt>
          <dd>{d.claude_code ? '✅ available' : '— not installed'}</dd>

          <dt class="text-ink-400">Codex CLI</dt>
          <dd>{d.codex ? '✅ available' : '— not installed'}</dd>

          <dt class="text-ink-400">OCI vault ready</dt>
          <dd>{d.oci_vault_ready ? '✅ ready' : '— not ready'}</dd>
        </dl>
        <div class="mt-4 flex flex-wrap gap-2">
          <a href="/app" class="btn-primary btn-sm">
            Launch HQ →
          </a>
          <button class="btn-ghost btn-sm" on:click={() => probeHealth()}>
            Re-check
          </button>
        </div>
      {:else if $endpointHealth.state === 'error'}
        <p class="mt-3 text-sm text-rose-300">
          Couldn't reach this endpoint: {$endpointHealth.error}
        </p>
        <a href="/settings" class="btn-ghost btn-sm mt-3">Update endpoint</a>
      {:else if !$endpointUrl}
        <p class="mt-3 text-sm text-ink-200">
          Configure the URL of your OCI Container Instance to connect.
        </p>
        <a href="/settings" class="btn-primary btn-sm mt-3">Configure endpoint →</a>
      {/if}
    </div>
  </div>

  <!-- ── Auto-provision panel (only meaningful when signed in) ─────────── -->
  {#if $isAuthenticated}
    <ProvisionPanel />
  {/if}

  <!-- ── Quick actions ──────────────────────────────────────────────────── -->
  <div class="grid gap-4 sm:grid-cols-3">
    <a href="/chat" class="card p-5 hover:border-brand-500/40 transition-colors group">
      <div class="text-xs uppercase tracking-wider text-ink-400">Action</div>
      <div class="mt-1 text-lg font-semibold group-hover:text-brand-400 transition-colors">Chat</div>
      <p class="mt-2 text-sm text-ink-200">Talk to Claude through your private container.</p>
    </a>
    <a href="/vault" class="card p-5 hover:border-brand-500/40 transition-colors group">
      <div class="text-xs uppercase tracking-wider text-ink-400">Action</div>
      <div class="mt-1 text-lg font-semibold group-hover:text-brand-400 transition-colors">Vault</div>
      <p class="mt-2 text-sm text-ink-200">Browse your Markdown notes stored in OCI Object Storage.</p>
    </a>
    <a href="/settings" class="card p-5 hover:border-brand-500/40 transition-colors group">
      <div class="text-xs uppercase tracking-wider text-ink-400">Action</div>
      <div class="mt-1 text-lg font-semibold group-hover:text-brand-400 transition-colors">Settings</div>
      <p class="mt-2 text-sm text-ink-200">Endpoint URL, deployment mode, debug info.</p>
    </a>
  </div>
</section>
