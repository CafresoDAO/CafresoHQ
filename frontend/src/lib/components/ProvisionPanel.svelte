<script>
  import { onDestroy } from 'svelte';
  import { isAuthenticated, principalText } from '$lib/stores/auth.js';
  import { setEndpoint, clearEndpoint, detectLocalCompanion, localNetworkPermission, probeHealth } from '$lib/stores/endpoint.js';
  import { deployTarget, setDeployTarget } from '$lib/stores/deployTarget.js';
  import { lookup, provisionAndWait, wakeAndWait, deprovision, fleetHealth, FleetApiError, fleetApiUrl }
    from '$lib/api/fleetClient.js';
  import { mintSessionToken } from '$lib/api/hqSession.js';

  const LOCAL_URL = 'http://localhost:8787';

  // ── OCI flow state ──
  let state = 'unknown';   // unknown | checking | no-api | no-container | provisioning | waking | existing | ready | error
  let phase = '';
  let error = '';
  let endpoint = '';
  let apiOk = null;
  // Set when a wake reports the container is gone (deleted/failed) so we route
  // the user to a fresh provision with a reassuring "your vault is preserved" note.
  let goneNote = '';

  // ── Local flow state ──
  let localState = 'idle'; // idle | detecting | found | absent
  // Chrome/Edge 138+ "local network access" permission state for this site:
  // '' (unknown) | 'granted' | 'prompt' | 'denied' | 'unsupported'. While
  // 'prompt', probes hang on the browser's Allow dialog; while 'denied', every
  // probe fails instantly even with a healthy local HQ — surface both.
  let lnaState = '';

  // OS-aware self-host instructions. Docker is the recommended path — the
  // public image runs identically on macOS / Windows / Linux and includes
  // Hermes (which is unix-only, so a *native* Windows run needs WSL).
  const DOCKER_CMD = 'docker run -d --name cafresohq -p 8787:8787 -v cafresohq-data:/data docker.io/anthonycf1/cafresoai-serve:latest';
  function detectOS() {
    if (typeof navigator === 'undefined') return 'linux';
    const p = (navigator.platform || '') + ' ' + (navigator.userAgent || '');
    if (/Win/i.test(p)) return 'windows';
    if (/Mac|iPhone|iPad/i.test(p)) return 'mac';
    return 'linux';
  }
  let os = detectOS();
  let copied = false;
  async function copyDockerCmd() {
    try {
      await navigator.clipboard.writeText(DOCKER_CMD);
      copied = true;
      setTimeout(() => { copied = false; }, 2000);
    } catch (_) {}
  }

  // ── Provisioning progress (human-readable milestones + elapsed clock) ──
  const PHASE_LABELS = {
    starting:  'Requesting a private container…',
    queued:    'Waiting for capacity…',
    accepted:  'Request accepted…',
    creating:  'Creating your container…',
    CREATING:  'Creating your container…',
    pulling:   'Pulling the HQ image…',
    running:   'Container is up — wiring your private route…',
    ACTIVE:    'Container is up — wiring your private route…',
    route:        'Publishing your secure route…',
    waking:       'Waking your HQ… (~30–60s)',
    waking_boot:  'HQ engine starting…',
    ready:        'Ready!',
    working:      'Working…',
  };
  let provisionStartedAt = 0;
  let elapsed = 0;
  let elapsedTimer = null;
  function startElapsed() {
    provisionStartedAt = Date.now();
    elapsed = 0;
    clearInterval(elapsedTimer);
    elapsedTimer = setInterval(() => { elapsed = Math.round((Date.now() - provisionStartedAt) / 1000); }, 1000);
  }
  function stopElapsed() { clearInterval(elapsedTimer); elapsedTimer = null; }
  $: phaseLabel = PHASE_LABELS[phase] || (phase ? phase : 'Working…');
  // 0→100% capped at 95% until actually ready (honest-ish bar). Waking from
  // sleep is quicker than a cold provision, so it fills over ~60s vs ~120s.
  $: pct = state === 'ready' ? 100
         : Math.min(95, Math.round((elapsed / (state === 'waking' ? 60 : 120)) * 100));

  $: principal = $principalText;
  $: target = $deployTarget;

  // ── OCI helpers (unchanged behaviour) ──
  async function checkApi() {
    apiOk = null;
    try { await fleetHealth(); apiOk = true; } catch (_) { apiOk = false; }
  }
  function pickEndpoint(r) { return r?.gateway_url || r?.endpoint || null; }

  async function autoLookup() {
    if (!$isAuthenticated || !principal) return;
    state = 'checking'; phase = ''; error = ''; goneNote = '';
    await checkApi();
    if (!apiOk) { state = 'no-api'; return; }
    try {
      const r = await lookup(principal);
      const ep = r && pickEndpoint(r);
      if (!ep) { state = 'no-container'; return; }
      // A container is on record. If the fleet says it's stopped (idle-reaped),
      // wake it straight away. Otherwise adopt the endpoint and confirm it's
      // actually answering — a stale ACTIVE that 502s also means "wake me".
      if (r.status === 'INACTIVE') { await startWake(); return; }
      setEndpoint(ep); endpoint = ep;
      try {
        await probeHealth({ timeoutMs: 8000 });
        state = 'existing';
      } catch (_) {
        await startWake();   // recorded but not answering → wake (idempotent)
      }
    } catch (err) { error = describe(err); state = 'error'; }
  }

  // Wake a stopped container hands-free (auto-wake, silent): mint the
  // self-service session token, start it, and poll until /health answers.
  // Reuses the provisioning progress UI. A 'gone' result (container deleted/
  // failed — fleet-api already forgot the stale entry) drops back to the
  // provision state with a reassuring note; the encrypted vault is preserved.
  async function startWake() {
    if (state === 'waking' || state === 'provisioning') return;   // dedup
    state = 'waking'; phase = 'waking'; error = ''; goneNote = '';
    startElapsed();
    try {
      const token = await mintSessionToken();
      const job = await wakeAndWait(token, {
        onUpdate: (j) => { phase = j.phase || j.status || 'waking'; },
        pollMs: 3000, maxWaitMs: 180000
      });
      let ep = pickEndpoint(job);
      if (!ep) {                         // woke but result lacked an endpoint
        const r = await lookup(principal);
        ep = r && pickEndpoint(r);
      }
      if (ep) { setEndpoint(ep); endpoint = ep; state = 'ready'; phase = 'ready'; }
      else { throw new Error('woke but no endpoint'); }
    } catch (err) {
      const gone = err instanceof FleetApiError
        && (err.body?.phase === 'gone' || err.status === 404 || err.body?.code === 'not_provisioned');
      if (gone) {
        state = 'no-container';
        goneNote = 'Your previous container was cleaned up — provision a fresh one. Your encrypted vault is preserved and reattaches automatically.';
      } else {
        error = describe(err); state = 'error';
      }
    }
    stopElapsed();
  }

  async function startProvision() {
    if (state === 'provisioning') return;   // double-click guard
    state = 'provisioning'; phase = 'starting'; error = ''; goneNote = '';
    startElapsed();
    try {
      // Self-service credential: an on-chain-minted session token proves this
      // principal owns the request, so the hardened fleet API provisions for it
      // (dev-mode no longer waves anonymous callers through). Best-effort — if
      // minting fails we still send the principal (admin/dev fallback path).
      let token = '';
      try { token = await mintSessionToken(); } catch (_) { /* fall through */ }
      const job = await provisionAndWait(principal, {
        onUpdate: (j) => { phase = j.phase || j.status || 'working'; },
        pollMs: 5000, maxWaitMs: 600000, token
      });
      const ep = pickEndpoint(job);
      if (ep) { setEndpoint(ep); endpoint = ep; state = 'ready'; phase = 'ready'; }
      else { throw new Error('no endpoint in job result'); }
    } catch (err) { error = describe(err); state = 'error'; }
    stopElapsed();
  }

  function describe(err) {
    if (err instanceof FleetApiError) {
      const detail = err.body?.error || err.message;
      return `${detail} (HTTP ${err.status || '?'})`;
    }
    return String(err?.message || err);
  }

  // ── Delete / deprovision flow ──
  let showDelete = false;
  let deleteConfirm = '';
  let deleting = false;
  let deleteError = '';
  async function deleteContainer() {
    if (deleting || deleteConfirm.trim().toUpperCase() !== 'DELETE') return;
    deleting = true; deleteError = '';
    try {
      // The on-chain-minted session token is the credential: the fleet API
      // takes the principal FROM it, so you can only delete your own container.
      const token = await mintSessionToken();
      await deprovision(token);
      clearEndpoint();
      // Reset back to the "no container" state so the user can re-provision.
      state = 'no-container'; endpoint = ''; showDelete = false; deleteConfirm = '';
    } catch (err) {
      deleteError = describe(err);
    } finally {
      deleting = false;
    }
  }

  // ── Local helpers ──
  async function detectLocal() {
    localState = 'detecting'; error = '';
    lnaState = await localNetworkPermission();
    try {
      // allowPrompt: this runs from a user gesture, so let the probe wait out
      // Chrome's "access devices on your local network" dialog instead of
      // aborting it after 2.5s.
      const url = await detectLocalCompanion({ timeoutMs: 2500, allowPrompt: true });
      if (url) { setEndpoint(url); endpoint = url; localState = 'found'; }
      else { localState = 'absent'; }
    } catch (_) { localState = 'absent'; }
    lnaState = await localNetworkPermission();   // the user may have just answered
  }

  // ── Detected local agents + embed capability ──
  // The local app reports which agent CLIs are installed (and logged in) via
  // GET /agents — surface them as chips so users see their existing agents
  // synced. HTTPS endpoint = the browser trusts the local cert (mkcert), which
  // also means the in-dashboard embed works in every browser incl. Safari.
  const AGENT_ICONS = { hermes: '☼', 'claude-code': '✦', codex: '◈', gemini: '✧' };
  let localAgents = [];
  let localAgentsFor = '';
  async function loadLocalAgents() {
    if (!endpoint || localAgentsFor === endpoint) return;
    localAgentsFor = endpoint;
    try {
      const r = await fetch(endpoint + '/agents', { headers: { Accept: 'application/json' } });
      if (!r.ok) return;
      const d = await r.json();
      localAgents = (d.agents || []).filter(a => a.installed);
    } catch (_) { localAgents = []; }
  }
  $: if (target === 'local' && localState === 'found' && endpoint) loadLocalAgents();
  $: localIsHttps = !!endpoint && endpoint.startsWith('https://');
  // Quiet background re-probe while waiting — the user starts their HQ
  // (docker run / launcher) and this page flips to "detected" on its own,
  // without flashing the "Looking…" state every few seconds.
  async function probeQuiet() {
    lnaState = await localNetworkPermission();   // flips us live when the user allows
    if (lnaState === 'denied') return;           // pointless until re-allowed in site settings
    try {
      const url = await detectLocalCompanion({ timeoutMs: 2500 });
      if (url) { setEndpoint(url); endpoint = url; localState = 'found'; }
    } catch (_) {}
  }
  let localPoll = null;
  $: {
    if (target === 'local' && localState === 'absent' && !localPoll) {
      localPoll = setInterval(probeQuiet, 6000);
    } else if ((target !== 'local' || localState === 'found') && localPoll) {
      clearInterval(localPoll); localPoll = null;
    }
  }
  onDestroy(() => { clearInterval(localPoll); stopElapsed(); });

  // ── Target selection ──
  function chooseTarget(t) {
    setDeployTarget(t);
    state = 'unknown'; localState = 'idle'; phase = ''; error = ''; endpoint = '';
    if (t === 'oci-fleet') autoLookup();
    else if (t === 'local') detectLocal();
  }
  function changeTarget() {
    clearEndpoint();
    setDeployTarget('');
    state = 'unknown'; localState = 'idle'; phase = ''; error = ''; endpoint = '';
  }

  // Drive the right flow on init / when a target is already chosen.
  $: if ($isAuthenticated && principal && target === 'oci-fleet' && state === 'unknown') autoLookup();
  $: if (target === 'local' && localState === 'idle') detectLocal();
  $: if (!$isAuthenticated && target === 'oci-fleet' && state !== 'unknown') {
    state = 'unknown'; phase = ''; error = ''; endpoint = '';
  }
</script>

<div class="card p-5">
  {#if !target}
    <!-- ── Step 1: choose where HQ runs ── -->
    <div class="page-kicker">Your CafresoAI HQ</div>
    <div class="mt-2 text-xl font-semibold">Where should your HQ run?</div>
    <p class="mt-3 text-sm leading-6 text-ink-300">
      Pick where your private agent backend lives. You can change this anytime.
    </p>
    <div class="mt-4 grid gap-3 sm:grid-cols-2">
      <button class="card p-4 text-left transition-colors hover:border-brand-500/60" on:click={() => chooseTarget('oci-fleet')}>
        <div class="flex items-center gap-2 text-base font-semibold">☁️ OCI Cloud
          <span class="pill-ok"><span class="glow-dot text-emerald-400"></span> Managed</span>
        </div>
        <p class="mt-2 text-xs leading-5 text-ink-400">
          We provision and run a private container for you. One click, nothing to install.
        </p>
      </button>
      <button class="card p-4 text-left transition-colors hover:border-brand-500/60" on:click={() => chooseTarget('local')}>
        <div class="text-base font-semibold">💻 Local machine</div>
        <p class="mt-2 text-xs leading-5 text-ink-400">
          Run HQ on your own Mac / Windows / Linux via Start-CafresoHQ. Your data never leaves your device.
        </p>
      </button>
    </div>
  {:else}
    <div class="flex items-center justify-between gap-3">
      <div class="page-kicker">
        Your CafresoAI HQ · {target === 'local' ? 'Local machine' : 'OCI Cloud'}
      </div>
      <button class="text-xs text-ink-400 underline hover:text-ink-200" on:click={changeTarget}>Change</button>
    </div>

    {#if target === 'local'}
      <!-- ── Local (Native/WSL) flow ── -->
      {#if localState === 'detecting'}
        <div class="mt-2 flex items-center gap-2 text-xl font-semibold">
          <span class="glow-dot text-amber-400 animate-pulse"></span> Looking for your local HQ…
        </div>
        <p class="mt-3 text-sm leading-6 text-ink-300">Probing <code class="font-mono">{LOCAL_URL}</code>.</p>
        {#if lnaState === 'prompt'}
          <p class="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs leading-5 text-amber-700 dark:text-amber-300">
            🔐 Your browser is asking to <strong>“access devices on your local network”</strong> —
            click <strong>Allow</strong> so this page can reach your HQ at localhost. One-time.
          </p>
        {/if}
      {:else if localState === 'found'}
        <div class="mt-2 flex items-center gap-2 text-xl font-semibold">
          Local HQ detected
          {#if localIsHttps}
            <span class="pill-ok text-[10px]"><span class="glow-dot text-emerald-400"></span> Trusted HTTPS</span>
          {/if}
        </div>
        <p class="mt-3 text-sm leading-6 text-ink-300">
          Running on your machine at <code class="font-mono text-brand-600 dark:text-brand-300">{endpoint}</code>.
          Your vault, agents, and terminals all stay local.
        </p>

        {#if localAgents.length > 0}
          <div class="mt-3">
            <div class="text-xs uppercase tracking-[0.18em] text-ink-400">Agents found on your machine</div>
            <div class="mt-2 flex flex-wrap gap-1.5">
              {#each localAgents as a (a.id)}
                <span class="inline-flex items-center gap-1.5 rounded-lg border border-ink-600/60 bg-ink-800/40 px-2.5 py-1 text-xs"
                      title={a.version || a.label}>
                  <span class="text-brand-500">{AGENT_ICONS[a.id] || '◆'}</span>
                  <span class="font-semibold">{a.label || a.id}</span>
                  {#if a.id === 'hermes' ? a.running : a.authenticated}
                    <span class="text-emerald-500" title={a.id === 'hermes' ? 'gateway running' : 'logged in'}>✓</span>
                  {:else}
                    <span class="text-ink-500" title={a.id === 'hermes' ? 'gateway not running' : 'needs login — run it once in a Terminal tab'}>○</span>
                  {/if}
                </span>
              {/each}
            </div>
            <p class="mt-1.5 text-[11px] leading-4 text-ink-500">
              These sync into your HQ crew automatically. ✓ = ready · ○ = needs a one-time login (open a Terminal tab in HQ).
            </p>
          </div>
        {/if}

        <div class="mt-4 flex flex-wrap gap-2">
          {#if localIsHttps}
            <a class="btn-primary btn-sm" href="/hq/app">Launch HQ (embedded)</a>
            <a class="btn-ghost btn-sm" href="{endpoint}/hq.html" target="_blank" rel="noopener noreferrer">Open in its own tab</a>
          {:else}
            <a class="btn-primary btn-sm" href="{endpoint}/hq.html" target="_blank" rel="noopener noreferrer">Open my local HQ</a>
            <a class="btn-ghost btn-sm" href="/hq/app">Launch in dashboard</a>
          {/if}
          <button class="btn-ghost btn-sm" on:click={detectLocal}>Re-check</button>
        </div>
        {#if !localIsHttps}
          <p class="mt-2 text-[11px] leading-4 text-ink-500">
            The embedded dashboard view works in Chrome and Edge (allow the one-time
            “local network” prompt) and Firefox. For Safari (and a warning-free padlock),
            install <a class="underline" href="https://github.com/FiloSottile/mkcert"
            target="_blank" rel="noopener noreferrer">mkcert</a> and restart your HQ — it picks up a
            browser-trusted certificate automatically.
          </p>
        {/if}
      {:else}
        <!-- absent / idle -->
        <div class="mt-2 text-xl font-semibold">Run CafresoHQ on this machine</div>
        <p class="mt-3 text-sm leading-6 text-ink-300">
          No local HQ is running yet. Start one below — this page re-checks automatically.
        </p>
        {#if lnaState === 'prompt'}
          <p class="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs leading-5 text-amber-700 dark:text-amber-300">
            🔐 Already running? Chrome asks to <strong>“access devices on your local network”</strong>
            before this page can see localhost — hit <strong>Re-check</strong> below and click
            <strong>Allow</strong> on the prompt. One-time.
          </p>
        {:else if lnaState === 'denied'}
          <p class="mt-3 rounded-lg border border-rose-500/40 bg-rose-500/10 p-2.5 text-xs leading-5 text-rose-700 dark:text-rose-300">
            🚫 Your browser is blocking this site from reaching localhost (local network access
            denied). Click the icon left of the address bar → <strong>Site settings</strong> →
            <strong>Local network access</strong> → Allow, then Re-check.
          </p>
        {/if}

        <!-- OS picker (pre-selected from your browser) -->
        <div class="mt-4 flex gap-1.5">
          {#each [['mac','🍎 macOS'],['windows','🪟 Windows'],['linux','🐧 Linux']] as [id,label]}
            <button class="rounded-lg border px-2.5 py-1 text-xs font-semibold transition-colors
                {os===id ? 'border-brand-500 bg-brand-500/10 text-brand-600 dark:text-brand-300' : 'border-ink-600/50 text-ink-400 hover:text-ink-200'}"
              on:click={() => { os = id; }}>{label}</button>
          {/each}
        </div>

        <!-- Recommended: Docker (identical on every OS, Hermes included) -->
        <div class="mt-3 rounded-xl border border-ink-600/60 p-3">
          <div class="flex items-center gap-2 text-sm font-semibold">
            🐳 With Docker <span class="pill-ok text-[10px]">Recommended</span>
          </div>
          <p class="mt-1 text-xs leading-5 text-ink-400">
            {#if os === 'windows'}
              Install <a class="underline" href="https://www.docker.com/products/docker-desktop/" target="_blank" rel="noopener noreferrer">Docker Desktop</a>, then run this in PowerShell:
            {:else if os === 'mac'}
              Install <a class="underline" href="https://www.docker.com/products/docker-desktop/" target="_blank" rel="noopener noreferrer">Docker Desktop</a> (or OrbStack), then run this in Terminal:
            {:else}
              With Docker installed, run:
            {/if}
          </p>
          <div class="mt-2 flex items-stretch gap-2">
            <code class="block flex-1 overflow-x-auto whitespace-nowrap rounded-lg border border-ink-600/60 bg-[var(--code-bg)] px-3 py-2 font-mono text-[11px] text-ink-100">{DOCKER_CMD}</code>
            <button class="btn-ghost btn-sm shrink-0" on:click={copyDockerCmd}>{copied ? '✓ Copied' : 'Copy'}</button>
          </div>
          <p class="mt-2 text-[11px] leading-4 text-ink-500">
            Runs the same image as our cloud — full agent runtime included. Your data stays in the
            <code class="font-mono">cafresohq-data</code> volume on your machine.
          </p>
        </div>

        <!-- Alternative: from source -->
        <div class="mt-2 rounded-xl border border-ink-600/60 p-3">
          <div class="text-sm font-semibold">⚙️ From source</div>
          <p class="mt-1 text-xs leading-5 text-ink-400">
            {#if os === 'windows'}
              Clone the repo and double-click <code class="font-mono">Start-CafresoHQ.cmd</code> (runs inside WSL — the agent runtime is unix-only).
            {:else}
              Clone the repo and run <code class="font-mono">sh Start-CafresoHQ.sh</code>.
            {/if}
          </p>
        </div>

        <p class="mt-3 text-xs leading-5 text-ink-400">
          Either way it serves HQ at <code class="font-mono">{LOCAL_URL}</code> (loopback-only by default).
          To reach it from another device, expose it with a key — see the launcher notes.
        </p>
        <button class="btn-primary btn-sm mt-4" on:click={detectLocal}>Re-check for local HQ</button>
      {/if}

    {:else}
      <!-- ── OCI Fleet flow (unchanged) ── -->
      <div class="flex items-start justify-between gap-3">
        <div class="mt-1 text-xl font-semibold">
          {#if state === 'checking'}Checking the fleet...
          {:else if state === 'existing' || state === 'ready'}Container ready
          {:else if state === 'provisioning'}Provisioning your HQ...
          {:else if state === 'waking'}Waking your HQ...
          {:else if state === 'no-container'}No container yet
          {:else if state === 'no-api'}Fleet API unreachable
          {:else if state === 'error'}Couldn't check fleet
          {:else}Sign in to check{/if}
        </div>
        {#if state === 'existing' || state === 'ready'}
          <span class="pill-ok"><span class="glow-dot text-emerald-400"></span> Live</span>
        {:else if state === 'provisioning' || state === 'waking' || state === 'checking'}
          <span class="pill-warn"><span class="glow-dot text-amber-400 animate-pulse"></span> Working</span>
        {:else if state === 'no-container'}
          <span class="pill-idle"><span class="glow-dot text-ink-400"></span> Idle</span>
        {:else if state === 'error' || state === 'no-api'}
          <span class="pill-err"><span class="glow-dot text-rose-400"></span> Error</span>
        {/if}
      </div>

      {#if state === 'checking'}
        <p class="mt-3 text-sm leading-6 text-ink-300">Asking the fleet API if your principal already has an HQ...</p>
      {:else if state === 'no-api'}
        <p class="mt-3 text-sm leading-6 text-ink-300">
          Can't reach the fleet API at <code class="font-mono text-brand-600 dark:text-brand-300">{$fleetApiUrl}</code>.
        </p>
        <p class="mt-1 text-xs leading-5 text-ink-400">
          Start it locally with <code class="font-mono">python oci-fleet/fleet-api.py</code>,
          or update the URL in
          <a href="/hq/settings" class="font-semibold text-brand-600 underline dark:text-brand-300">Settings</a>.
        </p>
        <button class="btn-ghost btn-sm mt-3" on:click={autoLookup}>Retry</button>
      {:else if state === 'no-container'}
        {#if goneNote}
          <p class="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-2.5 text-sm leading-6 text-amber-700 dark:text-amber-300">
            {goneNote}
          </p>
        {/if}
        <p class="mt-3 text-sm leading-6 text-ink-300">
          Your principal doesn't have a CafresoAI HQ yet. Provisioning takes about a minute.
          We'll spin up a private OCI container in Ashburn with 1 OCPU, 6 GB, and ARM64.
        </p>
        <button class="btn-primary mt-4" on:click={startProvision}>Provision my HQ</button>
      {:else if state === 'provisioning' || state === 'waking'}
        <p class="mt-3 text-sm leading-6 text-ink-300">
          {#if state === 'waking'}
            Waking your HQ from sleep — usually about 30 to 60 seconds. Keep this tab open; it launches itself when ready.
          {:else}
            Building your HQ — usually 60 to 90 seconds. Keep this tab open; it launches itself when ready.
          {/if}
        </p>
        <div class="mt-4 space-y-2">
          <div class="flex items-center justify-between gap-2 text-sm">
            <span class="flex items-center gap-2">
              <span class="glow-dot text-amber-400 animate-pulse"></span>
              <span class="text-ink-200">{phaseLabel}</span>
            </span>
            <span class="font-mono text-xs text-ink-400">{elapsed}s</span>
          </div>
          <div class="h-1.5 w-full overflow-hidden rounded-full bg-ink-800/70">
            <div class="h-full rounded-full bg-brand-500 transition-all duration-1000" style="width:{pct}%"></div>
          </div>
          {#if elapsed > 150 && state === 'provisioning'}
            <p class="text-xs leading-5 text-amber-500/90">
              Taking longer than usual — OCI may be tight on capacity. We keep retrying for up to 10 minutes.
            </p>
          {/if}
        </div>
      {:else if state === 'existing' || state === 'ready'}
        <p class="mt-3 text-sm leading-6 text-ink-300">
          Your HQ is live. Endpoint adopted, and the rest of the app is already pointed at it.
        </p>
        <code class="mt-2 block break-all rounded-xl border border-ink-600/60 bg-[var(--code-bg)] px-3 py-3 font-mono text-xs text-ink-100">{endpoint}</code>
        <a href="/hq/app" class="btn-primary btn-sm mt-3">Launch HQ</a>

        <!-- Danger zone: delete the container -->
        <details class="mt-6 rounded-xl border border-rose-500/30 bg-rose-500/5 p-3"
                 bind:open={showDelete}>
          <summary class="cursor-pointer select-none text-sm font-semibold text-rose-600 dark:text-rose-300">
            Delete my HQ container
          </summary>
          <p class="mt-2 text-xs leading-5 text-ink-400">
            Permanently deletes this cloud container and its private route. Your
            <strong>encrypted vault is kept</strong> in storage — re-provisioning
            with the same identity restores all your data. Use this to free
            resources or start fresh.
          </p>
          <label class="mt-3 block text-xs text-ink-400">
            Type <span class="font-mono font-semibold text-rose-600 dark:text-rose-300">DELETE</span> to confirm
            <input
              class="input mt-1"
              type="text"
              autocomplete="off"
              spellcheck="false"
              placeholder="DELETE"
              bind:value={deleteConfirm}
              on:keydown={(e) => e.key === 'Enter' && deleteContainer()}
            />
          </label>
          {#if deleteError}
            <p class="mt-2 text-xs text-rose-700 dark:text-rose-300">{deleteError}</p>
          {/if}
          <button
            class="btn-danger btn-sm mt-3"
            on:click={deleteContainer}
            disabled={deleting || deleteConfirm.trim().toUpperCase() !== 'DELETE'}
          >
            {deleting ? 'Deleting…' : 'Delete container'}
          </button>
        </details>
      {:else if state === 'error'}
        <p class="mt-3 text-sm text-rose-700 dark:text-rose-300">{error}</p>
        <div class="mt-3 flex gap-2">
          <button class="btn-ghost btn-sm" on:click={autoLookup}>Retry lookup</button>
          <button class="btn-ghost btn-sm" on:click={startProvision} disabled={!apiOk}>Try provision</button>
        </div>
      {:else}
        <p class="mt-3 text-sm leading-6 text-ink-300">Sign in with Internet Identity to check your HQ.</p>
      {/if}
    {/if}
  {/if}
</div>
