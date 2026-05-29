<script>
  import { onMount } from 'svelte';
  import Tag from '$lib/components/Tag.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import ProductCard from '$lib/components/ProductCard.svelte';
  import { PRODUCTS as SEED_PRODUCTS } from '$lib/data/products.js';
  import { listProducts } from '$lib/api/store.js';

  let products = SEED_PRODUCTS;
  let filter = 'all';

  onMount(async () => {
    const fresh = await listProducts();
    if (fresh && fresh.length > 0) products = fresh;
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

<svelte:head><title>Cafreso Café · Shop</title></svelte:head>

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
  <div class="shop-grid grid gap-6" style="grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));">
    {#each filtered as p (p.slug)}
      <ProductCard {p} />
    {/each}
  </div>
</div>
