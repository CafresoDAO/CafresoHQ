<script>
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { PRODUCTS as SEED_PRODUCTS, productImage, usd } from '$lib/data/products.js';
  import { getProduct } from '$lib/api/store.js';
  import { cart, showToast, cartOpen } from '$lib/stores/cart.js';
  import Icon from '$lib/components/Icon.svelte';
  import Button from '$lib/components/Button.svelte';
  import { goto } from '$app/navigation';

  let p = SEED_PRODUCTS.find((x) => x.slug === $page.params.slug) || null;
  /* Seed data only covers the built-in catalogue, so a canister-only product
     starts as null here. Rendering the {:else} branch on that would flash
     "Product not found" at someone who is, in fact, looking at a real product —
     it just hasn't been fetched yet. Stay in a loading state until the canister
     answers, and only call it missing once we've actually looked.
     (A seed hit still paints instantly — no spinner for the common case.) */
  let resolving = !p;

  onMount(async () => {
    try {
      const fresh = await getProduct($page.params.slug);
      if (fresh) p = fresh;
    } finally {
      resolving = false;
    }
  });

  let qty = 1;
  $: total = p ? (p.price || 0) * qty : 0;

  function addToCart() {
    if (!p) return;
    cart.add({ ...p, name: p.name || p.title }, qty);
    showToast(`Added ${p.name || p.title} to cart`);
    cartOpen.set(true);
  }
</script>

<svelte:head>
  <title>{p ? p.name : 'Product'} · Cafreso</title>
  {#if p}
    <meta property="og:title" content={p.name} />
    <meta property="og:description" content={p.desc || p.excerpt || ''} />
    <meta property="og:type" content="product" />
    <meta property="og:image" content={p.img ? productImage(p.img) : '/assets/cafreso-wordmark.png'} />
    <meta name="twitter:card" content="summary_large_image" />
  {/if}
</svelte:head>

{#if p}
  <div class="mx-auto px-4 py-6 md:p-10" style="max-width: 1280px;">
    <button
      on:click={() => goto('/shop')}
      class="bg-transparent border-none text-primary cursor-pointer text-sm p-0 mb-5 inline-flex items-center gap-1.5"
    >
      <Icon name="caret-left" size={16} /> Back to shop
    </button>
    <div class="pdp-layout flex gap-10 flex-col md:flex-row">
      <div class="pdp-gallery flex-1 flex justify-center items-start p-6">
        <img src={productImage(p.img)} alt={p.name} style="max-width: 100%; max-height: 420px;" />
      </div>
      <div class="pdp-copy flex-1 flex flex-col gap-4 p-6">
        <h1 class="text-[36px] font-extrabold m-0 mt-3 leading-[1.1]">{p.name}</h1>
        <div class="flex items-end gap-2">
          <span class="text-[30px] inline-flex items-center gap-2">
            {p.price.toLocaleString()} Nanas
            <img src="/assets/nanas-coin.png" alt="" class="w-7" />
          </span>
          <span class="text-[13px] text-muted-foreground pb-1">
            (${usd(p.price)} USD)
          </span>
        </div>
        <p class="m-0 leading-[1.6]">{p.desc}</p>
        <div class="flex gap-3 items-center">
          {#if !p.unavailable}
            <span class="text-sm">Quantity</span>
            <div
              class="inline-flex items-center overflow-hidden rounded-md"
              style="border: 1px solid hsl(var(--pg-border)); background: hsl(var(--pg-elevated));"
            >
              <button
                on:click={() => (qty = Math.max(1, qty - 1))}
                class="border-none bg-transparent cursor-pointer text-base"
                style="width: 32px; height: 36px;"
                aria-label="Decrease"
              >−</button>
              <span class="text-center text-sm" style="width: 32px;">{qty}</span>
              <button
                on:click={() => (qty += 1)}
                class="border-none bg-transparent cursor-pointer text-base"
                style="width: 32px; height: 36px;"
                aria-label="Increase"
              >+</button>
            </div>
          {/if}
          <Button
            variant="default"
            size="lg"
            on:click={addToCart}
            disabled={p.unavailable}
          >Add to cart</Button>
        </div>
        {#if p.unavailable}
          <p class="text-sm text-muted-foreground m-0">This product is coming soon.</p>
        {:else}
          <div class="flex gap-2 items-center text-sm text-primary">
            <span>{total.toLocaleString()}</span>
            <img src="/assets/nanas-coin.png" alt="" class="w-[18px]" />
            Nanas
            <span class="text-muted-foreground">(${usd(total)} USD)</span>
          </div>
        {/if}
      </div>
    </div>
  </div>
{:else if resolving}
  <!-- Skeleton matching the PDP's shape, so the canister round-trip reads as
       "loading this product" rather than a flash of "not found". -->
  <div class="mx-auto px-4 py-6 md:p-10" style="max-width: 1280px;">
    <div class="pdp-layout flex gap-8 rounded-[18px] p-8"
      style="background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));">
      <div class="pdp-gallery flex-1 rounded-[14px] pdp-skel" style="min-height: 320px;"></div>
      <div class="pdp-copy flex-1 flex flex-col gap-3">
        <div class="pdp-skel rounded-[8px]" style="height: 30px; width: 65%;"></div>
        <div class="pdp-skel rounded-[6px]" style="height: 14px; width: 90%;"></div>
        <div class="pdp-skel rounded-[6px]" style="height: 14px; width: 78%;"></div>
        <div class="pdp-skel rounded-[10px] mt-3" style="height: 44px; width: 180px;"></div>
      </div>
    </div>
  </div>
{:else}
  <div class="mx-auto p-10" style="max-width: 640px;">
    <div class="rounded-[14px] px-4 py-10 text-center"
      style="background: hsl(var(--pg-surface)); border: 1px dashed hsl(var(--pg-border));"
    >
      <Icon name="package" size={28} style="color: hsl(32 56% 35%);" />
      <h3 class="font-bold text-[17px] mt-3 mb-1.5" style="color: hsl(var(--pg-fg));">Product not found</h3>
      <p class="text-[13.5px] mx-auto mb-4 max-w-[380px]" style="color: hsl(var(--pg-fg-muted));">
        This item may have been renamed or removed. Browse everything else in the shop.
      </p>
      <Button href="/shop">
        <Icon name="storefront" size={14} /> Back to shop
      </Button>
    </div>
  </div>
{/if}

<style>
  /* Same shimmer the library/blog skeletons use, kept local since the PDP is
     the only shop surface that needs one. */
  .pdp-skel {
    background: linear-gradient(90deg, hsl(var(--pg-hover)) 25%, hsl(var(--pg-border)) 50%, hsl(var(--pg-hover)) 75%);
    background-size: 200% 100%;
    animation: pdp-shimmer 1.4s ease-in-out infinite;
  }
  @keyframes pdp-shimmer { to { background-position: -200% 0; } }
  @media (prefers-reduced-motion: reduce) { .pdp-skel { animation: none; } }
</style>
