<script>
  import Icon from './Icon.svelte';
  export let active = false;
  export let icon = '';
</script>

<button
  on:click
  class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-[13px] font-medium whitespace-nowrap transition-colors cursor-pointer"
  style="
    background: {active ? 'hsl(222 47% 11%)' : 'hsl(26 45% 96% / 0.7)'};
    color: {active ? 'white' : 'hsl(222 47% 11%)'};
    border: {active ? 'none' : '1px solid hsl(26 30% 85%)'};
  "
>
  {#if icon}<Icon name={icon} size={15} />{/if}
  <slot />
</button>
