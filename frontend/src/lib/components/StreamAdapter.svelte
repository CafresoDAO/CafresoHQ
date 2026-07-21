<script>
  /**
   * Renders the appropriate streaming view based on session protocol.
   * iframe: vault bridge postMessage IPC for agent workspaces
   * webrtc: full WebRTC stream via Sunshine / moonlight-web-stream / Selkies
   * canister: auto-redirect to ICP canister URL
   */
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import WebRTCStream from './WebRTCStream.svelte';
  import {
    vaultFiles,
    vaultUnlocked,
    unlockVault,
    readFile,
    updateFile,
    createFile,
    deleteFile
  } from '$lib/stores/vault.js';
  import { isAuthenticated } from '$lib/stores/auth.js';

  export let session;
  export let onLoaded = () => {};

  let iframe;
  let loaded = false;

  // ── iframe vault bridge (ported from /app route) ──────────────────────────

  function iframeOrigin() {
    if (!session?.stream_url) return null;
    try { return new URL(session.stream_url).origin; }
    catch { return null; }
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
        reply({ type: 'vault:error', code: 'locked', message: 'Vault locked.' });
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
    if (session?.stream_protocol === 'canister' && session.stream_url) {
      window.open(session.stream_url, '_blank', 'noopener,noreferrer');
      return;
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('message', onVaultMessage);
    }
    vaultUnsub = vaultFiles.subscribe((files) => pushFiles(files));
  });

  onDestroy(() => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('message', onVaultMessage);
    }
    vaultUnsub?.();
  });

  function onIframeLoad() {
    loaded = true;
    onLoaded();
    setTimeout(() => pushFiles(get(vaultFiles)), 600);
    // Keyboard reaches the remote desktop only while the iframe's document
    // has focus — Guacamole listens on ITS document, not ours. Focus it on
    // load so the user can type immediately, without needing a first click.
    focusStream();
  }

  function focusStream() {
    try { iframe?.focus(); } catch (_) {}
  }
</script>

<!-- Any click/tap anywhere in the viewer hands focus back to the stream —
     e.g. after using the toolbar or dock, typing keeps working without the
     user knowing anything about focus. -->
<svelte:window on:focus={focusStream} />

{#if session?.stream_protocol === 'iframe'}
  <!-- Full-viewport iframe for agent workspaces -->
  {#if !loaded}
    <div class="absolute inset-0 z-10 grid place-items-center bg-ink-900/70 text-sm text-ink-300 backdrop-blur-sm pointer-events-none">
      <div class="flex items-center gap-2 rounded-full border border-ink-600/60 bg-ink-800/80 px-4 py-2">
        <span class="glow-dot text-brand-400 animate-pulse"></span>
        Loading workspace...
      </div>
    </div>
  {/if}
  <iframe
    bind:this={iframe}
    src={session.stream_url}
    title={session.display_name || 'Workspace'}
    on:load={onIframeLoad}
    class="block h-full w-full border-0 bg-ink-900"
    allow="clipboard-write *; clipboard-read *; fullscreen *"
  ></iframe>

{:else if session?.stream_protocol === 'webrtc'}
  <!-- WebRTC remote desktop stream -->
  <WebRTCStream
    {session}
    onConnected={onLoaded}
    onError={(msg) => console.error('[stream]', msg)}
  />

{:else if session?.stream_protocol === 'canister'}
  <!-- Canister redirect handled in onMount -->
  <div class="grid h-full w-full place-items-center bg-ink-900 text-ink-300">
    <div class="text-center space-y-3">
      <div class="text-sm">Opening {session.display_name}...</div>
      <a href={session.stream_url} target="_blank" rel="noopener noreferrer" class="btn-primary text-xs">
        Open in new tab
      </a>
    </div>
  </div>

{:else}
  <div class="grid h-full w-full place-items-center bg-ink-900 text-ink-300">
    <div class="text-sm">Unknown stream protocol: {session?.stream_protocol}</div>
  </div>
{/if}
