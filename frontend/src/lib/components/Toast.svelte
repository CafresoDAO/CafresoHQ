<script>
  import { toast } from '$lib/stores/cart.js';
</script>

{#if $toast}
  <div
    class="fixed bottom-6 left-1/2 z-30 text-white text-sm rounded-md px-4 py-2.5"
    style="transform: translateX(-50%);
      background: hsl(222 47% 11%);
      box-shadow: 0 10px 15px rgba(0,0,0,.1);"
    role="status"
  >{$toast}</div>
{/if}
