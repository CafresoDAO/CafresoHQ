<script>
  import Avatar from './Avatar.svelte';
  import Icon from './Icon.svelte';
  import GoldCoin from './GoldCoin.svelte';
  import Button from './Button.svelte';
  import MentionText from './MentionText.svelte';

  export let comments = [];
  export let onPost = (text) => {};
  // Moderation overlay (optional — pages that load it pass these through).
  // hiddenKeys: Set of "slug#id" keys currently hidden. isAdmin unlocks the
  // hide/unhide controls; non-admins simply never see hidden comments.
  export let hiddenKeys = null;
  export let isAdmin = false;
  export let onToggleHidden = null; // (comment, nowHidden) => Promise
  export let modSlug = '';          // slug used to build the comment's key

  let text = '';
  let busyKey = null;

  $: keyOf = (c) => `${modSlug}#${c.id}`;
  $: isHidden = (c) => !!(hiddenKeys && c.id != null && hiddenKeys.has(keyOf(c)));
  $: visibleComments = comments.filter((c) => isAdmin || !isHidden(c));

  async function toggleHidden(c) {
    if (!onToggleHidden || busyKey) return;
    busyKey = keyOf(c);
    try { await onToggleHidden(c, !isHidden(c)); }
    finally { busyKey = null; }
  }

  function submit() {
    if (text.trim().length < 3) return;
    onPost(text.trim());
    text = '';
  }
</script>

<div class="mt-7">
  <div class="flex items-baseline gap-3 mb-5">
    <h2 style="font-size: 22px; font-weight: 700; margin: 0;">Comments</h2>
    <span class="text-[13px]" style="color: hsl(var(--pg-fg-muted));">
      {comments.length} from the community
    </span>
  </div>

  <!-- Composer: stake 0.05 sGLDT -->
  <div
    class="rounded-xl mb-7"
    style="background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border)); padding: 16px;"
  >
    <div class="flex gap-3 items-start">
      <Avatar name="you" hue={180} size={34} />
      <div class="flex-1">
        <textarea
          bind:value={text}
          placeholder="Share what you think. Comments require a 0.05 sGLDT stake — forfeited if flagged, returned if not."
          class="w-full border-none outline-none resize-y bg-transparent text-sm leading-normal"
          style="min-height: 60px; font-family: inherit; color: hsl(var(--pg-fg));"
        ></textarea>
        <div
          class="flex items-center flex-wrap pt-2.5"
          style="gap: 10px; border-top: 1px dashed hsl(var(--pg-border));"
        >
          <div class="inline-flex items-center gap-1.5 text-xs" style="color: hsl(var(--pg-fg-muted));">
            <Icon name="shield-check" size={14} style="color: hsl(var(--brand-leaf));" />
            Signed with Internet Identity
          </div>
          <span class="flex-1"></span>
          <span
            class="inline-flex items-center gap-1 font-semibold text-xs"
            style="background: hsl(45 80% 94%); border: 1px solid hsl(45 75% 78%); padding: 4px 10px; border-radius: 999px;"
          >
            <Icon name="fire" size={12} style="color: hsl(32 72% 50%);" />
            Stake 0.05 <GoldCoin size={12} />
          </span>
          <Button variant="default" size="sm" disabled={text.trim().length < 3} on:click={submit}>
            Post comment
          </Button>
        </div>
      </div>
    </div>
  </div>

  <div class="flex flex-col gap-6">
    {#if comments.length === 0}
      <p class="text-[13.5px] m-0 py-6 text-center" style="color: hsl(var(--pg-fg-muted));">
        No comments yet — be the first to share your thoughts.
      </p>
    {/if}
    {#each visibleComments as c (c.id ?? c.date + c.author.name)}
      <div class="flex flex-col gap-4" style={isAdmin && isHidden(c) ? 'opacity:0.45' : ''}>
        <div class="flex gap-3">
          <Avatar name={c.author.name} hue={c.author.hue} size={36} />
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap mb-1">
              <span class="font-semibold text-[13.5px]">{c.author.name}</span>
              {#if c.author.isAuthor}
                <span
                  class="uppercase font-bold"
                  style="font-size: 10px; letter-spacing: 0.06em; background: hsl(var(--pg-solid)); color: hsl(var(--pg-solid-fg)); padding: 2px 7px; border-radius: 999px;"
                >Author</span>
              {/if}
              <span class="text-[11px]" style="color: hsl(var(--pg-fg-muted));">{c.author.role}</span>
              <span class="text-[11px]" style="color: hsl(var(--pg-fg-muted));">· {c.date}</span>
              {#if isAdmin && isHidden(c)}
                <span
                  class="uppercase font-bold"
                  style="font-size: 10px; letter-spacing: 0.06em; background: hsl(0 60% 92%); color: hsl(0 55% 38%); border: 1px solid hsl(0 55% 80%); padding: 2px 7px; border-radius: 999px;"
                  title="Hidden from the community by moderation — only admins see it"
                >Hidden</span>
              {/if}
              {#if c.burned > 0}
                <span
                  class="inline-flex items-center gap-[3px] font-semibold"
                  style="
                    font-size: 11px; color: hsl(24 40% 22%);
                    background: hsl(45 80% 92%); border: 1px solid hsl(45 75% 78%);
                    padding: 2px 7px; border-radius: 999px;
                  "
                >
                  <Icon name="fire" size={11} style="color: hsl(32 72% 50%);" /> {c.burned}
                </span>
              {/if}
            </div>
            <p class="m-0 text-sm" style="line-height: 1.55;"><MentionText text={c.text} /></p>
            <!-- Reply / Tip / Verify aren't built yet. They previously rendered
                 as normal buttons with no handler at all — clickable-looking
                 controls that silently did nothing. Until they're wired, say so:
                 disabled + a title, matching the "coming soon" treatment used on
                 unavailable products and the SneedDAO teaser. -->
            <div class="flex gap-3.5 mt-2 text-xs" style="color: hsl(var(--pg-fg-muted));">
              <button
                disabled
                title="Threaded replies are coming with the on-chain comment upgrade"
                class="comment-soon bg-transparent border-none p-0 inline-flex items-center gap-1"
                style="color: inherit; font-family: inherit; font-size: 12px;"
              >
                <Icon name="arrow-bend-up-left" size={13} /> Reply
              </button>
              <button
                disabled
                title="Tipping a comment is coming with the on-chain comment upgrade"
                class="comment-soon bg-transparent border-none p-0 inline-flex items-center gap-1"
                style="color: inherit; font-family: inherit; font-size: 12px;"
              >
                <Icon name="fire" size={13} /> Tip
              </button>
              <button
                disabled
                title="Per-comment receipts are coming with the on-chain comment upgrade"
                class="comment-soon bg-transparent border-none p-0"
                style="color: inherit; font-family: inherit; font-size: 12px;"
              >
                Verify on-chain
              </button>
              {#if isAdmin && onToggleHidden && c.id != null}
                <button
                  class="bg-transparent border-none p-0 inline-flex items-center gap-1"
                  style="color: hsl(0 55% 45%); font-family: inherit; font-size: 12px; cursor: pointer;"
                  disabled={busyKey === keyOf(c)}
                  title={isHidden(c)
                    ? 'Restore this comment for everyone (signed admin update)'
                    : 'Hide this comment from the community (signed admin update — the comment stays on-chain)'}
                  on:click={() => toggleHidden(c)}
                >
                  <Icon name={isHidden(c) ? 'eye' : 'eye-slash'} size={13} />
                  {busyKey === keyOf(c) ? 'Saving…' : isHidden(c) ? 'Unhide' : 'Hide'}
                </button>
              {/if}
            </div>
          </div>
        </div>
        {#if c.replies}
          {#each c.replies as r (r.date + r.author.name)}
            <div class="flex gap-3" style="padding-left: 44px;">
              <Avatar name={r.author.name} hue={r.author.hue} size={36} />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap mb-1">
                  <span class="font-semibold text-[13.5px]">{r.author.name}</span>
                  {#if r.author.isAuthor}
                    <span
                      class="uppercase font-bold"
                      style="font-size: 10px; letter-spacing: 0.06em; background: hsl(var(--pg-solid)); color: hsl(var(--pg-solid-fg)); padding: 2px 7px; border-radius: 999px;"
                    >Author</span>
                  {/if}
                  <span class="text-[11px]" style="color: hsl(var(--pg-fg-muted));">{r.author.role}</span>
                  <span class="text-[11px]" style="color: hsl(var(--pg-fg-muted));">· {r.date}</span>
                </div>
                <p class="m-0 text-sm" style="line-height: 1.55;"><MentionText text={r.text} /></p>
              </div>
            </div>
          {/each}
        {/if}
      </div>
    {/each}
  </div>
</div>

<style>
  .comment-soon { cursor: not-allowed; opacity: 0.5; }
</style>
