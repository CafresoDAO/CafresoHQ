<script>
  import { onMount } from 'svelte';
  import Tag from '$lib/components/Tag.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import ProductCard from '$lib/components/ProductCard.svelte';
  import { PRODUCTS as SEED_PRODUCTS } from '$lib/data/products.js';
  import { listProducts } from '$lib/api/store.js';

  let products = SEED_PRODUCTS;
  let filter = 'all';
  let isLoading = true;

  onMount(async () => {
    try {
      const fresh = await listProducts();
      if (fresh && fresh.length > 0) products = fresh;
    } finally {
      isLoading = false;
    }
  });

  // Products accept either `tag` (seed shape) or `cat` (canister shape); the
  // tag-based filter covers both so admin-edited products keep showing.
  $: filtered = filter === 'all'
    ? products
    : products.filter((p) => (p.cat || p.tag) === filter);

  const filters = [
    ['all', 'storefront', 'All'],
    ['coffee', 'coffee-bean', 'Coffee'],
    ['dao', 'infinity', 'DAO'],
    ['accessories', 't-shirt', 'Merch']
  ];
</script>

<svelte:head>
  <title>Cafreso Café · Shop</title>
  <meta name="description" content="Browse the Cafreso Café shop — coffee, DAO memberships and merch, paid on-chain. Filter by category and check out with your Internet Identity." />
</svelte:head>

<div class="mx-auto p-6" style="max-width: 1280px;">
  <div class="flex justify-center gap-5 flex-wrap py-4">
    {#each filters as [v, i, l]}
      <Tag active={filter === v} on:click={() => (filter = v)}>
        <Icon name={i} size={18} />
        {l}
      </Tag>
    {/each}
  </div>
  <hr class="border-none m-0 mb-5" style="border-top: 1px solid hsl(26 30% 60%);" />
  <div class="text-center mb-6 text-[15px]">
    Shop {filter.charAt(0).toUpperCase() + filter.slice(1)}
  </div>
  {#if isLoading && products.length === 0}
    <div class="rounded-[14px] px-4 py-10 text-center text-[13.5px]"
      style="background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border)); color: hsl(var(--pg-fg-muted));"
    >
      <Icon name="spinner-gap" size={16} class="spin" /> Loading products…
    </div>
  {:else if filtered.length === 0}
    <div class="rounded-[14px] px-4 py-10 text-center"
      style="background: hsl(var(--pg-surface)); border: 1px dashed hsl(26 30% 75%);"
    >
      <Icon name="storefront" size={28} style="color: hsl(32 56% 35%);" />
      <h3 class="font-bold text-[17px] mt-3 mb-1.5" style="color: hsl(var(--pg-fg));">Nothing here yet</h3>
      <p class="text-[13.5px] mx-auto mb-4 max-w-[380px]" style="color: hsl(var(--pg-fg-muted));">
        No products in this category right now — try another filter above.
      </p>
    </div>
  {:else}
    <div class="shop-grid grid gap-6" style="grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));">
      {#each filtered as p (p.slug)}
        <ProductCard {p} />
      {/each}
    </div>
  {/if}
</div>
