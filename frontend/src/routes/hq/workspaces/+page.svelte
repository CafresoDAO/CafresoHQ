<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { isAuthenticated, principalText } from '$lib/stores/auth.js';
  import {
    templates,
    sessions,
    categories,
    activeCategory,
    searchQuery,
    filteredTemplates,
    activeSessions,
    launchingId,
    fetchTemplates,
    fetchSessions,
    launchWorkspace,
    runningSessionForTemplate,
    createCustomTemplate,
    deleteCustomTemplate,
  } from '$lib/stores/workspaces.js';
  import WorkspaceCard from '$lib/components/WorkspaceCard.svelte';
  import AppIcon from '$lib/components/AppIcon.svelte';
  import AddVmModal from '$lib/components/AddVmModal.svelte';
  import { operatorConfig, refreshOperatorConfig, workspaceAllowed, workspacesMessage } from '$lib/stores/operator.js';

  // ── Entitlement (private preview) ────────────────────────────────────────
  // The on-chain operator config carries the grant list; the fleet API
  // enforces the same list server-side — this gate is UX, not security.
  let entLoading = true;
  // DEV ONLY: local dev servers get the gallery without an on-chain grant so
  // the click/launch mechanics can be tested; compiled out of production.
  $: allowed = workspaceAllowed($operatorConfig, $principalText) || import.meta.env.DEV;
  $: previewMessage = workspacesMessage($operatorConfig);

  // ── Responsive: detect mobile ─────────────────────────────────────────────
  let isMobile = false;
  function checkMobile() {
    if (typeof window === 'undefined') return;
    isMobile = window.innerWidth < 768 ||
               window.matchMedia('(hover: none) and (pointer: coarse)').matches;
  }

  // ── Launch state ──────────────────────────────────────────────────────────
  let launchModal    = null;   // template being confirmed
  let launchError    = '';
  let launchProgress = '';

  // ── Add VM modal state ───────────────────────────────────────────────────
  let showAddVm     = false;
  let addVmError    = '';
  let addVmBusy     = false;

  async function handleAddVm(data) {
    addVmBusy  = true;
    addVmError = '';
    try {
      data.principal = $principalText || '';
      await createCustomTemplate(data);
      showAddVm = false;
    } catch (err) {
      addVmError = err.message || 'Failed to register VM';
    } finally {
      addVmBusy = false;
    }
  }

  async function handleDeleteCustom(template) {
    if (!template.id.startsWith('custom-')) return;
    try {
      await deleteCustomTemplate(template.id);
    } catch (_) { /* ignore */ }
  }

  function handleLaunch(template) {
    if (template.provider === 'canister') {
      // Canisters open immediately
      if (template.canister_url) {
        window.open(template.canister_url, '_blank', 'noopener,noreferrer');
      }
      return;
    }
    launchModal = template;
    launchError = '';
    launchProgress = '';
  }

  // launchWorkspace()'s poll loop isn't tied to this component's lifetime —
  // if the user navigates away mid-launch, the poll keeps running in the
  // background and, on completion, would still goto() the new session and
  // still write into launchProgress/launchError for a page nobody's looking
  // at. Guard every post-await effect on this flag.
  let destroyed = false;

  async function confirmLaunch() {
    if (!launchModal || !$principalText) return;
    const template = launchModal;
    launchModal = null;
    launchError = '';

    try {
      const session = await launchWorkspace($principalText, template.id, {
        onUpdate: (s) => { if (!destroyed) launchProgress = s.status || 'starting...'; },
      });
      if (destroyed) return;
      launchProgress = '';
      if (session?.session_id) {
        goto(`/hq/workspaces/${session.session_id}`);
      }
    } catch (err) {
      if (destroyed) return;
      launchError = err.message || 'Launch failed';
      launchProgress = '';
    }
  }

  function handleConnect(session) {
    if (session?.stream_protocol === 'canister' && session.stream_url) {
      window.open(session.stream_url, '_blank', 'noopener,noreferrer');
    } else if (session?.session_id) {
      goto(`/hq/workspaces/${session.session_id}`);
    }
  }

  function handleAppTap(template, runningSession) {
    if (runningSession) {
      handleConnect(runningSession);
    } else {
      handleLaunch(template);
    }
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────
  onMount(() => {
    checkMobile();
    if (typeof window !== 'undefined') {
      window.addEventListener('resize', checkMobile);
    }
    refreshOperatorConfig().finally(() => { entLoading = false; });
    return () => {
      destroyed = true;
      if (typeof window !== 'undefined') {
        window.removeEventListener('resize', checkMobile);
      }
    };
  });

  // Fetch catalog + sessions only once the user is granted — the server 403s
  // otherwise, so skipping the calls keeps the console clean.
  let _fetchedFor = '';
  $: if (allowed && $principalText && _fetchedFor !== $principalText) {
    _fetchedFor = $principalText;
    fetchTemplates($principalText).catch(() => {});
    fetchSessions($principalText).catch(() => {});
  }

  // Template count per category
  $: categoryCounts = categories.map((c) => {
    if (c.id === 'all') return { ...c, count: $templates.length };
    return { ...c, count: $templates.filter((t) => t.category === c.id).length };
  }).filter((c) => c.count > 0 || c.id === 'all');
</script>

{#if !$isAuthenticated}
  <!-- ── Auth gate ─────────────────────────────────────────────────────────── -->
  <section class="space-y-5">
    <header class="card p-6 sm:p-8">
      <div class="page-kicker">Workspaces</div>
      <h1 class="page-title mt-4">Sign in to continue<span class="text-brand-500">.</span></h1>
      <p class="mt-4 max-w-2xl text-sm leading-6 text-ink-300">
        Your Internet Identity principal scopes every workspace, vault, and session.
      </p>
    </header>
  </section>

{:else if entLoading}
  <section class="space-y-5">
    <header class="card p-6 sm:p-8">
      <div class="page-kicker">Workspaces</div>
      <p class="mt-4 text-sm text-ink-300">Checking access…</p>
    </header>
  </section>

{:else if !allowed}
  <!-- ── Private preview gate (grant list lives on-chain) ─────────────────── -->
  <section class="space-y-5">
    <header class="card p-6 sm:p-8">
      <div class="page-kicker">Workspaces · private preview</div>
      <h1 class="page-title mt-4">Live desktops, streaming soon<span class="text-brand-500">.</span></h1>
      <p class="mt-4 max-w-2xl text-sm leading-6 text-ink-300">
        Full Windows 11 workspaces streamed to your browser — your HQ, your VMs, your desktop,
        anywhere. Access is granted per Internet Identity principal during the preview.
      </p>
      <p class="mt-3 max-w-2xl text-sm leading-6 text-ink-400">{previewMessage}</p>
      <p class="mt-4 text-xs text-ink-500 font-mono break-all">Your principal: {$principalText}</p>
    </header>
  </section>

{:else if isMobile}
  <!-- ── Mobile: iOS-style app launcher ───────────────────────────────────── -->
  <div class="app-launcher" style="background-image: url('/wallpapers/slc-mountains.svg')">
    <div class="app-launcher-overlay">
      <!-- Status bar -->
      <div class="flex items-center justify-between px-6 pt-4 pb-2">
        <span class="text-[11px] font-medium text-white/70">CafresoAI</span>
        <span class="flex items-center gap-1.5 text-[11px] text-white/70">
          <span class="glow-dot text-green-400" style="font-size:6px"></span>
          Connected
        </span>
      </div>

      <!-- App grid -->
      <div class="flex-1 flex items-center justify-center px-4">
        <div class="grid grid-cols-4 gap-y-6 gap-x-4 max-w-xs">
          {#each $filteredTemplates as template (template.id)}
            <AppIcon
              {template}
              runningSession={runningSessionForTemplate(template.id)}
              onTap={handleAppTap}
            />
          {/each}
        </div>
      </div>

      <!-- Dock -->
      {#if $activeSessions.length > 0}
        <div class="app-dock mx-4 mb-6 flex items-center justify-center gap-4 px-4 py-2">
          {#each $activeSessions.slice(0, 4) as session}
            <button
              class="h-12 w-12 rounded-2xl bg-gradient-to-br from-brand-400 to-brand-600 grid place-items-center text-sm font-bold text-white shadow-lg active:scale-90 transition-transform"
              on:click={() => handleConnect(session)}
              title={session.display_name}
            >
              {(session.display_name || '?')[0]}
            </button>
          {/each}
        </div>
      {/if}
    </div>
  </div>

{:else}
  <!-- ── Desktop: card grid layout ────────────────────────────────────────── -->
  <section class="space-y-6">
    <!-- Hero -->
    <header class="card p-6 sm:p-8">
      <div class="page-kicker">Workspaces &middot; {$templates.length} images available</div>
      <h1 class="page-title mt-4">Spin up a workspace<span class="text-brand-500">.</span></h1>
      <p class="mt-4 max-w-3xl text-sm leading-6 text-ink-300">
        Anything from a one-tab Claude Code shell to a full Ubuntu desktop or RDP bastion.
        Streams to your browser in seconds, encrypted to your Internet Identity principal.
      </p>
    </header>

    <!-- Filters -->
    <div class="flex flex-wrap items-center gap-2">
      {#each categoryCounts as cat}
        <button
          class="category-pill {$activeCategory === cat.id ? 'category-pill-active' : 'category-pill-inactive'}"
          on:click={() => activeCategory.set(cat.id)}
        >
          {cat.label}
          <span class="ml-1 text-[10px] opacity-60">{cat.count}</span>
        </button>
      {/each}

      <div class="ml-auto">
        <input
          type="text"
          placeholder="search workspaces..."
          class="rounded-full border border-ink-600/50 bg-ink-800/60 px-4 py-2 text-xs text-ink-200 placeholder-ink-500 outline-none focus:border-brand-500/50 focus:ring-1 focus:ring-brand-500/30 w-48"
          bind:value={$searchQuery}
        />
      </div>
    </div>

    <!-- Grid + sidebar -->
    <div class="flex gap-6">
      <!-- Card grid -->
      <div class="flex-1 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {#each $filteredTemplates as template (template.id)}
          <WorkspaceCard
            {template}
            runningSession={runningSessionForTemplate(template.id)}
            onLaunch={handleLaunch}
            onConnect={handleConnect}
          />
        {/each}

        <!-- "Add Your Own" card -->
        <button
          class="workspace-card group flex flex-col items-center justify-center gap-3 border-dashed border-2
                 border-ink-600/40 bg-transparent hover:border-brand-500/50 hover:bg-ink-800/20
                 min-h-[180px] transition-all duration-200 cursor-pointer"
          on:click={() => showAddVm = true}
        >
          <div class="grid h-12 w-12 place-items-center rounded-xl bg-ink-800/50 text-ink-400
                      group-hover:bg-brand-500/20 group-hover:text-brand-400 transition-colors">
            <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path d="M12 4v16m8-8H4" />
            </svg>
          </div>
          <div class="text-center">
            <span class="text-sm font-semibold text-ink-200 group-hover:text-ink-50">Bring Your Own VM</span>
            <p class="text-[10px] text-ink-500 mt-0.5">Register a machine or endpoint</p>
          </div>
        </button>

        {#if $filteredTemplates.length === 0}
          <div class="col-span-full py-12 text-center text-sm text-ink-500">
            No workspaces match your filters.
          </div>
        {/if}
      </div>

      <!-- Running sessions sidebar (lg+) -->
      {#if $activeSessions.length > 0}
        <aside class="hidden lg:block w-56 shrink-0 space-y-2">
          <div class="page-kicker">{$activeSessions.length} running</div>
          {#each $activeSessions as session}
            <button
              class="card w-full p-3 text-left transition-colors hover:border-brand-500/30"
              on:click={() => handleConnect(session)}
            >
              <div class="flex items-center gap-2">
                <span class="glow-dot text-green-400"></span>
                <span class="text-xs font-semibold text-ink-100 truncate">{session.display_name || session.template_id}</span>
              </div>
              <div class="mt-1 text-[10px] text-ink-500">
                {session.provider === 'hyperv' ? 'Hyper-V' : session.provider === 'oci' ? 'OCI' : session.provider === 'local' ? 'Local' : 'ICP'}
                {#if session.status === 'starting'}
                  &middot; <span class="text-yellow-400">starting...</span>
                {/if}
              </div>
            </button>
          {/each}
        </aside>
      {/if}
    </div>
  </section>
{/if}

<!-- ── Launch confirmation modal ───────────────────────────────────────────── -->
{#if launchModal}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions a11y_interactive_supports_focus -->
  <div class="fixed inset-0 z-50 grid place-items-center bg-black/60 backdrop-blur-sm" role="dialog" on:click|self={() => launchModal = null}>
    <div class="card w-full max-w-sm p-6 space-y-4 shadow-2xl">
      <h2 class="text-lg font-semibold text-ink-50">Launch {launchModal.name}?</h2>
      <p class="text-sm text-ink-300">{launchModal.description}</p>

      <div class="flex flex-wrap gap-1.5 text-[10px]">
        <span class="rounded-full border border-ink-600/50 bg-ink-800/60 px-2 py-0.5 font-mono text-ink-300">
          {launchModal.provider === 'hyperv' ? 'Hyper-V' : launchModal.provider === 'local' ? 'Local (WSL)' : 'OCI Container'}
        </span>
        {#if launchModal.resources?.vcpus || launchModal.resources?.ocpus}
          <span class="rounded-full border border-ink-600/50 bg-ink-800/60 px-2 py-0.5 font-mono text-ink-300">
            {launchModal.resources.vcpus || launchModal.resources.ocpus} cpu
          </span>
        {/if}
        {#if launchModal.resources?.memory_gb}
          <span class="rounded-full border border-ink-600/50 bg-ink-800/60 px-2 py-0.5 font-mono text-ink-300">
            {launchModal.resources.memory_gb} gb
          </span>
        {/if}
        {#if launchModal.resources?.gpu_partition}
          <span class="rounded-full border border-ink-600/50 bg-ink-800/60 px-2 py-0.5 font-mono text-ink-300">
            GPU {launchModal.resources.gpu_partition}
          </span>
        {/if}
      </div>

      <div class="flex gap-2 pt-2">
        <button class="btn-primary flex-1" on:click={confirmLaunch}>
          Launch
        </button>
        <button class="btn-ghost" on:click={() => launchModal = null}>
          Cancel
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- ── Launch progress toast ───────────────────────────────────────────────── -->
{#if $launchingId}
  <div class="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-full border border-ink-600/60 bg-ink-900/90 px-4 py-2 text-sm text-ink-200 shadow-lg backdrop-blur-md">
    <span class="glow-dot text-brand-400 animate-pulse"></span>
    Launching {$launchingId}... {launchProgress || ''}
  </div>
{/if}

{#if launchError}
  <div class="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-full border border-red-500/40 bg-ink-900/90 px-4 py-2 text-sm text-red-300 shadow-lg backdrop-blur-md">
    {launchError}
    <button class="ml-2 text-xs text-ink-400 hover:text-ink-200" on:click={() => launchError = ''}>dismiss</button>
  </div>
{/if}

<!-- ── Add VM modal ──────────────────────────────────────────────────────── -->
{#if showAddVm}
  <AddVmModal
    onSubmit={handleAddVm}
    onCancel={() => { showAddVm = false; addVmError = ''; }}
    submitting={addVmBusy}
    error={addVmError}
  />
{/if}
