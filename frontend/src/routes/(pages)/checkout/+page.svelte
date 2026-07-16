<svelte:options runes={true} />

<script>
  import { goto } from '$app/navigation';
  import { cart, cartTotal, showToast } from '$lib/stores/cart.js';
  import { productImage, usd } from '$lib/data/products.js';
  import { refreshNanasBalance } from '$lib/stores/blog.js';
  import { transfer } from '$lib/api/icrc1.js';
  import { recordOrder, getTreasury } from '$lib/api/store.js';
  import { createStripeSession, savePendingStripeOrder } from '$lib/api/stripe.js';
  import { isAuthenticated, authStatus, login, principalText } from '$lib/stores/auth.js';
  import { nanasBalance } from '$lib/stores/blog.js';
  import NanasCoin from '$lib/components/NanasCoin.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import Button from '$lib/components/Button.svelte';
  import Input from '$lib/components/Input.svelte';

  // ── Form state ────────────────────────────────────────────────────────────
  let form = $state({ name: '', email: '', street: '', city: '', postal: '' });

  // ── Payment method ────────────────────────────────────────────────────────
  /** 'nanas' | 'card' */
  let payMethod = $state('nanas');

  // ── Transaction state ─────────────────────────────────────────────────────
  let phase = $state('idle'); // idle | transferring | recording | redirecting | done | error
  let error = $state(null);
  let blockIndex = $state(null);
  let orderId = $state(null);
  let treasury = $state(null);

  async function ensureTreasury() {
    if (treasury) return treasury;
    treasury = await getTreasury();
    return treasury;
  }

  // ── Shared validation ─────────────────────────────────────────────────────
  function validateShipping() {
    if ($cart.length === 0) return 'Cart is empty.';
    for (const field of ['name', 'email', 'street', 'city', 'postal']) {
      if (!form[field]?.trim()) return `Shipping ${field} is required.`;
    }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim())) return 'Enter a valid email.';
    return null;
  }

  // ── $nanas payment ────────────────────────────────────────────────────────
  async function payWithNanas(e) {
    e.preventDefault();
    error = null;
    if (!$isAuthenticated) { error = 'Sign in with Internet Identity to pay with $nanas.'; return; }
    const bad = validateShipping();
    if (bad) { error = bad; return; }

    const treasuryPrincipal = await ensureTreasury();
    if (!treasuryPrincipal) {
      error = 'Treasury principal not configured. Ask an admin to set one on /admin/store.';
      return;
    }

    // 1) Move $nanas from buyer → treasury via ICRC-1
    phase = 'transferring';
    const transferRes = await transfer({
      tokenKey: 'nanas',
      toPrincipalText: treasuryPrincipal,
      amount: $cartTotal,
      memoText: `cafreso-order-${Date.now().toString(16)}`
    });
    if (transferRes.err) { phase = 'error'; error = transferRes.err; return; }
    blockIndex = transferRes.ok;

    // 2) Record order on the store canister with block proof
    phase = 'recording';
    const orderRes = await recordOrder({
      items: $cart.map((it) => ({ slug: it.slug, qty: it.qty, priceNanas: it.price })),
      shipping: {
        name: form.name.trim(), email: form.email.trim(),
        street: form.street.trim(), city: form.city.trim(), postal: form.postal.trim()
      },
      paidBlock: blockIndex
    });
    if (orderRes.err) {
      phase = 'error';
      error = `Payment confirmed (block #${blockIndex}) but order logging failed: ${orderRes.err}. Contact support with this block number.`;
      return;
    }

    orderId = orderRes.ok.id;
    phase = 'done';
    cart.clear();
    refreshNanasBalance();
    showToast(`Order #${orderId} submitted · block #${blockIndex}`);
    setTimeout(() => goto(`/success?order=${orderId}&block=${blockIndex}`), 900);
  }

  // ── Card (Stripe) payment ─────────────────────────────────────────────────
  async function payWithCard(e) {
    e.preventDefault();
    error = null;
    const bad = validateShipping();
    if (bad) { error = bad; return; }

    phase = 'redirecting';

    // Generate a local order reference that survives the Stripe redirect
    const pendingOrderId = `card-${Date.now().toString(16)}`;
    const shipping = {
      name: form.name.trim(), email: form.email.trim(),
      street: form.street.trim(), city: form.city.trim(), postal: form.postal.trim()
    };
    const items = $cart.map(it => ({ slug: it.slug, name: it.name, price: usd(it.price * it.qty), qty: it.qty }));

    // Stash pending order so the success page can record it after Stripe redirects back
    savePendingStripeOrder({ orderId: pendingOrderId, items, shipping });

    const origin = window.location.origin;
    const result = await createStripeSession({
      items,
      shipping,
      orderId: pendingOrderId,
      successUrl: `${origin}/success?order=${pendingOrderId}&method=card`,
      cancelUrl:  `${origin}/checkout`
    });

    if (result.error) {
      phase = 'error';
      error = `Payment setup failed: ${result.error}`;
      return;
    }

    // Hand off to Stripe's hosted checkout page
    window.location.href = result.url;
  }

  const busy = $derived(phase === 'transferring' || phase === 'recording' || phase === 'redirecting');
  const hasSufficientNanas = $derived($nanasBalance >= $cartTotal);
</script>

<svelte:head><title>Checkout · Cafreso</title></svelte:head>

<div class="mx-auto px-4 py-8" style="max-width: 720px;">
  <div class="text-center">
    <div class="inline-flex items-center gap-2 text-[13px] font-medium mb-2" style="color: hsl(var(--pg-eyebrow));">
      <Icon name="shopping-cart" size={14} /> Checkout
    </div>
    <h1 class="text-[28px] sm:text-[32px] font-bold">Your order</h1>
  </div>

  <!-- ── Empty cart ─────────────────────────────────────────────────────── -->
  {#if $cart.length === 0 && phase !== 'done'}
    <div class="rounded-[14px] p-6 sm:p-8 mt-6 text-center"
      style="background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));">
      <Icon name="shopping-cart-simple" size={24} style="color: hsl(var(--pg-fg-muted));" />
      <p class="mt-3 text-[14px]" style="color: hsl(var(--pg-fg-muted));">Your cart is empty.</p>
      <div class="mt-4"><Button on:click={() => goto('/shop')}>Back to shop</Button></div>
    </div>

  {:else}
    <!-- ── Cart summary ──────────────────────────────────────────────────── -->
    <div class="flex flex-col gap-2 mt-6 mb-5">
      {#each $cart as it}
        <div class="flex gap-3 p-3 items-center rounded-[12px]"
          style="border: 1px solid hsl(var(--pg-border)); background: hsl(var(--pg-elevated));">
          <img src={productImage(it.img)} alt={it.name || 'Product image'} class="w-12 h-12 object-contain" loading="lazy" decoding="async" />
          <div class="flex-1 min-w-0">
            <div class="font-medium truncate">{it.name}</div>
            <div class="text-[12.5px]" style="color: hsl(var(--pg-fg-muted));">Qty {it.qty}</div>
          </div>
          <div class="inline-flex items-center gap-1.5 tabular-nums">
            {(it.price * it.qty).toLocaleString()}
            <img src="/assets/nanas-coin.png" alt="" class="w-[18px]" />
          </div>
        </div>
      {/each}
    </div>

    <!-- ── Payment method picker ─────────────────────────────────────────── -->
    <div class="mb-4">
      <div class="text-[11.5px] font-semibold uppercase mb-2" style="letter-spacing: 0.1em; color: hsl(var(--pg-fg-muted));">
        Payment method
      </div>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <!-- $nanas option -->
        <button
          type="button"
          on:click={() => (payMethod = 'nanas')}
          class="flex items-center gap-2.5 p-3.5 rounded-[12px] cursor-pointer border-none text-left"
          style="
            background: {payMethod === 'nanas' ? 'hsl(45 80% 94%)' : 'hsl(var(--pg-elevated))'};
            border: 2px solid {payMethod === 'nanas' ? 'hsl(45 75% 65%)' : 'hsl(var(--pg-border))'};
            transition: all .2s;
          "
        >
          <NanasCoin size={20} />
          <div>
            <div class="font-semibold text-[13.5px]">Pay with $nanas</div>
            <div class="text-[11.5px]" style="color: hsl(var(--pg-fg-muted));">On-chain · ICRC-1</div>
          </div>
          {#if payMethod === 'nanas'}
            <Icon name="check-circle" size={16} style="color: hsl(112 43% 45%); margin-left: auto;" weight="fill" />
          {/if}
        </button>

        <!-- Card option -->
        <button
          type="button"
          on:click={() => (payMethod = 'card')}
          class="flex items-center gap-2.5 p-3.5 rounded-[12px] cursor-pointer border-none text-left"
          style="
            background: {payMethod === 'card' ? 'hsl(222 47% 96%)' : 'hsl(var(--pg-elevated))'};
            border: 2px solid {payMethod === 'card' ? 'hsl(222 47% 60%)' : 'hsl(var(--pg-border))'};
            transition: all .2s;
          "
        >
          <div class="inline-flex items-center justify-center rounded-[8px]"
            style="width: 32px; height: 32px; background: hsl(var(--pg-solid)); flex-shrink: 0;">
            <Icon name="credit-card" size={17} style="color: hsl(var(--pg-solid-fg));" />
          </div>
          <div>
            <div class="font-semibold text-[13.5px]">Pay with card</div>
            <div class="text-[11.5px]" style="color: hsl(var(--pg-fg-muted));">Stripe · USD</div>
          </div>
          {#if payMethod === 'card'}
            <Icon name="check-circle" size={16} style="color: hsl(222 47% 50%); margin-left: auto;" weight="fill" />
          {/if}
        </button>
      </div>
    </div>

    <!-- ── Shipping form ──────────────────────────────────────────────────── -->
    <form
      on:submit={payMethod === 'nanas' ? payWithNanas : payWithCard}
      class="flex flex-col gap-3 p-5 rounded-[14px]"
      style="border: 1px solid hsl(var(--pg-border)); background: hsl(var(--pg-elevated));"
    >
      <div class="text-center mb-1">
        <span class="text-[20px] sm:text-[22px] font-bold">Shipping address</span>
      </div>

      <Input label="Full name" bind:value={form.name} />
      <Input label="Email" bind:value={form.email} />
      <Input label="Street address" bind:value={form.street} />
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Input label="City" bind:value={form.city} />
        <Input label="Postal code" bind:value={form.postal} />
      </div>

      <!-- ── $nanas payment summary ──────────────────────────────────────── -->
      {#if payMethod === 'nanas'}
        {#if !$isAuthenticated}
          <div class="rounded-[12px] p-4 mt-1 text-center"
            style="background: hsl(45 80% 94%); border: 1px solid hsl(45 75% 75%);">
            <Icon name="fingerprint" size={22} style="color: hsl(32 56% 25%);" />
            <p class="text-[13px] mt-1.5 mb-2.5" style="color: hsl(32 40% 28%);">
              Sign in with Internet Identity to pay with $nanas
            </p>
            <Button type="button" on:click={login} disabled={$authStatus === 'logging-in'}>
              <Icon name="fingerprint" size={15} /> Sign in
            </Button>
          </div>
        {:else}
          <div class="flex items-center gap-2.5 p-3.5 rounded-[12px] text-[13.5px] mt-1"
            style="background: hsl(45 95% 62% / 0.15); border: 1px solid hsl(45 75% 75%);">
            <NanasCoin size={26} />
            <div class="flex-1 min-w-0">
              <div>Pay <b class="tabular-nums">{$cartTotal.toLocaleString()} $nanas</b></div>
              <div class="text-[11.5px]" style="color: hsl(var(--pg-fg-muted));">
                ≈ ${usd($cartTotal)} USD · settles on the ICRC-1 ledger
                {#if !hasSufficientNanas}
                  <span style="color: hsl(0 70% 40%);"> · Insufficient balance</span>
                {/if}
              </div>
            </div>
            {#if hasSufficientNanas}
              <Icon name="check-circle" size={18} style="color: hsl(112 43% 45%);" weight="fill" />
            {:else}
              <Icon name="warning" size={18} style="color: hsl(0 70% 50%);" weight="fill" />
            {/if}
          </div>
        {/if}
      {/if}

      <!-- ── Card payment summary ────────────────────────────────────────── -->
      {#if payMethod === 'card'}
        <div class="flex items-center gap-2.5 p-3.5 rounded-[12px] text-[13.5px] mt-1"
          style="background: hsl(222 47% 97%); border: 1px solid hsl(222 47% 85%);">
          <Icon name="credit-card" size={22} style="color: hsl(222 47% 40%);" />
          <div class="flex-1 min-w-0">
            <div>Pay <b>${usd($cartTotal)} USD</b> via Stripe</div>
            <div class="text-[11.5px]" style="color: hsl(var(--pg-fg-muted));">
              Secure card checkout · you'll be redirected to Stripe
            </div>
          </div>
          <!-- Stripe logo / trust badge -->
          <svg width="42" height="18" viewBox="0 0 60 25" fill="none" style="flex-shrink:0; opacity: 0.7;">
            <path d="M27.5 8.2c0-1.3 1-1.8 2.7-1.8 2.4 0 5.5.7 7.9 2V2.5C35.7.9 32.8 0 29.2 0 22.5 0 18 3.4 18 9c0 8.7 12 7.3 12 11.1 0 1.5-1.3 2-3.1 2-2.7 0-6.1-.9-8.8-2.5v5.9c3 1.3 6 1.8 8.8 1.8 6.9 0 11.6-3.2 11.6-8.9-.1-9.5-12-7.8-12-10.2zM0 24.6h6.5V.4H0v24.2zm49.3-16.4c0-1.3.9-1.8 2.4-1.8 2.1 0 4.9.7 7 2V3.2c-2-.8-4-.9-7-.9-6 0-10 3.1-10 8.6 0 8.3 11.4 7 11.4 10.7 0 1.5-1.1 2-2.9 2-2.5 0-5.5-.9-7.9-2.3v5.4c2.7 1.2 5.5 1.7 7.9 1.7 6.2 0 10.5-3 10.5-8.5-.1-9-11.4-7.4-11.4-9.7z" fill="hsl(222 47% 35%)"/>
          </svg>
        </div>
        <p class="text-[11.5px] text-center" style="color: hsl(var(--pg-fg-muted));">
          No account required. Visa, Mastercard, Amex accepted. Order is recorded on-chain after payment.
        </p>
      {/if}

      <!-- ── Error ──────────────────────────────────────────────────────── -->
      {#if error}
        <div class="rounded-[10px] px-3 py-2 text-[13px] flex items-start gap-2"
          style="background: hsl(0 70% 96%); color: hsl(0 70% 30%); border: 1px solid hsl(0 70% 85%);">
          <Icon name="warning" size={14} />
          <span>{error}</span>
        </div>
      {/if}

      <!-- ── Actions ───────────────────────────────────────────────────── -->
      <div class="flex justify-center gap-2 mt-2 flex-col sm:flex-row">
        <Button variant="outline" type="button" on:click={() => goto('/shop')} disabled={busy}>
          Cancel
        </Button>

        {#if payMethod === 'nanas'}
          <Button
            type="submit"
            disabled={busy || !$isAuthenticated || !hasSufficientNanas}
          >
            {#if phase === 'transferring'}
              <Icon name="spinner-gap" size={15} class="spin" /> Transferring $nanas…
            {:else if phase === 'recording'}
              <Icon name="spinner-gap" size={15} class="spin" /> Recording order…
            {:else if phase === 'done'}
              <Icon name="check" size={15} /> Confirmed
            {:else}
              <NanasCoin size={15} /> Pay {$cartTotal.toLocaleString()} $nanas
            {/if}
          </Button>
        {:else}
          <Button type="submit" disabled={busy}>
            {#if phase === 'redirecting'}
              <Icon name="spinner-gap" size={15} class="spin" /> Opening Stripe…
            {:else}
              <Icon name="credit-card" size={15} /> Pay ${usd($cartTotal)} with card
            {/if}
          </Button>
        {/if}
      </div>

      <p class="text-[11.5px] mt-1 text-center" style="color: hsl(var(--pg-fg-muted));">
        {#if payMethod === 'nanas'}
          Funds move directly to the treasury principal — this dapp never custodies them.
        {:else}
          Card payment processed by Stripe. Order is recorded on the ICP store canister after confirmation.
        {/if}
      </p>
    </form>
  {/if}
</div>
