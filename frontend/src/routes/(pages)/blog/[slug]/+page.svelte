<svelte:options runes={true} />

<script>
  import { page } from '$app/stores';
  import { POSTS, COMMENTS, fmtDate, postHeroImg } from '$lib/data/blog.js';
  import { burnTarget, userBurns } from '$lib/stores/blog.js';
  import { getPost } from '$lib/api/devlog.js';
  import { principalText } from '$lib/stores/auth.js';
  import { isDevlogAdmin } from '$lib/data/admins.js';
  import { detectMentions } from '$lib/stores/notifications.js';
  import { profile } from '$lib/stores/profile.js';
  import { get } from 'svelte/store';
  import Icon from '$lib/components/Icon.svelte';
  import Avatar from '$lib/components/Avatar.svelte';
  import Button from '$lib/components/Button.svelte';
  import CategoryTag from '$lib/components/CategoryTag.svelte';
  import OnChainBadge from '$lib/components/OnChainBadge.svelte';
  import PostReactionBar from '$lib/components/PostReactionBar.svelte';
  import MobileReactionBar from '$lib/components/MobileReactionBar.svelte';
  import CommentThread from '$lib/components/CommentThread.svelte';
  import BankingBravePost from '$lib/components/BankingBravePost.svelte';
  import PostRenderer from '$lib/components/PostRenderer.svelte';
  import { getTheme } from '$lib/themes.js';

  // Runes-mode state — post-await assignments reliably trigger re-renders.
  let post = $state(null);
  let loading = $state(true);
  let loadedSlug = $state(null);

  const slug = $derived($page.params.slug);
  const userBurned = $derived($userBurns[slug] || 0);
  // Comments scoped to THIS post (+ slug-less general comments). Without this the
  // thread rendered the entire global COMMENTS list on every post.
  const postComments = $derived(COMMENTS.filter((c) => c.slug === slug || !c.slug));
  const body = $derived(
    post?.body && post.body.length > 0
      ? post.body
      : [
          { kind: 'p', text: post?.excerpt || '' },
          { kind: 'p', text: 'Full post content is drafted in this space for each update. Keep reading for the details.' }
        ]
  );

  $effect(() => {
    const nextSlug = slug;
    if (!nextSlug || nextSlug === loadedSlug) return;
    loadedSlug = nextSlug;
    loading = true;
    post = null;
    (async () => {
      try {
        // Seed posts are authoritative (only 2: cafreso + banking.brave
        // intros). Unknown slugs resolve to "not found" even if the canister
        // happens to have the post under that slug.
        const seed = POSTS.find((p) => p.slug === nextSlug);
        if (!seed) {
          if (loadedSlug === nextSlug) post = null;
          return;
        }
        const fromCanister = await getPost(nextSlug);
        if (loadedSlug !== nextSlug) return;
        // Merge canister-side enhancements (burned/tips/comments counts,
        // richer body) over the seed. Seed always wins on author/canister-
        // ID identity so fake test authors don't leak into the UI.
        post = fromCanister
          ? { ...seed, ...fromCanister, author: seed.author, layout: seed.layout }
          : seed;

        // Detect @mentions in blog comments.
        const allComments = COMMENTS.filter((c) => c.slug === nextSlug || !c.slug);
        const myName = get(profile)?.name;
        if (myName && allComments.length) {
          detectMentions(allComments, myName, `/blog/${nextSlug}`);
        }
      } finally {
        if (loadedSlug === nextSlug) loading = false;
      }
    })();
  });

  function onTip() {
    burnTarget.set(slug);
  }

  const canEdit = $derived(isDevlogAdmin($principalText));
  const theme = $derived(getTheme(post?.theme ?? (post?.layout === 'banking-brave' ? 'banking-brave' : 'standard')));
</script>

<svelte:head>
  <title>{post ? post.title : 'Post'} · Cafreso Dev Log</title>
  {#if post}
    <meta property="og:title" content={post.title} />
    <meta property="og:description" content={post.excerpt} />
    <meta property="og:type" content="article" />
    <meta name="twitter:card" content="summary_large_image" />
  {/if}
</svelte:head>

{#if loading}
  <div class="mx-auto p-10 text-center" style="color: hsl(215 16% 47%);">
    <Icon name="spinner-gap" size={18} /> Loading post…
  </div>
{:else if !post}
  <div class="mx-auto p-10 text-center">
    <h1 class="text-3xl font-bold">Post not found</h1>
    <a href="/blog" class="underline underline-offset-4">Back to Dev Log</a>
  </div>
{:else if post.layout === 'banking-brave'}
  <BankingBravePost post={post} />
{:else}
  <div class="blog-container mx-auto" style="max-width: 1280px; padding: 28px 18px 120px;">
    <div class="flex items-center justify-between gap-3 mb-4 flex-wrap">
      <a
        href="/blog"
        class="bg-transparent border-none text-primary text-[13px] p-0 inline-flex items-center gap-1.5 no-underline cursor-pointer"
      >
        <Icon name="caret-left" size={14} /> Back to Dev Log
      </a>
      {#if canEdit}
        <a
          href="/blog/new?edit={slug}"
          class="inline-flex items-center gap-1.5 text-[12px] font-semibold rounded-full px-3 py-1.5 no-underline"
          style="background: hsl(26 40% 96%); border: 1px solid hsl(26 30% 82%); color: hsl(222 47% 11%);"
        >
          <Icon name="pencil-simple" size={12} /> Edit post
        </a>
      {/if}
    </div>

    <div class="flex gap-6 items-start">
      <PostReactionBar {post} {userBurned} {onTip} />

      <article class="flex-1 min-w-0">
        <!-- Header -->
        <header class="mb-6">
          <div class="flex gap-2.5 items-center mb-3.5 flex-wrap">
            <CategoryTag cat={post.cat} />
            <span class="text-xs" style="color: hsl(215 16% 47%);">{fmtDate(post.date)}</span>
            <span class="text-xs" style="color: hsl(215 16% 47%);">· {post.readMin} min read</span>
          </div>
          <h1
            class="post-hero-title"
            style="font-size: 46px; font-weight: 800; line-height: 1.05; margin: 0 0 16px; letter-spacing: -0.025em; text-wrap: pretty;"
          >{post.title}</h1>
          <p style="font-size: 18px; line-height: 1.5; color: hsl(215 16% 35%); margin: 0 0 5px; max-width: 62ch; text-wrap: pretty;">
            {post.excerpt}
          </p>

          <div class="flex items-center gap-4 flex-wrap mt-5">
            <div class="inline-flex items-center gap-2.5">
              <Avatar name={post.author.name} hue={post.author.hue} size={40} />
              <div class="text-[13px]">
                <div class="font-semibold">{post.author.name}</div>
                <div style="color: hsl(215 16% 47%); font-size: 11.5px;">{post.author.role}</div>
              </div>
            </div>
            <span class="w-px" style="height: 28px; background: hsl(26 25% 80%);"></span>
            <OnChainBadge canister={post.canister} block={post.block} />
            <button
              class="inline-flex items-center gap-1.5 bg-white cursor-pointer whitespace-nowrap"
              style="
                border: 1px solid hsl(26 30% 85%);
                padding: 5px 10px; border-radius: 999px; font-size: 12px;
                font-family: inherit;
              "
            >
              <Icon name="seal-check" size={14} style="color: hsl(112 43% 45%);" /> Verify signature
            </button>
          </div>
        </header>

        <!-- Hero image -->
        <div
          class="post-hero-img relative flex items-center justify-center overflow-hidden mb-6"
          style="
            aspect-ratio: 2 / 1; border-radius: 14px;
            background: {post.hero === 'farm'
              ? 'radial-gradient(ellipse at 50% 70%, hsl(112 40% 82%), hsl(26 30% 74%))'
              : 'linear-gradient(180deg, hsl(26 45% 96%), hsl(26 40% 88%))'};
            border: 1px solid hsl(26 30% 82%);
          "
        >
          <img
            src={postHeroImg(post.hero)}
            alt={post.title}
            style="width: 72%; height: 82%; object-fit: contain; image-rendering: {post.hero === 'farm' ? 'pixelated' : 'auto'};"
          />
          <div
            class="absolute inline-flex items-center gap-2"
            style="
              left: 14px; bottom: 14px;
              background: hsl(24 48% 12% / 0.82); color: hsl(26 40% 88%);
              padding: 6px 12px; border-radius: 8px;
              font-family: ui-monospace, monospace; font-size: 11px; letter-spacing: 0.04em;
            "
          >
            <img src="/assets/icp.png" alt="" style="width: 13px;" />
            posted at block #{post.block.toLocaleString()}
          </div>
        </div>

        <!-- Article body — themed via PostRenderer -->
        <PostRenderer blocks={body} {theme} />

        <div
          class="flex justify-end items-center flex-wrap gap-3.5 mt-3 px-1"
        >
          <Button
            variant="default"
            size="sm"
            class="!bg-[hsl(45_95%_62%)] !text-[hsl(24_48%_12%)] !border !border-[hsl(32_72%_50%)]"
            on:click={onTip}
          >
            <Icon name="fire" size={14} /> Tip the author
          </Button>
        </div>

        <CommentThread comments={postComments} />

        <!-- Next up -->
        <div class="grid mt-10" style="grid-template-columns: 1fr 1fr; gap: 16px;">
          {#each POSTS.filter((p) => p.slug !== post.slug).slice(0, 2) as p (p.slug)}
            <a
              href="/blog/{p.slug}"
              class="no-underline text-primary cursor-pointer"
            >
              <div
                style="
                  background: hsl(26 45% 98% / 0.7); border: 1px solid hsl(26 30% 85%);
                  border-radius: 12px; padding: 16px;
                "
              >
                <div class="mb-1.5" style="font-size: 11px; color: hsl(215 16% 47%);">Next up</div>
                <div style="font-size: 15px; font-weight: 600; line-height: 1.3;">{p.title}</div>
              </div>
            </a>
          {/each}
        </div>
      </article>
    </div>

    <MobileReactionBar {post} {userBurned} {onTip} />
  </div>
{/if}
