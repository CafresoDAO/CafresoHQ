<script>
  import Icon from './Icon.svelte';
  import NanasCoin from './NanasCoin.svelte';

  export let post;
  export let userBurned = 0;
  export let onTip = () => {};

  let saved = false;
  $: saveKey = `cafreso:saved:${post.slug}`;

  import { onMount } from 'svelte';
  onMount(() => {
    try {
      saved = localStorage.getItem(saveKey) === '1';
    } catch {}
  });

  function scrollToComments() {
    document.querySelector('#comments')?.scrollIntoView({ behavior: 'smooth' });
  }

  function toggleSave() {
    saved = !saved;
    try {
      if (saved) localStorage.setItem(saveKey, '1');
      else localStorage.removeItem(saveKey);
    } catch {}
  }

  async function share() {
    const url = typeof location !== 'undefined' ? location.href : '';
    if (navigator.share) {
      try {
        await navigator.share({ title: post.title, url });
      } catch {}
    } else {
      try {
        await navigator.clipboard.writeText(url);
      } catch {}
    }
  }

  function handleReaction(label) {
    if (label === 'Comments') scrollToComments();
    else if (label === 'Save') toggleSave();
    else if (label === 'Share') share();
  }
</script>

<div
  class="desktop-only flex flex-col flex-shrink-0"
  style="
    position: sticky; top: 92px; align-self: flex-start;
    width: 170px; gap: 12px; padding: 16px 14px;
    background: hsl(26 45% 98% / 0.7); border: 1px solid hsl(26 30% 85%);
    border-radius: 14px;
  "
>
  <h4
    class="uppercase font-bold m-0"
    style="font-size: 10.5px; letter-spacing: 0.12em; color: hsl(215 16% 47%);"
  >Reactions</h4>

  <button
    on:click={onTip}
    class="flex flex-col items-center gap-1.5 cursor-pointer"
    style="
      background: {userBurned > 0 ? 'hsl(45 95% 62%)' : 'white'};
      border: 1px solid hsl(32 72% 50%);
      border-radius: 12px; padding: 14px 10px;
      font-family: inherit;
      transition: background .2s, transform .2s;
    "
    on:mouseenter={(e) => (e.currentTarget.style.transform = 'translateY(-2px)')}
    on:mouseleave={(e) => (e.currentTarget.style.transform = 'none')}
  >
    <Icon name="fire" size={28} weight="fill" style="color: hsl(32 72% 45%);" />
    <div style="font-size: 22px; font-weight: 800; letter-spacing: -0.02em; line-height: 1;">
      {(post.burned + userBurned).toLocaleString()}
    </div>
    <div class="inline-flex items-center gap-1 text-[11px]" style="color: hsl(24 40% 22%);">
      <NanasCoin size={11} /> burned
    </div>
    <div
      class="mt-0.5 font-semibold text-[11px] text-white"
      style="padding: 4px 10px; border-radius: 999px; background: hsl(24 48% 12%);"
    >
      {userBurned > 0 ? `You burned ${userBurned}` : 'Tap to burn'}
    </div>
  </button>

  {#each [['chat-circle', post.comments, 'Comments'], ['bookmark-simple', null, 'Save'], ['share-network', null, 'Share']] as [icon, n, label]}
    <button
      aria-label={label}
      on:click={() => handleReaction(label)}
      class="flex items-center gap-2.5 cursor-pointer bg-transparent border-none text-primary text-[13px]"
      style="padding: 8px 6px; border-radius: 8px; font-family: inherit; transition: background .15s;"
      on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(26 40% 92% / 0.6)')}
      on:mouseleave={(e) => (e.currentTarget.style.background = 'transparent')}
    >
      <Icon name={icon} size={17} style="color: hsl(215 16% 47%);" />
      <span class="flex-1 text-left">{label}</span>
      {#if n != null}
        <span class="text-xs" style="color: hsl(215 16% 47%);">{n}</span>
      {/if}
    </button>
  {/each}
</div>
