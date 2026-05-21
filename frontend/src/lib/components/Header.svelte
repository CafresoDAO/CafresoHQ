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

  const navLinks = [
    { href: '/', label: 'Dashboard' },
    { href: '/workspaces', label: 'Workspaces' },
    { href: '/app', label: 'HQ' },
    { href: '/chat', label: 'Chat' },
    { href: '/vault', label: 'Vault' },
    { href: '/admin', label: 'Admin' },
    { href: '/settings', label: 'Settings' }
  ];

  function shortPrincipal(p) {
    if (!p) return '';
    return p.length > 20 ? p.slice(0, 6) + '...' + p.slice(-4) : p;
  }
</script>

<header class="sticky top-3 z-30 px-4 sm:px-6 lg:px-8">
  <div class="shell-panel mx-auto flex max-w-7xl items-center gap-3 rounded-[1.75rem] px-3 py-2 backdrop-blur-xl">
    <a href="/" class="group flex shrink-0 items-center gap-2">
      <div class="grid h-10 w-10 place-items-center rounded-xl bg-ink-50 font-display text-xl font-bold italic text-ink-900 shadow-[0_14px_28px_-18px_var(--brand-glow)] transition-transform group-hover:-translate-y-0.5">
        Cf
      </div>
      <div class="leading-none">
        <div class="font-display text-2xl font-semibold text-ink-50">
          Cafreso<span class="text-brand-500">AI</span>
        </div>
        <div class="hidden font-mono text-[0.68rem] uppercase tracking-[0.22em] text-ink-400 sm:block">
          v1.0.0
        </div>
      </div>
    </a>

    <nav class="ml-2 hidden min-w-0 flex-1 items-center justify-center gap-1 md:flex">
      {#each navLinks as l}
        <a
          href={l.href}
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
