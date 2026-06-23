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

  onMount(async () => {
    const fresh = await getProduct($page.params.slug);
    if (fresh) p = fresh;
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
              class="inline-flex items-center bg-white overflow-hidden rounded-md"
              style="border: 1px solid hsl(214 32% 91%);"
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
{:else}
  <div class="mx-auto p-10 text-center">
    <h1 class="text-3xl font-bold">Not found</h1>
  </div>
{/if}
