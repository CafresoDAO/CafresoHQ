<script>
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import {
    endpointUrl,
    probeHealth,
    detectLocalCompanion,
    setEndpoint
  } from '$lib/stores/endpoint.js';
  import Header from '$lib/components/Header.svelte';

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
        <span class="font-mono">Ecosystem principal: Banking.Brave anchor</span>
      </div>
    </footer>
  </div>
</div>
