<script>
  import { page } from '$app/stores';
  import { cartCount, cartOpen } from '$lib/stores/cart.js';
  import { nanasBalance, nanasBalanceSource } from '$lib/stores/blog.js';
  import Icon from './Icon.svelte';
  import Logo from './Logo.svelte';
  import NanasCoin from './NanasCoin.svelte';
  import {
    authStatus,
    isAuthenticated,
    principalText,
    login,
    logout
  } from '$lib/stores/auth.js';
  import { bbLinks, aiCafresoOrigin } from '$lib/links.js';
  import { aiSearchOpen } from '$lib/stores/blog.js';
  import { isDevlogAdmin } from '$lib/data/admins.js';
  import NotificationBell from './NotificationBell.svelte';

  $: isAdmin = isDevlogAdmin($principalText);

  let menuOpen = false;
  let mobileNavOpen = false;
  function closeMobileNav() { mobileNavOpen = false; }
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
  const items = [
    { href: '/', key: 'home', icon: 'house', label: 'Home' },
    { href: '/shop', key: 'shop', icon: 'coffee-bean', label: 'Shop' },
    { href: bbLinks.mine, key: 'mine', icon: 'coin', label: 'Mine', external: true },
    { href: aiCafresoOrigin, key: 'ai', icon: 'brain', label: 'AI', external: true },
    { href: '/blog', key: 'blog', icon: 'article', label: 'Dev Log' },
    { href: '/forums', key: 'forums', icon: 'chats-circle', label: 'Forums' },
    { href: '/governance', key: 'governance', icon: 'gavel', label: 'Governance', beta: true },
    { href: '/leaderboard', key: 'leaderboard', icon: 'trophy', label: 'Contest' },
    { href: '/about', key: 'about', icon: 'info', label: 'About' }
  ];

  let navEl;
  let ind = { x: 0, w: 0, v: 0 };

  $: path = $page.url.pathname;
  $: activeKey = path === '/'
    ? 'home'
    : path.startsWith('/shop') || path.startsWith('/product') || path.startsWith('/checkout') || path.startsWith('/success')
      ? 'shop'
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

  function moveTo(el) {
    if (!el || !navEl) return;
    const r = el.getBoundingClientRect();
    const n = navEl.getBoundingClientRect();
    ind = { x: r.left - n.left, w: r.width, v: 1 };
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
    return () => window.removeEventListener('resize', on);
  });
</script>

<div class="site-header-wrap sticky top-0 z-10 pt-3 px-4 sm:px-[18px]">
  <header
    class="site-header mx-auto flex items-center h-[60px] rounded-[14px]"
    style="max-width: 1240px; padding: 0 14px 0 10px;
      background: hsl(26 30% 82% / 0.55);
      backdrop-filter: blur(18px) saturate(140%);
      -webkit-backdrop-filter: blur(18px) saturate(140%);
      border: 1px solid hsl(26 35% 95% / 0.6);
      box-shadow: 0 1px 0 hsl(26 40% 98% / 0.5) inset, 0 12px 30px -16px hsl(24 35% 25% / 0.35);"
  >
    <a
      href="/"
      class="cursor-pointer inline-flex items-center gap-2.5 py-1 pl-1.5 pr-3 rounded-full transition-colors"
      style="transition: background .25s;"
      on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(26 40% 96% / 0.5)')}
      on:mouseleave={(e) => (e.currentTarget.style.background = 'transparent')}
    >
      <Logo size={32} />
      <span class="font-semibold text-[15px] tracking-tight">Cafreso</span>
    </a>

    <span class="desktop-only w-px h-6 mx-3.5" style="background: hsl(222 47% 11% / 0.15);"></span>

    <nav
      bind:this={navEl}
      class="desktop-only flex gap-0.5 relative"
      on:mouseleave={restore}
    >
      <span
        class="absolute top-0 left-0 h-full rounded-[10px] pointer-events-none"
        style="transform: translateX({ind.x}px); width: {ind.w}px; opacity: {ind.v};
          background: hsl(26 45% 98% / 0.7);
          border: 1px solid hsl(26 30% 88% / 0.8);
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
          style="color: {active ? 'hsl(222 47% 11%)' : 'hsl(222 47% 11% / 0.62)'};"
        >
          <Icon name={it.icon} size={17} /> {it.label}
          {#if it.beta}
            <span style="font-size: 8.5px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; background: hsl(260 70% 62%); color: white; padding: 1px 4px; border-radius: 4px; line-height: 1.6;">BETA</span>
          {/if}
          {#if it.external}
            <Icon name="arrow-up-right" size={11} style="opacity: 0.55;" />
          {/if}
        </a>
      {/each}
    </nav>

    <div class="ml-auto flex items-center gap-2.5">
      <!-- Full chip: desktop. Tapping jumps to the profile (wallet) page.
           `title` reflects whether the balance is live from the ICRC-1
           ledger, cached/stale, or the anonymous localStorage counter. -->
      <a
        href="/profile"
        class="nanas-chip-full inline-flex items-center gap-1.5 font-semibold no-underline cursor-pointer"
        style="
          background: hsl(45 80% 94%); border: 1px solid hsl(45 75% 75%);
          padding: 6px 12px; border-radius: 999px; font-size: 13px;
          color: hsl(24 48% 18%);
        "
        title={$nanasBalanceSource === 'ledger'
          ? 'Live $nanas balance from the ICRC-1 ledger · tap for wallet'
          : $nanasBalanceSource === 'ledger-stale'
            ? 'Ledger lookup failed — showing cached balance'
            : 'Sign in to see your live $nanas balance'}
      >
        <NanasCoin size={16} />
        {$nanasBalance.toLocaleString()}
        <span class="font-normal" style="color: hsl(215 16% 47%); font-size: 12px;">$nanas</span>
        {#if $nanasBalanceSource === 'ledger'}
          <span
            class="w-[7px] h-[7px] rounded-full shrink-0"
            style="background: hsl(112 60% 45%); box-shadow: 0 0 0 2px hsl(112 60% 45% / 0.25);"
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
          background: hsl(45 80% 94%); border: 1px solid hsl(45 75% 75%);
          padding: 4px 8px; border-radius: 999px; font-size: 12px;
          color: hsl(24 48% 18%);
        "
        title="$nanas balance · tap for wallet"
      >
        <NanasCoin size={14} />
        {$nanasBalance >= 1000 ? `${(Number($nanasBalance) / 1000).toFixed(1)}k` : $nanasBalance}
      </a>

      <NotificationBell />

      <button
        type="button"
        aria-label="AI Search"
        on:click={() => aiSearchOpen.set(true)}
        class="w-[38px] h-[38px] inline-flex items-center justify-center border-none bg-transparent rounded-[10px] cursor-pointer"
        style="color: hsl(215 16% 47%); transition: background .2s, color .2s; position: relative;"
        on:mouseenter={(e) => { e.currentTarget.style.background = 'hsl(26 40% 96% / 0.55)'; e.currentTarget.style.color = 'hsl(260 70% 50%)'; }}
        on:mouseleave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'hsl(215 16% 47%)'; }}
        title="AI Search — powered by ai.cafreso.com"
      >
        <Icon name="magnifying-glass" size={19} />
        <span style="
          position: absolute; top: 6px; right: 6px;
          width: 6px; height: 6px; border-radius: 50%;
          background: hsl(260 70% 55%);
          border: 1.5px solid hsl(26 40% 88%);
        "></span>
      </button>

      <!-- Hamburger — mobile only -->
      <button
        type="button"
        aria-label={mobileNavOpen ? 'Close menu' : 'Open menu'}
        class="mobile-hamburger"
        on:click={() => (mobileNavOpen = !mobileNavOpen)}
      >
        <Icon name={mobileNavOpen ? 'x' : 'list'} size={22} />
      </button>

      {#if $isAuthenticated}
        <div class="relative">
          <button
            type="button"
            on:click={() => (menuOpen = !menuOpen)}
            class="site-header-login h-[38px] px-3 border-none rounded-[10px] cursor-pointer text-[13px] font-medium text-white inline-flex items-center gap-2"
            style="background: hsl(222 47% 11%);
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
              style="background: hsl(26 40% 98%);
                border: 1px solid hsl(26 30% 88%);
                box-shadow: 0 12px 30px -10px hsl(24 35% 25% / 0.35);"
            >
              <div class="px-2.5 py-2 text-[11px]" style="color: hsl(215 16% 47%);">
                Signed in as
                <div class="font-mono text-[11px] break-all mt-0.5" style="color: hsl(222 47% 11%);">
                  {$principalText}
                </div>
              </div>
              <button
                type="button"
                on:click={copyPrincipal}
                class="w-full text-left px-2.5 py-2 rounded-[8px] text-[13px] bg-transparent border-none cursor-pointer inline-flex items-center gap-2"
                style="color: hsl(222 47% 11%); transition: background .15s;"
                on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(26 40% 94%)')}
                on:mouseleave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <Icon name="copy" size={15} /> Copy principal
              </button>
              <a
                href="/profile"
                on:click={() => (menuOpen = false)}
                class="w-full text-left px-2.5 py-2 rounded-[8px] text-[13px] inline-flex items-center gap-2"
                style="color: hsl(222 47% 11%); transition: background .15s;"
                on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(26 40% 94%)')}
                on:mouseleave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <Icon name="user-circle" size={15} /> Profile + wallet
              </a>
              <a
                href="/drafts"
                on:click={() => (menuOpen = false)}
                class="w-full text-left px-2.5 py-2 rounded-[8px] text-[13px] inline-flex items-center gap-2"
                style="color: hsl(222 47% 11%); transition: background .15s;"
                on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(26 40% 94%)')}
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
                style="color: hsl(222 47% 11%); transition: background .15s;"
                on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(26 40% 94%)')}
                on:mouseleave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                <Icon name="receipt" size={15} /> Mining transactions
                <Icon name="arrow-up-right" size={11} style="opacity: 0.6; margin-left: auto;" />
              </a>
              {#if isAdmin}
                <div class="my-1" style="height: 1px; background: hsl(26 30% 88%);"></div>
                <a
                  href="/admin/store"
                  on:click={() => (menuOpen = false)}
                  class="w-full text-left px-2.5 py-2 rounded-[8px] text-[13px] inline-flex items-center gap-2"
                  style="color: hsl(222 47% 11%); transition: background .15s;"
                  on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(26 40% 94%)')}
                  on:mouseleave={(e) => (e.currentTarget.style.background = 'transparent')}
                >
                  <Icon name="storefront" size={15} /> Admin · Store
                </a>
              {/if}
              <button
                type="button"
                on:click={handleLogout}
                class="w-full text-left px-2.5 py-2 rounded-[8px] text-[13px] bg-transparent border-none cursor-pointer inline-flex items-center gap-2"
                style="color: hsl(0 72% 42%); transition: background .15s;"
                on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(0 80% 96%)')}
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
          class="site-header-login h-[38px] px-3 sm:px-4 border-none rounded-[10px] cursor-pointer text-[12.5px] sm:text-[13px] font-medium text-white inline-flex items-center gap-1.5"
          style="background: hsl(222 47% 11%);
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
          class="w-[38px] h-[38px] inline-flex items-center justify-center border-none bg-transparent rounded-[10px] text-primary cursor-pointer"
          style="transition: background .2s, transform .25s cubic-bezier(.2,.8,.2,1);"
          on:mouseenter={(e) => {
            e.currentTarget.style.background = 'hsl(26 40% 96% / 0.55)';
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
              style="background: hsl(0 84% 60%);
                border: 2px solid hsl(26 40% 88%);
                box-shadow: 0 2px 6px hsl(0 80% 50% / 0.35);"
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
      background: hsl(222 47% 11% / 0.45);
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
      {#each items as it}
        {@const active = activeKey === it.key}
        <a
          href={it.href}
          data-sveltekit-reload={it.external ? 'on' : undefined}
          rel={it.external ? 'noopener' : undefined}
          on:click={closeMobileNav}
          class="mobile-drawer-item"
          style="
            background: {active ? 'hsl(222 47% 11%)' : 'transparent'};
            color: {active ? '#fff' : 'hsl(222 47% 11%)'};
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
  /* Hamburger button — shown only on mobile via app.css mobile breakpoint */
  .mobile-hamburger {
    display: none; /* shown by app.css when ≤ 880px */
    width: 38px; height: 38px;
    align-items: center; justify-content: center;
    border: none; background: transparent; border-radius: 10px;
    cursor: pointer; color: hsl(222 47% 11%);
    transition: background .2s;
  }
  .mobile-hamburger:hover {
    background: hsl(26 40% 96% / 0.55);
  }

  /* Slide-in panel from the right */
  .mobile-drawer {
    position: fixed;
    top: 0; right: 0; bottom: 0;
    width: min(300px, 85vw);
    z-index: 40;
    background: hsl(26 45% 98%);
    border-left: 1px solid hsl(26 30% 85%);
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
    border-bottom: 1px solid hsl(26 30% 88%);
  }
  .mobile-drawer-close {
    width: 34px; height: 34px;
    border: none; background: transparent; border-radius: 8px;
    cursor: pointer; color: hsl(215 16% 47%);
    display: flex; align-items: center; justify-content: center;
    transition: background .15s;
  }
  .mobile-drawer-close:hover { background: hsl(26 40% 93%); }

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
    background: hsl(260 70% 62%); color: white;
    padding: 1px 5px; border-radius: 4px;
  }

  .mobile-drawer-footer {
    padding: 14px 12px 24px;
    border-top: 1px solid hsl(26 30% 88%);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .mobile-drawer-principal {
    font-size: 12px; font-family: ui-monospace, monospace;
    color: hsl(215 16% 47%);
    display: flex; align-items: center; gap: 6px;
    padding: 6px 4px;
  }
  .mobile-drawer-signout {
    display: flex; align-items: center; gap: 8px;
    width: 100%; padding: 10px 14px; border-radius: 10px;
    border: 1px solid hsl(0 50% 88%); background: transparent;
    color: hsl(0 72% 42%); font-size: 13.5px; font-weight: 500;
    cursor: pointer; transition: background .15s;
  }
  .mobile-drawer-signout:hover { background: hsl(0 80% 97%); }
  .mobile-drawer-signin {
    display: flex; align-items: center; justify-content: center; gap: 8px;
    width: 100%; padding: 12px 14px; border-radius: 10px;
    border: none; background: hsl(222 47% 11%);
    color: white; font-size: 13.5px; font-weight: 600;
    cursor: pointer; transition: opacity .15s;
  }
  .mobile-drawer-signin:hover { opacity: 0.88; }
</style>
