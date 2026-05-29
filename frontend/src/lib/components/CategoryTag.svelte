<script>
  import Icon from './Icon.svelte';
  import { CATEGORIES } from '$lib/data/blog.js';
  export let cat;
  /** @type {'default' | 'sm'} */
  export let size = 'default';
  $: meta = CATEGORIES[cat] || { label: cat, icon: 'tag', hue: 24 };
  $: small = size === 'sm';
</script>

<span
  class="inline-flex items-center gap-1.5 uppercase font-semibold whitespace-nowrap"
  style="
    font-size: {small ? '10.5px' : '11px'};
    letter-spacing: 0.08em;
    background: hsl({meta.hue} 50% 92%);
    color: hsl({meta.hue} 50% 22%);
    border: 1px solid hsl({meta.hue} 40% 80%);
    padding: {small ? '2px 8px' : '4px 10px'};
    border-radius: 999px;
  "
>
  <Icon name={meta.icon} size={small ? 12 : 13} />
  {meta.label}
</span>
