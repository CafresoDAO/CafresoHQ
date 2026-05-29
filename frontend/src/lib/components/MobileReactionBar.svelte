<script>
  import Icon from './Icon.svelte';
  import NanasCoin from './NanasCoin.svelte';
  export let post;
  export let userBurned = 0;
  export let onTip = () => {};
</script>

<div
  class="mobile-only fixed z-[15] flex items-center"
  style="
    left: 12px; right: 12px; bottom: 78px;
    background: hsl(26 45% 98% / 0.92);
    backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
    border: 1px solid hsl(26 30% 85%); border-radius: 14px;
    padding: 10px; gap: 10px;
    box-shadow: 0 12px 30px -10px hsl(24 35% 15% / 0.3);
  "
>
  <button
    on:click={onTip}
    class="inline-flex items-center gap-1.5 cursor-pointer"
    style="
      background: hsl(45 95% 62%); border: 1px solid hsl(32 72% 50%);
      border-radius: 10px; padding: 8px 14px;
      font-family: inherit; font-size: 13px; font-weight: 600;
    "
  >
    <Icon name="fire" size={16} /> Burn <NanasCoin size={14} />
  </button>
  <div class="flex-1 text-xs" style="line-height: 1.3;">
    <div class="font-semibold">{(post.burned + userBurned).toLocaleString()} burned</div>
    <div style="color: hsl(215 16% 47%);">{post.comments} comments</div>
  </div>
  <button class="bg-transparent border-none cursor-pointer" style="padding: 8px; color: hsl(215 16% 47%);" aria-label="Comments">
    <Icon name="chat-circle" size={18} />
  </button>
  <button class="bg-transparent border-none cursor-pointer" style="padding: 8px; color: hsl(215 16% 47%);" aria-label="Share">
    <Icon name="share-network" size={18} />
  </button>
</div>
