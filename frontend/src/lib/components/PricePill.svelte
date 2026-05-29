<script>
  import { usd } from '$lib/data/products.js';
  /** @type {number} */
  export let nanas;
  /** @type {'md' | 'lg'} */
  export let size = 'md';
  $: px = size === 'lg' ? { fs: 18, coin: 22 } : { fs: 14, coin: 18 };
</script>

<span class="inline-flex items-center gap-1.5 font-semibold" style="font-size: {px.fs}px;">
  {nanas.toLocaleString()}
  <img
    src="/assets/nanas-coin.png"
    alt=""
    style="width: {px.coin}px; height: {px.coin}px;"
  />
  Nanas
  <span class="text-muted-foreground text-xs font-normal">(${usd(nanas)} USD)</span>
</span>
