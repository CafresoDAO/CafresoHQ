<script>
  import { page } from '$app/stores';
  import { cartCount, cartOpen } from '$lib/stores/cart.js';
  import { goldBalance, goldBalanceSource } from '$lib/stores/blog.js';
  import { fmtGold } from '$lib/gold.js';
  import Icon from './Icon.svelte';
  import Logo from './Logo.svelte';
  import GoldCoin from './GoldCoin.svelte';
  import {
    authStatus,
    isAuthenticated,
    principalText,
    login,
    logout
  } from '$lib/stores/auth.js';
  import { bbLinks, aiCafresoOrigin } from '$lib/links.js';
  import { aiSearchOpen } from '$lib/stores/blog.js';
  import { theme, toggleTheme } from '$lib/stores/theme.js';
  import { isDevlogAdmin } from '$lib/data/admins.js';
  import NotificationBell from './NotificationBell.svelte';
  import { mobileOverlay, toggleMobileOverlay, closeMobileOverlay } from '$lib/stores/mobileOverlay.js';

  $: isAdmin = isDevlogAdmin($principalText);

  let menuOpen = false;
  // Mutually exclusive with MobileNav's Explore popover — see mobileOverlay.js.
  $: mobileNavOpen = $mobileOverlay === 'drawer';
  function closeMobileNav() { closeMobileOverlay(); }
  function shortPrincipal(p) {
    if (!p) return '';
    return `${p.slice(0, 5)}…${p.slice(-3)}`;
  }
  async function copyPrincipal() {
    if (!$principalText) return;
    try {
      await navigator.clipboard.writeText($principalText);
    } catch {}
    menuOpen = false;
  }
  async function handleLogin() {
    menuOpen = false;
    await login();
  }
  async function handleLogout() {
    menuOpen = false;
    await logout();
  }

  // Items flagged `external: true` cross-link to the Banking.Brave canister.
  // They render as plain anchors (not SPA `sveltekit-preload-code`) so the
  // browser does a full navigation into the other canister's origin.
  // Six core destinations stay visible; everything else lives under "More".
  // The old 12-item row scrolled horizontally with the scrollbar hidden, so
  // at most widths half the site silently disappeared past the clip edge.
  const items = [
    { href: '/', key: 'home', icon: 'house', label: 'Home' },
    { href: '/how-it-works', key: 'how', icon: 'compass', label: 'How it Works' },
    { href: '/projects', key: 'projects', icon: 'stack', label: 'Projects' },
    { href: '/library', key: 'library', icon: 'books', label: 'Library' },
    { href: '/shop', key: 'shop', icon: 'coffee-bean', label: 'Shop' },
    { href: '/blog', key: 'blog', icon: 'article', label: 'Dev Log' }
  ];
  // Labels match the mobile tab bar ("DAO", not "Governance") so the site
  // reads as one map on every surface.
  const moreItems = [
    { href: '/forums', key: 'forums', icon: 'chats-circle', label: 'Forums' },
    { href: '/governance', key: 'governance', icon: 'gavel', label: 'DAO', beta: true },
    { href: '/leaderboard', key: 'leaderboard', icon: 'trophy', label: 'Contest' },
    { href: '/about', key: 'about', icon: 'info', label: 'About' },
    { href: aiCafresoOrigin, key: 'ai', icon: 'brain', label: 'Cafreso AI', external: true },
    { href: bbLinks.mine, key: 'mine', icon: 'coin', label: 'Mine', external: true }
  ];

  let moreOpen = false;
  let moreWrap;
  $: moreActive = moreItems.some((it) => it.key === activeKey);
  function onMoreClickOutside(e) {
    if (moreWrap && !moreWrap.contains(e.target)) moreOpen = false;
  }

  let navEl;
  let ind = { x: 0, w: 0, v: 0 };

  $: path = $page.url.pathname;
  $: activeKey = path === '/'
    ? 'home'
    : path.startsWith('/shop') || path.startsWith('/product') || path.startsWith('/checkout') || path.startsWith('/success')
      ? 'shop'
      : path.startsWith('/projects')
        ? 'projects'
        : path.startsWith('/leaderboard')
        ? 'leaderboard'
        : path.startsWith('/blog')
          ? 'blog'
          : path.startsWith('/forums')
            ? 'forums'
            : path.startsWith('/governance')
              ? 'governance'
              : path.startsWith('/about')
                ? 'about'
                : '';

  // Position the sliding indicator in the nav's OWN content coordinate space
  // (offsetLeft/offsetWidth), not viewport rects — the nav can scroll
  // horizontally when the 12 links don't fit, and content-space coords keep
  // the pill glued to its item through any scroll offset.
  function moveTo(el) {
    if (!el || !navEl) return;
    ind = { x: el.offsetLeft, w: el.offsetWidth, v: 1 };
  }

  function restore() {
    if (!navEl) return;
    const el = navEl.querySelector(`[data-k="${activeKey}"]`);
    if (el) moveTo(el);
    else ind = { ...ind, v: 0 };
  }

  $: if (typeof window !== 'undefined' && activeKey) {
    requestAnimationFrame(restore);
  }

  import { onMount } from 'svelte';
  onMount(() => {
    restore();
    const on = () => restore();
    window.addEventListener('resize', on);
    document.addEventListener('mousedown', onMoreClickOutside);
    return () => {
      window.removeEventListener('resize', on);
      document.removeEventListener('mousedown', onMoreClickOutside);
    };
  });
</script>

<div class="site-header-wrap sticky top-0 z-10 pt-3 px-4 sm:px-[18px]">
  <header
    class="site-header mx-auto flex items-center h-[60px] rounded-[14px]"
    style="max-width: 1240px; padding: 0 14px 0 10px;
      background: hsl(var(--pg-header) / 0.55);
      backdrop-filter: blur(18px) saturate(140%);
      -webkit-backdrop-filter: blur(18px) saturate(140%);
      border: 1px solid hsl(var(--pg-header-edge) / 0.6);
      box-shadow: 0 1px 0 hsl(var(--pg-header-edge) / 0.5) inset, 0 12px 30px -16px hsl(24 35% 25% / 0.35);"
  >
    <a
      href="/"
      class="pg-logo cursor-pointer inline-flex items-center gap-2.5 py-1 pl-1.5 pr-3 rounded-full transition-colors"
      style="transition: background .25s;"
      on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(var(--pg-hover) / 0.6)')}
      on:mouseleave={(e) => (e.currentTarget.style.background = 'transparent')}
    >
      <Logo size={32} />
      <span class="font-semibold text-[15px] tracking-tight" style="color: hsl(var(--pg-fg));">Cafreso</span>
    </a>

    <span class="desktop-only w-px h-6 mx-3.5" style="background: hsl(var(--pg-fg) / 0.15);"></span>

    <nav
      bind:this={navEl}
      class="site-nav desktop-only flex gap-0.5 relative min-w-0 flex-1"
      on:mouseleave={restore}
    >
      <span
        class="absolute top-0 left-0 h-full rounded-[10px] pointer-events-none"
        style="transform: translateX({ind.x}px); width: {ind.w}px; opacity: {ind.v};
          background: hsl(var(--pg-hover) / 0.75);
          border: 1px solid hsl(var(--pg-border) / 0.8);
          transition: transform .45s cubic-bezier(.2,.8,.2,1), width .45s cubic-bezier(.2,.8,.2,1), opacity .2s;
          box-shadow: 0 1px 2px hsl(24 20% 30% / 0.06);
          z-index: 0;"
      ></span>
      {#each items as it}
        {@const active = activeKey === it.key}
        <a
          href={it.href}
          data-k={it.key}
          data-sveltekit-reload={it.external ? 'on' : undefined}
          rel={it.external ? 'noopener' : undefined}
          on:mouseenter={(e) => moveTo(e.currentTarget)}
          class="relative z-[1] inline-flex items-center gap-1.5 px-3.5 py-2 rounded-[10px] text-[13.5px] font-medium cursor-pointer transition-colors"
          style="color: {active ? 'hsl(var(--pg-fg))' : 'hsl(var(--pg-fg) / 0.62)'};"
        >
          <Icon name={it.icon} size={17} /> {it.label}
          {#if it.beta}
            <span style="font-size: 8.5px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; background: hsl(var(--pg-accent-purple)); color: white; padding: 1px 4px; border-radius: 4px; line-height: 1.6;">BETA</span>
          {/if}
          {#if it.external}
            <Icon name="arrow-up-right" size={11} style="opacity: 0.55;" />
          {/if}
        </a>
      {/each}
    </nav>

    <!-- Sibling of the scrollable nav, not a child: the row can scroll while
         "More" stays pinned and its menu is never clipped by the scroll box. -->
    <div class="desktop-only relative shrink-0" bind:this={moreWrap}>
        <button
          type="button"
          aria-expanded={moreOpen}
          on:click={() => (moreOpen = !moreOpen)}
          class="relative z-[1] inline-flex items-center gap-1.5 px-3.5 py-2 rounded-[10px] text-[13.5px] font-medium cursor-pointer transition-colors"
          style="color: {moreActive || moreOpen ? 'hsl(var(--pg-fg))' : 'hsl(var(--pg-fg) / 0.62)'}; background: transparent; border: 0;"
        >
          More <span aria-hidden="true" style="font-size: 9px;">{moreOpen ? '▴' : '▾'}</span>
        </button>
        {#if moreOpen}
          <div
            role="menu"
            class="absolute left-0 z-50 flex flex-col gap-0.5"
            style="top: calc(100% + 10px); min-width: 190px; padding: 6px;
              background: hsl(var(--pg-header));
              border: 1px solid hsl(var(--pg-header-edge) / 0.8);
              border-radius: 12px;
              box-shadow: 0 12px 30px -12px hsl(24 35% 25% / 0.4);"
          >
            {#each moreItems as it}
              {@const active = activeKey === it.key}
              <a
                role="menuitem"
                href={it.href}
                data-sveltekit-reload={it.external ? 'on' : undefined}
                rel={it.external ? 'noopener' : undefined}
                on:click={() => (moreOpen = false)}
                class="inline-flex items-center gap-2 px-3 py-2 rounded-[8px] text-[13px] font-medium cursor-pointer transition-colors"
                style="color: {active ? 'hsl(var(--pg-fg))' : 'hsl(var(--pg-fg) / 0.72)'};
                  background: {active ? 'hsl(var(--pg-hover) / 0.75)' : 'transparent'};"
                on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(var(--pg-hover) / 0.6)')}
                on:mouseleave={(e) => (e.currentTarget.style.background = active ? 'hsl(var(--pg-hover) / 0.75)' : 'transparent')}
              >
                <Icon name={it.icon} size={16} /> {it.label}
                {#if it.beta}
                  <span style="font-size: 8.5px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; background: hsl(var(--pg-accent-purple)); color: white; padding: 1px 4px; border-radius: 4px; line-height: 1.6;">BETA</span>
                {/if}
                {#if it.external}
                  <Icon name="arrow-up-right" size={11} style="opacity: 0.55;" />
                {/if}
              </a>
            {/each}
          </div>
        {/if}
      </div>

    <div class="pg-cluster ml-auto flex items-center gap-2.5">
      <!-- Full chip: desktop. Tapping jumps to the profile (wallet) page.
           `title` reflects whether the balance is live from the ICRC-1
           ledger, cached/stale, or the anonymous localStorage counter. -->
      <a
        href="/profile"
        class="nanas-chip-full inline-flex items-center gap-1.5 font-semibold no-underline cursor-pointer"
        style="
          background: hsl(45 80% 60% / 0.16); border: 1px solid hsl(45 75% 52% / 0.4);
          padding: 6px 12px; border-radius: 999px; font-size: 13px;
          color: hsl(var(--pg-fg));
        "
        title={$goldBalanceSource === 'ledger'
          ? 'Live sGLDT (gold) balance from the ledger · tap for wallet'
          : $goldBalanceSource === 'ledger-stale'
            ? 'Ledger lookup failed — balance may be stale'
            : 'Sign in to see your gold (sGLDT) balance'}
      >
        <GoldCoin size={16} />
        {$goldBalance === null ? '—' : fmtGold($goldBalance)}
        <span class="font-normal" style="color: hsl(var(--pg-fg-muted)); font-size: 12px;">sGLDT</span>
        {#if $goldBalanceSource === 'ledger'}
          <span
            class="w-[7px] h-[7px] rounded-full shrink-0"
            style="background: hsl(var(--pg-success-fg)); box-shadow: 0 0 0 2px hsl(var(--pg-success-fg) / 0.25);"
            aria-label="Live balance"
          ></span>
        {/if}
      </a>
      <!-- Compact chip: mobile -->
      <a
        href="/profile"
        class="nanas-chip-compact items-center gap-1 font-semibold no-underline cursor-pointer"
        style="
          display: none;
          background: hsl(45 80% 60% / 0.16); border: 1px solid hsl(45 75% 52% / 0.4);
          padding: 4px 8px; border-radius: 999px; font-size: 12px;
          color: hsl(var(--pg-fg));
        "
        title="Gold (sGLDT) balance · tap for wallet"
      >
        <GoldCoin size={14} />
        {$goldBalance === null ? '—' : fmtGold($goldBalance)}
      </a>

      <NotificationBell />

      <!-- Light / dark toggle (desktop; mobile has its own row in the drawer) -->
      <button
        type="button"
        aria-label="Switch to {$theme === 'dark' ? 'light' : 'dark'} mode"
        title="Switch to {$theme === 'dark' ? 'light' : 'dark'} mode"
        on:click={toggleTheme}
        class="desktop-only w-[38px] h-[38px] inline-flex items-center justify-center border-none bg-transparent rounded-[10px] cursor-pointer"
        style="color: hsl(var(--pg-fg-muted)); transition: background .2s, color .2s;"
        on:mouseenter={(e) => { e.currentTarget.style.background = 'hsl(var(--pg-hover) / 0.7)'; e.currentTarget.style.color = 'hsl(var(--pg-fg))'; }}
        on:mouseleave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'hsl(var(--pg-fg-muted))'; }}
      >
        <Icon name={$theme === 'dark' ? 'sun' : 'moon'} size={19} />
      </button>

      <button
        type="button"
        aria-label="AI Search"
        on:click={() => aiSearchOpen.set(true)}
        class="w-[38px] h-[38px] inline-flex items-center justify-center border-none bg-transparent rounded-[10px] cursor-pointer"
        style="color: hsl(var(--pg-fg-muted)); transition: background .2s, color .2s; position: relative;"
        on:mouseenter={(e) => { e.currentTarget.style.background = 'hsl(var(--pg-hover) / 0.7)'; e.currentTarget.style.color = 'hsl(var(--pg-accent-purple))'; }}
        on:mouseleave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'hsl(var(--pg-fg-muted))'; }}
        title="AI Search — powered by ai.cafreso.com"
      >
        <Icon name="magnifying-glass" size={19} />
        <span style="
          position: absolute; top: 6px; right: 6px;
          width: 6px; height: 6px; border-radius: 50%;
          background: hsl(var(--pg-accent-purple));
          border: 1.5px solid hsl(var(--pg-header));
        "></span>
      </button>

      <!-- Hamburger — mobile only -->
      <button
        type="button"
        aria-label={mobileNavOpen ? 'Close menu' : 'Open menu'}
        class="mobile-hamburger"
        on:click={() => toggleMobileOverlay('drawer')}
      >
        <Icon name={mobileNavOpen ? 'x' : 'list'} size={22} />
      </button>

      {#if $isAuthenticated}
        <div class="relative">
          <button
            type="button"
            on:click={() => (menuOpen = !menuOpen)}
            class="site-header-login h-[38px] px-3 border-none rounded-[10px] cursor-pointer text-[13px] font-medium inline-flex items-center gap-2"
            style="background: hsl(var(--pg-solid)); color: hsl(var(--pg-solid-fg));
              transition: transform .25s cubic-bezier(.2,.8,.2,1), box-shadow .25s;
              box-shadow: 0 1px 0 hsl(0 0% 100% / 0.1) inset, 0 6px 16px -8px hsl(222 47% 11% / 0.5);"
            on:mouseenter={(e) => (e.currentTarget.style.transform = 'translateY(-1px)')}
            on:mouseleave={(e) => (e.currentTarget.style.transform = 'none')}
          >
            <Icon name="user-circle" size={16} />
            <span class="relative z-[1] font-mono">{shortPrincipal($principalText)}</span>
          </button>
          {#if menuOpen}
            <div
              class="absolute right-0 mt-2 w-[240px] p-1.5 rounded-[12px] z-20"
              style="background: hsl(var(--pg-surface));
                border: 1px solid hsl(var(--pg-border));
                box-shadow: 0 12px 30px -10px hsl(24 35% 25% / 0.35);"
            >
              <div class="px-2.5 py-2 text-[11px]" style="color: hsl(var(--pg-fg-muted));">
                Signed in as
                <div class="font-mono text-[11px] break-all mt-0.5" style="color: hsl(var(--pg-fg));">
                  {$principalText}
                </div>
              </div>
              <button
                type="button"
                on:click={copyPrincipal}
                class="w-full text-left px-2.5 py-2 rounded-[8px] text-[13px] bg-transparent border-none cursor-pointer inline-flex items-center gap-2"
                style="color: hsl(var(--pg-fg)); transition: background .15s;"
                on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(var(--pg-hover))')}
                on:mouseleave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <Icon name="copy" size={15} /> Copy principal
              </button>
              <a
                href="/profile"
                on:click={() => (menuOpen = false)}
                class="w-full text-left px-2.5 py-2 rounded-[8px] text-[13px] inline-flex items-center gap-2"
                style="color: hsl(var(--pg-fg)); transition: background .15s;"
                on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(var(--pg-hover))')}
                on:mouseleave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <Icon name="user-circle" size={15} /> Profile + wallet
              </a>
              <a
                href="/drafts"
                on:click={() => (menuOpen = false)}
                class="w-full text-left px-2.5 py-2 rounded-[8px] text-[13px] inline-flex items-center gap-2"
                style="color: hsl(var(--pg-fg)); transition: background .15s;"
                on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(var(--pg-hover))')}
                on:mouseleave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <Icon name="note-pencil" size={15} /> My drafts
              </a>
              <a
                href={bbLinks.transactions}
                data-sveltekit-reload="on"
                rel="noopener"
                on:click={() => (menuOpen = false)}
                class="w-full text-left px-2.5 py-2 rounded-[8px] text-[13px] inline-flex items-center gap-2"
                style="color: hsl(var(--pg-fg)); transition: background .15s;"
                on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(var(--pg-hover))')}
                on:mouseleave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <Icon name="receipt" size={15} /> Mining transactions
                <Icon name="arrow-up-right" size={11} style="opacity: 0.6; margin-left: auto;" />
              </a>
              {#if isAdmin}
                <div class="my-1" style="height: 1px; background: hsl(var(--pg-border));"></div>
                <a
                  href="/admin/store"
                  on:click={() => (menuOpen = false)}
                  class="w-full text-left px-2.5 py-2 rounded-[8px] text-[13px] inline-flex items-center gap-2"
                  style="color: hsl(var(--pg-fg)); transition: background .15s;"
                  on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(var(--pg-hover))')}
                  on:mouseleave={(e) => (e.currentTarget.style.background = 'transparent')}
                >
                  <Icon name="storefront" size={15} /> Admin · Store
                </a>
                <a
                  href="/admin/analytics"
                  on:click={() => (menuOpen = false)}
                  class="w-full text-left px-2.5 py-2 rounded-[8px] text-[13px] inline-flex items-center gap-2"
                  style="color: hsl(var(--pg-fg)); transition: background .15s;"
                  on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(var(--pg-hover))')}
                  on:mouseleave={(e) => (e.currentTarget.style.background = 'transparent')}
                >
                  <Icon name="chart-line" size={15} /> Admin · Analytics
                </a>
              {/if}
              <button
                type="button"
                on:click={handleLogout}
                class="w-full text-left px-2.5 py-2 rounded-[8px] text-[13px] bg-transparent border-none cursor-pointer inline-flex items-center gap-2"
                style="color: hsl(var(--pg-danger-fg)); transition: background .15s;"
                on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(var(--pg-danger-fg) / 0.14)')}
                on:mouseleave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <Icon name="sign-out" size={15} /> Log out
              </button>
            </div>
          {/if}
        </div>
      {:else}
        <button
          type="button"
          on:click={handleLogin}
          disabled={$authStatus === 'initializing' || $authStatus === 'logging-in'}
          class="site-header-login h-[38px] px-3 sm:px-4 border-none rounded-[10px] cursor-pointer text-[12.5px] sm:text-[13px] font-medium inline-flex items-center gap-1.5"
          style="background: hsl(var(--pg-solid)); color: hsl(var(--pg-solid-fg));
            transition: transform .25s cubic-bezier(.2,.8,.2,1), box-shadow .25s, opacity .2s;
            box-shadow: 0 1px 0 hsl(0 0% 100% / 0.1) inset, 0 6px 16px -8px hsl(222 47% 11% / 0.5);
            opacity: {$authStatus === 'initializing' || $authStatus === 'logging-in' ? 0.6 : 1};"
          on:mouseenter={(e) => (e.currentTarget.style.transform = 'translateY(-1px)')}
          on:mouseleave={(e) => (e.currentTarget.style.transform = 'none')}
        >
          <Icon name="fingerprint" size={16} />
          <span class="relative z-[1]">
            {$authStatus === 'logging-in' ? 'Connecting…' : 'Log in'}
          </span>
        </button>
      {/if}

      <div class="relative">
        <button
          on:click={() => cartOpen.set(true)}
          aria-label={`Cart (${$cartCount} items)`}
          class="w-[38px] h-[38px] inline-flex items-center justify-center border-none bg-transparent rounded-[10px] cursor-pointer"
          style="color: hsl(var(--pg-fg)); transition: background .2s, transform .25s cubic-bezier(.2,.8,.2,1);"
          on:mouseenter={(e) => {
            e.currentTarget.style.background = 'hsl(var(--pg-hover) / 0.7)';
            const i = e.currentTarget.querySelector('i');
            if (i) i.style.transform = 'translateY(-2px) rotate(-6deg)';
          }}
          on:mouseleave={(e) => {
            e.currentTarget.style.background = 'transparent';
            const i = e.currentTarget.querySelector('i');
            if (i) i.style.transform = 'none';
          }}
        >
          <Icon name="shopping-cart" size={20} style="transition: transform .4s cubic-bezier(.2,.8,.2,1);" />
        </button>
        {#if $cartCount > 0}
          {#key $cartCount}
            <span
              class="absolute top-0.5 right-0.5 min-w-[18px] h-[18px] px-1.5 text-[10px] font-bold text-white rounded-full inline-flex items-center justify-center animate-pop"
              style="background: hsl(var(--brand-cart-badge));
                border: 2px solid hsl(var(--pg-header));
                box-shadow: 0 2px 6px hsl(var(--brand-cart-badge) / 0.35);"
            >
              {$cartCount}
            </span>
          {/key}
        {/if}
      </div>
    </div>
  </header>
</div>

<!-- ── Mobile slide-out nav ───────────────────────────────────── -->
{#if mobileNavOpen}
  <!-- Backdrop -->
  <button
    type="button"
    aria-label="Close menu"
    on:click={closeMobileNav}
    style="
      position: fixed; inset: 0; z-index: 39;
      background: hsl(24 40% 4% / 0.55);
      backdrop-filter: blur(3px);
      -webkit-backdrop-filter: blur(3px);
      border: none; cursor: pointer; width: 100%; height: 100%;
    "
  ></button>

  <!-- Panel -->
  <div class="mobile-drawer" role="dialog" aria-label="Navigation menu">
    <div class="mobile-drawer-head">
      <Logo size={28} />
      <button
        type="button"
        aria-label="Close"
        on:click={closeMobileNav}
        class="mobile-drawer-close"
      >
        <Icon name="x" size={20} />
      </button>
    </div>

    <nav class="mobile-drawer-nav">
      <!-- The drawer is the full map — core items plus everything under More. -->
      {#each [...items, ...moreItems] as it}
        {@const active = activeKey === it.key}
        <a
          href={it.href}
          data-sveltekit-reload={it.external ? 'on' : undefined}
          rel={it.external ? 'noopener' : undefined}
          on:click={closeMobileNav}
          class="mobile-drawer-item"
          style="
            background: {active ? 'hsl(var(--pg-solid))' : 'transparent'};
            color: {active ? 'hsl(var(--pg-solid-fg))' : 'hsl(var(--pg-fg))'};
          "
        >
          <Icon name={it.icon} size={19} />
          <span>{it.label}</span>
          {#if it.beta}
            <span class="mobile-drawer-beta">BETA</span>
          {/if}
          {#if it.external}
            <Icon name="arrow-up-right" size={12} style="opacity: 0.55; margin-left: auto;" />
          {/if}
        </a>
      {/each}
    </nav>

    <div class="mobile-drawer-footer">
      <button
        type="button"
        on:click={toggleTheme}
        class="mobile-drawer-theme"
      >
        <Icon name={$theme === 'dark' ? 'sun' : 'moon'} size={16} />
        {$theme === 'dark' ? 'Light mode' : 'Dark mode'}
      </button>
      {#if $isAuthenticated}
        <div class="mobile-drawer-principal">
          <Icon name="user-circle" size={14} />
          {shortPrincipal($principalText)}
        </div>
        <button
          type="button"
          on:click={() => { closeMobileNav(); handleLogout(); }}
          class="mobile-drawer-signout"
        >
          <Icon name="sign-out" size={15} /> Sign out
        </button>
      {:else}
        <button
          type="button"
          on:click={() => { closeMobileNav(); handleLogin(); }}
          class="mobile-drawer-signin"
        >
          <Icon name="fingerprint" size={16} /> Sign in with Internet Identity
        </button>
      {/if}
    </div>
  </div>
{/if}

<style>
  /* The six core links scroll horizontally if they ever don't fit; "More"
     sits outside this box so it stays pinned and its menu is never clipped.
     Scrollbar hidden — the sliding indicator + hover already signal position. */
  .site-nav {
    overflow-x: auto;
    overflow-y: hidden;
    scrollbar-width: none;        /* Firefox */
    -ms-overflow-style: none;     /* old Edge */
    scroll-behavior: smooth;
  }
  .site-nav::-webkit-scrollbar { display: none; }  /* Chrome/Safari */

  /* Pin the logo + action cluster only on desktop, where the nav is the
     flex-1 element that absorbs shrink (and scrolls). Below 881px the nav is
     hidden, so the logo + cluster must keep their default flex-shrink to fit a
     narrow header — otherwise they'd overflow and force a horizontal scroll. */
  @media (min-width: 881px) {
    .pg-logo,
    .pg-cluster { flex-shrink: 0; }
  }

  /* Hamburger button — shown only on mobile via app.css mobile breakpoint */
  .mobile-hamburger {
    display: none; /* shown by app.css when ≤ 880px */
    width: 38px; height: 38px;
    align-items: center; justify-content: center;
    border: none; background: transparent; border-radius: 10px;
    cursor: pointer; color: hsl(var(--pg-fg));
    transition: background .2s;
  }
  .mobile-hamburger:hover {
    background: hsl(var(--pg-hover) / 0.7);
  }

  /* Slide-in panel from the right */
  .mobile-drawer {
    position: fixed;
    top: 0; right: 0; bottom: 0;
    width: min(300px, 85vw);
    z-index: 40;
    background: hsl(var(--pg-surface));
    border-left: 1px solid hsl(var(--pg-border));
    box-shadow: -12px 0 40px -8px hsl(24 35% 20% / 0.25);
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    animation: drawerIn .22s cubic-bezier(.2,.8,.2,1);
  }
  @keyframes drawerIn {
    from { transform: translateX(100%); }
    to   { transform: translateX(0); }
  }

  .mobile-drawer-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 18px 16px 14px;
    border-bottom: 1px solid hsl(var(--pg-border));
  }
  .mobile-drawer-close {
    width: 34px; height: 34px;
    border: none; background: transparent; border-radius: 8px;
    cursor: pointer; color: hsl(var(--pg-fg-muted));
    display: flex; align-items: center; justify-content: center;
    transition: background .15s;
  }
  .mobile-drawer-close:hover { background: hsl(var(--pg-hover)); }

  .mobile-drawer-nav {
    padding: 10px 10px;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .mobile-drawer-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 11px 14px;
    border-radius: 10px;
    text-decoration: none;
    font-size: 15px;
    font-weight: 500;
    transition: background .15s;
  }
  .mobile-drawer-beta {
    font-size: 8px; font-weight: 800;
    letter-spacing: 0.1em; text-transform: uppercase;
    background: hsl(var(--pg-accent-purple)); color: white;
    padding: 1px 5px; border-radius: 4px;
  }

  .mobile-drawer-footer {
    padding: 14px 12px 24px;
    border-top: 1px solid hsl(var(--pg-border));
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .mobile-drawer-theme {
    display: flex; align-items: center; gap: 8px;
    width: 100%; padding: 10px 14px; border-radius: 10px;
    border: 1px solid hsl(var(--pg-border)); background: transparent;
    color: hsl(var(--pg-fg)); font-size: 13.5px; font-weight: 500;
    cursor: pointer; transition: background .15s;
  }
  .mobile-drawer-theme:hover { background: hsl(var(--pg-hover)); }
  .mobile-drawer-principal {
    font-size: 12px; font-family: ui-monospace, monospace;
    color: hsl(var(--pg-fg-muted));
    display: flex; align-items: center; gap: 6px;
    padding: 6px 4px;
  }
  .mobile-drawer-signout {
    display: flex; align-items: center; gap: 8px;
    width: 100%; padding: 10px 14px; border-radius: 10px;
    border: 1px solid hsl(var(--pg-danger-border)); background: transparent;
    color: hsl(var(--pg-danger-fg)); font-size: 13.5px; font-weight: 500;
    cursor: pointer; transition: background .15s;
  }
  .mobile-drawer-signout:hover { background: hsl(var(--pg-danger-fg) / 0.12); }
  .mobile-drawer-signin {
    display: flex; align-items: center; justify-content: center; gap: 8px;
    width: 100%; padding: 12px 14px; border-radius: 10px;
    border: none; background: hsl(var(--pg-solid));
    color: hsl(var(--pg-solid-fg)); font-size: 13.5px; font-weight: 600;
    cursor: pointer; transition: opacity .15s;
  }
  .mobile-drawer-signin:hover { opacity: 0.88; }
</style>
