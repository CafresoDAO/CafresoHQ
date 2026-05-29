<script>
  /** @type {'default' | 'secondary' | 'outline' | 'ghost' | 'destructive' | 'link'} */
  export let variant = 'default';
  /** @type {'default' | 'sm' | 'lg' | 'icon'} */
  export let size = 'default';
  /** @type {'button' | 'submit' | 'reset'} */
  export let type = 'button';
  export let disabled = false;
  export let href = undefined;
  let className = '';
  export { className as class };

  const variantCls = {
    default: 'bg-primary text-primary-foreground hover:bg-primary/90',
    secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
    outline:
      'bg-white text-primary border border-border hover:bg-accent hover:text-accent-foreground',
    ghost: 'bg-transparent text-primary hover:bg-accent hover:text-accent-foreground',
    destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
    link: 'bg-transparent text-primary underline-offset-4 hover:underline'
  };
  const sizeCls = {
    default: 'h-10 px-4 text-sm',
    sm: 'h-9 px-3 text-sm',
    lg: 'h-11 px-8 text-[15px]',
    icon: 'h-10 w-10'
  };
  $: cls =
    'inline-flex items-center justify-center gap-2 font-medium rounded-md whitespace-nowrap transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 ' +
    variantCls[variant] +
    ' ' +
    sizeCls[size] +
    ' ' +
    className;
</script>

{#if href}
  <a {href} class={cls} on:click>
    <slot />
  </a>
{:else}
  <button {type} {disabled} class={cls} on:click>
    <slot />
  </button>
{/if}
