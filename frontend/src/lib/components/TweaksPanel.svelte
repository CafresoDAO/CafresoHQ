<script>
  import Icon from './Icon.svelte';
  import { tweaks, tweaksOpen } from '$lib/stores/blog.js';

  $: isOpen = $tweaksOpen;

  function seg(active) {
    return `flex-1 border-none cursor-pointer transition-colors
      px-2 py-1.5 rounded-md text-xs
      ${active ? 'bg-white font-semibold text-primary shadow-sm' : 'bg-transparent text-muted-foreground font-medium'}`;
  }
</script>

{#if isOpen}
  <div
    class="fade-up fixed z-[40] shadow-xl"
    style="
      bottom: 20px; right: 20px; width: 280px;
      background: hsl(var(--pg-surface) / 0.92);
      backdrop-filter: blur(16px) saturate(140%);
      -webkit-backdrop-filter: blur(16px) saturate(140%);
      border: 1px solid hsl(var(--pg-border));
      border-radius: 14px; padding: 16px;
      font-size: 13px;
    "
    role="dialog"
  >
    <div class="flex items-center justify-between mb-2.5">
      <div class="font-bold text-sm" style="letter-spacing: -0.01em;">Tweaks</div>
      <button
        on:click={() => tweaksOpen.set(false)}
        class="bg-transparent border-none cursor-pointer"
        style="color: hsl(var(--pg-fg-muted));"
        aria-label="Close tweaks"
      >
        <Icon name="x" size={16} />
      </button>
    </div>

    <div class="flex flex-col gap-1.5 mb-3.5">
      <h4 class="uppercase text-xs font-semibold m-0" style="letter-spacing: 0.06em; color: hsl(var(--pg-fg-muted));">Density</h4>
      <div class="flex gap-[3px] p-[3px] rounded-lg" style="background: hsl(var(--pg-border));">
        {#each ['cozy', 'compact'] as v}
          <button on:click={() => tweaks.update((t) => ({ ...t, density: v }))} class={seg($tweaks.density === v)}>
            {v.charAt(0).toUpperCase() + v.slice(1)}
          </button>
        {/each}
      </div>
    </div>

    <div class="flex flex-col gap-1.5 mb-3.5">
      <h4 class="uppercase text-xs font-semibold m-0" style="letter-spacing: 0.06em; color: hsl(var(--pg-fg-muted));">Burn interaction</h4>
      <div class="flex gap-[3px] p-[3px] rounded-lg" style="background: hsl(var(--pg-border));">
        {#each [['hold', 'Hold'], ['slider', 'Slider'], ['quick', 'Quick']] as [v, l]}
          <button on:click={() => tweaks.update((t) => ({ ...t, burnModel: v }))} class={seg($tweaks.burnModel === v)}>{l}</button>
        {/each}
      </div>
      <div class="text-[11px] mt-0.5" style="color: hsl(var(--pg-fg-muted));">
        {#if $tweaks.burnModel === 'hold'}Tap-and-hold fills a ring — tactile, prevents misclicks.{/if}
        {#if $tweaks.burnModel === 'slider'}Classic slider — fine control, slower.{/if}
        {#if $tweaks.burnModel === 'quick'}Four preset amounts — fastest, least nuanced.{/if}
      </div>
    </div>

    <div class="flex flex-col gap-1.5 mb-3.5">
      <h4 class="uppercase text-xs font-semibold m-0" style="letter-spacing: 0.06em; color: hsl(var(--pg-fg-muted));">Pixel-art decoration</h4>
      <div class="flex gap-[3px] p-[3px] rounded-lg" style="background: hsl(var(--pg-border));">
        {#each [['on', 'On'], ['off', 'Off']] as [v, l]}
          <button on:click={() => tweaks.update((t) => ({ ...t, pixelArt: v }))} class={seg($tweaks.pixelArt === v)}>{l}</button>
        {/each}
      </div>
    </div>

    <div class="text-[11px] pt-2.5" style="border-top: 1px dashed hsl(var(--pg-border)); color: hsl(var(--pg-fg-muted));">
      Try <b>Burn interaction</b> — open a post and tap the big burn button.
    </div>
  </div>
{/if}

<button
  on:click={() => tweaksOpen.update((v) => !v)}
  aria-label="Tweaks"
  class="fixed z-[39] cursor-pointer"
  style="
    bottom: 20px; right: 20px;
    width: 44px; height: 44px; border-radius: 999px;
    background: hsl(var(--pg-solid)); color: hsl(var(--pg-solid-fg));
    border: none;
    box-shadow: 0 10px 20px -6px hsl(24 35% 15% / 0.35);
    display: {isOpen ? 'none' : 'flex'};
    align-items: center; justify-content: center;
  "
>
  <Icon name="sliders" size={20} />
</button>
