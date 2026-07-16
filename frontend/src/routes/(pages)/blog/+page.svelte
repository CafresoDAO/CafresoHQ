<script>
  import { onMount, tick } from 'svelte';
  import { page } from '$app/stores';
  import { POSTS as SEED_POSTS, CATEGORIES, fmtDate } from '$lib/data/blog.js';
  import { listPosts } from '$lib/api/devlog.js';
  import Icon from '$lib/components/Icon.svelte';
  import Chip from '$lib/components/Chip.svelte';
  import PostCard from '$lib/components/PostCard.svelte';
  import Button from '$lib/components/Button.svelte';
  import { tweaks, burnTarget } from '$lib/stores/blog.js';
  import { principalText } from '$lib/stores/auth.js';
  import { isDevlogAdmin } from '$lib/data/admins.js';

  $: canAuthor = isDevlogAdmin($principalText);

  // The canister is authoritative: every published post shows here. Seeds
  // (Cafreso intro + Banking.Brave intro) enrich their matching canister
  // posts with the richer local author/layout identity, and fill in only
  // when the canister doesn't have them yet (fresh deploys, local replica).
  // Deep-link support: /blog?cat=<category> preselects a filter (project pages
  // link here). Read once at init so the user can still clear it afterward.
  const _initialCat = (() => {
    try {
      const c = $page.url.searchParams.get('cat');
      return c && CATEGORIES[c] ? c : 'all';
    } catch { return 'all'; }
  })();

  let posts = SEED_POSTS;
  let filter = _initialCat;
  let query = '';
  // The posts=[] -> tick() -> posts=merged swap below (load-bearing — see its
  // own comment) briefly makes `filtered` empty, which without this flag
  // flashed the real "no posts match" empty state on every single page load.
  let isSwapping = false;

  onMount(async () => {
    const fresh = await listPosts();
    if (!fresh || fresh.length === 0) return;
    const liveSlugs = new Set(fresh.map((p) => p.slug));
    const merged = [
      ...fresh.map((live) => {
        const seed = SEED_POSTS.find((s) => s.slug === live.slug);
        return seed ? { ...seed, ...live, author: seed.author } : live;
      }),
      ...SEED_POSTS.filter((s) => !liveSlugs.has(s.slug)),
    ];
    // Pinned posts first (that's what the composer's "pin" checkbox means),
    // then newest by date; ties broken by canister write time.
    merged.sort(
      (a, b) =>
        Number(b.pinned === true) - Number(a.pinned === true) ||
        String(b.date).localeCompare(String(a.date)) ||
        (b.timestampCreated || 0) - (a.timestampCreated || 0)
    );
    // Force a reactive flush so dependent derivations (featured, filtered)
    // pick up the merged list instead of the initial seed reference.
    isSwapping = true;
    posts = [];
    await tick();
    posts = merged;
    isSwapping = false;
  });

  $: filtered = posts.filter((p) => {
    if (filter !== 'all' && p.cat !== filter) return false;
    if (query && !(p.title + p.excerpt).toLowerCase().includes(query.toLowerCase())) return false;
    return true;
  });

  $: filters = [['all', 'list', 'All posts'], ...Object.entries(CATEGORIES).map(([k, m]) => [k, m.icon, m.label])];

  // Subscribing reuses the existing burn flow (the same global BurnTipModal
  // that PostReactionBar/onTip drives via burnTarget). Burn against the most
  // recent post so the modal has a valid on-chain target.
  function onSubscribe() {
    const target = posts[0]?.slug;
    if (target) burnTarget.set(target);
  }
</script>

<svelte:head>
  <title>Dev Log · Cafreso</title>
  <meta
    name="description"
    content="Every Cafreso build, proposal, and bag of beans — shipped here first, signed on-chain, tippable in $nanas, open to the community."
  />
</svelte:head>

<div class="blog-container mx-auto" style="max-width: 1280px; padding: 28px 18px 24px;">
  <!-- Masthead -->
  <div class="text-center relative" style="padding: 20px 16px 32px;">
    <div
      class="inline-flex items-center gap-2.5 font-medium"
      style="
        font-size: 12px;
        background: hsl(var(--pg-hover) / 0.7);
        border: 1px solid hsl(var(--pg-border));
        padding: 5px 14px; border-radius: 999px; margin-bottom: 16px;
        white-space: nowrap;
      "
    >
      <span
        class="pulse-ring"
        style="width: 7px; height: 7px; border-radius: 50%; background: hsl(112 60% 45%); flex-shrink: 0;"
      ></span>
      <span>Publishing live from <code style="font-size: 11px;">bek5d-2…rq-cai</code></span>
    </div>
    <h1 style="font-size: clamp(32px, 8vw, 52px); font-weight: 800; margin: 0 0 10px; letter-spacing: -0.03em; line-height: 1;">
      The Dev Log
    </h1>
    <p style="font-size: clamp(14.5px, 2.2vw, 17px); color: hsl(var(--pg-fg-muted)); margin: 0 auto; max-width: 56ch; line-height: 1.55;">
      Every build, every proposal, every bag of beans. We ship updates here before anywhere else — signed on-chain, tippable in $nanas, open to the community.
    </p>
    {#if canAuthor}
      <div class="mt-5">
        <Button href="/blog/new">
          <Icon name="pencil-simple" size={15} /> Write a new post
        </Button>
      </div>
    {/if}
  </div>

  <!-- Filters + search -->
  <div
    class="blog-filters flex items-center flex-wrap"
    style="
      gap: 12px; padding: 14px 16px;
      background: hsl(var(--pg-surface) / 0.55); border: 1px solid hsl(var(--pg-border));
      border-radius: 14px; margin-bottom: 20px;
    "
  >
    <div class="flex gap-1.5 flex-wrap flex-1">
      {#each filters as [k, icon, label]}
        <Chip active={filter === k} {icon} on:click={() => (filter = k)}>{label}</Chip>
      {/each}
    </div>
    <label
      class="blog-search inline-flex items-center gap-2"
      style="
        background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border)); border-radius: 9999px;
        padding: 6px 14px; width: 240px; max-width: 100%;
      "
    >
      <Icon name="magnifying-glass" size={15} style="color: hsl(var(--pg-fg-muted));" />
      <input
        bind:value={query}
        placeholder="Search posts"
        aria-label="Search posts"
        class="border-none outline-none bg-transparent flex-1 text-[13px]"
        style="font-family: inherit;"
      />
    </label>
  </div>

  <div class="flex gap-6 items-start">
    <div class="flex-1 min-w-0">
      {#if filtered.length > 0}
        {#key filtered[0].slug}
          <PostCard post={filtered[0]} featured={true} />
        {/key}
      {/if}
      {#if filtered.length > 1}
        <div
          class="grid mt-6"
          style="grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: {$tweaks.density === 'compact' ? 14 : 20}px;"
        >
          {#each filtered.slice(1) as p (p.slug)}
            <PostCard post={p} />
          {/each}
        </div>
      {/if}
      {#if isSwapping}
        <div class="rounded-[14px] px-4 py-10 text-center text-[13.5px]"
          style="background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border)); color: hsl(var(--pg-fg-muted));"
        >
          <Icon name="spinner-gap" size={16} class="spin" /> Loading posts…
        </div>
      {:else if filtered.length === 0}
        <div class="text-center" style="padding: 64px 24px; color: hsl(var(--pg-fg-muted));">
          <Icon name="coffee" size={36} style="opacity: 0.4;" />
          <p style="margin-top: 12px;">No posts match that filter yet.</p>
        </div>
      {/if}

      <!-- Subscribe strip -->
      <div
        class="flex items-center flex-wrap mt-7"
        style="
          gap: 20px; padding: 28px;
          background: linear-gradient(180deg, hsl(var(--pg-surface) / 0.9), hsl(var(--pg-hover) / 0.9));
          border: 1px solid hsl(var(--pg-border)); border-radius: 16px;
        "
      >
        <img src="/assets/cf-gold.png" alt="" loading="lazy" decoding="async" style="width: 56px; height: 56px; flex-shrink: 0;" />
        <div style="flex: 1; min-width: 220px;">
          <h3 style="margin: 0 0 6px; font-size: 20px; font-weight: 700; letter-spacing: -0.01em;">
            Subscribe to the Dev Log
          </h3>
          <p style="margin: 0; font-size: 14px; color: hsl(var(--pg-fg-muted)); line-height: 1.5;">
            Burn 500 $nanas once, and every new post lands on-chain in your inbox — no email, no tracking, just canister-signed updates.
          </p>
        </div>
        <Button variant="default" size="lg" class="!bg-[hsl(45_95%_62%)] !text-[hsl(24_48%_12%)] !border !border-[hsl(32_72%_50%)]" on:click={onSubscribe}>
          <Icon name="fire" size={16} /> Burn 500 to subscribe
        </Button>
      </div>
    </div>

    <!-- Timeline rail -->
    <aside
      class="desktop-only flex-shrink-0"
      style="
        position: sticky; top: 92px; width: 250px; align-self: flex-start;
        padding: 16px 16px 12px;
        background: hsl(var(--pg-surface) / 0.55); border: 1px solid hsl(var(--pg-border));
        border-radius: 14px; max-height: calc(100vh - 110px); overflow: auto;
      "
    >
      <h4
        class="flex items-center gap-1.5 uppercase font-bold m-0 mb-3.5"
        style="font-size: 10.5px; letter-spacing: 0.12em; color: hsl(var(--pg-fg-muted));"
      >
        <Icon name="git-commit" size={13} /> Timeline
      </h4>
      <div class="relative">
        <div
          style="
            position: absolute; left: 7px; top: 4px; bottom: 4px; width: 2px;
            background: linear-gradient(180deg, hsl(24 40% 30%), hsl(26 30% 74%));
          "
        ></div>
        {#each posts as p (p.slug)}
          <a
            href="/blog/{p.slug}"
            class="timeline-item relative block no-underline text-primary"
            style="
              padding: 8px 0 12px 24px;
              border-radius: 6px;
              transition: background .15s;
            "
            on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(var(--pg-hover) / 0.5)')}
            on:mouseleave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <span
              style="
                position: absolute; left: 0; top: 11px;
                width: 16px; height: 12px; border-radius: 50%;
                background: linear-gradient(135deg, hsl({CATEGORIES[p.cat]?.hue ?? 24} 55% 55%), hsl({CATEGORIES[p.cat]?.hue ?? 24} 55% 35%));
                box-shadow: 0 0 0 3px hsl(var(--pg-surface) / 0.55), 0 1px 2px hsl(24 30% 20% / 0.3);
                transform: rotate(-20deg);
              "
            >
              <span
                style="
                  position: absolute; left: 50%; top: 0; bottom: 0; width: 1px;
                  background: hsl(24 40% 20% / 0.6);
                  transform: translateX(-50%) rotate(20deg);
                "
              ></span>
            </span>
            <div style="font-size: 11px; color: hsl(var(--pg-fg-muted)); margin-bottom: 2px;">{fmtDate(p.date)}</div>
            <div
              class="overflow-hidden"
              style="
                font-size: 13px; font-weight: 500; line-height: 1.3;
                display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
              "
            >{p.title}</div>
          </a>
        {/each}
      </div>
    </aside>
  </div>
</div>
