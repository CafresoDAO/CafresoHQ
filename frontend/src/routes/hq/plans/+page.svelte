<script>
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import { isAuthenticated, principalText, login } from '$lib/stores/auth.js';
  import { prices, startPrices } from '$lib/stores/prices.js';
  import {
    PLANS, getPlan, subscribeWithIcp, subscribeWithCard, notifyFleet, usdToIcp
  } from '$lib/api/hqPlans.js';
  import { getPlanPriceUsdCents } from '$lib/api/store.js';

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

  // Card payments stay hidden until the Stripe webhook → on-chain confirmOrder
  // chain is live (a card charge can't activate a plan without it — mintPlanToken
  // only accepts orders the ledger says are paid). Flip PUBLIC_CARD_PAYMENTS=on
  // once the worker webhook is deployed and verified in test mode.
  const CARD_ENABLED = import.meta.env?.PUBLIC_CARD_PAYMENTS === 'on';

  let current = 'free';
  let activeUntil = null;
  let busy = '';        // plan id currently processing
  let msg = null;       // { kind: 'ok'|'err', text }
  let loading = true;
  let priced = {};      // plan id → true once the canister has a USD price set
  let pendingApplyOrderId = null;  // set when an order is PAID but fleet activation failed

  $: icpUsd = Number($prices?.ICP) || 0;
  // Live ICP estimate for a USD price (display only — the canister charges the
  // exact live-rate amount via XRC at purchase). null until the rate loads.
  function icpFor(usd) {
    const v = usdToIcp(usd);
    return v == null ? null : v;
  }

  async function loadPriced() {
    const next = {};
    for (const t of TIERS) {
      const plan = PLANS[t.id];
      if (!plan || plan.usd <= 0) continue;
      try {
        const cents = await getPlanPriceUsdCents(plan.slug);   // BigInt cents | null
        next[t.id] = cents != null;
      } catch (_) { next[t.id] = false; }
    }
    priced = next;
  }

  async function refresh() {
    loading = true;
    if ($isAuthenticated) {
      const p = await getPlan();
      current = p.plan; activeUntil = p.activeUntil;
    }
    await loadPriced();
    loading = false;
  }

  // Stripe card return: ?paid=<plan>&order=<id>. The order was already recorded
  // PENDING before redirect; the Stripe webhook → confirmCardOrder flips it to
  // "paid". We poll until that lands, then apply the plan. NO recordOrder here
  // (that was the old double-record bug) and no auto re-apply on every load.
  let handledReturn = false;
  // waitForOrderPaid polls for up to 90s — without this, navigating away from
  // /hq/plans mid-confirmation leaves it polling in the background for the
  // full timeout for no reason. Aborted on unmount.
  const stripeReturnAbort = new AbortController();
  async function handleStripeReturn() {
    if (handledReturn) return;
    const params = new URLSearchParams(window.location.search);
    const paidPlan = params.get('paid');
    const orderParam = params.get('order');
    if (!paidPlan || !PLANS[paidPlan] || !orderParam) return;
    handledReturn = true;
    const icOrderId = Number(orderParam);
    // Strip the params immediately so a refresh can't re-enter.
    window.history.replaceState({}, '', '/hq/plans');
    busy = paidPlan; pendingApplyOrderId = null;
    msg = { kind: 'warn', text: `Confirming your ${PLANS[paidPlan].label} card payment on-chain…` };
    try {
      const { waitForOrderPaid } = await import('$lib/api/hqPlans.js');
      const paid = await waitForOrderPaid(icOrderId, { pollMs: 3000, timeoutMs: 90000, signal: stripeReturnAbort.signal });
      if (stripeReturnAbort.signal.aborted) return;
      if (paid) {
        const applied = await notifyFleet(icOrderId);
        if (applied.ok) {
          msg = { kind: 'ok', text: `${PLANS[paidPlan].label} active! Your HQ is updating (~10s).` };
        } else {
          pendingApplyOrderId = icOrderId;
          msg = { kind: 'warn', text: `Payment confirmed, but activating your HQ didn't finish. Use “Apply plan” to retry — you won't be charged again.` };
        }
      } else {
        // Webhook hasn't landed yet (it retries up to ~3 days). Plan activates
        // automatically; offer a manual retry.
        pendingApplyOrderId = icOrderId;
        msg = { kind: 'warn', text: `Payment received — still confirming on-chain. Your ${PLANS[paidPlan].label} plan activates automatically; use “Apply plan” to retry.` };
      }
      if (!stripeReturnAbort.signal.aborted) await refresh();
    } finally { if (!stripeReturnAbort.signal.aborted) busy = ''; }
  }

  onMount(() => { startPrices(); refresh(); handleStripeReturn(); });
  onDestroy(() => stripeReturnAbort.abort());
  $: if ($isAuthenticated) { /* re-check when auth flips */ }

  async function payIcp(planId) {
    msg = null; busy = planId; pendingApplyOrderId = null;
    try {
      const r = await subscribeWithIcp(planId);
      if (r.err) { msg = { kind: 'err', text: r.err }; return; }
      const applied = await notifyFleet(r.order?.id);
      if (applied.ok) {
        msg = { kind: 'ok', text: `Subscribed to ${PLANS[planId].label}! Your HQ is updating (~10s).` };
      } else {
        // Paid ON-CHAIN but applying it to the fleet didn't complete. Let the
        // user retry activation WITHOUT paying again (the order is already paid).
        pendingApplyOrderId = r.order?.id ?? null;
        msg = { kind: 'warn', text: `Payment received for ${PLANS[planId].label}, but activating your HQ didn't finish${applied.reason ? ` (${applied.reason})` : ''}. Use “Apply plan” to retry — you won't be charged again.` };
      }
      await refresh();
    } finally { busy = ''; }
  }

  // Retry fleet activation for an already-PAID order (no re-charge).
  async function applyPlan() {
    if (pendingApplyOrderId == null) return;
    msg = null; busy = 'apply';
    try {
      const applied = await notifyFleet(pendingApplyOrderId);
      if (applied.ok) {
        msg = { kind: 'ok', text: 'Plan applied! Your HQ is updating (~10s).' };
        pendingApplyOrderId = null;
      } else {
        msg = { kind: 'warn', text: `Still couldn't apply${applied.reason ? ` (${applied.reason})` : ''}. Try again in a moment.` };
      }
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

<svelte:head>
  <title>Plans · CafresoHQ</title>
</svelte:head>

<section class="space-y-5">
  <header class="card p-6 sm:p-8">
    <div class="page-kicker">CafresoHQ / Plans</div>
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
    <div class="card p-4 text-sm {msg.kind === 'ok' ? 'text-emerald-300' : msg.kind === 'warn' ? 'text-amber-300' : 'text-rose-300'}">
      {msg.text}
      {#if pendingApplyOrderId != null}
        <button class="btn-ghost btn-sm mt-2" disabled={busy === 'apply'} on:click={applyPlan}>
          {busy === 'apply' ? 'Applying…' : 'Apply plan'}
        </button>
      {/if}
    </div>
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
        {@const canBuy = priced[t.id] && icp != null}
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
              {#if icp != null}
                <div class="text-xs text-ink-400">≈ {icp.toFixed(3)} ICP at current rate</div>
              {/if}
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
              <button class="btn-primary w-full" disabled={busy === t.id || !canBuy}
                      on:click={() => payIcp(t.id)}>
                {busy === t.id ? 'Processing…' : (canBuy ? `Pay ~${icp.toFixed(3)} ICP` : 'ICP pricing coming soon')}
              </button>
              {#if CARD_ENABLED}
                <button class="btn-ghost w-full" disabled={busy === t.id}
                        on:click={() => payCard(t.id)}>
                  Pay by card
                </button>
              {:else}
                <span class="block text-center text-xs text-ink-400">Card payments coming soon</span>
              {/if}
            {/if}
          </div>
        </div>
      {/each}
    </div>
    <p class="text-xs text-ink-400">
      Paid in ICP from your signed-in wallet, recorded on-chain. Prices are in USD; the
      ICP shown is an estimate at the current rate — the exact amount is set on-chain at
      purchase from a live price oracle and may differ slightly. $nanas payment coming soon.
    </p>
  {/if}
</section>
