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
  import { navMode } from '$lib/stores/navMode.js';
  import EndpointStatus from './EndpointStatus.svelte';
  import EcosystemNav from './EcosystemNav.svelte';

  const navLinks = [
    { href: '/hq', label: 'Dashboard', slug: 'dashboard' },
    { href: '/hq/app', label: 'HQ', slug: 'app' },
    { href: '/hq/chat', label: 'Chat', slug: 'chat' },
    { href: '/hq/search', label: 'Search', slug: 'search' },
    { href: '/library', label: 'Library', slug: 'library' },
    { href: '/hq/workspaces', label: 'Workspaces', slug: 'workspaces' },
    { href: '/hq/vault', label: 'Vault', slug: 'vault' },
    { href: '/hq/plans', label: 'Plans', slug: 'plans' },
    { href: '/hq/settings', label: 'Settings', slug: 'settings' }
  ];

  function shortPrincipal(p) {
    if (!p) return '';
    return p.length > 20 ? p.slice(0, 6) + '...' + p.slice(-4) : p;
  }

  // 'windows' mode: a plain left-click opens/refocuses a dedicated OS window
  // per surface instead of navigating this one. Modified clicks (Cmd/Ctrl,
  // Shift, middle-click) are left alone so "open in new tab" still works
  // exactly like any other link, in either mode. The window NAME is stable
  // per surface (`hq-<slug>`), which is what makes a second click on the same
  // link refocus the existing window instead of spawning a duplicate — that's
  // ordinary window.open(url, name) behavior at a fixed name + origin, no
  // extra bookkeeping needed.
  function onNavClick(e, href, slug) {
    if ($navMode !== 'windows') return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    window.open(href, `hq-${slug}`);
  }
</script>

<header class="sticky top-3 z-30 px-4 sm:px-6 lg:px-8">
  <div class="shell-panel mx-auto flex max-w-7xl items-center gap-3 rounded-[1.75rem] px-3 py-2">
    <EcosystemNav active="ai" />

    <!-- overflow-x-auto + safe center: when the seven links don't fit (md–lg
         widths) the row scrolls inside its own box instead of bleeding under
         the brand on the left and the status chip on the right. -->
    <nav class="ml-2 hidden min-w-0 flex-1 items-center gap-1 overflow-x-auto whitespace-nowrap [justify-content:safe_center] [scrollbar-width:none] md:flex">
      {#each navLinks as l}
        <a
          href={l.href}
          on:click={(e) => onNavClick(e, l.href, l.slug)}
          aria-current={$page.url.pathname === l.href ? 'page' : undefined}
          class="shrink-0 rounded-full px-3 py-2 text-sm font-semibold transition-colors
                 {$page.url.pathname === l.href
                   ? 'bg-ink-50 text-ink-900 shadow-sm'
                   : 'text-ink-200 hover:bg-ink-800/55 hover:text-ink-50'}"
        >
          {l.label}
        </a>
      {/each}
    </nav>

    <div class="ml-auto flex items-center gap-2">
      <!-- Container status is signed-in plumbing — an anonymous visitor has no
           container, so a "CONTAINER LIVE · localhost" chip only confuses. -->
      {#if $isAuthenticated}
        <EndpointStatus compact />
      {/if}

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
