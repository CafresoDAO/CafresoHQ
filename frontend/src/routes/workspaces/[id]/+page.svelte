<script>
  import { onMount, onDestroy } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { isAuthenticated } from '$lib/stores/auth.js';
  import {
    activeSessions,
    getSession,
    stopSession,
    fetchSessions,
  } from '$lib/stores/workspaces.js';
  import { principalText } from '$lib/stores/auth.js';
  import StreamAdapter from '$lib/components/StreamAdapter.svelte';
  import SessionToolbar from '$lib/components/SessionToolbar.svelte';
  import SessionDock from '$lib/components/SessionDock.svelte';

  $: sessionId = $page.params.id;

  let session = null;
  let error   = '';
  let loaded  = false;

  // ── Uptime counter ────────────────────────────────────────────────────────
  let uptimeStr = '00:00:00';
  let uptimeInterval;

  function updateUptime() {
    if (!session?.created_at) return;
    const elapsed = Math.floor((Date.now() - new Date(session.created_at).getTime()) / 1000);
    const h = String(Math.floor(elapsed / 3600)).padStart(2, '0');
    const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, '0');
    const s = String(elapsed % 60).padStart(2, '0');
    uptimeStr = `${h}:${m}:${s}`;
  }

  // ── Mixed content detection (ported from /app) ────────────────────────────
  $: shellIsHttps    = typeof window !== 'undefined' && window.location?.protocol === 'https:';
  $: streamIsHttp    = session?.stream_url?.startsWith('http://');
  $: isLocalhost     = session?.stream_url && /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test(session.stream_url);
  $: mixedContent    = shellIsHttps && streamIsHttp && !isLocalhost;

  // ── Protocol badge ────────────────────────────────────────────────────────
  const protocolLabel = {
    iframe:    'iframe',
    webrtc:    'WebRTC',
    canister:  'canister',
    websocket: 'WebSocket',
  };

  const providerLabel = {
    hyperv:   'Hyper-V',
    oci:      'OCI',
    local:    'Local (WSL)',
    custom:   'Custom',
    canister: 'ICP',
  };

  // ── Actions ───────────────────────────────────────────────────────────────
  function handleRefresh() {
    // Force reload by re-fetching session
    loadSession();
  }

  function handleFullscreen() {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      document.documentElement.requestFullscreen();
    }
  }

  async function handleDisconnect() {
    if (!session) return;
    try {
      await stopSession(session.session_id);
    } catch (_) { /* ignore */ }
    goto('/workspaces');
  }

  function handleDockSelect(sid) {
    goto(`/workspaces/${sid}`);
  }

  function handleDockNew() {
    goto('/workspaces');
  }

  async function loadSession() {
    try {
      session = await getSession(sessionId);
      if (session?.stream_protocol === 'canister' && session.stream_url) {
        window.open(session.stream_url, '_blank', 'noopener,noreferrer');
        goto('/workspaces');
        return;
      }
    } catch (err) {
      error = err.message || 'Session not found';
    }
  }

  onMount(() => {
    loadSession();
    if ($principalText) {
      fetchSessions($principalText).catch(() => {});
    }
    uptimeInterval = setInterval(updateUptime, 1000);
  });

  onDestroy(() => {
    clearInterval(uptimeInterval);
  });

  function onKey(e) {
    if (e.key === 'Escape') goto('/workspaces');
  }
</script>

<svelte:window on:keydown={onKey} />

{#if error}
  <section class="space-y-5">
    <header class="card p-6 sm:p-8">
      <div class="page-kicker">Workspaces / Session</div>
      <h1 class="page-title mt-4">Session not found<span class="text-brand-500">.</span></h1>
      <p class="mt-4 text-sm text-ink-300">{error}</p>
      <a href="/workspaces" class="btn-primary mt-4 inline-block">Back to workspaces</a>
    </header>
  </section>

{:else if !session}
  <div class="fixed inset-0 z-40 grid place-items-center bg-ink-900">
    <div class="flex items-center gap-2 rounded-full border border-ink-600/60 bg-ink-800/80 px-4 py-2 text-sm text-ink-300">
      <span class="glow-dot text-brand-400 animate-pulse"></span>
      Loading session...
    </div>
  </div>

{:else if mixedContent}
  <section class="space-y-5">
    <header class="card p-6 sm:p-8">
      <div class="page-kicker">Workspaces / {session.display_name}</div>
      <h2 class="mt-2 text-xl font-semibold text-ink-50">Mixed content blocked</h2>
      <p class="mt-4 text-sm leading-6 text-ink-300">
        This shell is served over HTTPS but the workspace endpoint is HTTP.
        Use the Caddy gateway at <code class="font-mono text-brand-300">hq.cafreso.com</code> for TLS.
      </p>
      <div class="flex flex-wrap gap-2 pt-4">
        <button class="btn-primary" on:click={() => window.open(session.stream_url, '_blank')}>
          Open in new tab
        </button>
        <a href="/workspaces" class="btn-ghost">Back</a>
      </div>
    </header>
  </section>

{:else}
  <!-- ── Full-bleed session viewer ─────────────────────────────────────────── -->
  <div class="fixed inset-0 z-40 bg-ink-900">
    <!-- Top bar -->
    <div class="absolute top-0 inset-x-0 z-50 flex items-center justify-between px-4 py-2 bg-ink-900/80 backdrop-blur-md border-b border-ink-700/50">
      <div class="flex items-center gap-3">
        <a
          href="/workspaces"
          class="flex items-center gap-1.5 rounded-full px-3 py-1 text-xs text-ink-300 transition-colors hover:bg-ink-800/80 hover:text-ink-50"
        >
          <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M15 19l-7-7 7-7"/></svg>
          Workspaces
        </a>
        <span class="h-4 w-px bg-ink-600/50"></span>
        <div class="flex items-center gap-2">
          <span class="glow-dot {session.status === 'running' ? 'text-green-400' : 'text-yellow-400 animate-pulse'}"></span>
          <span class="text-sm font-semibold text-ink-100">{session.display_name || session.template_id}</span>
        </div>
      </div>

      <div class="flex items-center gap-3 text-[11px] text-ink-400">
        <span>{uptimeStr}</span>
        <span class="h-3 w-px bg-ink-600/50"></span>
        <span>{providerLabel[session.provider] || session.provider}</span>
        {#if session.resources?.vcpus || session.resources?.ocpus}
          <span>{session.resources.vcpus || session.resources.ocpus} cpu</span>
        {/if}
        {#if session.resources?.memory_gb}
          <span>{session.resources.memory_gb} gb</span>
        {/if}
        <span class="rounded-full bg-ink-800/60 border border-ink-600/40 px-2 py-0.5 text-[10px] uppercase tracking-wider">
          {protocolLabel[session.stream_protocol] || session.stream_protocol}
        </span>
      </div>
    </div>

    <!-- Stream content -->
    <div class="absolute inset-0 pt-10">
      <StreamAdapter {session} onLoaded={() => loaded = true} />
    </div>

    <!-- Session dock (left edge) -->
    <SessionDock
      sessions={$activeSessions}
      activeSessionId={sessionId}
      onSelect={handleDockSelect}
      onNew={handleDockNew}
    />

    <!-- Floating toolbar (bottom center) -->
    <div class="absolute bottom-6 left-1/2 z-50 -translate-x-1/2">
      <SessionToolbar
        {session}
        onRefresh={handleRefresh}
        onFullscreen={handleFullscreen}
        onDisconnect={handleDisconnect}
      />
    </div>
  </div>
{/if}
