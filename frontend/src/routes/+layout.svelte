<script>
  import '../app.css';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { initAuth } from '$lib/stores/auth.js';
  import { initTheme } from '$lib/stores/theme.js';
  import { migrateStorageKeys } from '$lib/storageMigrate.js';

  let { children } = $props();

  // Theme + Internet Identity are global to the whole ecosystem app.
  // Surface-specific chrome lives in (pages)/+layout.svelte and hq/+layout.svelte.
  onMount(() => {
    // Migrate legacy cafresoai.* / openclaw* storage keys BEFORE auth/vault read them.
    migrateStorageKeys();
    initTheme();
    initAuth();

    // Host-based default landing (only at the bare root path, so deep links
    // like /shop or /hq/vault are never redirected):
    //   ai.cafreso.com        → control plane  (/hq)
    //   cafreso.com + raw canister / localhost → consumer home (/)
    if (
      typeof window !== 'undefined' &&
      window.location.pathname === '/' &&
      window.location.hostname === 'ai.cafreso.com'
    ) {
      goto('/hq', { replaceState: true });
    }
  });
</script>

{@render children()}
