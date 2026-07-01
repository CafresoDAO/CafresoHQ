<svelte:options runes={true} />

<script>
  import { onMount } from 'svelte';
  import Icon from '$lib/components/Icon.svelte';
  import Button from '$lib/components/Button.svelte';
  import Avatar from '$lib/components/Avatar.svelte';
  import {
    authIdentity,
    isAuthenticated,
    principalText,
    login,
    logout,
    authStatus
  } from '$lib/stores/auth.js';
  import { profile, ACCENTS } from '$lib/stores/profile.js';
  import { TOKENS, getAllBalances, formatBalance } from '$lib/api/icrc1.js';
  import { listMyOrders } from '$lib/api/store.js';
  import { bbLinks, bankingBraveOrigin } from '$lib/links.js';
  import SendTokenModal from '$lib/components/SendTokenModal.svelte';
  import { refreshNanasBalance } from '$lib/stores/blog.js';
  import { prices, formatUsd, rawToWhole } from '$lib/stores/prices.js';
  import AuditTrail from '$lib/components/AuditTrail.svelte';

  // Send-modal state — tokenKey drives which ledger the modal talks to,
  // `sendOpen` controls visibility. We refresh the wallet on a successful
  // transfer so the balance UI doesn't lie for the window until the user
  // manually clicks Refresh.
  let sendOpen = $state(false);
  let sendTokenKey = $state('nanas');

  function openSend(tokenKey) {
    sendTokenKey = tokenKey;
    sendOpen = true;
  }

  async function handleSent(_info) {
    await refresh();
    // `$nanas` header chip is driven by a separate live-balance store —
    // re-poll it so the header updates in lock-step with the wallet row.
    refreshNanasBalance();
  }

  let signingOut = $state(false);
  async function signOut() {
    if (signingOut) return;
    signingOut = true;
    try {
      await logout();
    } finally {
      signingOut = false;
    }
  }

  let balances = $state({});
  let loadingBalances = $state(false);
  let refreshedAt = $state(null);
  let copied = $state(false);
  let editing = $state(false);
  let draft = $state({ name: '', bio: '', accent: 'banana' });
  let orders = $state([]);
  let loadingOrders = $state(false);

  // Load balances + orders whenever the principal changes (login/logout).
  let lastPrincipalLoaded = null;
  $effect(() => {
    const p = $principalText;
    if (!p || p === lastPrincipalLoaded) return;
    lastPrincipalLoaded = p;
    refresh(p);
    loadOrders();
  });

  async function refresh(p) {
    const who = p || $principalText;
    if (!who) return;
    loadingBalances = true;
    try {
      balances = await getAllBalances(who);
      refreshedAt = Date.now();
    } finally {
      loadingBalances = false;
    }
  }

  async function loadOrders() {
    loadingOrders = true;
    try {
      orders = await listMyOrders();
    } finally {
      loadingOrders = false;
    }
  }

  const ORDER_COLOR = {
    pending: 'hsl(42 80% 92%)',
    paid: 'hsl(142 50% 94%)',
    shipped: 'hsl(215 40% 96%)',
    delivered: 'hsl(112 45% 92%)',
    refunded: 'hsl(26 30% 92%)',
    cancelled: 'hsl(0 70% 96%)'
  };

  async function copyPrincipal() {
    if (!$principalText) return;
    try {
      await navigator.clipboard.writeText($principalText);
      copied = true;
      setTimeout(() => (copied = false), 1800);
    } catch {}
  }

  function startEdit() {
    draft = { ...$profile };
    editing = true;
  }

  function saveEdit() {
    profile.set({
      name: draft.name.trim(),
      bio: draft.bio.trim().slice(0, 280),
      accent: draft.accent || 'banana'
    });
    editing = false;
  }

  function cancelEdit() {
    editing = false;
  }

  function displayName() {
    if ($profile.name) return $profile.name;
    if ($principalText) return `${$principalText.slice(0, 5)}…${$principalText.slice(-3)}`;
    return 'Guest';
  }

  function accentHue() {
    const a = ACCENTS.find((x) => x.key === $profile.accent);
    return a?.hue ?? 45;
  }

  const tokenOrder = ['ICP', 'ckUSDT', 'ckUNI', 'sGLDT', 'nanas'];

  // Seed audit events — replaced by canister fetch once audit log is live.
  const NOW_SEED = 1746662400000; // 2026-05-08 00:00 UTC
  const auditEvents = $derived([
    {
      id: 'ae-1', kind: 'login', title: 'Internet Identity login',
      sub: 'Session started · anchor #12_847',
      block: 4_220_104, ts: NOW_SEED - 3_600_000, url: null, amount: null,
    },
    {
      id: 'ae-2', kind: 'post', title: 'Posted: "Introducing Cafreso"',
      sub: 'Dev Log post authored on-chain',
      block: 4_218_812, ts: NOW_SEED - 86_400_000 * 2, url: '/blog/introducing-cafreso', amount: null,
    },
    {
      id: 'ae-3', kind: 'comment', title: 'Commented on: "Banking.Brave Launch"',
      sub: 'Forum comment posted',
      block: 4_215_003, ts: NOW_SEED - 86_400_000 * 5, url: '/forums/banking-brave-discussion', amount: null,
    },
    {
      id: 'ae-4', kind: 'burn', title: 'Tipped "Introducing Banking.Brave"',
      sub: 'Burn transferred on-chain',
      block: 4_210_444, ts: NOW_SEED - 86_400_000 * 8, url: '/blog/introducing-banking-brave', amount: 150,
    },
    {
      id: 'ae-5', kind: 'vote', title: 'Voted YES: Prop #001 — Q2 APY',
      sub: 'Governance vote cast · 4,200 $CF voting power',
      block: 4_208_001, ts: NOW_SEED - 86_400_000 * 10, url: '/governance/prop-001', amount: null,
    },
  ]);

  // Compute per-token USD value and total portfolio worth. `balances[key]`
  // is the raw ICRC-1 amount (bigint or number); `TOKENS[key].decimals` is
  // 8 or 18; `$prices[key]` is the live USD per whole unit.
  const usdByKey = $derived.by(() => {
    const out = {};
    for (const k of tokenOrder) {
      const t = TOKENS[k];
      const whole = rawToWhole(balances[k], t.decimals);
      const px = $prices?.[k] ?? 0;
      out[k] = whole * px;
    }
    return out;
  });
  const totalUsd = $derived(
    tokenOrder.reduce((acc, k) => acc + (usdByKey[k] || 0), 0)
  );
  const priceStale = $derived($prices?.source === 'cache-stale' || $prices?.source === 'default');
</script>

<svelte:head>
  <title>Profile · Cafreso</title>
</svelte:head>

<section class="mx-auto px-4 sm:px-[18px] pt-6 sm:pt-8 pb-24" style="max-width: 840px;">
  <div class="flex items-center gap-2 text-[13px] font-medium mb-3" style="color: hsl(24 48% 28%);">
    <Icon name="user-circle" size={16} /> Your account
  </div>
  <h1 class="font-bold leading-tight mb-2" style="font-size: clamp(26px, 5vw, 36px); color: hsl(222 47% 11%);">
    Profile
  </h1>
  <p class="text-[14.5px] leading-[1.55] mb-6 sm:mb-8 max-w-[560px]" style="color: hsl(215 16% 47%);">
    Your Internet Identity principal, customized look, and live ICRC-1 wallet balances on the Internet Computer.
  </p>

  {#if !$isAuthenticated}
    <div
      class="rounded-[14px] p-6 sm:p-8 text-center"
      style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%);"
    >
      <Icon name="fingerprint" size={32} style="color: hsl(32 56% 35%);" />
      <h2 class="text-[20px] font-bold mt-3 mb-2" style="color: hsl(222 47% 11%);">
        Sign in to see your wallet
      </h2>
      <p class="text-[13.5px] mb-5 max-w-[380px] mx-auto" style="color: hsl(215 16% 47%);">
        Your principal and balances are derived from your Internet Identity. Nothing is stored on a server — it's all on-chain.
      </p>
      <Button onclick={login} disabled={$authStatus === 'logging-in'}>
        <Icon name="fingerprint" size={16} />
        {$authStatus === 'logging-in' ? 'Connecting…' : 'Sign in with Internet Identity'}
      </Button>
    </div>
  {:else}
    <!-- Identity card -->
    <div
      class="rounded-[16px] p-5 sm:p-6 mb-5"
      style="background: linear-gradient(135deg, hsl({accentHue()} 80% 94%), hsl({accentHue()} 70% 86%));
             border: 1px solid hsl({accentHue()} 55% 70%);"
    >
      <div class="flex items-start gap-4">
        <Avatar name={displayName()} hue={accentHue()} size={56} />
        <div class="flex-1 min-w-0">
          {#if editing}
            <input
              bind:value={draft.name}
              placeholder="Display name"
              maxlength="40"
              class="w-full text-[18px] font-bold bg-white rounded-[10px] px-3 py-2 outline-none"
              style="border: 1px solid hsl({accentHue()} 40% 70%); color: hsl(222 47% 11%);"
            />
            <textarea
              bind:value={draft.bio}
              placeholder="Short bio — 280 chars max"
              maxlength="280"
              rows="2"
              class="w-full mt-2 text-[13.5px] bg-white rounded-[10px] px-3 py-2 outline-none resize-none"
              style="border: 1px solid hsl({accentHue()} 40% 70%); color: hsl(222 47% 11%);"
            ></textarea>
            <div class="mt-2 flex flex-wrap gap-1.5">
              {#each ACCENTS as a}
                <button
                  type="button"
                  onclick={() => (draft.accent = a.key)}
                  class="h-7 px-2.5 rounded-full text-[11px] font-semibold cursor-pointer"
                  style="
                    background: {draft.accent === a.key ? `hsl(${a.hue} 80% 40%)` : 'white'};
                    color: {draft.accent === a.key ? 'white' : `hsl(${a.hue} 55% 25%)`};
                    border: 1px solid hsl({a.hue} 55% 70%);
                  "
                >
                  {a.label}
                </button>
              {/each}
            </div>
          {:else}
            <div class="text-[18px] sm:text-[20px] font-bold truncate" style="color: hsl(222 47% 11%);">
              {displayName()}
            </div>
            {#if $profile.bio}
              <p class="text-[13px] mt-0.5 leading-[1.45]" style="color: hsl(222 47% 11% / 0.7);">
                {$profile.bio}
              </p>
            {:else}
              <p class="text-[12.5px] mt-0.5 italic" style="color: hsl(222 47% 11% / 0.55);">
                No bio yet. Add one to make the profile yours.
              </p>
            {/if}
          {/if}
        </div>
        <div class="shrink-0">
          {#if editing}
            <div class="flex flex-col sm:flex-row gap-1.5">
              <Button size="sm" onclick={saveEdit}>Save</Button>
              <Button size="sm" variant="ghost" onclick={cancelEdit}>Cancel</Button>
            </div>
          {:else}
            <Button size="sm" variant="outline" onclick={startEdit}>
              <Icon name="pencil-simple" size={14} /> Edit
            </Button>
          {/if}
        </div>
      </div>

      <!-- Principal -->
      <div
        class="mt-4 sm:mt-5 rounded-[12px] p-3 sm:p-3.5 flex items-center gap-2.5"
        style="background: hsl(0 0% 100% / 0.55); border: 1px dashed hsl({accentHue()} 40% 50%);"
      >
        <Icon name="identification-card" size={16} style="color: hsl({accentHue()} 55% 30%); flex-shrink: 0;" />
        <div class="min-w-0 flex-1">
          <div class="text-[10.5px] font-semibold uppercase tracking-wide" style="color: hsl({accentHue()} 55% 30%);">
            Principal
          </div>
          <div class="font-mono text-[11.5px] sm:text-[12.5px] break-all" style="color: hsl(222 47% 11%);">
            {$principalText}
          </div>
        </div>
        <button
          type="button"
          onclick={copyPrincipal}
          aria-label="Copy principal"
          class="h-8 px-2.5 rounded-[8px] text-[11.5px] font-semibold cursor-pointer shrink-0 inline-flex items-center gap-1"
          style="background: hsl({accentHue()} 55% 30%); color: white; border: none;"
        >
          <Icon name={copied ? 'check' : 'copy'} size={13} />
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>
    </div>

    <!-- Session controls -->
    <div
      class="rounded-[14px] p-4 sm:p-5 mb-5"
      style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%);"
    >
      <div class="flex items-center gap-2 mb-1">
        <Icon name="shield-check" size={15} style="color: hsl(24 48% 28%);" />
        <h2 class="text-[13.5px] font-semibold" style="color: hsl(222 47% 11%);">Account</h2>
      </div>
      <p class="text-[12.5px] leading-[1.55] mb-3" style="color: hsl(215 16% 47%);">
        Signed in via Internet Identity. The same principal is derived on
        Banking.Brave thanks to the shared derivation origin — sign in there
        with the same II anchor to confirm the unified account.
      </p>
      <div class="flex flex-col sm:flex-row gap-2">
        <Button variant="outline" onclick={signOut} disabled={signingOut} class="flex-1 sm:flex-none">
          {#if signingOut}
            <Icon name="spinner-gap" size={14} /> Signing out…
          {:else}
            <Icon name="sign-out" size={14} /> Sign out
          {/if}
        </Button>
        <a
          href={bbLinks.mine}
          data-sveltekit-reload="on"
          rel="noopener"
          class="inline-flex items-center gap-1.5 h-9 px-3 rounded-[8px] text-[12.5px] font-medium no-underline"
          style="background: hsl(222 47% 11%); color: white;"
        >
          <Icon name="coin" size={13} /> Test same principal on Banking.Brave
          <Icon name="arrow-up-right" size={11} style="opacity: 0.7;" />
        </a>
      </div>
      <p class="text-[11.5px] mt-2.5 leading-[1.45]" style="color: hsl(215 16% 55%);">
        Tip: to verify, sign out here, sign back in with any II anchor, then
        open <a href={bbLinks.mine} data-sveltekit-reload="on" rel="noopener" style="color: hsl(38 85% 30%); text-decoration: underline;">Banking.Brave</a>
        and sign in with the same anchor. The principal on both pages should match.
      </p>
    </div>

    <!-- Wallet -->
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <Icon name="wallet" size={16} style="color: hsl(24 48% 28%);" />
        <h2 class="text-[15px] sm:text-[16px] font-bold" style="color: hsl(222 47% 11%);">Wallet</h2>
      </div>
      <button
        type="button"
        onclick={() => refresh()}
        disabled={loadingBalances}
        class="h-8 px-2.5 rounded-[8px] text-[12px] font-medium cursor-pointer inline-flex items-center gap-1.5"
        style="background: transparent; border: 1px solid hsl(26 30% 85%); color: hsl(222 47% 11%);"
      >
        <Icon name={loadingBalances ? 'spinner-gap' : 'arrows-clockwise'} size={13} />
        <span class="hidden sm:inline">{loadingBalances ? 'Refreshing' : 'Refresh'}</span>
      </button>
    </div>

    <!-- Portfolio total -->
    <div
      class="rounded-[16px] p-5 sm:p-6 mb-3"
      style="background: linear-gradient(135deg, hsl(222 47% 11%), hsl(222 47% 19%));
             color: white;
             box-shadow: 0 12px 30px -16px hsl(222 47% 11% / 0.55);"
    >
      <div class="text-[11px] uppercase tracking-wider mb-1.5" style="color: hsl(45 80% 78%); letter-spacing: 0.08em;">
        Portfolio value
      </div>
      <div class="flex items-baseline gap-2 flex-wrap">
        <div class="font-bold tabular-nums leading-none" style="font-size: clamp(28px, 7vw, 40px);">
          {formatUsd(totalUsd)}
        </div>
        {#if priceStale}
          <span class="text-[10.5px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded"
            style="background: hsl(45 95% 62% / 0.22); color: hsl(45 95% 78%);"
          >
            cached prices
          </span>
        {:else if $prices.source === 'live'}
          <span class="inline-flex items-center gap-1 text-[10.5px] font-semibold uppercase tracking-wider"
            style="color: hsl(112 55% 78%);"
          >
            <span class="w-[7px] h-[7px] rounded-full" style="background: hsl(112 60% 55%);"></span>
            live
          </span>
        {/if}
      </div>
      <div class="text-[11.5px] mt-1" style="color: hsl(26 30% 74%);">
        Across {tokenOrder.length} ICRC-1 tokens · prices via CoinGecko + GeckoTerminal (ICPSwap)
        {#if $prices.updatedAt}
          · updated {new Date($prices.updatedAt).toLocaleTimeString()}
        {/if}
      </div>
    </div>

    <!-- Token rows -->
    <div
      class="rounded-[16px] overflow-hidden"
      style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%);"
    >
      {#each tokenOrder as key, idx}
        {@const t = TOKENS[key]}
        {@const raw = balances[key]}
        {@const whole = rawToWhole(raw, t.decimals)}
        {@const unitPrice = $prices?.[key] ?? 0}
        {@const rowUsd = usdByKey[key] || 0}
        <div
          class="flex items-center gap-3 sm:gap-4 px-4 sm:px-5 py-3.5 sm:py-4"
          style="{idx > 0 ? 'border-top: 1px solid hsl(26 30% 92%);' : ''}"
        >
          <div
            class="w-10 h-10 rounded-full flex items-center justify-center shrink-0 overflow-hidden"
            style="background: hsl(42 80% 92%); border: 1px solid hsl(42 70% 78%);"
          >
            {#if t.logo}
              <img src={t.logo} alt="" class="w-[22px] h-[22px] object-contain" />
            {:else}
              <span class="text-[10.5px] font-bold" style="color: hsl(32 56% 25%);">
                {t.symbol.replace('$', '').slice(0, 3).toUpperCase()}
              </span>
            {/if}
          </div>

          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="font-semibold text-[14.5px]" style="color: hsl(222 47% 11%);">{t.symbol}</span>
              <span class="text-[11px] tabular-nums" style="color: hsl(215 16% 52%);">
                {formatUsd(unitPrice)}
              </span>
            </div>
            <div class="font-mono text-[10.5px] truncate" style="color: hsl(215 16% 55%);">
              {t.canister}
            </div>
          </div>

          <div class="text-right shrink-0">
            {#if loadingBalances && raw === undefined}
              <Icon name="spinner-gap" size={14} style="color: hsl(215 16% 47%);" />
            {:else}
              <div class="font-bold tabular-nums text-[15px] sm:text-[16px]" style="color: hsl(222 47% 11%);">
                {formatBalance(raw, t.decimals, t.decimals >= 8 ? 4 : 2)}
              </div>
              <div class="text-[11px] tabular-nums" style="color: hsl(215 16% 47%);">
                {raw === null ? 'lookup failed' : formatUsd(rowUsd)}
              </div>
            {/if}
          </div>

          <button
            type="button"
            onclick={() => openSend(key)}
            disabled={!raw || raw === 0n}
            aria-label={`Send ${t.symbol}`}
            title={!raw || raw === 0n ? 'No balance to send' : `Send ${t.symbol}`}
            class="h-10 w-10 shrink-0 rounded-[10px] cursor-pointer inline-flex items-center justify-center transition-opacity"
            style="background: hsl(222 47% 11%); color: white; border: none; opacity: {!raw || raw === 0n ? 0.35 : 1};"
          >
            <Icon name="paper-plane-tilt" size={14} />
          </button>
        </div>
      {/each}
    </div>

    <p class="text-[11.5px] text-center mt-3" style="color: hsl(215 16% 47%);">
      Balances queried directly from each ICRC-1 ledger canister. USD values refreshed every 60s.
      {#if refreshedAt}
        Wallet last refresh: {new Date(refreshedAt).toLocaleTimeString()}
      {/if}
    </p>

    <!-- Orders -->
    <div class="mt-7 flex items-center gap-2 mb-3">
      <Icon name="receipt" size={16} style="color: hsl(24 48% 28%);" />
      <h2 class="text-[15px] sm:text-[16px] font-bold" style="color: hsl(222 47% 11%);">Orders</h2>
    </div>
    <div
      class="rounded-[14px] overflow-hidden"
      style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%);"
    >
      {#if loadingOrders}
        <div class="px-4 py-5 text-center text-[13px]" style="color: hsl(215 16% 47%);">
          <Icon name="spinner-gap" size={14} /> Loading orders…
        </div>
      {:else if orders.length === 0}
        <div class="px-4 py-5 text-center text-[13px]" style="color: hsl(215 16% 47%);">
          No orders yet. <a href="/shop" style="color: hsl(38 85% 30%);">Shop</a> when you're ready.
        </div>
      {:else}
        {#each orders as o, i (o.id)}
          <div class="px-4 sm:px-5 py-3.5 text-[13px]" style="{i > 0 ? 'border-top: 1px solid hsl(26 30% 92%);' : ''}">
            <div class="flex items-center justify-between gap-2 flex-wrap">
              <div class="min-w-0">
                <div class="font-semibold" style="color: hsl(222 47% 11%);">
                  Order #{o.id} · {o.totalNanas.toLocaleString()} $nanas
                </div>
                <div class="text-[11.5px]" style="color: hsl(215 16% 47%);">
                  {new Date(o.createdAt).toLocaleString()}
                  {#if o.paidBlock != null}
                    · <span class="font-mono">block #{o.paidBlock}</span>
                  {/if}
                </div>
              </div>
              <span
                class="inline-flex items-center text-[10.5px] font-semibold uppercase px-2 py-0.5 rounded-full"
                style="background: {ORDER_COLOR[o.status] || 'hsl(26 30% 92%)'}; color: hsl(222 47% 11%);"
              >
                {o.status}
              </span>
            </div>
            <div class="mt-1 text-[11.5px]" style="color: hsl(215 25% 25%);">
              {o.items.map((it) => `${it.qty}× ${it.slug}`).join(' · ')}
            </div>
          </div>
        {/each}
      {/if}
    </div>

    <!-- On-Chain Audit Trail -->
    <div id="audit" class="mt-8 rounded-[16px] p-5 sm:p-6"
      style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%);">
      <AuditTrail
        principalId={$principalText ? `${$principalText.slice(0, 12)}…${$principalText.slice(-5)}` : ''}
        events={auditEvents}
      />
    </div>

    <!-- Quick actions -->
    <div class="mt-7 grid grid-cols-1 sm:grid-cols-2 gap-3">
      <a
        href={bbLinks.mine}
        data-sveltekit-reload="on"
        rel="noopener"
        class="rounded-[12px] p-4 flex items-center gap-3 no-underline"
        style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%); color: hsl(222 47% 11%);"
      >
        <div
          class="w-10 h-10 rounded-[10px] flex items-center justify-center shrink-0"
          style="background: hsl(42 80% 92%); color: hsl(38 85% 30%);"
        >
          <Icon name="coin" size={18} />
        </div>
        <div class="flex-1 min-w-0">
          <div class="font-semibold text-[13.5px]">Mine on Banking.Brave</div>
          <div class="text-[11.5px]" style="color: hsl(215 16% 47%);">Refine UNI into sGLDT</div>
        </div>
        <Icon name="arrow-up-right" size={14} style="color: hsl(215 16% 47%);" />
      </a>
      <a
        href="/leaderboard"
        class="rounded-[12px] p-4 flex items-center gap-3 no-underline"
        style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%); color: hsl(222 47% 11%);"
      >
        <div
          class="w-10 h-10 rounded-[10px] flex items-center justify-center shrink-0"
          style="background: hsl(45 80% 92%); color: hsl(32 56% 25%);"
        >
          <Icon name="trophy" size={18} />
        </div>
        <div class="flex-1 min-w-0">
          <div class="font-semibold text-[13.5px]">See the leaderboard</div>
          <div class="text-[11.5px]" style="color: hsl(215 16% 47%);">Burn $nanas to climb</div>
        </div>
        <Icon name="arrow-right" size={14} style="color: hsl(215 16% 47%);" />
      </a>
    </div>
  {/if}
</section>

<SendTokenModal
  bind:open={sendOpen}
  tokenKey={sendTokenKey}
  rawBalance={balances[sendTokenKey]}
  onSent={handleSent}
/>
