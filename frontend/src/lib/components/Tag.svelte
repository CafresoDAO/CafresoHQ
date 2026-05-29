<script>
  export let active = false;
</script>

<button
  class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full border-none text-[13px] font-medium transition-colors
  {active ? 'bg-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'}"
  on:click
>
  <slot />
</button>
