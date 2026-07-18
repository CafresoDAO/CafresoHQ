<script>
  import '../app.css';
  // Phosphor icon font — the whole app renders icons via <Icon> which emits
  // `ph`/`ph-fill` classes; without these stylesheets every icon is blank.
  // Imported here (not from a CDN) so the woff2 is bundled + served from the
  // canister — self-contained, offline-safe, no external dependency.
  import '@phosphor-icons/web/regular';
  import '@phosphor-icons/web/fill';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { initAuth } from '$lib/stores/auth.js';
  import { initTheme } from '$lib/stores/theme.js';
  import { migrateStorageKeys } from '$lib/storageMigrate.js';

  let { children } = $props();

  // Theme + Internet Identity are global to the whole ecosystem app.
  // Surface-specific chrome lives in (pages)/+layout.svelte and hq/+layout.svelte.
  onMount(async () => {
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
      // Await it so the boot splash below outlives the redirect — visitors go
      // splash → dashboard, never marketing-home-flash → dashboard.
      await goto('/hq', { replaceState: true }).catch(() => {});
    }

    // We're hydrated (and any host redirect has landed) — drop the inline
    // boot splash from app.html with a short fade.
    const splash = document.getElementById('boot-splash');
    if (splash) {
      splash.style.transition = 'opacity 180ms ease';
      splash.style.opacity = '0';
      setTimeout(() => splash.remove(), 200);
    }
  });
</script>

{@render children()}
