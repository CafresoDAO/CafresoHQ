<script>
  import { onMount, onDestroy } from 'svelte';
  import { isAuthenticated, principalText } from '$lib/stores/auth.js';
  import {
    isAdmin,
    adminTab,
    dashboardMetrics,
    allSessions,
    infrastructure,
    adminLoading,
    adminError,
    fetchDashboard,
    fetchAllSessions,
    fetchInfrastructure,
    killSession,
    verifyAdmin,
  } from '$lib/stores/admin.js';
  import {
    templates,
    fetchTemplates,
  } from '$lib/stores/workspaces.js';

  let pollInterval;
  let killing = {};

  // Sidebar tabs
  const tabs = [
    { id: 'dashboard',      label: 'Dashboard',      icon: 'chart' },
    { id: 'sessions',       label: 'Sessions',        icon: 'play' },
    { id: 'workspaces',     label: 'Workspaces',      icon: 'grid' },
    { id: 'infrastructure', label: 'Infrastructure',  icon: 'server' },
  ];

  // ── Data loading ──────────────────────────────────────────────────────────

  async function loadAll() {
    await Promise.all([
      fetchDashboard(),
      fetchAllSessions(),
      fetchInfrastructure(),
      fetchTemplates(),
    ]);
  }

  onMount(async () => {
    if ($isAuthenticated) {
      await verifyAdmin();
    }
    await loadAll();
    // Poll every 15s for live data
    pollInterval = setInterval(loadAll, 15_000);
  });

  onDestroy(() => {
    clearInterval(pollInterval);
  });

  // ── Actions ───────────────────────────────────────────────────────────────

  async function handleKill(sid) {
    if (!confirm(`Kill session ${sid.slice(0, 12)}...? This will force-stop the VM/container.`)) return;
    killing = { ...killing, [sid]: true };
    try {
      await killSession(sid);
    } catch (e) {
      alert('Kill failed: ' + (e.message || e));
    } finally {
      killing = { ...killing, [sid]: false };
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  function fmtUptime(s) {
    if (!s) return '-';
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  }

  function fmtDate(iso) {
    if (!iso) return '-';
    return new Date(iso).toLocaleString('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
  }

  function shortPrincipal(p) {
    if (!p) return '-';
    return p.length > 20 ? p.slice(0, 6) + '...' + p.slice(-4) : p;
  }

  function statusColor(s) {
    if (s === 'running') return 'text-green-400';
    if (s === 'starting') return 'text-yellow-400';
    if (s === 'stopping') return 'text-orange-400';
    if (s === 'error') return 'text-red-400';
    return 'text-ink-400';
  }

  function providerColor(p) {
    if (p === 'hyperv') return 'bg-blue-500/15 text-blue-300 border-blue-500/30';
    if (p === 'oci') return 'bg-orange-500/15 text-orange-300 border-orange-500/30';
    if (p === 'canister') return 'bg-purple-500/15 text-purple-300 border-purple-500/30';
    if (p === 'custom') return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
    return 'bg-ink-700 text-ink-300 border-ink-600';
  }

  // Dashboard metric cards
  $: metrics = $dashboardMetrics || {};
  $: totalSessions = $allSessions.length;
  $: runningSessions = $allSessions.filter(s => s.status === 'running').length;
  $: errorSessions = $allSessions.filter(s => s.status === 'error').length;
  $: providerCounts = $allSessions.reduce((acc, s) => {
    acc[s.provider] = (acc[s.provider] || 0) + 1;
    return acc;
  }, {});
</script>

{#if !$isAuthenticated}
  <section class="space-y-5">
    <header class="card p-6 sm:p-8">
      <div class="page-kicker">Admin</div>
      <h1 class="page-title mt-4">Sign in required<span class="text-brand-500">.</span></h1>
      <p class="mt-4 text-sm text-ink-300">Admin dashboard requires authentication.</p>
    </header>
  </section>

{:else if !$isAdmin}
  <section class="space-y-5">
    <header class="card p-6 sm:p-8">
      <div class="page-kicker">Admin</div>
      <h1 class="page-title mt-4">Access denied<span class="text-brand-500">.</span></h1>
      <p class="mt-4 text-sm text-ink-300">
        Your principal does not have admin privileges.
      </p>
      <code class="mt-2 block text-xs font-mono text-ink-400 break-all">{$principalText}</code>
    </header>
  </section>

{:else}
  <div class="flex gap-0 min-h-[calc(100vh-6rem)]">
    <!-- ── Sidebar ─────────────────────────────────────────────────────── -->
    <aside class="hidden md:flex flex-col w-56 shrink-0 border-r border-ink-700/50 pr-2">
      <div class="sticky top-20 space-y-1 py-2">
        <div class="px-3 pb-3">
          <div class="text-xs uppercase tracking-[0.22em] text-ink-400">Admin</div>
        </div>
        {#each tabs as tab}
          <button
            class="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium transition-colors
                   {$adminTab === tab.id
                     ? 'bg-brand-500/15 text-brand-300'
                     : 'text-ink-300 hover:bg-ink-800/60 hover:text-ink-100'}"
            on:click={() => adminTab.set(tab.id)}
          >
            {#if tab.icon === 'chart'}
              <svg class="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M3 13h4v8H3zM10 9h4v12h-4zM17 5h4v16h-4z"/></svg>
            {:else if tab.icon === 'play'}
              <svg class="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M10 8l6 4-6 4V8z"/></svg>
            {:else if tab.icon === 'grid'}
              <svg class="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
            {:else if tab.icon === 'server'}
              <svg class="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="20" height="6" rx="2"/><rect x="2" y="15" width="20" height="6" rx="2"/><circle cx="6" cy="6" r="1"/><circle cx="6" cy="18" r="1"/></svg>
            {/if}
            {tab.label}
          </button>
        {/each}

        <div class="mt-6 px-3 pt-4 border-t border-ink-700/50">
          <div class="text-[10px] uppercase tracking-[0.2em] text-ink-500 mb-2">Quick stats</div>
          <div class="space-y-1.5 text-xs text-ink-300">
            <div class="flex justify-between"><span>Sessions</span><span class="text-ink-100 font-mono">{totalSessions}</span></div>
            <div class="flex justify-between"><span>Running</span><span class="text-green-400 font-mono">{runningSessions}</span></div>
            {#if errorSessions > 0}
              <div class="flex justify-between"><span>Errors</span><span class="text-red-400 font-mono">{errorSessions}</span></div>
            {/if}
            <div class="flex justify-between"><span>Templates</span><span class="text-ink-100 font-mono">{$templates.length}</span></div>
          </div>
        </div>
      </div>
    </aside>

    <!-- ── Mobile tab bar ──────────────────────────────────────────────── -->
    <div class="flex md:hidden overflow-x-auto gap-1 px-2 py-2 mb-4 border-b border-ink-700/50 w-full shrink-0">
      {#each tabs as tab}
        <button
          class="rounded-full px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-colors
                 {$adminTab === tab.id
                   ? 'bg-brand-500/20 text-brand-300'
                   : 'text-ink-400 hover:text-ink-200'}"
          on:click={() => adminTab.set(tab.id)}
        >{tab.label}</button>
      {/each}
    </div>

    <!-- ── Main content area ───────────────────────────────────────────── -->
    <main class="flex-1 min-w-0 px-2 sm:px-4 py-2">
      {#if $adminLoading && !$dashboardMetrics}
        <div class="flex items-center gap-2 text-sm text-ink-300 py-8">
          <span class="glow-dot text-brand-400 animate-pulse"></span>
          Loading admin data...
        </div>
      {/if}

      {#if $adminError}
        <div class="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {$adminError}
        </div>
      {/if}

      <!-- ════════════════ DASHBOARD TAB ════════════════ -->
      {#if $adminTab === 'dashboard'}
        <div class="space-y-5">
          <div>
            <div class="page-kicker">Admin / Dashboard</div>
            <h1 class="text-2xl font-semibold text-ink-50 mt-1">Overview<span class="text-brand-500">.</span></h1>
          </div>

          <!-- Metric cards row -->
          <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div class="card p-4">
              <div class="text-[10px] uppercase tracking-[0.2em] text-ink-400">Active sessions</div>
              <div class="mt-1 text-3xl font-bold text-ink-50 font-mono">{runningSessions}</div>
              <div class="mt-1 text-xs text-ink-400">{totalSessions} total</div>
            </div>
            <div class="card p-4">
              <div class="text-[10px] uppercase tracking-[0.2em] text-ink-400">Hyper-V VMs</div>
              <div class="mt-1 text-3xl font-bold text-blue-300 font-mono">{providerCounts.hyperv || 0}</div>
              <div class="mt-1 text-xs text-ink-400">sessions</div>
            </div>
            <div class="card p-4">
              <div class="text-[10px] uppercase tracking-[0.2em] text-ink-400">OCI containers</div>
              <div class="mt-1 text-3xl font-bold text-orange-300 font-mono">{providerCounts.oci || 0}</div>
              <div class="mt-1 text-xs text-ink-400">sessions</div>
            </div>
            <div class="card p-4">
              <div class="text-[10px] uppercase tracking-[0.2em] text-ink-400">Errors</div>
              <div class="mt-1 text-3xl font-bold {errorSessions > 0 ? 'text-red-400' : 'text-green-400'} font-mono">{errorSessions}</div>
              <div class="mt-1 text-xs text-ink-400">{errorSessions === 0 ? 'all clear' : 'need attention'}</div>
            </div>
          </div>

          <!-- Infrastructure summary -->
          {#if $infrastructure}
            <div class="card p-5">
              <h3 class="text-sm font-semibold text-ink-100 mb-3">Infrastructure</h3>
              <div class="grid gap-4 sm:grid-cols-3">
                <!-- Hyper-V -->
                <div class="rounded-xl border border-ink-600/40 bg-ink-800/30 p-3">
                  <div class="flex items-center gap-2 mb-2">
                    <span class="glow-dot {$infrastructure.hyperv?.status === 'healthy' ? 'text-green-400' : 'text-red-400'}"></span>
                    <span class="text-xs font-semibold text-ink-100">Hyper-V Host</span>
                  </div>
                  <div class="space-y-1 text-xs text-ink-300">
                    <div class="flex justify-between"><span>Status</span><span class="text-ink-100">{$infrastructure.hyperv?.status || 'unknown'}</span></div>
                    <div class="flex justify-between"><span>Total VMs</span><span class="font-mono">{$infrastructure.hyperv?.total_vms ?? '-'}</span></div>
                    <div class="flex justify-between"><span>Running</span><span class="font-mono text-green-400">{$infrastructure.hyperv?.running_vms ?? '-'}</span></div>
                  </div>
                </div>
                <!-- OCI -->
                <div class="rounded-xl border border-ink-600/40 bg-ink-800/30 p-3">
                  <div class="flex items-center gap-2 mb-2">
                    <span class="glow-dot {$infrastructure.oci?.status === 'healthy' ? 'text-green-400' : 'text-yellow-400'}"></span>
                    <span class="text-xs font-semibold text-ink-100">OCI Fleet</span>
                  </div>
                  <div class="space-y-1 text-xs text-ink-300">
                    <div class="flex justify-between"><span>Status</span><span class="text-ink-100">{$infrastructure.oci?.status || 'unknown'}</span></div>
                    <div class="flex justify-between"><span>Containers</span><span class="font-mono">{$infrastructure.oci?.total_containers ?? '-'}</span></div>
                    <div class="flex justify-between"><span>Region</span><span>{$infrastructure.oci?.region || '-'}</span></div>
                  </div>
                </div>
                <!-- coturn -->
                <div class="rounded-xl border border-ink-600/40 bg-ink-800/30 p-3">
                  <div class="flex items-center gap-2 mb-2">
                    <span class="glow-dot {$infrastructure.turn?.status === 'healthy' ? 'text-green-400' : 'text-yellow-400'}"></span>
                    <span class="text-xs font-semibold text-ink-100">TURN Relay</span>
                  </div>
                  <div class="space-y-1 text-xs text-ink-300">
                    <div class="flex justify-between"><span>Status</span><span class="text-ink-100">{$infrastructure.turn?.status || 'not configured'}</span></div>
                    <div class="flex justify-between"><span>Port</span><span class="font-mono">{$infrastructure.turn?.port || '3478'}</span></div>
                    <div class="flex justify-between"><span>TLS</span><span>{$infrastructure.turn?.tls ? 'yes' : 'no'}</span></div>
                  </div>
                </div>
              </div>
            </div>
          {/if}

          <!-- Recent sessions -->
          <div class="card p-5">
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-sm font-semibold text-ink-100">Recent sessions</h3>
              <button class="text-xs text-brand-400 hover:text-brand-300" on:click={() => adminTab.set('sessions')}>
                View all
              </button>
            </div>
            <div class="overflow-x-auto -mx-2">
              <table class="w-full text-xs">
                <thead>
                  <tr class="text-ink-400 text-left">
                    <th class="px-2 py-1.5 font-medium">Session</th>
                    <th class="px-2 py-1.5 font-medium">Template</th>
                    <th class="px-2 py-1.5 font-medium">Provider</th>
                    <th class="px-2 py-1.5 font-medium">Status</th>
                    <th class="px-2 py-1.5 font-medium">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {#each $allSessions.slice(0, 8) as s}
                    <tr class="border-t border-ink-700/40 hover:bg-ink-800/30">
                      <td class="px-2 py-2 font-mono text-ink-200">{s.session_id?.slice(0, 16) || '-'}</td>
                      <td class="px-2 py-2 text-ink-200">{s.display_name || s.template_id}</td>
                      <td class="px-2 py-2">
                        <span class="inline-block rounded-full border px-1.5 py-0.5 text-[10px] {providerColor(s.provider)}">
                          {s.provider || '-'}
                        </span>
                      </td>
                      <td class="px-2 py-2">
                        <span class="flex items-center gap-1">
                          <span class="glow-dot {statusColor(s.status)}"></span>
                          {s.status}
                        </span>
                      </td>
                      <td class="px-2 py-2 text-ink-400">{fmtDate(s.created_at)}</td>
                    </tr>
                  {/each}
                  {#if $allSessions.length === 0}
                    <tr><td colspan="5" class="px-2 py-4 text-center text-ink-400">No sessions</td></tr>
                  {/if}
                </tbody>
              </table>
            </div>
          </div>
        </div>

      <!-- ════════════════ SESSIONS TAB ════════════════ -->
      {:else if $adminTab === 'sessions'}
        <div class="space-y-5">
          <div class="flex items-center justify-between">
            <div>
              <div class="page-kicker">Admin / Sessions</div>
              <h1 class="text-2xl font-semibold text-ink-50 mt-1">All sessions<span class="text-brand-500">.</span></h1>
            </div>
            <button class="btn-ghost text-xs" on:click={fetchAllSessions}>Refresh</button>
          </div>

          <div class="card overflow-hidden">
            <div class="overflow-x-auto">
              <table class="w-full text-xs">
                <thead>
                  <tr class="text-ink-400 text-left bg-ink-800/40">
                    <th class="px-3 py-2.5 font-medium">Session ID</th>
                    <th class="px-3 py-2.5 font-medium">Display name</th>
                    <th class="px-3 py-2.5 font-medium">Principal</th>
                    <th class="px-3 py-2.5 font-medium">Provider</th>
                    <th class="px-3 py-2.5 font-medium">Protocol</th>
                    <th class="px-3 py-2.5 font-medium">Status</th>
                    <th class="px-3 py-2.5 font-medium">IP</th>
                    <th class="px-3 py-2.5 font-medium">Created</th>
                    <th class="px-3 py-2.5 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {#each $allSessions as s}
                    <tr class="border-t border-ink-700/40 hover:bg-ink-800/20 transition-colors">
                      <td class="px-3 py-2 font-mono text-ink-200 whitespace-nowrap" title={s.session_id}>
                        {s.session_id?.slice(0, 16) || '-'}
                      </td>
                      <td class="px-3 py-2 text-ink-100 font-medium">{s.display_name || s.template_id}</td>
                      <td class="px-3 py-2 font-mono text-ink-300" title={s.principal}>
                        {shortPrincipal(s.principal)}
                      </td>
                      <td class="px-3 py-2">
                        <span class="inline-block rounded-full border px-1.5 py-0.5 text-[10px] {providerColor(s.provider)}">
                          {s.provider || '-'}
                        </span>
                      </td>
                      <td class="px-3 py-2 text-ink-300">{s.stream_protocol || '-'}</td>
                      <td class="px-3 py-2">
                        <span class="flex items-center gap-1.5">
                          <span class="glow-dot {statusColor(s.status)}"></span>
                          <span class="text-ink-200">{s.status}</span>
                        </span>
                      </td>
                      <td class="px-3 py-2 font-mono text-ink-300">{s.ip || '-'}</td>
                      <td class="px-3 py-2 text-ink-400 whitespace-nowrap">{fmtDate(s.created_at)}</td>
                      <td class="px-3 py-2">
                        {#if s.status === 'running' || s.status === 'starting' || s.status === 'error'}
                          <button
                            class="rounded-lg bg-red-500/15 border border-red-500/30 px-2 py-1 text-[10px] font-medium text-red-300 hover:bg-red-500/25 transition-colors disabled:opacity-50"
                            disabled={killing[s.session_id]}
                            on:click={() => handleKill(s.session_id)}
                          >
                            {killing[s.session_id] ? 'Killing...' : 'Kill'}
                          </button>
                        {:else}
                          <span class="text-ink-500 text-[10px]">{s.status}</span>
                        {/if}
                      </td>
                    </tr>
                  {/each}
                  {#if $allSessions.length === 0}
                    <tr><td colspan="9" class="px-3 py-6 text-center text-ink-400">No sessions found</td></tr>
                  {/if}
                </tbody>
              </table>
            </div>
          </div>

          {#if $allSessions.length > 0}
            <div class="text-xs text-ink-400 text-right">{$allSessions.length} session{$allSessions.length === 1 ? '' : 's'} total</div>
          {/if}
        </div>

      <!-- ════════════════ WORKSPACES TAB ════════════════ -->
      {:else if $adminTab === 'workspaces'}
        <div class="space-y-5">
          <div>
            <div class="page-kicker">Admin / Workspaces</div>
            <h1 class="text-2xl font-semibold text-ink-50 mt-1">Template catalog<span class="text-brand-500">.</span></h1>
          </div>

          <div class="card overflow-hidden">
            <div class="overflow-x-auto">
              <table class="w-full text-xs">
                <thead>
                  <tr class="text-ink-400 text-left bg-ink-800/40">
                    <th class="px-3 py-2.5 font-medium">ID</th>
                    <th class="px-3 py-2.5 font-medium">Name</th>
                    <th class="px-3 py-2.5 font-medium">Category</th>
                    <th class="px-3 py-2.5 font-medium">Provider</th>
                    <th class="px-3 py-2.5 font-medium">Protocol</th>
                    <th class="px-3 py-2.5 font-medium">Resources</th>
                    <th class="px-3 py-2.5 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {#each $templates as t}
                    <tr class="border-t border-ink-700/40 hover:bg-ink-800/20 transition-colors {t.enabled ? '' : 'opacity-50'}">
                      <td class="px-3 py-2 font-mono text-ink-300">{t.id}</td>
                      <td class="px-3 py-2 text-ink-100 font-medium">{t.name}</td>
                      <td class="px-3 py-2 text-ink-300">{t.category}</td>
                      <td class="px-3 py-2">
                        <span class="inline-block rounded-full border px-1.5 py-0.5 text-[10px] {providerColor(t.provider)}">
                          {t.provider}
                        </span>
                      </td>
                      <td class="px-3 py-2 text-ink-300">{t.stream_protocol}</td>
                      <td class="px-3 py-2 text-ink-300 font-mono">
                        {#if t.resources?.vcpus}
                          {t.resources.vcpus}cpu
                        {:else if t.resources?.ocpus}
                          {t.resources.ocpus}cpu
                        {/if}
                        {#if t.resources?.memory_gb}
                          {t.resources.memory_gb}gb
                        {/if}
                        {#if t.resources?.gpu_partition}
                          gpu:{t.resources.gpu_partition}
                        {/if}
                        {#if !t.resources?.vcpus && !t.resources?.ocpus && !t.resources?.memory_gb}
                          -
                        {/if}
                      </td>
                      <td class="px-3 py-2">
                        {#if t.enabled}
                          <span class="inline-flex items-center gap-1 text-green-400">
                            <span class="glow-dot text-green-400"></span> enabled
                          </span>
                        {:else}
                          <span class="inline-flex items-center gap-1 text-ink-500">
                            <span class="glow-dot text-ink-500"></span> disabled
                          </span>
                        {/if}
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </div>

          <div class="text-xs text-ink-400 text-right">
            {$templates.length} template{$templates.length === 1 ? '' : 's'}
            ({$templates.filter(t => t.enabled).length} enabled)
          </div>
        </div>

      <!-- ════════════════ INFRASTRUCTURE TAB ════════════════ -->
      {:else if $adminTab === 'infrastructure'}
        <div class="space-y-5">
          <div class="flex items-center justify-between">
            <div>
              <div class="page-kicker">Admin / Infrastructure</div>
              <h1 class="text-2xl font-semibold text-ink-50 mt-1">Provider health<span class="text-brand-500">.</span></h1>
            </div>
            <button class="btn-ghost text-xs" on:click={fetchInfrastructure}>Refresh</button>
          </div>

          {#if $infrastructure}
            <div class="grid gap-4 lg:grid-cols-2">
              <!-- Hyper-V Host -->
              <div class="card p-5">
                <div class="flex items-center gap-3 mb-4">
                  <div class="grid h-10 w-10 place-items-center rounded-xl bg-blue-500/15 text-blue-300">
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>
                  </div>
                  <div>
                    <div class="text-sm font-semibold text-ink-100">Hyper-V Host</div>
                    <div class="text-[10px] text-ink-400">Windows Server 2025 Datacenter</div>
                  </div>
                  <span class="ml-auto glow-dot {$infrastructure.hyperv?.status === 'healthy' ? 'text-green-400' : 'text-red-400'}"></span>
                </div>
                <div class="space-y-2 text-xs">
                  <div class="flex justify-between text-ink-300">
                    <span>Status</span>
                    <span class="text-ink-100 font-medium">{$infrastructure.hyperv?.status || 'unknown'}</span>
                  </div>
                  <div class="flex justify-between text-ink-300">
                    <span>Total VMs</span>
                    <span class="font-mono text-ink-100">{$infrastructure.hyperv?.total_vms ?? '-'}</span>
                  </div>
                  <div class="flex justify-between text-ink-300">
                    <span>Running VMs</span>
                    <span class="font-mono text-green-400">{$infrastructure.hyperv?.running_vms ?? '-'}</span>
                  </div>
                  <div class="flex justify-between text-ink-300">
                    <span>Stopped VMs</span>
                    <span class="font-mono text-ink-400">{$infrastructure.hyperv?.stopped_vms ?? '-'}</span>
                  </div>
                  {#if $infrastructure.hyperv?.vms}
                    <div class="mt-3 pt-3 border-t border-ink-700/40">
                      <div class="text-[10px] uppercase tracking-[0.2em] text-ink-400 mb-2">VM List</div>
                      {#each $infrastructure.hyperv.vms as vm}
                        <div class="flex items-center justify-between py-1">
                          <span class="font-mono text-ink-200">{vm.name}</span>
                          <span class="flex items-center gap-1">
                            <span class="glow-dot {vm.state === 'running' ? 'text-green-400' : 'text-ink-400'}"></span>
                            <span class="text-ink-300">{vm.state}</span>
                          </span>
                        </div>
                      {/each}
                    </div>
                  {/if}
                </div>
              </div>

              <!-- OCI Fleet -->
              <div class="card p-5">
                <div class="flex items-center gap-3 mb-4">
                  <div class="grid h-10 w-10 place-items-center rounded-xl bg-orange-500/15 text-orange-300">
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4"/></svg>
                  </div>
                  <div>
                    <div class="text-sm font-semibold text-ink-100">OCI Fleet</div>
                    <div class="text-[10px] text-ink-400">Oracle Cloud Container Instances</div>
                  </div>
                  <span class="ml-auto glow-dot {$infrastructure.oci?.status === 'healthy' ? 'text-green-400' : 'text-yellow-400'}"></span>
                </div>
                <div class="space-y-2 text-xs">
                  <div class="flex justify-between text-ink-300">
                    <span>Status</span>
                    <span class="text-ink-100 font-medium">{$infrastructure.oci?.status || 'unknown'}</span>
                  </div>
                  <div class="flex justify-between text-ink-300">
                    <span>Containers</span>
                    <span class="font-mono text-ink-100">{$infrastructure.oci?.total_containers ?? '-'}</span>
                  </div>
                  <div class="flex justify-between text-ink-300">
                    <span>Region</span>
                    <span class="text-ink-100">{$infrastructure.oci?.region || '-'}</span>
                  </div>
                  <div class="flex justify-between text-ink-300">
                    <span>Fleet file</span>
                    <span class="text-ink-100">{$infrastructure.oci?.fleet_file_exists ? 'present' : 'missing'}</span>
                  </div>
                </div>
              </div>

              <!-- TURN Relay -->
              <div class="card p-5">
                <div class="flex items-center gap-3 mb-4">
                  <div class="grid h-10 w-10 place-items-center rounded-xl bg-purple-500/15 text-purple-300">
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
                  </div>
                  <div>
                    <div class="text-sm font-semibold text-ink-100">TURN Relay</div>
                    <div class="text-[10px] text-ink-400">coturn for WebRTC NAT traversal</div>
                  </div>
                  <span class="ml-auto glow-dot {$infrastructure.turn?.status === 'healthy' ? 'text-green-400' : 'text-yellow-400'}"></span>
                </div>
                <div class="space-y-2 text-xs">
                  <div class="flex justify-between text-ink-300">
                    <span>Status</span>
                    <span class="text-ink-100 font-medium">{$infrastructure.turn?.status || 'not configured'}</span>
                  </div>
                  <div class="flex justify-between text-ink-300">
                    <span>Listening port</span>
                    <span class="font-mono text-ink-100">{$infrastructure.turn?.port || '3478'}</span>
                  </div>
                  <div class="flex justify-between text-ink-300">
                    <span>TLS port</span>
                    <span class="font-mono text-ink-100">{$infrastructure.turn?.tls_port || '5349'}</span>
                  </div>
                  <div class="flex justify-between text-ink-300">
                    <span>Auth secret</span>
                    <span class="text-ink-100">{$infrastructure.turn?.secret_configured ? 'configured' : 'not set'}</span>
                  </div>
                  <div class="flex justify-between text-ink-300">
                    <span>TLS certs</span>
                    <span class="text-ink-100">{$infrastructure.turn?.tls ? 'installed' : 'not found'}</span>
                  </div>
                  {#if $infrastructure.turn?.tls_listening !== undefined}
                  <div class="flex justify-between text-ink-300">
                    <span>TLS listening</span>
                    <span class="text-ink-100">{$infrastructure.turn?.tls_listening ? 'yes (5349)' : 'no'}</span>
                  </div>
                  {/if}
                  {#if $infrastructure.turn?.turn_url}
                  <div class="flex justify-between text-ink-300">
                    <span>Public URL</span>
                    <span class="font-mono text-ink-100 text-[10px]">{$infrastructure.turn?.turn_url}</span>
                  </div>
                  {/if}
                </div>
              </div>

              <!-- Caddy Gateway -->
              <div class="card p-5">
                <div class="flex items-center gap-3 mb-4">
                  <div class="grid h-10 w-10 place-items-center rounded-xl bg-green-500/15 text-green-300">
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/></svg>
                  </div>
                  <div>
                    <div class="text-sm font-semibold text-ink-100">Caddy Gateway</div>
                    <div class="text-[10px] text-ink-400">TLS terminator + reverse proxy</div>
                  </div>
                  <span class="ml-auto glow-dot {$infrastructure.caddy?.status === 'healthy' ? 'text-green-400' : 'text-yellow-400'}"></span>
                </div>
                <div class="space-y-2 text-xs">
                  <div class="flex justify-between text-ink-300">
                    <span>Status</span>
                    <span class="text-ink-100 font-medium">{$infrastructure.caddy?.status || 'unknown'}</span>
                  </div>
                  <div class="flex justify-between text-ink-300">
                    <span>Hostname</span>
                    <span class="text-ink-100">{$infrastructure.caddy?.hostname || '-'}</span>
                  </div>
                  <div class="flex justify-between text-ink-300">
                    <span>User routes</span>
                    <span class="font-mono text-ink-100">{$infrastructure.caddy?.user_routes ?? '-'}</span>
                  </div>
                  <div class="flex justify-between text-ink-300">
                    <span>Stream routes</span>
                    <span class="font-mono text-ink-100">{$infrastructure.caddy?.stream_routes ?? '-'}</span>
                  </div>
                </div>
              </div>

              <!-- VM Pool (Pre-warming) -->
              <div class="card p-5">
                <div class="flex items-center gap-3 mb-4">
                  <div class="grid h-10 w-10 place-items-center rounded-xl bg-emerald-500/15 text-emerald-300">
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>
                  </div>
                  <div>
                    <div class="text-sm font-semibold text-ink-100">VM Pool</div>
                    <div class="text-[10px] text-ink-400">Pre-warmed VMs for instant launch</div>
                  </div>
                  <span class="ml-auto glow-dot {($infrastructure.vm_pool?.total ?? 0) > 0 ? 'text-green-400' : 'text-yellow-400'}"></span>
                </div>
                <div class="space-y-2 text-xs">
                  <div class="flex justify-between text-ink-300">
                    <span>Total pool VMs</span>
                    <span class="font-mono text-ink-100">{$infrastructure.vm_pool?.total ?? 0}</span>
                  </div>
                  <div class="flex justify-between text-ink-300">
                    <span>Target per template</span>
                    <span class="font-mono text-ink-100">{$infrastructure.vm_pool?.target_per_template ?? '-'}</span>
                  </div>
                  <div class="flex justify-between text-ink-300">
                    <span>Max age</span>
                    <span class="text-ink-100">{$infrastructure.vm_pool?.max_age_hours ?? '-'}h</span>
                  </div>
                  {#if $infrastructure.vm_pool?.by_template}
                    <div class="mt-3 pt-3 border-t border-ink-700/40">
                      <div class="text-[10px] uppercase tracking-[0.2em] text-ink-400 mb-2">By Template</div>
                      {#each Object.entries($infrastructure.vm_pool.by_template) as [tid, info]}
                        <div class="flex items-center justify-between py-1">
                          <span class="font-mono text-ink-200">{tid}</span>
                          <span class="flex items-center gap-2">
                            <span class="text-green-400">{info.ready} ready</span>
                            <span class="text-ink-500">/</span>
                            <span class="text-ink-300">{info.total} total</span>
                          </span>
                        </div>
                      {/each}
                    </div>
                  {/if}
                  {#if $infrastructure.vm_pool?.entries?.length}
                    <div class="mt-3 pt-3 border-t border-ink-700/40">
                      <div class="text-[10px] uppercase tracking-[0.2em] text-ink-400 mb-2">Pool VMs</div>
                      {#each $infrastructure.vm_pool.entries as entry}
                        <div class="flex items-center justify-between py-1">
                          <span class="font-mono text-ink-200 truncate max-w-[200px]">{entry.vm_name}</span>
                          <span class="flex items-center gap-1">
                            <span class="glow-dot {entry.state === 'ready' ? 'text-green-400' : 'text-yellow-400'}"></span>
                            <span class="text-ink-300">{entry.state}</span>
                          </span>
                        </div>
                      {/each}
                    </div>
                  {/if}
                </div>
              </div>
            </div>
          {:else}
            <div class="card p-6 text-center text-sm text-ink-400">
              Loading infrastructure data...
            </div>
          {/if}
        </div>
      {/if}
    </main>
  </div>
{/if}
