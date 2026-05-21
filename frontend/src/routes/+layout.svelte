<script>
  import '../app.css';
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import { initAuth } from '$lib/stores/auth.js';
  import {
    endpointUrl,
    probeHealth,
    detectLocalCompanion,
    setEndpoint
  } from '$lib/stores/endpoint.js';
  import { initTheme } from '$lib/stores/theme.js';
  import Header from '$lib/components/Header.svelte';

  let { children } = $props();

  onMount(async () => {
    initTheme();

    // 1. Init Internet Identity (resumes session if cookie present)
    await initAuth();

    // 2. If no endpoint saved, try to auto-detect a Local Companion on this machine.
    if (!get(endpointUrl)) {
      const local = await detectLocalCompanion();
      if (local) setEndpoint(local);
    }

    // 3. Probe whichever endpoint we have; UI updates reactively.
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
        <span>2026 Cafreso - CafresoAI is part of the Cafreso ecosystem</span>
        <span class="font-mono">Ecosystem principal: Banking.Brave anchor</span>
      </div>
    </footer>
  </div>
</div>
