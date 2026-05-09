<script>
  import '../app.css';
  import { onMount } from 'svelte';
  import { initAuth }     from '$lib/stores/auth.js';
  import { endpointUrl,
           probeHealth,
           detectLocalCompanion,
           setEndpoint }   from '$lib/stores/endpoint.js';
  import { get }           from 'svelte/store';
  import Header            from '$lib/components/Header.svelte';

  onMount(async () => {
    // 1. Init Internet Identity (resumes session if cookie present)
    await initAuth();

    // 2. If no endpoint saved, try to auto-detect a Local Companion on this machine.
    if (!get(endpointUrl)) {
      const local = await detectLocalCompanion();
      if (local) setEndpoint(local);
    }

    // 3. Probe whichever endpoint we have — fire-and-forget; UI updates reactively.
    if (get(endpointUrl)) {
      probeHealth().catch(() => { /* shown in EndpointStatus */ });
    }
  });
</script>

<div class="min-h-full bg-ink-900 text-ink-50 bg-grid">
  <div class="min-h-full bg-gradient-to-b from-ink-900 via-ink-900/80 to-ink-900">
    <Header />
    <main class="mx-auto max-w-6xl px-4 py-6">
      <slot />
    </main>
    <footer class="mx-auto max-w-6xl px-4 py-8 text-xs text-ink-400">
      <div class="flex flex-wrap items-center justify-between gap-2 border-t border-ink-600/30 pt-4">
        <span>© 2026 Cafreso · CafresoAI is part of the Cafreso ecosystem</span>
        <span class="font-mono">Ecosystem principal: Banking.Brave anchor</span>
      </div>
    </footer>
  </div>
</div>
