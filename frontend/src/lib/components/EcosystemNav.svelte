<script>
  /* EcosystemNav — Cafreso wordmark + app-switcher dropdown.
     Visually links the SvelteKit app to the wider Cafreso ecosystem
     (Pages, AI, HQ, Mine) so users feel they're in the same product
     family across subdomains. Mirrors the shared <cafreso-ecobar> web
     component used by HQ + Minegold — keep the app list/labels in sync. */
  import { onMount } from 'svelte';

  /** Active app id — pass from parent ('pages' | 'ai' | 'hq' | 'mine'). */
  export let active = 'ai';

  const apps = [
    { id: 'pages',   label: 'Pages',   url: 'https://cafreso.com',                                  icon: '📄', accent: 'var(--eco-pages)' },
    { id: 'ai',      label: 'AI',      url: 'https://ai.cafreso.com',                                icon: '🧠', accent: 'var(--eco-ai)' },
    { id: 'hq',      label: 'HQ',      url: 'https://ai.cafreso.com/hq',                             icon: '🏢', accent: 'var(--eco-hq)' },
    { id: 'mine',    label: 'Mine',    url: 'https://cqyto-tiaaa-aaaau-agppa-cai.icp0.io/',          icon: '⛏', accent: 'var(--eco-banking)' }
  ];

  let open = false;
  let wrap;

  function onClickOutside(e) {
    if (wrap && !wrap.contains(e.target)) open = false;
  }

  onMount(() => {
    document.addEventListener('mousedown', onClickOutside);
    document.addEventListener('touchstart', onClickOutside);
    return () => {
      document.removeEventListener('mousedown', onClickOutside);
      document.removeEventListener('touchstart', onClickOutside);
    };
  });
</script>

<div class="ecosystem-nav">
  <a class="cf-brand" href="/" aria-label="Cafreso home">
    <img src="/cf-black.png" alt="Cafreso" class="cf-mark" />
    {#if active === 'hq'}
      <span class="cf-suffix"><i>H</i><i>Q</i></span>
    {:else if active === 'ai'}
      <span class="cf-suffix cf-suffix--ai"><i>A</i><i>I</i></span>
    {/if}
  </a>

  <div class="cf-apps-wrap" bind:this={wrap}>
    <button
      class="cf-apps-btn"
      aria-expanded={open}
      type="button"
      on:click={() => (open = !open)}
    >
      Apps
      <span aria-hidden="true">{open ? '▴' : '▾'}</span>
    </button>

    {#if open}
      <div class="cf-apps-menu" role="menu">
        {#each apps as app (app.id)}
          <a
            role="menuitem"
            class="cf-apps-item"
            class:is-active={app.id === active}
            href={app.id === active ? undefined : app.url}
            aria-current={app.id === active ? 'page' : undefined}
            style="--app-accent: {app.accent}"
            on:click={() => (open = false)}
          >
            <span class="cf-apps-icon" aria-hidden="true">{app.icon}</span>
            <span class="cf-apps-label">{app.label}</span>
            {#if app.id === active}
              <span class="cf-apps-current">CURRENT</span>
            {/if}
          </a>
        {/each}
      </div>
    {/if}
  </div>
</div>

<style>
  .ecosystem-nav {
    display: inline-flex;
    align-items: center;
    gap: 12px;
    flex: 0 0 auto;
  }
  .cf-brand {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    text-decoration: none;
    color: inherit;
  }
  .cf-wordmark {
    height: 30px;
    width: auto;
    display: block;
    /* Subtle white inset so the dark cursive script lifts off the warm bg */
    filter: drop-shadow(0 1px 0 rgba(255, 255, 255, 0.5));
  }
  :global(.dark) .cf-wordmark {
    /* Invert in dark mode so the black script reads on the dark surface */
    filter: invert(1) brightness(1.05);
  }
  /* Compact "Cf" monogram — preferred mark in the EcosystemNav so the
     letterpress HQ/AI chip has room to breathe alongside it. */
  .cf-mark {
    height: 36px;
    width: auto;
    display: block;
    filter: drop-shadow(0 1px 0 rgba(255, 255, 255, 0.4));
  }
  :global(.dark) .cf-mark {
    filter: invert(1) brightness(1.05);
  }
  .cf-suffix {
    display: inline-flex;
    gap: 2px;
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
    align-self: flex-end;
    margin-bottom: 4px;
  }
  .cf-suffix i {
    display: inline-grid;
    place-items: center;
    width: 14px;
    height: 16px;
    background: hsl(var(--brand-500));
    color: hsl(var(--ink-50));
    border: 1px solid hsl(var(--ink-50));
    border-radius: 2px;
    font-style: normal;
    line-height: 1;
    box-shadow: 0 1px 0 0 hsl(var(--ink-50));
  }
  .cf-suffix--ai i {
    background: var(--eco-ai);
    color: hsl(var(--ink-900));
    border-color: var(--eco-ai);
  }
  .cf-apps-wrap {
    position: relative;
  }
  .cf-apps-btn {
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.02em;
    padding: 6px 12px;
    background: transparent;
    color: hsl(var(--ink-50));
    border: 1.5px solid hsl(var(--surface-border));
    border-radius: 999px;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 32px;
  }
  .cf-apps-btn:hover {
    background: hsl(var(--ink-800) / 0.6);
    border-color: hsl(var(--brand-700));
  }
  .cf-apps-btn[aria-expanded='true'] {
    background: hsl(var(--ink-800) / 0.7);
    border-color: hsl(var(--brand-500));
  }
  .cf-apps-menu {
    position: absolute;
    top: calc(100% + 8px);
    left: 0;
    z-index: 200;
    min-width: 220px;
    padding: 6px;
    background: linear-gradient(180deg, var(--surface-card), var(--surface-card-strong));
    border: 1px solid hsl(var(--surface-border));
    border-radius: 14px;
    box-shadow: var(--card-shadow);
    display: flex;
    flex-direction: column;
    gap: 2px;
    animation: cf-menu-in 120ms cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  @keyframes cf-menu-in {
    from {
      opacity: 0;
      transform: translateY(-4px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  .cf-apps-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px 10px 14px;
    border-radius: 10px;
    border-left: 3px solid var(--app-accent, transparent);
    text-decoration: none;
    color: hsl(var(--ink-50));
    font-family: 'Inter', sans-serif;
    font-size: 13px;
    font-weight: 600;
    background: transparent;
    cursor: pointer;
    transition: background 0.12s, transform 0.12s;
  }
  .cf-apps-item:hover {
    background: hsl(var(--ink-800) / 0.45);
    transform: translateX(2px);
  }
  .cf-apps-item.is-active {
    background: hsl(var(--brand-500) / 0.18);
    cursor: default;
  }
  .cf-apps-item.is-active:hover {
    transform: none;
  }
  .cf-apps-icon {
    font-size: 16px;
    line-height: 1;
  }
  .cf-apps-label {
    flex: 1;
  }
  .cf-apps-current {
    font-size: 8px;
    font-weight: 800;
    letter-spacing: 0.12em;
    background: hsl(var(--ink-50));
    color: hsl(var(--brand-500));
    padding: 2px 6px;
    border-radius: 3px;
  }

  @media (max-width: 768px) {
    .ecosystem-nav {
      gap: 8px;
    }
    .cf-wordmark {
      height: 24px;
    }
    .cf-mark {
      height: 28px;
    }
    .cf-suffix i {
      width: 12px;
      height: 14px;
      font-size: 9px;
    }
    .cf-apps-btn {
      padding: 5px 10px;
      font-size: 11px;
      min-height: 30px;
    }
    .cf-apps-menu {
      min-width: 180px;
    }
  }
</style>
