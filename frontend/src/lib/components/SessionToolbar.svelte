<script>
  /** Floating bottom toolbar for the session viewer. */
  // eslint-disable-next-line -- reserved for Phase 2 session-specific toolbar state
  export let session = null;
  export let onDisconnect = () => {};
  export let onRefresh    = () => {};
  export let onFullscreen = () => {};

  // Suppress unused-export warning — session will be consumed in Phase 2
  void session;

  const buttons = [
    { id: 'clipboard', icon: 'clipboard', label: 'Clipboard',   enabled: false },
    { id: 'monitor',   icon: 'monitor',   label: 'Display',     enabled: false },
    { id: 'chat',      icon: 'chat',      label: 'Chat',        enabled: false },
    { id: 'audio',     icon: 'audio',     label: 'Audio',       enabled: false },
    { id: 'refresh',   icon: 'refresh',   label: 'Refresh',     enabled: true },
    { id: 'settings',  icon: 'settings',  label: 'Settings',    enabled: false },
    { id: 'fullscreen',icon: 'fullscreen',label: 'Fullscreen',  enabled: true },
    { id: 'power',     icon: 'power',     label: 'Disconnect',  enabled: true,  danger: true },
    { id: 'more',      icon: 'more',      label: 'More',        enabled: false },
  ];

  function handleClick(btn) {
    if (!btn.enabled) return;
    if (btn.id === 'refresh')    onRefresh();
    if (btn.id === 'fullscreen') onFullscreen();
    if (btn.id === 'power')      onDisconnect();
  }
</script>

<div class="floating-toolbar">
  {#each buttons as btn}
    <button
      class="toolbar-btn {btn.danger ? 'toolbar-btn-danger' : ''}"
      class:opacity-30={!btn.enabled}
      class:cursor-not-allowed={!btn.enabled}
      on:click={() => handleClick(btn)}
      title={btn.enabled ? btn.label : `${btn.label} (coming soon)`}
      disabled={!btn.enabled}
    >
      {#if btn.icon === 'clipboard'}
        <svg class="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a1 1 0 011 1v14a1 1 0 01-1 1H6a1 1 0 01-1-1V5a1 1 0 011-1h2"/></svg>
      {:else if btn.icon === 'monitor'}
        <svg class="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M9 17h6M12 17v4M4 5h16a1 1 0 011 1v9a1 1 0 01-1 1H4a1 1 0 01-1-1V6a1 1 0 011-1z"/></svg>
      {:else if btn.icon === 'chat'}
        <svg class="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
      {:else if btn.icon === 'audio'}
        <svg class="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M11 5L6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 010 14.14M15.54 8.46a5 5 0 010 7.07"/></svg>
      {:else if btn.icon === 'refresh'}
        <svg class="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M1 4v6h6M23 20v-6h-6"/><path d="M20.49 9A9 9 0 005.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 013.51 15"/></svg>
      {:else if btn.icon === 'settings'}
        <svg class="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
      {:else if btn.icon === 'fullscreen'}
        <svg class="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/></svg>
      {:else if btn.icon === 'power'}
        <svg class="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path d="M18.36 6.64a9 9 0 11-12.73 0M12 2v10"/></svg>
      {:else if btn.icon === 'more'}
        <svg class="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg>
      {/if}
    </button>
  {/each}
</div>
