<script>
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import {
    endpointUrl,
    endpointReady,
    probeHealth,
    detectLocalCompanion,
    setEndpoint
  } from '$lib/stores/endpoint.js';
  import { isAuthenticated } from '$lib/stores/auth.js';
  import {
    ensureHqSession, endpointNeedsSession, hqSessionReady
  } from '$lib/api/hqSession.js';
  import Header from '$lib/components/Header.svelte';
  import AISearchModal from '$lib/components/AISearchModal.svelte';

  let { children } = $props();

  // Endpoint detection is specific to the HQ control plane.
  onMount(async () => {
    if (!get(endpointUrl)) {
      const local = await detectLocalCompanion();
      if (local) setEndpoint(local);
    }
    if (get(endpointUrl)) {
      probeHealth().catch(() => {});
    }
  });

  // Install the container session cookie for ANY /hq page that talks to the
  // gateway (Chat, Vault, Search, App) — so they work even when opened directly,
  // not only after visiting the HQ app page.
  $effect(() => {
    if ($isAuthenticated && $endpointReady
        && endpointNeedsSession($endpointUrl) && !$hqSessionReady) {
      ensureHqSession().catch(() => {});
    }
  });
</script>

<div class="app-shell">
  <div class="relative min-h-screen">
    <Header />
    <main class="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      {@render children()}
    </main>
    <footer class="mx-auto max-w-7xl px-4 py-8 text-xs text-ink-400 sm:px-6 lg:px-8">
      <div class="flex flex-wrap items-center justify-between gap-2 border-t border-ink-600/60 pt-4">
        <span>© 2026 Cafreso — CafresoHQ is part of the Cafreso ecosystem</span>
        <span>One Internet Identity across Cafreso, AI, HQ &amp; Mine</span>
      </div>
    </footer>
  </div>
</div>

<!-- Same anonymous, on-chain search the homepage box opens — mounted here so
     the signed-out Dashboard and Search pages can launch it via aiSearchOpen. -->
<AISearchModal />
