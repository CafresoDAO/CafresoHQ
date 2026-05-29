<script>
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Footer from '$lib/components/Footer.svelte';
  import CartDrawer from '$lib/components/CartDrawer.svelte';
  import Toast from '$lib/components/Toast.svelte';
  import MobileNav from '$lib/components/MobileNav.svelte';
  import BurnTipModal from '$lib/components/BurnTipModal.svelte';
  import BBWaitlistModal from '$lib/components/BBWaitlistModal.svelte';
  import AISearchModal from '$lib/components/AISearchModal.svelte';
  import { initAuth } from '$lib/stores/auth.js';
  import { startPrices } from '$lib/stores/prices.js';
  import { onMount } from 'svelte';

  // Start the II session + the 60s DEX price poll together — the wallet
  // row USD values and the portfolio total both read from `stores/prices.js`
  // which calls CoinGecko + GeckoTerminal (ICPSwap) under the hood.
  onMount(() => {
    initAuth();
    startPrices();
  });
</script>

<div class="min-h-screen flex flex-col">
  <PageHeader />
  <main class="flex-1"><slot /></main>
  <Footer />
</div>

<CartDrawer />
<Toast />
<MobileNav />
<BurnTipModal />
<BBWaitlistModal />
<AISearchModal />
