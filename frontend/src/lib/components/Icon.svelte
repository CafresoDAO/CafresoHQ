<script>
  /** @type {string} */
  export let name;
  /** @type {number} */
  export let size = 18;
  /** @type {'regular' | 'fill'} */
  export let weight = 'regular';
  let className = '';
  export { className as class };
  export let style = '';
  $: cls = weight === 'fill' ? `ph-fill ph-${name}` : `ph ph-${name}`;
</script>

<i
  class="{cls} {className}"
  style="font-size: {size}px; line-height: 1; {style}"
  aria-hidden="true"
></i>
