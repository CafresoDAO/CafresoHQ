<script>
  import { theme } from '$lib/stores/theme.js';

  /** Explicit override. When omitted the logo follows the active theme:
   *  black wordmark in light, white wordmark in dark. Callers that need a
   *  fixed rendering (e.g. the design gallery) pass a variant to opt out.
   *  @type {'black' | 'white' | 'gold' | undefined} */
  export let variant = undefined;
  /** @type {number} */
  export let size = 36;

  $: resolved = variant ?? ($theme === 'dark' ? 'white' : 'black');
</script>

<img
  src="/assets/cf-{resolved}.png"
  alt="Cafreso"
  style="width: {size}px; height: auto; display: inline-block;"
/>
