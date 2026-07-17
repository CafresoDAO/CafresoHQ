<script>
  import { toast } from '$lib/stores/cart.js';
</script>

{#if $toast}
  <div
    class="fixed bottom-6 left-1/2 z-30 text-sm rounded-md px-4 py-2.5"
    style="transform: translateX(-50%);
      background: hsl(var(--pg-solid));
      color: hsl(var(--pg-solid-fg));
      box-shadow: 0 10px 15px rgba(0,0,0,.1);"
    role="status"
  >{$toast}</div>
{/if}
