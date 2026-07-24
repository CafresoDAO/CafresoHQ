<script>
  import PageHeader from '$lib/components/PageHeader.svelte';
  import Footer from '$lib/components/Footer.svelte';
  import CartDrawer from '$lib/components/CartDrawer.svelte';
  import Toast from '$lib/components/Toast.svelte';
  import MobileNav from '$lib/components/MobileNav.svelte';
  import BurnTipModal from '$lib/components/BurnTipModal.svelte';
  import BBWaitlistModal from '$lib/components/BBWaitlistModal.svelte';
  import AISearchModal from '$lib/components/AISearchModal.svelte';
  import WeatherModal from '$lib/components/WeatherModal.svelte';
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

<a href="#main-content" class="skip-link">Skip to main content</a>

<div class="min-h-screen flex flex-col">
  <PageHeader />
  <main id="main-content" class="flex-1"><slot /></main>
  <Footer />
</div>

<CartDrawer />
<Toast />
<MobileNav />
<BurnTipModal />
<BBWaitlistModal />
<AISearchModal />
<WeatherModal />

<style>
  /* Visually hidden until keyboard focus — lets keyboard/screen-reader
     users jump straight past the header to the page content. */
  .skip-link {
    position: absolute;
    left: 12px;
    top: -48px;
    z-index: 100;
    padding: 8px 16px;
    border-radius: 8px;
    background: hsl(260 70% 50%);
    color: #fff;
    font-size: 14px;
    font-weight: 600;
    text-decoration: none;
    transition: top 0.18s ease;
  }
  .skip-link:focus {
    top: 12px;
  }

  /* Visible focus ring for keyboard users across the app. */
  :global(a:focus-visible),
  :global(button:focus-visible) {
    outline: 2px solid hsl(260 70% 50%);
    outline-offset: 2px;
  }
</style>
