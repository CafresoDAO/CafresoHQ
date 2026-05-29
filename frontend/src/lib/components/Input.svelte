<script>
  export let label = '';
  export let error = '';
  export let value = '';
  export let name = '';
  export let type = 'text';
  export let placeholder = '';
  let className = '';
  export { className as class };
</script>

<label class="flex flex-col gap-1.5 text-sm font-medium text-primary {className}">
  {#if label}<span>{label}</span>{/if}
  <input
    {type}
    {name}
    {placeholder}
    bind:value
    class="h-10 rounded-md px-3 text-sm bg-white text-primary outline-none border
    {error ? 'border-destructive' : 'border-border'}
    focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
  />
  {#if error}<span class="text-destructive text-xs font-normal">{error}</span>{/if}
</label>
