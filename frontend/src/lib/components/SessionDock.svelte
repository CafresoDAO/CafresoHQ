<script>
  /** Left-edge mini-tab switcher for concurrent sessions. */
  export let sessions = [];
  export let activeSessionId = '';
  export let onSelect = (/** @type {string} */ _sid) => {};
  export let onNew    = () => {};

  const iconLetter = (s) => {
    if (s.display_name) return s.display_name[0].toUpperCase();
    if (s.template_id)  return s.template_id[0].toUpperCase();
    return '?';
  };

  const providerColor = {
    hyperv:   'from-blue-500 to-blue-700',
    oci:      'from-brand-400 to-brand-600',
    canister: 'from-purple-500 to-purple-700',
  };
</script>

{#if sessions.length > 0}
  <div class="fixed left-0 top-1/2 z-50 -translate-y-1/2 flex flex-col items-center gap-1 py-2 pl-1">
    {#each sessions as session}
      <button
        class="session-dock-item {session.session_id === activeSessionId ? 'session-dock-item-active' : ''}"
        on:click={() => onSelect(session.session_id)}
        title="{session.display_name || session.template_id} — {session.status}"
      >
        <div class="h-full w-full rounded-lg bg-gradient-to-br {providerColor[session.provider] || 'from-ink-600 to-ink-800'} grid place-items-center text-xs font-bold text-white">
          {iconLetter(session)}
        </div>
        {#if session.status === 'running'}
          <span class="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-ink-900 bg-green-400"></span>
        {:else if session.status === 'starting'}
          <span class="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-ink-900 bg-yellow-400 animate-pulse"></span>
        {/if}
      </button>
    {/each}

    <button
      class="session-dock-item mt-1 border-dashed"
      on:click={onNew}
      title="Launch new workspace"
    >
      <div class="grid h-full w-full place-items-center text-lg text-ink-400">+</div>
    </button>
  </div>
{/if}
