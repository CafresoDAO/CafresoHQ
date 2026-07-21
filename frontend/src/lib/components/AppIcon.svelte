<script>
  /** iOS-style app icon tile for mobile launcher. */
  export let template;
  export let runningSession = null;
  export let onTap = (/** @type {any} */ _t, /** @type {any} */ _s) => {};

  const iconMap = {
    hq:       { bg: 'bg-gradient-to-br from-brand-400 to-brand-600', label: 'HQ',  type: 'text' },
    cf:       { bg: 'bg-gradient-to-br from-brand-500 to-brand-700', label: 'Cf',  type: 'text' },
    terminal: { bg: 'bg-ink-800',                                     label: '>_',  type: 'text' },
    monitor:  { bg: 'bg-gradient-to-br from-blue-500 to-blue-700',   label: null,  type: 'svg', svg: 'monitor' },
    gamepad:  { bg: 'bg-gradient-to-br from-purple-500 to-purple-700', label: null, type: 'svg', svg: 'gamepad' },
    gold:     { bg: 'bg-gradient-to-br from-yellow-600 to-amber-800', label: null,  type: 'svg', svg: 'gold' },
    shield:   { bg: 'bg-gradient-to-br from-green-500 to-green-700', label: null,  type: 'svg', svg: 'shield' },
    globe:    { bg: 'bg-gradient-to-br from-sky-500 to-sky-700',     label: null,  type: 'svg', svg: 'globe' },
    linux:    { bg: 'bg-gradient-to-br from-orange-500 to-orange-700', label: null, type: 'svg', svg: 'linux' },
    notebook: { bg: 'bg-gradient-to-br from-orange-400 to-gray-600', label: null,  type: 'svg', svg: 'notebook' },
    code:     { bg: 'bg-gradient-to-br from-cyan-500 to-cyan-700',   label: '</>',  type: 'text' },
  };

  $: icon = iconMap[template.icon] || { bg: 'bg-ink-700', label: template.name?.[0] || '?', type: 'text' };
  $: disabled = !template.enabled;
  $: hasSession = !!runningSession;
</script>

<button
  class="app-icon-wrap flex flex-col items-center gap-1 {disabled ? 'opacity-40' : ''}"
  on:click={() => !disabled && onTap(template, runningSession)}
  disabled={disabled}
  title={disabled ? 'Coming soon' : template.name}
>
  <div class="app-icon relative {icon.bg} {disabled ? '' : 'active:scale-90'} transition-transform">
    {#if icon.type === 'text'}
      <span class="font-display font-bold text-white {icon.label?.length > 2 ? 'text-lg' : 'text-xl'}">
        {icon.label}
      </span>
    {:else if icon.svg === 'monitor'}
      <svg class="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
        <path d="M9 17h6M12 17v4M4 5h16a1 1 0 011 1v9a1 1 0 01-1 1H4a1 1 0 01-1-1V6a1 1 0 011-1z"/>
      </svg>
    {:else if icon.svg === 'gamepad'}
      <svg class="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
        <path d="M6 12h4M8 10v4M15 13h.01M18 11h.01M17.32 5H6.68a3 3 0 00-2.96 2.52l-1.46 8.77A2 2 0 004.24 19h1.52a2 2 0 001.94-1.51L8 16h8l.3 1.49A2 2 0 0018.24 19h1.52a2 2 0 001.98-2.71l-1.46-8.77A3 3 0 0017.32 5z"/>
      </svg>
    {:else if icon.svg === 'gold'}
      <svg class="w-7 h-7 text-white" fill="currentColor" viewBox="0 0 24 24">
        <rect x="7" y="4" width="10" height="4" rx="0.5"/>
        <rect x="5" y="9" width="14" height="4" rx="0.5"/>
        <rect x="3" y="14" width="18" height="4" rx="0.5"/>
      </svg>
    {:else if icon.svg === 'shield'}
      <svg class="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
      </svg>
    {:else if icon.svg === 'globe'}
      <svg class="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
        <circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10A15.3 15.3 0 0112 2z"/>
      </svg>
    {:else if icon.svg === 'linux'}
      <svg class="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
        <circle cx="12" cy="8" r="5"/><path d="M5 20c0-4 3-7 7-7s7 3 7 7"/>
      </svg>
    {:else if icon.svg === 'notebook'}
      <svg class="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
        <rect x="5" y="3" width="14" height="18" rx="1"/><path d="M9 7h6M9 11h6M9 15h3"/>
      </svg>
    {/if}

    {#if hasSession}
      <span class="app-icon-badge"></span>
    {/if}
  </div>

  <span class="app-icon-label">
    {template.name}
  </span>
</button>
