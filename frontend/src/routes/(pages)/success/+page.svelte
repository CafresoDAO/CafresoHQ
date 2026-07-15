<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import Button from '$lib/components/Button.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import { goto } from '$app/navigation';
  import { cart, showToast } from '$lib/stores/cart.js';
  import { recordOrder } from '$lib/api/store.js';
  import { consumePendingStripeOrder } from '$lib/api/stripe.js';
  import { isAuthenticated } from '$lib/stores/auth.js';

  let orderId  = $derived($page.url.searchParams.get('order'));
  let block    = $derived($page.url.searchParams.get('block'));
  let method   = $derived($page.url.searchParams.get('method')); // 'card' | null

  let cardRecording = $state('idle'); // idle | recording | done | error
  let cardError = $state(null);

  onMount(async () => {
    if (method !== 'card') return;

    // Stripe redirected back — read the pending order from sessionStorage,
    // record it on the store canister under the authenticated identity,
    // then clear the cart.
    const pending = consumePendingStripeOrder();
    if (!pending) return; // already recorded or sessionStorage was unavailable

    cardRecording = 'recording';
    const orderRes = await recordOrder({
      items: pending.items.map(it => ({
        slug: it.slug,
        qty: it.qty,
        priceNanas: 0   // card order — no $nanas price
      })),
      shipping: pending.shipping,
      paidBlock: BigInt(0), // 0 = card payment sentinel
      paymentMethod: 'stripe'
    });

    if (orderRes?.err) {
      cardRecording = 'error';
      cardError = orderRes.err;
    } else {
      cardRecording = 'done';
      cart.clear();
      showToast('Card payment confirmed · order recorded on-chain');
    }
  });
</script>

<svelte:head><title>Order submitted · Cafreso</title></svelte:head>

<div class="mx-auto text-center px-6 py-16 sm:py-20" style="max-width: 620px;">
  <img src="/assets/cafreso-roaster.webp" alt="" class="mx-auto" style="width: 160px; opacity: 0.9;" />

  <h1 class="mt-4 mb-2 font-extrabold" style="font-size: clamp(26px, 6vw, 36px);">
    {method === 'card' ? 'Payment confirmed' : 'Order submitted'}
  </h1>

  <p class="m-0 mb-6 text-[14.5px]" style="color: hsl(215 16% 47%);">
    {#if method === 'card'}
      Your card was charged. The farm team takes it from here — expect a shipping email within two business days.
    {:else}
      Your $nanas are in the treasury. The farm team takes it from here — expect a shipping email within two business days.
    {/if}
  </p>

  <!-- Card recording status -->
  {#if method === 'card' && cardRecording !== 'idle'}
    <div
      class="rounded-[12px] px-4 py-3 mb-5 text-[13px] inline-flex items-center gap-2"
      style="
        background: {cardRecording === 'error' ? 'hsl(0 70% 96%)' : 'hsl(112 50% 95%)'};
        border: 1px solid {cardRecording === 'error' ? 'hsl(0 70% 82%)' : 'hsl(112 43% 75%)'};
        color: {cardRecording === 'error' ? 'hsl(0 70% 30%)' : 'hsl(112 43% 22%)'};
      "
    >
      {#if cardRecording === 'recording'}
        <Icon name="spinner-gap" size={14} class="spin" /> Recording order on-chain…
      {:else if cardRecording === 'done'}
        <Icon name="check-circle" size={14} weight="fill" /> Order recorded on the ICP store canister
      {:else if cardRecording === 'error'}
        <Icon name="warning" size={14} /> Could not record on-chain: {cardError}
      {/if}
    </div>
  {/if}

  <!-- Order receipt -->
  {#if orderId || block}
    <div
      class="rounded-[14px] p-4 sm:p-5 mb-6 text-left inline-block mx-auto"
      style="background: hsl(26 40% 98%); border: 1px solid hsl(26 30% 88%); min-width: min(100%, 360px);"
    >
      {#if orderId}
        <div class="flex items-center gap-2 mb-2 text-[12.5px]" style="color: hsl(215 16% 47%);">
          <Icon name="receipt" size={13} />
          <span>Order</span>
          <span class="font-mono" style="color: hsl(222 47% 11%);">#{orderId}</span>
        </div>
      {/if}
      {#if block && method !== 'card'}
        <div class="flex items-center gap-2 text-[12.5px]" style="color: hsl(215 16% 47%);">
          <Icon name="link" size={13} />
          <span>$nanas ledger block</span>
          <span class="font-mono" style="color: hsl(222 47% 11%);">#{block}</span>
        </div>
      {/if}
      {#if method === 'card'}
        <div class="flex items-center gap-2 text-[12.5px]" style="color: hsl(215 16% 47%);">
          <Icon name="credit-card" size={13} />
          <span>Paid via Stripe</span>
        </div>
      {/if}
    </div>
  {/if}

  <div class="flex flex-col sm:flex-row gap-2 justify-center">
    <Button on:click={() => goto('/shop')}>Back to shop</Button>
    <Button variant="outline" on:click={() => goto('/profile')}>
      <Icon name="user-circle" size={14} /> View wallet
    </Button>
  </div>
</div>
