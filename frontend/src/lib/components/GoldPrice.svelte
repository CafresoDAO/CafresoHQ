<script>
  /* GoldPrice — the one way a price renders anywhere in the shop.
     USD is the anchor (stable, what the product is actually worth);
     the sGLDT amount is computed live from the ICPSwap price feed, so
     buyers always see how much gold the purchase costs right now. */
  import { prices } from '$lib/stores/prices.js';
  import { usdCentsToGold, fmtGold } from '$lib/gold.js';
  import GoldCoin from './GoldCoin.svelte';

  /** Price in USD cents. */
  export let cents;
  /** @type {'sm' | 'md' | 'lg'} */
  export let size = 'md';

  $: px = size === 'lg' ? { fs: 18, coin: 20 } : size === 'sm' ? { fs: 12.5, coin: 14 } : { fs: 14, coin: 16 };
  $: gold = usdCentsToGold(cents, $prices?.sGLDT);
</script>

<span class="inline-flex items-center gap-1.5 font-semibold" style="font-size: {px.fs}px;">
  ${(cents / 100).toFixed(2)}
  {#if gold > 0}
    <span class="inline-flex items-center gap-1 font-normal text-muted-foreground" style="font-size: {px.fs - 2}px;">
      · ≈ {fmtGold(gold)} <GoldCoin size={px.coin} /> sGLDT
    </span>
  {/if}
</span>
