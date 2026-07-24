<svelte:options runes={true} />

<script>
  import { onMount } from 'svelte';
  import Icon from '$lib/components/Icon.svelte';
  import Button from '$lib/components/Button.svelte';
  import Avatar from '$lib/components/Avatar.svelte';
  import { listForumPosts, stripForumPrefix } from '$lib/api/devlog.js';
  import { isAuthenticated, login, authStatus } from '$lib/stores/auth.js';
  import { fmtDate } from '$lib/data/blog.js';
  import { goldFromRaw, fmtGold } from '$lib/gold.js';
  import GoldCoin from '$lib/components/GoldCoin.svelte';

  let posts = $state([]);
  let loading = $state(true);
  let err = $state(null);
  let q = $state('');

  onMount(async () => {
    try {
      const raw = await listForumPosts();
      // Newest threads first — the canister returns insertion order.
      posts = raw.sort(
        (a, b) =>
          String(b.date).localeCompare(String(a.date)) ||
          (b.timestampCreated || 0) - (a.timestampCreated || 0)
      );
    } catch (e) {
      err = String(e?.message || e);
    } finally {
      loading = false;
    }
  });

  const filtered = $derived(
    q.trim()
      ? posts.filter((p) => (p.title + ' ' + (p.excerpt || '')).toLowerCase().includes(q.toLowerCase()))
      : posts
  );
</script>

<svelte:head>
  <title>Forums · Cafreso</title>
  <meta name="description" content="Community forums where anyone with an Internet Identity can start threads, comment, and tip authors in gold (sGLDT). Coffee, DAO proposals, and mining strategy." />
</svelte:head>

<div class="mx-auto" style="max-width: 900px; padding: 28px 18px 48px;">
  <div class="text-center mb-6 sm:mb-8">
    <div class="inline-flex items-center gap-2 text-[12.5px] font-medium rounded-full px-3 py-1 mb-3"
      style="background: hsl(var(--pg-hover) / 0.7); border: 1px solid hsl(var(--pg-border));"
    >
      <Icon name="chats-circle" size={14} /> Community · open to everyone
    </div>
    <h1 class="font-extrabold m-0 leading-[1.05]" style="font-size: clamp(32px, 8vw, 48px); letter-spacing: -0.03em;">
      Forums
    </h1>
    <p class="mx-auto text-[14.5px] sm:text-[16px] leading-[1.55] mt-3 max-w-[52ch]" style="color: hsl(var(--pg-fg-muted));">
      Anyone with an Internet Identity can start a thread, comment, or tip
      other authors with gold (sGLDT). Separate from the <a href="/blog" class="underline" style="color: hsl(38 85% 30%);">Dev Log</a>, which stays curated by the core team.
    </p>
  </div>

  <div class="flex flex-col sm:flex-row gap-2 items-stretch sm:items-center mb-5">
    <div
      class="flex-1 flex items-center gap-2 rounded-[12px] px-3 py-2"
      style="background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));"
    >
      <Icon name="magnifying-glass" size={14} class="text-muted-foreground" />
      <input
        bind:value={q}
        placeholder="Search threads…"
        aria-label="Search threads"
        class="flex-1 min-w-0 text-[13.5px] bg-transparent border-none outline-none text-primary"
      />
      {#if q}
        <button
          type="button"
          on:click={() => (q = '')}
          class="text-[11px] cursor-pointer bg-transparent border-none text-muted-foreground"
          aria-label="Clear search"
        >
          Clear
        </button>
      {/if}
    </div>
    {#if $isAuthenticated}
      <Button href="/forums/new">
        <Icon name="plus" size={14} /> New thread
      </Button>
    {:else}
      <Button on:click={login} disabled={$authStatus === 'logging-in'}>
        <Icon name="fingerprint" size={14} />
        {$authStatus === 'logging-in' ? 'Connecting…' : 'Sign in to post'}
      </Button>
    {/if}
  </div>

  {#if loading}
    <div class="rounded-[14px] px-4 py-10 text-center text-[13.5px] text-muted-foreground"
      style="background: hsl(var(--pg-surface)); border: 1px solid hsl(var(--pg-border));"
    >
      <Icon name="spinner-gap" size={16} /> Loading threads…
    </div>
  {:else if err}
    <div class="rounded-[14px] px-4 py-6 text-[13.5px]"
      style="background: hsl(var(--pg-danger-bg)); color: hsl(var(--pg-danger-fg)); border: 1px solid hsl(var(--pg-danger-border));"
    >
      <Icon name="warning" size={14} /> {err}
    </div>
  {:else if filtered.length === 0}
    <div class="rounded-[14px] px-4 py-10 text-center"
      style="background: hsl(var(--pg-surface)); border: 1px dashed hsl(var(--pg-border));"
    >
      <Icon name="chats-circle" size={28} style="color: hsl(32 56% 35%);" />
      <h3 class="font-bold text-[17px] mt-3 mb-1.5 text-primary">
        {q ? 'No matches' : 'Be the first voice'}
      </h3>
      <p class="text-[13.5px] mx-auto mb-4 max-w-[380px] text-muted-foreground">
        {q
          ? 'Try a different search term.'
          : 'Open the first thread — coffee gossip, DAO proposals, mining strategy, anything goes. Tips in gold reward good writing.'}
      </p>
      {#if !q && $isAuthenticated}
        <Button href="/forums/new">
          <Icon name="plus" size={14} /> Start a thread
        </Button>
      {/if}
    </div>
  {:else}
    <div
      class="rounded-[14px] overflow-hidden"
      style="background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border));"
    >
      {#each filtered as p, i (p.slug)}
        {@const viewSlug = stripForumPrefix(p.slug)}
        <a
          href="/forums/{viewSlug}"
          class="block no-underline px-4 sm:px-5 py-4 sm:py-5"
          style="color: inherit; {i > 0 ? 'border-top: 1px solid hsl(var(--pg-border));' : ''}"
        >
          <div class="flex items-start gap-3 sm:gap-4">
            <Avatar name={p.author?.name || 'Guest'} hue={p.author?.hue || 24} size={36} />
            <div class="flex-1 min-w-0">
              <div class="font-bold text-[15.5px] sm:text-[16px] leading-[1.3] mb-0.5 text-primary"
                style="text-wrap: pretty;"
              >
                {p.title}
              </div>
              <div class="text-[12.5px] mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-muted-foreground">
                <span class="font-medium">{p.author?.name || 'Guest'}</span>
                <span>·</span>
                <span>{fmtDate(p.date)}</span>
                <span>·</span>
                <span>~{p.readMin || 1} min</span>
              </div>
              <p class="text-[13.5px] leading-[1.55] mb-2 line-clamp-2" style="color: hsl(var(--pg-fg-muted));">
                {p.excerpt}
              </p>
              <div class="flex items-center gap-3 text-[11.5px] text-muted-foreground">
                <span class="inline-flex items-center gap-1 tabular-nums">
                  <GoldCoin size={12} /> {fmtGold(goldFromRaw(p.burned))} tipped
                </span>
                <span class="inline-flex items-center gap-1 tabular-nums">
                  <Icon name="chat-circle" size={12} /> {p.comments}
                </span>
              </div>
            </div>
            <Icon name="caret-right" size={14} class="text-muted-foreground" style="margin-top: 4px;" />
          </div>
        </a>
      {/each}
    </div>
  {/if}
</div>
