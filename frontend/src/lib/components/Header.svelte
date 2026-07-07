<script>
  import { page } from '$app/stores';
  import {
    authStatus,
    isAuthenticated,
    principalText,
    login,
    logout
  } from '$lib/stores/auth.js';
  import { theme, toggleTheme } from '$lib/stores/theme.js';
  import EndpointStatus from './EndpointStatus.svelte';
  import EcosystemNav from './EcosystemNav.svelte';

  const navLinks = [
    { href: '/hq', label: 'Dashboard' },
    { href: '/hq/app', label: 'HQ' },
    { href: '/hq/chat', label: 'Chat' },
    { href: '/hq/search', label: 'Search' },
    { href: '/hq/vault', label: 'Vault' },
    { href: '/hq/plans', label: 'Plans' },
    { href: '/hq/settings', label: 'Settings' }
  ];

  function shortPrincipal(p) {
    if (!p) return '';
    return p.length > 20 ? p.slice(0, 6) + '...' + p.slice(-4) : p;
  }
</script>

<header class="sticky top-3 z-30 px-4 sm:px-6 lg:px-8">
  <div class="shell-panel mx-auto flex max-w-7xl items-center gap-3 rounded-[1.75rem] px-3 py-2">
    <EcosystemNav active="ai" />

    <nav class="ml-2 hidden min-w-0 flex-1 items-center justify-center gap-1 md:flex">
      {#each navLinks as l}
        <a
          href={l.href}
          aria-current={$page.url.pathname === l.href ? 'page' : undefined}
          class="rounded-full px-3 py-2 text-sm font-semibold transition-colors
                 {$page.url.pathname === l.href
                   ? 'bg-ink-50 text-ink-900 shadow-sm'
                   : 'text-ink-200 hover:bg-ink-800/55 hover:text-ink-50'}"
        >
          {l.label}
        </a>
      {/each}
    </nav>

    <div class="ml-auto flex items-center gap-2">
      <EndpointStatus compact />

      <button
        class="btn-ghost btn-sm hidden sm:inline-flex"
        type="button"
        on:click={toggleTheme}
        aria-label="Switch to {$theme === 'dark' ? 'light' : 'dark'} mode"
      >
        {$theme === 'dark' ? 'Light' : 'Dark'}
      </button>

      {#if $isAuthenticated}
        <div
          class="hidden items-center gap-2 rounded-full border border-ink-600/70 bg-ink-800/45 px-2.5 py-1.5 text-xs font-mono text-ink-200 md:flex"
          title={$principalText}
        >
          <span class="h-6 w-6 rounded-full bg-gradient-to-br from-brand-400 to-purple-500"></span>
          {shortPrincipal($principalText)}
        </div>
        <button class="btn-ghost btn-sm" on:click={logout} title="Sign out">
          Logout
        </button>
      {:else if $authStatus === 'logging-in'}
        <button class="btn-primary btn-sm" disabled>
          <span class="animate-pulse">Connecting...</span>
        </button>
      {:else}
        <button class="btn-primary btn-sm" on:click={login}>
          Sign in
        </button>
      {/if}
    </div>
  </div>
</header>
