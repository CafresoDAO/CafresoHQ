<script>
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import { isAuthenticated, principalText, login } from '$lib/stores/auth.js';
  import { prices, startPrices } from '$lib/stores/prices.js';
  import {
    PLANS, getPlan, subscribeWithIcp, subscribeWithCard, notifyFleet, usdToIcp
  } from '$lib/api/hqPlans.js';

  // Display order + per-plan blurbs (logic lives in hqPlans.js).
  const TIERS = [
    { id: 'free',      tagline: 'Try it free', perks: [
        'Your own private HQ container', 'Bring your own free OpenRouter key',
        'Lite agent capability', 'Auto-sleeps after 20 min idle' ] },
    { id: 'pro',       tagline: 'For daily use', perks: [
        'Everything in Free', 'Full agent toolset', 'Model quick-switch (Nemotron, GPT-OSS, …)',
        'Stays warm 60 min', 'Vault to 5 GB' ], featured: true },
    { id: 'always-on', tagline: 'Always ready', perks: [
        'Everything in Pro', 'Never sleeps — instant every time',
        'Priority capacity', 'Email support' ] },
  ];

  let current = 'free';
  let activeUntil = null;
  let busy = '';        // plan id currently processing
  let msg = null;       // { kind: 'ok'|'err', text }
  let loading = true;

  $: icpUsd = Number($prices?.ICP) || 0;
  function icpFor(usd) {
    const v = usdToIcp(usd);
    return v == null ? null : v;
  }

  async function refresh() {
    loading = true;
    if ($isAuthenticated) {
      const p = await getPlan();
      current = p.plan; activeUntil = p.activeUntil;
    }
    loading = false;
  }

  // Stripe return: ?paid=<plan> → record the order on-chain + notify the fleet.
  // (The pending order was stashed in sessionStorage before the redirect.)
  async function handleStripeReturn() {
    const params = new URLSearchParams(window.location.search);
    const paidPlan = params.get('paid');
    if (!paidPlan || !PLANS[paidPlan]) return;
    busy = paidPlan;
    try {
      const { consumePendingStripeOrder } = await import('$lib/api/stripe.js');
      const { recordOrder } = await import('$lib/api/store.js');
      consumePendingStripeOrder();  // clear it
      const rec = await recordOrder({
        items: [{ slug: PLANS[paidPlan].slug, qty: 1, priceNanas: 0, price: PLANS[paidPlan].usd }],
        shipping: {}, paidBlock: 0, paymentMethod: 'stripe',
      });
      if (!rec.err) {
        const applied = await notifyFleet(rec.ok?.id);
        msg = applied.ok
          ? { kind: 'ok', text: `${PLANS[paidPlan].label} active! Your HQ is updating (~10s).` }
          : { kind: 'ok', text: `Payment recorded. Your ${PLANS[paidPlan].label} plan activates once the card charge is confirmed on-chain.` };
      } else {
        msg = { kind: 'err', text: `Payment ok but recording failed: ${rec.err}` };
      }
      // strip the query param so a refresh doesn't double-record
      window.history.replaceState({}, '', '/hq/plans');
      await refresh();
    } finally { busy = ''; }
  }

  onMount(() => { startPrices(); refresh(); handleStripeReturn(); });
  $: if ($isAuthenticated) { /* re-check when auth flips */ }

  async function payIcp(planId) {
    msg = null; busy = planId;
    try {
      const r = await subscribeWithIcp(planId);
      if (r.err) { msg = { kind: 'err', text: r.err }; return; }
      const applied = await notifyFleet(r.order?.id);
      msg = applied.ok
        ? { kind: 'ok', text: `Subscribed to ${PLANS[planId].label}! Your HQ is updating (~10s).` }
        : { kind: 'ok', text: `Paid! ${PLANS[planId].label} will apply to your HQ momentarily.${applied.reason ? '' : ''}` };
      await refresh();
    } finally { busy = ''; }
  }

  async function payCard(planId) {
    msg = null; busy = planId;
    try {
      const origin = window.location.origin;
      const r = await subscribeWithCard(planId, {
        successUrl: `${origin}/hq/plans?paid=${planId}`,
        cancelUrl: `${origin}/hq/plans`,
      });
      if (r.err) { msg = { kind: 'err', text: r.err }; busy = ''; }
      // on success the browser redirects to Stripe
    } catch (e) { msg = { kind: 'err', text: String(e) }; busy = ''; }
  }
</script>

<section class="space-y-5">
  <header class="card p-6 sm:p-8">
    <div class="page-kicker">CafresoAI / Plans</div>
    <h1 class="page-title mt-4">Choose your HQ<span class="text-brand-500">.</span></h1>
    <p class="mt-4 max-w-2xl text-sm leading-6 text-ink-300">
      Your HQ runs in a private container. Pay in <strong>ICP</strong> or by card —
      your plan controls how powerful and how always-on it is.
      {#if icpUsd > 0}<span class="text-ink-400"> (ICP ≈ ${icpUsd.toFixed(2)})</span>{/if}
    </p>
    {#if $isAuthenticated && !loading}
      <p class="mt-3 text-sm">
        Current plan:
        <span class="pill-ok">{PLANS[current]?.label || current}</span>
        {#if activeUntil}<span class="text-ink-400 ml-2">renews {new Date(activeUntil).toLocaleDateString()}</span>{/if}
      </p>
    {/if}
  </header>

  {#if msg}
    <div class="card p-4 text-sm {msg.kind === 'ok' ? 'text-emerald-300' : 'text-rose-300'}">{msg.text}</div>
  {/if}

  {#if !$isAuthenticated}
    <div class="card p-5 text-sm leading-6 text-ink-300">
      <button class="btn-primary" on:click={login}>Sign in</button>
      to choose a plan — your identity is your account and your wallet.
    </div>
  {:else}
    <div class="grid gap-4 md:grid-cols-3">
      {#each TIERS as t}
        {@const plan = PLANS[t.id]}
        {@const isCurrent = current === t.id}
        {@const icp = icpFor(plan.usd)}
        <div class="card p-5 flex flex-col {t.featured ? 'ring-2 ring-brand-500' : ''}">
          <div class="page-kicker">{t.tagline}</div>
          <div class="mt-2 flex items-baseline gap-2">
            <span class="text-2xl font-semibold">{plan.label}</span>
            {#if t.featured}<span class="pill-warn">Popular</span>{/if}
          </div>
          <div class="mt-2 text-lg">
            {#if plan.usd === 0}
              Free
            {:else}
              ${plan.usd}<span class="text-ink-400 text-sm">/mo</span>
              {#if icp != null}<div class="text-xs text-ink-400">≈ {icp.toFixed(3)} ICP</div>{/if}
            {/if}
          </div>
          <ul class="mt-4 space-y-1.5 text-sm text-ink-300 flex-1">
            {#each t.perks as perk}<li>• {perk}</li>{/each}
          </ul>
          <div class="mt-5 space-y-2">
            {#if isCurrent}
              <button class="btn-ghost w-full" disabled>Current plan</button>
            {:else if plan.usd === 0}
              <span class="text-xs text-ink-400">Default — no payment needed</span>
            {:else}
              <button class="btn-primary w-full" disabled={busy === t.id}
                      on:click={() => payIcp(t.id)}>
                {busy === t.id ? 'Processing…' : `Pay with ICP${icp != null ? ` (${icp.toFixed(3)})` : ''}`}
              </button>
              <button class="btn-ghost w-full" disabled={busy === t.id}
                      on:click={() => payCard(t.id)}>
                Pay by card
              </button>
            {/if}
          </div>
        </div>
      {/each}
    </div>
    <p class="text-xs text-ink-400">
      Paid in ICP from your signed-in wallet, recorded on-chain. $nanas payment coming soon.
    </p>
  {/if}
</section>
