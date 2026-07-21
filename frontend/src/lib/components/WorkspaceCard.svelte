<script>
  /** Workspace tile for the desktop card grid. */
  export let template;
  export let runningSession = null;
  export let onLaunch  = (/** @type {any} */ _t) => {};
  export let onConnect = (/** @type {any} */ _s) => {};

  $: disabled = !template.enabled;
  $: isCanister = template.provider === 'canister';
  $: hasSession = !!runningSession;

  const providerLabel = {
    hyperv:   'Hyper-V',
    oci:      'OCI',
    canister: 'ICP',
    custom:   'Custom',
  };

  const providerClass = {
    hyperv:   'provider-badge-hyperv',
    oci:      'provider-badge-oci',
    canister: 'provider-badge-canister',
    custom:   'provider-badge-custom',
  };

  function resourcePills(r) {
    if (!r || Object.keys(r).length === 0) return [];
    const pills = [];
    if (r.ocpus)         pills.push(`${r.ocpus} cpu`);
    if (r.vcpus)         pills.push(`${r.vcpus} cpu`);
    if (r.memory_gb)     pills.push(`${r.memory_gb} gb`);
    if (r.gpu_partition) pills.push(`GPU ${r.gpu_partition}`);
    return pills;
  }

  $: pills = resourcePills(template.resources);

  function handleAction() {
    if (disabled) return;
    if (hasSession) {
      onConnect(runningSession);
    } else {
      onLaunch(template);
    }
  }
</script>

<div class="workspace-card {disabled ? 'workspace-card-disabled' : ''}">
  {#if disabled}
    <div class="absolute inset-0 z-10 grid place-items-center rounded-xl">
      <span class="rounded-full bg-ink-900/80 px-3 py-1 text-xs font-semibold text-ink-300 backdrop-blur-sm">
        Coming soon
      </span>
    </div>
  {/if}

  <div class="flex items-start justify-between gap-2">
    <div>
      <h3 class="text-sm font-semibold text-ink-50">{template.name}</h3>
      <span class="mt-0.5 inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider {providerClass[template.provider] || 'bg-ink-700 text-ink-300'}">
        {providerLabel[template.provider] || template.provider}
      </span>
    </div>
    {#if template.tags?.includes('popular')}
      <span class="rounded-full bg-brand-500/20 px-2 py-0.5 text-[10px] font-semibold text-brand-300">
        Popular
      </span>
    {/if}
  </div>

  <p class="mt-2 flex-1 text-xs leading-relaxed text-ink-400">
    {template.description}
  </p>

  <div class="mt-3 flex flex-wrap items-center gap-1.5">
    {#each pills as pill}
      <span class="rounded-full border border-ink-600/50 bg-ink-800/60 px-2 py-0.5 text-[10px] font-mono text-ink-300">
        {pill}
      </span>
    {/each}
    {#if template.persistent}
      <span class="pill-ok text-[10px]">persistent</span>
    {/if}
  </div>

  <div class="mt-4">
    {#if hasSession}
      <button class="btn-primary w-full text-xs" on:click={handleAction}>
        <span class="glow-dot text-green-400 mr-1.5"></span>
        Connect
      </button>
    {:else if isCanister}
      <button class="btn-primary w-full text-xs" on:click={handleAction}>
        Open
      </button>
    {:else}
      <button class="btn-primary w-full text-xs" on:click={handleAction} disabled={disabled}>
        Launch
      </button>
    {/if}
  </div>
</div>
