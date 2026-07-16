<script>
  import Avatar from './Avatar.svelte';
  import Icon from './Icon.svelte';
  import NanasCoin from './NanasCoin.svelte';
  import Button from './Button.svelte';
  import MentionText from './MentionText.svelte';

  export let comments = [];
  export let onPost = (text) => {};

  let text = '';

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

  <!-- Composer: stake 50 $nanas -->
  <div
    class="rounded-xl mb-7"
    style="background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border)); padding: 16px;"
  >
    <div class="flex gap-3 items-start">
      <Avatar name="you" hue={180} size={34} />
      <div class="flex-1">
        <textarea
          bind:value={text}
          placeholder="Share what you think. Comments require a 50 $nanas stake — burned if flagged, returned if not."
          class="w-full border-none outline-none resize-y bg-transparent text-sm leading-normal"
          style="min-height: 60px; font-family: inherit; color: hsl(var(--pg-fg));"
        ></textarea>
        <div
          class="flex items-center flex-wrap pt-2.5"
          style="gap: 10px; border-top: 1px dashed hsl(var(--pg-border));"
        >
          <div class="inline-flex items-center gap-1.5 text-xs" style="color: hsl(var(--pg-fg-muted));">
            <Icon name="shield-check" size={14} style="color: hsl(112 43% 45%);" />
            Signed with Internet Identity
          </div>
          <span class="flex-1"></span>
          <span
            class="inline-flex items-center gap-1 font-semibold text-xs"
            style="background: hsl(45 80% 94%); border: 1px solid hsl(45 75% 78%); padding: 4px 10px; border-radius: 999px;"
          >
            <Icon name="fire" size={12} style="color: hsl(32 72% 50%);" />
            Stake 50 <NanasCoin size={12} />
          </span>
          <Button variant="default" size="sm" disabled={text.trim().length < 3} on:click={submit}>
            Post comment
          </Button>
        </div>
      </div>
    </div>
  </div>

  <div class="flex flex-col gap-6">
    {#each comments as c (c.date + c.author.name)}
      <div class="flex flex-col gap-4">
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
            <div class="flex gap-3.5 mt-2 text-xs" style="color: hsl(var(--pg-fg-muted));">
              <button class="bg-transparent border-none p-0 inline-flex items-center gap-1 cursor-pointer" style="color: inherit; font-family: inherit; font-size: 12px;">
                <Icon name="arrow-bend-up-left" size={13} /> Reply
              </button>
              <button class="bg-transparent border-none p-0 inline-flex items-center gap-1 cursor-pointer" style="color: inherit; font-family: inherit; font-size: 12px;">
                <Icon name="fire" size={13} /> Tip
              </button>
              <button class="bg-transparent border-none p-0 cursor-pointer" style="color: inherit; font-family: inherit; font-size: 12px;">
                Verify on-chain
              </button>
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
