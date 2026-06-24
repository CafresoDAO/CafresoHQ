<script>
  import { goto } from '$app/navigation';
  import { cart, cartOpen, cartTotal } from '$lib/stores/cart.js';
  import { productImage, usd } from '$lib/data/products.js';
  import Icon from './Icon.svelte';
  import Button from './Button.svelte';

  function close() {
    cartOpen.set(false);
  }
  function checkout() {
    close();
    goto('/checkout');
  }
</script>

{#if $cartOpen}
  <div
    on:click={close}
    class="fixed inset-0 z-[15]"
    style="background: rgba(0,0,0,0.4);"
    role="presentation"
  ></div>
  <div
    class="fixed right-0 top-0 bottom-0 w-full z-[20] flex flex-col"
    style="max-width: 520px; background: hsl(26 30% 74%);"
  >
    <div class="flex justify-between items-center px-5 py-4">
      <h1 class="text-xl font-bold m-0">
        {$cart.length}
        {$cart.length === 1 ? 'item' : 'items'}
      </h1>
      <button on:click={close} aria-label="Close" class="bg-transparent border-none cursor-pointer">
        <Icon name="x" size={24} />
      </button>
    </div>
    <hr class="m-0 border-none" style="border-top: 1px solid hsl(26 30% 60%);" />

    {#if $cart.length === 0}
      <div class="flex-1 flex flex-col justify-center gap-6 p-10">
        <p class="text-center m-0">Your cart is empty</p>
        <button
          on:click={close}
          class="h-12 w-full border-none cursor-pointer font-bold text-[15px] text-black"
          style="background: hsl(134 61% 70%); transition: background .15s;"
          on:mouseenter={(e) => (e.currentTarget.style.background = 'hsl(142 71% 45%)')}
          on:mouseleave={(e) => (e.currentTarget.style.background = 'hsl(134 61% 70%)')}
        >Start shopping</button>
      </div>
    {:else}
      <div class="flex-1 overflow-y-auto px-5 py-2">
        {#each $cart as it, ix}
          <div
            class="flex gap-4 py-4 items-center"
            style="border-bottom: 1px solid hsl(26 30% 60%);"
          >
            <img src={productImage(it.img)} alt="" class="w-16 h-16 object-contain" />
            <div class="flex-1">
              <div class="font-medium text-sm">{it.name}</div>
              <div class="text-[13px] mt-1 inline-flex items-center gap-1">
                {it.qty} × {it.price.toLocaleString()}
                <img src="/assets/nanas-coin.png" alt="" class="w-[14px]" />
              </div>
            </div>
            <button
              on:click={() => cart.remove(ix)}
              aria-label={`Remove ${it.name} from cart`}
              class="bg-transparent border-none cursor-pointer text-muted-foreground"
            ><Icon name="trash" size={18} /></button>
          </div>
        {/each}
      </div>
      <div class="p-10 flex justify-center">
        <Button
          variant="default"
          size="lg"
          class="!h-auto !py-3 !px-7 !flex-col !gap-0.5"
          on:click={checkout}
        >
          <span class="font-bold text-white">Checkout</span>
          <span class="text-[13px] font-normal inline-flex items-center gap-1.5">
            {$cartTotal.toLocaleString()} Nanas
            <img src="/assets/nanas-coin.png" alt="" class="w-[18px]" />
            <span class="text-[11px] ml-1 opacity-80">${usd($cartTotal)} USD</span>
          </span>
        </Button>
      </div>
    {/if}
  </div>
{/if}
