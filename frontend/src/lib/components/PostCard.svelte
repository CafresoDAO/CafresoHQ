<script>
  import Icon from './Icon.svelte';
  import Avatar from './Avatar.svelte';
  import NanasCoin from './NanasCoin.svelte';
  import CategoryTag from './CategoryTag.svelte';
  import OnChainBadge from './OnChainBadge.svelte';
  import { goto } from '$app/navigation';
  import { fmtDate, postHeroImg } from '$lib/data/blog.js';
  import { principalText } from '$lib/stores/auth.js';
  import { isDevlogAdmin } from '$lib/data/admins.js';

  export let post;
  export let featured = false;

  // Admins see a small pencil chip at the top-right of every post card —
  // one tap goes straight to `/blog/new?edit=<slug>` so maintenance doesn't
  // require opening the post first.
  $: canEdit = isDevlogAdmin($principalText);

  let cardEl;
  function enter() {
    cardEl.style.transform = 'translateY(-3px)';
    cardEl.style.boxShadow =
      '0 1px 0 hsl(0 0% 100% / 0.9) inset, 0 20px 32px -16px hsl(24 30% 15% / 0.38), 0 0 0 1px hsl(222 47% 11% / 0.15)';
  }
  function leave() {
    cardEl.style.transform = 'none';
    cardEl.style.boxShadow =
      '0 1px 0 hsl(0 0% 100% / 0.8) inset, 0 10px 24px -14px hsl(24 30% 20% / 0.3)';
  }
</script>

<a
  href="/blog/{post.slug}"
  bind:this={cardEl}
  on:mouseenter={enter}
  on:mouseleave={leave}
  class="post-card fade-up relative flex flex-col cursor-pointer overflow-hidden no-underline text-primary"
  style="
    background: linear-gradient(180deg, hsl(var(--pg-surface) / 0.9), hsl(var(--pg-hover) / 0.78));
    border: 1px solid hsl(var(--pg-border));
    border-radius: 16px;
    padding: 20px;
    gap: 14px;
    box-shadow: 0 1px 0 hsl(0 0% 100% / 0.8) inset, 0 10px 24px -14px hsl(24 30% 20% / 0.3);
    transition: transform .35s cubic-bezier(.2,.8,.2,1), box-shadow .35s ease, border-color .25s ease;
    grid-column: {featured ? '1 / -1' : 'auto'};
  "
>
  {#if canEdit}
    <!-- Admin quick-edit. A <button> rather than an <a>: this sits INSIDE the
         card's own <a>, and nested anchors are invalid HTML — the browser
         hoists the inner one out of the link during parsing, which both broke
         hydration (SSR/client trees disagreed) and made the pencil unreliable.
         goto() keeps the same navigation without nesting a link in a link. -->
    <button
      type="button"
      on:click|stopPropagation|preventDefault={() => goto(`/blog/new?edit=${post.slug}`)}
      aria-label="Edit post"
      title="Edit this post"
      class="absolute z-[2] inline-flex items-center gap-1.5 rounded-full cursor-pointer"
      style="top: 12px; right: 12px; padding: 5px 10px; font-size: 11.5px; font-weight: 600; border: none;
        background: hsl(var(--pg-solid)); color: hsl(var(--pg-solid-fg)); box-shadow: 0 4px 10px -4px hsl(222 47% 11% / 0.45);"
    >
      <Icon name="pencil-simple" size={11} /> Edit
    </button>
  {/if}
  {#if featured}
    <div class="blog-featured-inner" style="display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); gap: 32px; align-items: center;">
      <div>
        <div class="flex gap-2 items-center mb-3">
          <span
            class="text-[10.5px] font-bold uppercase"
            style="background: hsl(var(--pg-solid)); color: hsl(var(--pg-solid-fg)); padding: 4px 10px; border-radius: 999px; letter-spacing: 0.12em;"
          >Latest</span>
          <CategoryTag cat={post.cat} />
        </div>
        <h1
          class="post-hero-title"
          style="font-size: 44px; font-weight: 800; line-height: 1.05; margin: 0 0 14px; letter-spacing: -0.02em;"
        >{post.title}</h1>
        <p class="m-0 mb-4" style="font-size: 16px; line-height: 1.55; color: hsl(var(--pg-fg-muted)); max-width: 58ch;">
          {post.excerpt}
        </p>
        <div class="post-meta-row flex items-center gap-3.5 flex-wrap">
          <div class="inline-flex items-center gap-2">
            <Avatar name={post.author.name} hue={post.author.hue} size={32} />
            <div class="text-[13px]">
              <div class="font-semibold">{post.author.name}</div>
              <div style="color: hsl(var(--pg-fg-muted)); font-size: 11.5px;">
                {post.author.role} · {fmtDate(post.date)}
              </div>
            </div>
          </div>
          <span class="w-px h-6" style="background: hsl(var(--pg-border));"></span>
          <div class="inline-flex items-center gap-1 text-[13px] font-semibold">
            <Icon name="fire" size={15} style="color: hsl(32 72% 50%);" />
            {post.burned.toLocaleString()}
            <NanasCoin size={15} />
            <span class="font-normal ml-1" style="color: hsl(var(--pg-fg-muted));">burned</span>
          </div>
          <div class="inline-flex items-center gap-1 text-[13px]" style="color: hsl(var(--pg-fg-muted));">
            <Icon name="chat-circle" size={15} /> {post.comments}
          </div>
          <div class="inline-flex items-center gap-1 text-[13px]" style="color: hsl(var(--pg-fg-muted));">
            <Icon name="clock" size={15} /> {post.readMin} min read
          </div>
        </div>
        <div class="mt-4">
          <OnChainBadge canister={post.canister} block={post.block} />
        </div>
      </div>
      <div
        class="relative flex items-center justify-center overflow-hidden"
        style="
          aspect-ratio: 4 / 3;
          border-radius: 12px;
          background: {post.hero === 'farm'
            ? 'radial-gradient(ellipse at 50% 70%, hsl(112 40% 82%), hsl(26 30% 74%))'
            : 'linear-gradient(180deg, hsl(var(--pg-hover)), hsl(var(--pg-border)))'};
          border: 1px solid hsl(var(--pg-border));
        "
      >
        <img
          src={postHeroImg(post.hero)}
          alt={post.title}
          loading="lazy"
          decoding="async"
          style="
            width: 86%; height: 86%; object-fit: contain;
            image-rendering: {post.hero === 'farm' ? 'pixelated' : 'auto'};
          "
        />
        <div
          class="absolute left-3 bottom-3"
          style="
            font-family: ui-monospace, monospace; font-size: 10.5px;
            background: hsl(24 48% 12% / 0.82); color: hsl(26 40% 88%);
            padding: 4px 8px; border-radius: 6px; letter-spacing: 0.04em;
          "
        >block #{post.block.toLocaleString()}</div>
      </div>
    </div>
  {:else}
    <div class="flex justify-between items-start gap-2.5">
      <CategoryTag cat={post.cat} size="sm" />
      <div class="text-[11px]" style="color: hsl(var(--pg-fg-muted));">{fmtDate(post.date)}</div>
    </div>
    <div
      class="flex items-center justify-center overflow-hidden"
      style="
        height: 120px; border-radius: 10px;
        background: {post.hero === 'farm'
          ? 'radial-gradient(ellipse at 50% 70%, hsl(112 40% 82%), hsl(26 30% 74%))'
          : 'linear-gradient(180deg, hsl(var(--pg-hover)), hsl(var(--pg-border)))'};
        border: 1px solid hsl(var(--pg-border));
      "
    >
      <img
        src={postHeroImg(post.hero)}
        alt={post.title}
        loading="lazy"
        decoding="async"
        style="
          width: 70%; height: 70%; object-fit: contain;
          image-rendering: {post.hero === 'farm' ? 'pixelated' : 'auto'};
        "
      />
    </div>
    <div class="post-card-body flex flex-col gap-2.5">
      <h3 style="font-size: 18px; font-weight: 700; line-height: 1.2; margin: 0; letter-spacing: -0.01em;">
        {post.title}
      </h3>
      <p
        class="m-0 overflow-hidden"
        style="
          font-size: 13.5px; color: hsl(var(--pg-fg-muted)); line-height: 1.5;
          display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
        "
      >{post.excerpt}</p>
    </div>
    <div
      class="flex items-center justify-between pt-3 mt-auto"
      style="border-top: 1px dashed hsl(var(--pg-border));"
    >
      <div class="inline-flex items-center gap-2">
        <Avatar name={post.author.name} hue={post.author.hue} size={22} />
        <span class="text-xs font-medium">{post.author.name}</span>
      </div>
      <div class="inline-flex items-center gap-2.5 text-xs">
        <span class="inline-flex items-center gap-[3px] font-semibold pc-burn" style="color: hsl(24 40% 22%);">
          <Icon name="fire" size={13} style="color: hsl(32 72% 50%);" />
          {(post.burned / 1000).toFixed(1)}k
          <NanasCoin size={12} />
        </span>
        <span class="inline-flex items-center gap-[3px]" style="color: hsl(var(--pg-fg-muted));">
          <Icon name="chat-circle" size={13} /> {post.comments}
        </span>
      </div>
    </div>
  {/if}
</a>

<style>
  /* Warm-brown burn count keeps its light value; brighten in dark so it
     stays legible on the dark card. */
  :global(.dark) .pc-burn {
    color: hsl(var(--pg-fg));
  }
</style>
