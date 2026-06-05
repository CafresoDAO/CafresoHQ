<script>
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import { endpointUrl, endpointHealth, endpointReady, probeHealth } from '$lib/stores/endpoint.js';
  import { isAuthenticated } from '$lib/stores/auth.js';
  import {
    ensureHqSession, hqSessionReady, hqSessionError, endpointNeedsSession
  } from '$lib/api/hqSession.js';
  import {
    vaultFiles,
    vaultUnlocked,
    unlockVault,
    readFile,
    updateFile,
    createFile,
    deleteFile
  } from '$lib/stores/vault.js';
  import ProvisionPanel from '$lib/components/ProvisionPanel.svelte';
  import { HQ_UI_CANISTER_ORIGIN } from '$lib/config.js';

  $: if ($endpointUrl && $endpointHealth.state === 'idle') {
    probeHealth().catch(() => {});
  }

  const APP_PATH = '/hq.html';
  // Frontend/backend split (Phase 3): when the container is reached through the
  // public gateway, serve the UI from the cafresohq_ui canister and point it back
  // at the container API via ?api= — so UI updates ship via `dfx deploy`, not a
  // container image rebuild. Local/self-hosted endpoints (and any host that isn't
  // the gateway) load the container's own baked-in /hq.html as before.
  $: useCanisterUi = !!HQ_UI_CANISTER_ORIGIN && needsSession;
  $: appUrl = $endpointUrl
    ? (useCanisterUi
        ? `${HQ_UI_CANISTER_ORIGIN}${APP_PATH}?api=${encodeURIComponent($endpointUrl)}`
        : $endpointUrl + APP_PATH)
    : '';

  $: shellIsHttps = typeof window !== 'undefined' && window.location?.protocol === 'https:';
  $: endpointIsHttp = $endpointUrl?.startsWith('http://');
  $: isLocalhost = $endpointUrl && /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test($endpointUrl);
  $: mixedContent = shellIsHttps && endpointIsHttp && !isLocalhost;

  // Containers reached through the gateway require an HQ session cookie before
  // the iframe (and its vault/agent XHRs) can load — otherwise forward_auth 401s.
  // Local/self-hosted endpoints have no verifier and skip this.
  $: needsSession = endpointNeedsSession($endpointUrl);
  $: sessionOk = !needsSession || $hqSessionReady;

  // Mint + install the session as soon as we're signed in and the container is
  // reachable. Re-runs if the endpoint changes.
  $: if ($isAuthenticated && needsSession && $endpointReady && !$hqSessionReady) {
    ensureHqSession().catch(() => {});
  }

  $: fullscreenIframe = $isAuthenticated && $endpointReady && !mixedContent && sessionOk && !!appUrl;

  let iframe;
  let loaded = false;
  let controlsCollapsed = false;

  function reload() {
    loaded = false;
    // appUrl may already carry a query (?api=…) when serving the canister UI —
    // use the right separator so we don't produce a malformed double-?.
    if (iframe) iframe.src = appUrl + (appUrl.includes('?') ? '&' : '?') + '_t=' + Date.now();
  }

  function popout() {
    if (appUrl) window.open(appUrl, '_blank', 'noopener,noreferrer');
  }

  function onKey(e) {
    if (e.key === 'Escape' && fullscreenIframe) controlsCollapsed = !controlsCollapsed;
  }

  function iframeOrigin() {
    // The postMessage target must match the iframe DOCUMENT's origin. When the
    // UI is served from the canister (split mode), that's the canister origin —
    // not the container endpoint the UI talks to via ?api=.
    const src = useCanisterUi ? HQ_UI_CANISTER_ORIGIN : $endpointUrl;
    if (!src) return null;
    try {
      return new URL(src).origin;
    } catch {
      return null;
    }
  }

  function pushFiles(files) {
    if (!iframe?.contentWindow || !loaded) return;
    iframe.contentWindow.postMessage(
      { type: 'vault:files:update', files },
      iframeOrigin() || '*'
    );
  }

  async function onVaultMessage(e) {
    if (!iframe?.contentWindow || e.source !== iframe.contentWindow) return;
    const origin = iframeOrigin();
    if (origin && e.origin !== origin) return;
    const { type, reqId, id, name, content } = e.data || {};
    if (!type?.startsWith('vault:')) return;

    const reply = (payload) =>
      iframe.contentWindow?.postMessage({ ...payload, reqId }, origin || '*');

    if (!get(vaultUnlocked)) {
      if (get(isAuthenticated)) await unlockVault();
      if (!get(vaultUnlocked)) {
        reply({
          type: 'vault:error',
          code: 'locked',
          message: 'Vault locked. Visit ai.cafreso.com/vault to unlock.'
        });
        return;
      }
    }

    try {
      switch (type) {
        case 'vault:list':
          reply({ type: 'vault:list:response', files: get(vaultFiles) });
          break;
        case 'vault:read': {
          const text = await readFile(id);
          reply({ type: 'vault:read:response', id, content: text });
          break;
        }
        case 'vault:write':
          await updateFile(id, content);
          reply({ type: 'vault:write:response', id, ok: true });
          break;
        case 'vault:create': {
          const meta = await createFile(name, content || '');
          reply({ type: 'vault:create:response', meta });
          break;
        }
        case 'vault:delete':
          await deleteFile(id);
          reply({ type: 'vault:delete:response', id, ok: true });
          break;
      }
    } catch (err) {
      reply({ type: 'vault:error', code: 'op-failed', message: err?.message || String(err) });
    }
  }

  let vaultUnsub;

  onMount(() => {
    if (typeof window !== 'undefined') {
      window.addEventListener('keydown', onKey);
      window.addEventListener('message', onVaultMessage);
    }
    vaultUnsub = vaultFiles.subscribe((files) => pushFiles(files));
  });

  onDestroy(() => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('message', onVaultMessage);
    }
    vaultUnsub?.();
  });

  function onIframeLoad() {
    loaded = true;
    setTimeout(() => pushFiles(get(vaultFiles)), 600);
  }
</script>

{#if fullscreenIframe}
  <div class="fixed inset-0 z-40 bg-ink-900">
    {#if !loaded}
      <div class="absolute inset-0 z-10 grid place-items-center bg-ink-900/70 text-sm text-ink-300 backdrop-blur-sm pointer-events-none">
        <div class="flex items-center gap-2 rounded-full border border-ink-600/60 bg-ink-800/80 px-4 py-2">
          <span class="glow-dot text-brand-400 animate-pulse"></span>
          Loading HQ from your container...
        </div>
      </div>
    {/if}

    <iframe
      bind:this={iframe}
      src={appUrl}
      title="CafresoAI HQ"
      on:load={onIframeLoad}
      class="block h-full w-full border-0 bg-ink-900"
      allow="clipboard-write *; clipboard-read *; fullscreen *"
    ></iframe>

    {#if controlsCollapsed}
      <button
        class="absolute right-3 top-3 z-50 grid h-9 w-9 place-items-center rounded-full border border-ink-600/60 bg-ink-900/80 text-ink-200 backdrop-blur-md transition-colors hover:bg-ink-800/80 hover:text-ink-50"
        title="Show controls (Esc)"
        on:click={() => controlsCollapsed = false}
      >
        ...
      </button>
    {:else}
      <div class="absolute right-3 top-3 z-50 flex items-center gap-1 rounded-full border border-ink-600/60 bg-ink-900/80 p-1 shadow-lg backdrop-blur-md">
        <a
          href="/"
          class="rounded-full px-3 py-1 text-xs text-ink-200 transition-colors hover:bg-ink-800/80 hover:text-ink-50"
          title="Back to dashboard"
        >
          Dashboard
        </a>
        <span class="h-4 w-px bg-ink-600/60"></span>
        <button class="rounded-full px-3 py-1 text-xs text-ink-200 transition-colors hover:bg-ink-800/80 hover:text-ink-50" on:click={reload} title="Hard reload the iframe">
          Reload
        </button>
        <button class="rounded-full px-3 py-1 text-xs text-ink-200 transition-colors hover:bg-ink-800/80 hover:text-ink-50" on:click={popout} title="Open in new tab">
          Popout
        </button>
        <button class="rounded-full px-3 py-1 text-xs text-ink-200 transition-colors hover:bg-ink-800/80 hover:text-ink-50" on:click={() => controlsCollapsed = true} title="Hide controls (Esc)">
          Hide
        </button>
      </div>
    {/if}
  </div>
{:else}
  <section class="space-y-5">
    <header class="card p-6 sm:p-8">
      <div class="page-kicker">CafresoAI / HQ</div>
      <h1 class="page-title mt-4">CafresoAI HQ<span class="text-brand-500">.</span></h1>
      <p class="mt-4 max-w-2xl text-sm leading-6 text-ink-300">
        The full agent command center, running in your private OCI container.
      </p>
    </header>

    {#if !$isAuthenticated}
      <div class="card p-5 text-sm leading-6 text-ink-300">
        Sign in to launch HQ. Your principal scopes vault and agent state.
      </div>
    {:else if $endpointHealth.state === 'idle' || $endpointHealth.state === 'probing'}
      <div class="card flex items-center gap-3 p-5 text-sm text-ink-300">
        <span class="glow-dot text-brand-400 animate-pulse"></span>
        Connecting to your container...
      </div>
    {:else if !$endpointUrl || $endpointHealth.state === 'error'}
      <ProvisionPanel />
    {:else if mixedContent}
      <div class="card space-y-4 p-6">
        <div>
          <div class="page-kicker">Embedding Blocked</div>
          <h2 class="mt-2 text-xl font-semibold">Mixed content</h2>
        </div>
        <p class="text-sm leading-6 text-ink-300">
          This shell is served over <code class="font-mono text-brand-600 dark:text-brand-300">https://</code>,
          but your container endpoint is plain <code class="font-mono text-brand-600 dark:text-brand-300">http://</code>.
          Browsers block iframing an HTTP page from an HTTPS origin.
        </p>
        <p class="text-sm leading-6 text-ink-300">
          Production fix is the OCI Caddy gateway at
          <code class="font-mono text-brand-600 dark:text-brand-300">hq.cafreso.com/u/&lt;principal-slug&gt;/*</code>
          with managed TLS. Re-point your endpoint there.
        </p>
        <div class="flex flex-wrap gap-2 pt-1">
          <button class="btn-primary" on:click={popout}>Open HQ in new tab</button>
          <a href="/hq/settings" class="btn-ghost">Update endpoint</a>
        </div>
        <p class="pt-1 text-xs text-ink-400">
          Endpoint: <code class="font-mono">{$endpointUrl}</code>
        </p>
      </div>
    {:else if needsSession && !$hqSessionReady}
      <div class="card space-y-3 p-6">
        {#if $hqSessionError}
          <div class="page-kicker">Session</div>
          <h2 class="text-xl font-semibold">Couldn’t secure your session</h2>
          <p class="text-sm leading-6 text-ink-300">{$hqSessionError}</p>
          <div class="flex gap-2 pt-1">
            <button class="btn-primary" on:click={() => ensureHqSession()}>Retry</button>
            <a href="/hq/settings" class="btn-ghost">Settings</a>
          </div>
          <p class="text-xs text-ink-400">
            Your container is access-controlled — only your signed-in identity can open it.
          </p>
        {:else}
          <div class="flex items-center gap-3 text-sm text-ink-300">
            <span class="glow-dot text-brand-400 animate-pulse"></span>
            Securing your private session…
          </div>
        {/if}
      </div>
    {/if}
  </section>
{/if}
