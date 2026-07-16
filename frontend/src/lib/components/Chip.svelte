<script>
  import Icon from './Icon.svelte';
  export let active = false;
  export let icon = '';
</script>

<button
  on:click
  class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-[13px] font-medium whitespace-nowrap transition-colors cursor-pointer"
  style="
    background: {active ? 'hsl(var(--pg-solid))' : 'hsl(var(--pg-hover) / 0.7)'};
    color: {active ? 'hsl(var(--pg-solid-fg))' : 'hsl(var(--pg-fg))'};
    border: {active ? 'none' : '1px solid hsl(var(--pg-border))'};
  "
>
  {#if icon}<Icon name={icon} size={15} />{/if}
  <slot />
</button>
