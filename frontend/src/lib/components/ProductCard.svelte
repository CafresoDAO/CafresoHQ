<script>
  import GoldPrice from './GoldPrice.svelte';
  import Icon from './Icon.svelte';
  import { productImage, usd, TAG_LABEL } from '$lib/data/products.js';
  export let p;

  let arrEl, imgEl, cardEl;

  function enter() {
    if (p.unavailable) return;
    cardEl.style.transform = 'translateY(-4px)';
    cardEl.style.boxShadow =
      '0 1px 0 hsl(0 0% 100% / 0.9) inset, 0 20px 32px -16px hsl(24 30% 15% / 0.38), 0 0 0 1px hsl(222 47% 11% / 0.18)';
    if (arrEl) {
      arrEl.style.opacity = 1;
      arrEl.style.transform = 'translate(0, 0)';
    }
    if (imgEl) imgEl.style.transform = 'scale(1.04)';
  }
  function leave() {
    cardEl.style.transform = 'none';
    cardEl.style.boxShadow =
      '0 1px 0 hsl(0 0% 100% / 0.8) inset, 0 10px 24px -14px hsl(24 30% 20% / 0.3)';
    if (arrEl) {
      arrEl.style.opacity = 0;
      arrEl.style.transform = 'translate(6px, -6px)';
    }
    if (imgEl) imgEl.style.transform = 'scale(1)';
  }
</script>

<svelte:element
  this={p.unavailable ? 'div' : 'a'}
  role={p.unavailable ? 'presentation' : undefined}
  href={p.unavailable ? undefined : `/product/${p.slug}`}
  aria-disabled={p.unavailable ? 'true' : undefined}
  aria-label={p.unavailable ? `${p.name} — coming soon` : undefined}
  bind:this={cardEl}
  on:mouseenter={enter}
  on:mouseleave={leave}
  class="relative flex flex-col overflow-hidden no-underline text-primary"
  style="cursor: {p.unavailable ? 'not-allowed' : 'pointer'};
    background: linear-gradient(180deg, hsl(var(--pg-surface) / 0.9), hsl(var(--pg-hover) / 0.75));
    border: 1px solid hsl(var(--pg-border));
    border-radius: 16px;
    padding: 18px;
    box-shadow: 0 1px 0 hsl(0 0% 100% / 0.8) inset, 0 10px 24px -14px hsl(24 30% 20% / 0.3);
    transition: transform .35s cubic-bezier(.2,.8,.2,1), box-shadow .35s ease, border-color .25s ease;"
>
  <div class="flex justify-between items-start mb-1.5">
    <span
      class="cat-chip text-[11px] font-semibold uppercase"
      style="letter-spacing: 0.08em;
        padding: 4px 10px;
        border-radius: 999px;"
    >{TAG_LABEL[p.tag] || p.tag}</span>
    {#if p.unavailable}
      <span
        class="text-[10px] font-semibold uppercase"
        style="letter-spacing: 0.06em;
          color: hsl(var(--pg-danger-fg));
          background: hsl(var(--pg-danger-bg));
          padding: 3px 8px;
          border-radius: 999px;"
      >Soon</span>
    {:else}
      <span
        bind:this={arrEl}
        class="w-7 h-7 rounded-full text-white inline-flex items-center justify-center bg-primary"
        style="
          opacity: 0;
          transform: translate(6px, -6px);
          transition: opacity .25s ease, transform .35s cubic-bezier(.2,.8,.2,1);"
      ><Icon name="arrow-up-right" size={14} /></span>
    {/if}
  </div>

  <div class="flex items-center justify-center overflow-hidden" style="height: 180px; margin: 4px 0 14px;">
    <img
      bind:this={imgEl}
      src={productImage(p.img)}
      alt={p.name}
      loading="lazy"
      decoding="async"
      style="max-width: 100%; max-height: 100%; object-fit: contain;
        filter: {p.unavailable ? 'grayscale(1) opacity(0.55)' : 'none'};
        transition: transform .5s cubic-bezier(.2,.8,.2,1);"
    />
  </div>

  <div class="flex flex-col gap-1.5">
    <div class="text-[15.5px] font-semibold leading-[1.25]">{p.name}</div>
    <p
      class="m-0 text-[13px] leading-[1.45] text-muted-foreground overflow-hidden"
      style="display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;"
    >{p.desc}</p>
  </div>

  <div
    class="flex items-center justify-between mt-3.5 pt-3.5"
    style="border-top: 1px dashed hsl(var(--pg-border));"
  >
    <GoldPrice cents={p.priceCentsUSD ?? Math.round(p.price * 0.15)} />
  </div>
</svelte:element>

<style>
  /* Category chip: keep light values exact, flip to a warm chip in dark. */
  .cat-chip {
    background: hsl(26 30% 74% / 0.5);
    color: hsl(24 40% 22%);
  }
  :global(.dark) .cat-chip {
    background: hsl(30 25% 55% / 0.35);
    color: hsl(30 35% 85%);
  }
</style>
