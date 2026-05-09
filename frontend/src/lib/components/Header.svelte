<script>
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import {
    authStatus, isAuthenticated, principalText, login, logout
  } from '$lib/stores/auth.js';
  import EndpointStatus from './EndpointStatus.svelte';

  const navLinks = [
    { href: '/',        label: 'Dashboard' },
    { href: '/app',     label: 'HQ' },
    { href: '/chat',    label: 'Chat' },
    { href: '/vault',   label: 'Vault' },
    { href: '/settings', label: 'Settings' }
  ];

  function shortPrincipal(p) {
    if (!p) return '';
    return p.length > 20 ? p.slice(0, 6) + '…' + p.slice(-4) : p;
  }
</script>

<header class="sticky top-0 z-30 border-b border-ink-600/40 bg-ink-900/80 backdrop-blur-md">
  <div class="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
    <a href="/" class="flex items-center gap-2 group">
      <div class="grid h-8 w-8 place-items-center rounded-lg bg-brand-500 text-ink-900 font-bold
                  shadow-[0_0_24px_-6px_var(--brand-glow)] group-hover:shadow-[0_0_32px_-2px_var(--brand-glow)]
                  transition-shadow">C</div>
      <span class="font-semibold tracking-tight text-ink-50">CafresoAI</span>
      <span class="hidden md:inline text-xs text-ink-400 font-mono">v1.0.0</span>
    </a>

    <nav class="ml-6 hidden md:flex items-center gap-1">
      {#each navLinks as l}
        <a href={l.href}
           class="rounded-md px-3 py-1.5 text-sm transition-colors
                  {$page.url.pathname === l.href
                    ? 'bg-ink-800 text-ink-50'
                    : 'text-ink-200 hover:bg-ink-800/50 hover:text-ink-50'}">
          {l.label}
        </a>
      {/each}
    </nav>

    <div class="ml-auto flex items-center gap-2">
      <EndpointStatus compact />

      {#if $isAuthenticated}
        <div class="hidden md:flex items-center gap-2 rounded-lg border border-ink-600/40
                    bg-ink-900/60 px-3 py-1.5 text-xs font-mono text-ink-200"
             title={$principalText}>
          <span class="glow-dot text-emerald-400"></span>
          {shortPrincipal($principalText)}
        </div>
        <button class="btn-ghost btn-sm" on:click={logout} title="Sign out">
          Logout
        </button>
      {:else if $authStatus === 'logging-in'}
        <button class="btn-primary btn-sm" disabled>
          <span class="animate-pulse">Connecting…</span>
        </button>
      {:else}
        <button class="btn-primary btn-sm" on:click={login}>
          Sign in with Internet Identity
        </button>
      {/if}
    </div>
  </div>
</header>
