<script>
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import { endpointUrl, endpointHealth, endpointReady, probeHealth } from '$lib/stores/endpoint.js';
  import { isAuthenticated, authIdentity } from '$lib/stores/auth.js';
  import {
    ensureHqSession, hqSessionReady, hqSessionError, endpointNeedsSession
  } from '$lib/api/hqSession.js';
  import {
    listInstalledServices, setServiceInstalled,
    listAgentWallets, getAgentWalletPolicy, putAgentWalletPolicy, deleteAgentWallet,
    setAllSpendPaused, spendPausedAll,
    agentBalances, fundAgent, agentSend,
    deriveAgentSubaccount, subaccountToHex,
    encodeIcrcAccountText, legacyAccountIdText,
    putSalary, listSalaries, deleteSalary, setPayrollPaused, payrollPaused,
    listPayouts, runPayrollNow, approvePayroll, payrollAllowance, getSpendTotals
  } from '$lib/api/walletServices.js';
  import { sitesConfigured, publishSiteToCanister, listMySites } from '$lib/api/sitesActor.js';
  import { listHqDocs, pushHqDoc } from '$lib/api/stateSync.js';
  import { putWorkReceipt, listWorkReceipts } from '$lib/api/receipts.js';
  import { putMissionSchedule, listMissionSchedules, deleteMissionSchedule, wakeStatus } from '$lib/api/nightMissions.js';
  import { getKeychain, putKeychain } from '$lib/api/keychain.js';
  import { getStateActor, stateCanisterConfigured, stateCanisterId } from '$lib/api/stateActor.js';
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
  import ApprovalSheet from '$lib/components/ApprovalSheet.svelte';
  import { requestApproval } from '$lib/stores/approvalSheet.js';
  import { login } from '$lib/stores/auth.js';
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
    const origin = iframeOrigin();
    if (!origin) return; // never broadcast vault contents with a wildcard target
    iframe.contentWindow.postMessage({ type: 'vault:files:update', files }, origin);
  }

  async function onVaultMessage(e) {
    if (!iframe?.contentWindow || e.source !== iframe.contentWindow) return;
    const origin = iframeOrigin();
    if (!origin || e.origin !== origin) return;

    const { type, reqId, id, name, content } = e.data || {};
    if (!type?.startsWith('vault:')) return;

    // origin is verified non-null above — replies are never posted to '*'.
    const reply = (payload) =>
      iframe.contentWindow?.postMessage({ ...payload, reqId }, origin);

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

  // ── ICP Services + agent-wallet bridge ─────────────────────────────────────
  // Mirrors onVaultMessage: the embedded HQ app (which has no on-chain client)
  // posts `chain:*` requests; we run them here under the user's II identity and
  // reply by reqId. Every real signature happens HERE — the agent only requests.
  function principalText() {
    try { return get(authIdentity)?.getPrincipal()?.toText() || null; } catch { return null; }
  }
  // postMessage's structured clone chokes on nothing here, but BigInt is awkward
  // downstream — stringify all BigInts so the child gets predictable strings.
  function clean(v) {
    if (typeof v === 'bigint') return v.toString();
    if (Array.isArray(v)) return v.map(clean);
    if (v && typeof v === 'object') {
      const o = {};
      for (const k in v) o[k] = clean(v[k]);
      return o;
    }
    return v;
  }

  async function onChainMessage(e) {
    if (!iframe?.contentWindow || e.source !== iframe.contentWindow) return;
    const origin = iframeOrigin();
    // A null origin means we can't name the iframe's document origin — refuse to
    // handle rather than ever posting balances or keys to '*'.
    if (!origin || e.origin !== origin) return;

    const { type, reqId } = e.data || {};
    if (!type?.startsWith('chain:')) return;

    const reply = (payload) =>
      iframe.contentWindow?.postMessage({ ...clean(payload), reqId }, origin);
    const fail = (message) => reply({ type: 'chain:error', message });

    if (!get(isAuthenticated)) return fail('Sign in at ai.cafreso.com to use ICP Services.');
    const p = principalText();
    if (!p) return fail('No Internet Identity principal available.');

    try {
      const d = e.data;
      switch (type) {
        case 'chain:services:list':
          reply({ type: 'chain:services:list:response', services: await listInstalledServices() });
          break;
        case 'chain:services:set':
          await setServiceInstalled(d.serviceId, !!d.enabled, d.configJson || '');
          reply({ type: 'chain:services:set:response', serviceId: d.serviceId, enabled: !!d.enabled });
          break;

        case 'chain:wallet:list':
          reply({ type: 'chain:wallet:list:response', wallets: await listAgentWallets() });
          break;
        case 'chain:wallet:policy':
          reply({ type: 'chain:wallet:policy:response', policy: await getAgentWalletPolicy(d.agentId) });
          break;
        case 'chain:wallet:put': {
          const sub = await deriveAgentSubaccount(p, d.agentId);
          const subaccountHex = subaccountToHex(sub);
          await putAgentWalletPolicy({
            agentId: d.agentId, subaccountHex, token: d.token || 'ICP',
            spendCap: d.spendCap || 0, windowSecs: d.windowSecs || 0, paused: !!d.paused
          });
          reply({ type: 'chain:wallet:put:response', agentId: d.agentId, subaccountHex });
          break;
        }
        case 'chain:wallet:delete':
          await deleteAgentWallet(d.agentId);
          reply({ type: 'chain:wallet:delete:response', agentId: d.agentId, ok: true });
          break;
        case 'chain:wallet:address': {
          const sub = await deriveAgentSubaccount(p, d.agentId);
          const subaccountHex = subaccountToHex(sub);
          reply({
            type: 'chain:wallet:address:response', agentId: d.agentId, owner: p, subaccountHex,
            // Every shareable representation — wallet support is fragmented:
            accountText: encodeIcrcAccountText(p, subaccountHex),      // modern ICRC-1 wallets
            legacyAccountId: legacyAccountIdText(p, subaccountHex)      // exchanges / ICP-ledger-only
          });
          break;
        }
        case 'chain:wallet:balances':
          reply({
            type: 'chain:wallet:balances:response', agentId: d.agentId,
            balances: await agentBalances(p, d.agentId, d.tokens)
          });
          break;
        case 'chain:wallet:fund': {
          const res = await fundAgent({ principalText: p, agentId: d.agentId, tokenKey: d.token, amount: d.amount });
          reply({ type: 'chain:wallet:fund:response', ...res });
          break;
        }
        case 'chain:wallet:send': {
          let res = await agentSend({
            principalText: p, agentId: d.agentId, tokenKey: d.token,
            amount: d.amount, to: d.to, memo: d.memo
          });
          // Over-cap / off-token → the shell asks the user to authorize the send
          // (the one place a real signature is gated). Pause/noWallet are hard stops.
          if (res.status === 'needsApproval') {
            const ok = await requestApproval({
              title: 'Sign an agent transfer',
              rows: [
                { label: 'Agent', value: d.agentId },
                { label: 'Amount', value: `${d.amount} ${d.token}` },
                { label: 'Destination', value: d.to, mono: true }
              ],
              warning: `This transfer ${res.reason || 'needs your approval'} — it falls outside the spending policy you set, so nothing moves without this signature.`,
              note: 'Declining costs nothing; the agent is simply told no.',
              confirmLabel: `Sign · send ${d.amount} ${d.token}`,
              danger: true
            });
            if (ok) {
              res = await agentSend({
                principalText: p, agentId: d.agentId, tokenKey: d.token,
                amount: d.amount, to: d.to, memo: d.memo, force: true
              });
            } else {
              res = { status: 'declined' };
            }
          }
          reply({ type: 'chain:wallet:send:response', ...res });
          break;
        }
        case 'chain:wallet:pause-all':
          await setAllSpendPaused(!!d.paused);
          reply({ type: 'chain:wallet:pause-all:response', paused: !!d.paused });
          break;
        case 'chain:wallet:paused-all':
          reply({ type: 'chain:wallet:paused-all:response', paused: await spendPausedAll() });
          break;

        case 'chain:publish': {
          if (!sitesConfigured()) { reply({ type: 'chain:publish:response', mode: 'unconfigured' }); break; }
          const res = await publishSiteToCanister({ project: d.project, files: d.files || [] });
          reply({ type: 'chain:publish:response', mode: 'canister', ...res });
          break;
        }

        // ── read-only surface for hqsh + status chrome ──────────────────────
        case 'chain:whoami':
          reply({ type: 'chain:whoami:response', principal: p });
          break;
        case 'chain:sites:list':
          reply({ type: 'chain:sites:list:response', sites: await listMySites() });
          break;
        case 'chain:docs:list':
          reply({ type: 'chain:docs:list:response', docs: await listHqDocs() });
          break;
        case 'chain:docs:put': {
          // Generic HQ-doc anchor (journal digests etc.). Namespaced to
          // journal/… so the iframe can't overwrite tasks/settings/keychain.
          const name = String(d.name || '');
          if (!/^journal\//.test(name)) { fail('chain:docs:put only accepts journal/* docs'); break; }
          const ok = await pushHqDoc(name, String(d.body || ''));
          reply({ type: 'chain:docs:put:response', name, ok: !!ok });
          break;
        }

        // ── Work receipts (Sprint 3) — anchor + list; verify page is public ──
        case 'chain:receipt:put': {
          const res = await putWorkReceipt({
            agentId: d.agentId, agentName: d.agentName, tool: d.tool,
            title: d.title, argHash: d.argHash, contentSha256: d.contentSha256,
            ownerPrincipalText: p
          });
          reply({ type: 'chain:receipt:put:response', ...res });
          break;
        }
        case 'chain:receipt:list':
          reply({ type: 'chain:receipt:list:response', receipts: await listWorkReceipts(p) });
          break;

        // ── Night Shift wake mirror (Sprint 4 MVP-2) — unsigned config rows;
        // the canister-side outcall is planAdmin-gated and ships dark.
        case 'chain:missions:put': {
          const ok = await putMissionSchedule({
            id: d.id, agentId: d.agentId, topic: d.topic, recurrence: d.recurrence,
            durationSecs: d.durationSecs, intervalSecs: d.intervalSecs,
            enabled: d.enabled !== false, nextRunAtMs: d.nextRunAtMs
          });
          reply({ type: 'chain:missions:put:response', id: d.id, ok: !!ok });
          break;
        }
        case 'chain:missions:list':
          reply({ type: 'chain:missions:list:response', schedules: await listMissionSchedules() });
          break;
        case 'chain:missions:delete':
          reply({ type: 'chain:missions:delete:response', id: d.id, ok: await deleteMissionSchedule(d.id) });
          break;
        case 'chain:missions:wake-status':
          reply({ type: 'chain:missions:wake-status:response', ...(await wakeStatus()) });
          break;
        case 'chain:status': {
          let cycles = null;
          if (stateCanisterConfigured()) {
            try { cycles = await (await getStateActor()).cycle_balance(); } catch {}
          }
          reply({
            type: 'chain:status:response', principal: p,
            stateCanister: get(stateCanisterId), configured: stateCanisterConfigured(), cycles
          });
          break;
        }

        // ── Payroll (Sprint 2) — the canister timer pays under a user-signed
        // ICRC-2 allowance. Policy writes are unsigned config; the ONE real
        // signature (icrc2_approve) is gated by an explicit confirm below.
        case 'chain:payroll:list':
          reply({
            type: 'chain:payroll:list:response',
            salaries: await listSalaries(), paused: await payrollPaused()
          });
          break;
        case 'chain:payroll:put':
          await putSalary({
            agentId: d.agentId, tokenKey: d.token || 'ICP', amount: d.amount,
            lowWatermark: d.lowWatermark || 0, periodSecs: d.periodSecs,
            mode: d.mode === 'refill' ? 'refill' : 'salary', active: d.active !== false
          });
          reply({ type: 'chain:payroll:put:response', agentId: d.agentId, ok: true });
          break;
        case 'chain:payroll:delete':
          reply({ type: 'chain:payroll:delete:response', agentId: d.agentId, ok: await deleteSalary(d.agentId) });
          break;
        case 'chain:payroll:pause':
          await setPayrollPaused(!!d.paused);
          reply({ type: 'chain:payroll:pause:response', paused: !!d.paused });
          break;
        case 'chain:payroll:payouts':
          reply({ type: 'chain:payroll:payouts:response', payouts: await listPayouts() });
          break;
        case 'chain:payroll:run':
          reply({ type: 'chain:payroll:run:response', agentId: d.agentId, result: await runPayrollNow(d.agentId) });
          break;
        case 'chain:payroll:allowance':
          reply({
            type: 'chain:payroll:allowance:response', token: d.token || 'ICP',
            allowance: await payrollAllowance({ tokenKey: d.token || 'ICP', ownerPrincipalText: p })
          });
          break;
        case 'chain:payroll:approve': {
          // REAL signature — never auto-signed off an iframe request. Note the
          // allowance OVERWRITES the previous one; it is the payroll hard budget.
          const days = Number(d.expiresDays) || 0;
          const ok = await requestApproval({
            title: 'Approve the payroll budget',
            rows: [
              { label: 'Token', value: d.token || 'ICP' },
              { label: 'Hard budget', value: `${d.amount} ${d.token || 'ICP'}` },
              { label: 'Expires', value: days ? `in ${days} days` : 'No expiry' },
              { label: 'Spender', value: get(stateCanisterId) || 'HQ payroll canister', mono: true }
            ],
            warning: 'This REPLACES any previous payroll allowance. It is the absolute ceiling — the payroll canister can never move more than this from your main account, no matter what any agent does.',
            note: 'You can pause payroll or set a new (including zero) budget at any time.',
            confirmLabel: `Approve ${d.amount} ${d.token || 'ICP'}`
          });
          if (!ok) { reply({ type: 'chain:payroll:approve:response', status: 'declined' }); break; }
          const res = await approvePayroll({
            tokenKey: d.token || 'ICP', amount: d.amount,
            expiresAtMs: days ? Date.now() + days * 86_400_000 : null, noExpiry: !days
          });
          reply({ type: 'chain:payroll:approve:response', ...(res.err ? { status: 'error', error: res.err } : { status: 'ok', block: res.ok }) });
          break;
        }
        case 'chain:wallet:totals':
          reply({ type: 'chain:wallet:totals:response', totals: await getSpendTotals() });
          break;

        // ── BYOK keychain: ciphertext lives on-chain, crypto happens HERE ───
        // (plaintext keys cross postMessage shell→iframe only — same exposure
        // class as vault:read; the reply targetOrigin is always pinned above.)
        case 'chain:keychain:get': {
          const kc = await getKeychain();
          reply({ type: 'chain:keychain:get:response', keys: kc.keys, version: kc.version });
          break;
        }
        case 'chain:keychain:put': {
          const updates = d.keys || (d.provider ? { [d.provider]: d.key || '' } : {});
          const res = await putKeychain(updates);
          reply({ type: 'chain:keychain:put:response', ...res });
          break;
        }

        default:
          fail('Unknown chain request: ' + type);
      }
    } catch (err) {
      fail(err?.message || String(err));
    }
  }

  // The embedded HQ posts this when the gateway starts 401ing — the
  // hq_session cookie expired mid-use. Re-mint and reload the iframe so the
  // user recovers in place instead of facing a frozen app.
  let remintBusy = false;
  async function onSessionExpired(e) {
    if (!iframe?.contentWindow || e.source !== iframe.contentWindow) return;
    if (e.data?.type !== 'hq:session-expired' || remintBusy) return;
    remintBusy = true;
    try {
      const ok = await ensureHqSession();
      if (ok !== false) reload();
    } catch (_) { /* hqSessionError card offers manual retry */ }
    remintBusy = false;
  }

  let vaultUnsub;

  onMount(() => {
    if (typeof window !== 'undefined') {
      window.addEventListener('keydown', onKey);
      window.addEventListener('message', onVaultMessage);
      window.addEventListener('message', onChainMessage);
      window.addEventListener('message', onSessionExpired);
    }
    vaultUnsub = vaultFiles.subscribe((files) => pushFiles(files));
  });

  onDestroy(() => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('message', onVaultMessage);
      window.removeEventListener('message', onChainMessage);
      window.removeEventListener('message', onSessionExpired);
    }
    vaultUnsub?.();
  });

  function onIframeLoad() {
    loaded = true;
    setTimeout(() => pushFiles(get(vaultFiles)), 600);
  }

  // ── Staged launch progress ──────────────────────────────────────────────
  // One stepper derived from the same reactives that gate the iframe, so the
  // cold-start wait reads as an intentional sequence instead of a stack of
  // disconnected status cards. mixedContent surfaces as an error on the
  // container step (the container may be healthy, but it can't be embedded).
  $: launchSteps = [
    {
      id: 'signin', label: 'Sign in with Internet Identity',
      state: $isAuthenticated ? 'done' : 'active'
    },
    {
      id: 'container', label: 'Wake your container',
      state: !$isAuthenticated ? 'pending'
        : mixedContent || !$endpointUrl || $endpointHealth.state === 'error' ? 'error'
        : $endpointReady ? 'done'
        : 'active'
    },
    {
      id: 'session', label: 'Secure your private session',
      state: !$isAuthenticated || mixedContent || !$endpointReady ? 'pending'
        : sessionOk ? 'done'
        : $hqSessionError ? 'error'
        : 'active'
    },
    {
      id: 'open', label: 'Open the office',
      state: fullscreenIframe ? 'done' : 'pending'
    }
  ];
</script>

{#if fullscreenIframe}
  <div class="fixed inset-0 z-40 bg-ink-900">
    {#if !loaded}
      <!-- Pixel-styled handoff: the last thing the shell shows before the
           pixel-art office paints, so the transition reads as entering the
           building rather than switching products. Solid (not translucent)
           so the iframe's first-paint flash never shows through. -->
      <div class="pointer-events-none absolute inset-0 z-10 grid place-items-center bg-ink-900">
        <div class="pixel-load-card">
          <div class="pixel-load-office" aria-hidden="true">🏢</div>
          <div class="pixel-load-text">OPENING YOUR OFFICE<span class="pixel-caret">▮</span></div>
        </div>
      </div>
    {/if}

    <iframe
      bind:this={iframe}
      src={appUrl}
      title="CafresoHQ HQ"
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
      <div class="page-kicker">CafresoHQ / HQ</div>
      <h1 class="page-title mt-4">Opening your office<span class="text-brand-500">.</span></h1>
      <p class="mt-4 max-w-2xl text-sm leading-6 text-ink-300">
        Your agent command center runs in your own private container — here's where it's at:
      </p>
      <ol class="mt-6 space-y-3">
        {#each launchSteps as s, i}
          <li class="flex items-center gap-3 text-sm">
            {#if s.state === 'done'}
              <span class="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-brand-500/15 text-xs font-bold text-brand-600 dark:text-brand-300">✓</span>
            {:else if s.state === 'active'}
              <span class="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-brand-400/70">
                <span class="glow-dot text-brand-400 animate-pulse"></span>
              </span>
            {:else if s.state === 'error'}
              <span class="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-red-500/15 text-xs font-bold text-red-500">!</span>
            {:else}
              <span class="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-ink-600/50 text-xs text-ink-400">{i + 1}</span>
            {/if}
            <span class={s.state === 'pending' ? 'text-ink-400' : s.state === 'error' ? 'font-medium text-red-500' : 'text-ink-200'}>
              {s.label}
            </span>
            {#if s.state === 'active'}
              <span class="text-xs text-ink-400">— in progress…</span>
            {/if}
          </li>
        {/each}
      </ol>
    </header>

    {#if !$isAuthenticated}
      <div class="card space-y-3 p-5 text-sm leading-6 text-ink-300">
        <p>Sign in to open your office. Your Internet Identity scopes your vault, agents, and funds — nothing here is shared.</p>
        <button class="btn-primary" on:click={login}>Sign in with Internet Identity</button>
      </div>
    {:else if $endpointHealth.state === 'idle' || $endpointHealth.state === 'probing'}
      <div class="card flex items-center gap-3 p-5 text-sm text-ink-300">
        <span class="glow-dot text-brand-400 animate-pulse"></span>
        Waking your container — a cold start can take up to half a minute. Your office opens automatically the moment it answers.
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
          Your container is answering, but its address starts with plain
          <code class="font-mono text-brand-600 dark:text-brand-300">http://</code> and this page is secure
          (<code class="font-mono text-brand-600 dark:text-brand-300">https://</code>) — browsers refuse to embed
          one inside the other. Nothing is broken on your end.
        </p>
        <p class="text-sm leading-6 text-ink-300">
          <strong>Two ways forward:</strong> open HQ in its own tab (works right now), or point your endpoint at the
          secure gateway (<code class="font-mono text-brand-600 dark:text-brand-300">hq.cafreso.com/u/&lt;your-slug&gt;/</code>)
          in Settings so it can live here permanently.
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

<ApprovalSheet />

<style>
  /* Pixel-styled handoff card — hard edges, offset shadow, stepped motion:
     a deliberate visual bridge into the pixel-art app the iframe paints. */
  .pixel-load-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 14px;
    padding: 28px 36px;
    border: 2px solid hsl(var(--foreground) / 0.3);
    background: hsl(var(--background));
    box-shadow: 6px 6px 0 hsl(var(--foreground) / 0.18);
  }
  .pixel-load-office {
    font-size: 44px;
    line-height: 1;
    animation: pixel-bob 1.1s steps(2, end) infinite;
  }
  .pixel-load-text {
    font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.3em;
    color: hsl(var(--foreground) / 0.85);
  }
  .pixel-caret {
    margin-left: 2px;
    animation: pixel-blink 1s steps(1, end) infinite;
  }
  @keyframes pixel-blink { 50% { opacity: 0; } }
  @keyframes pixel-bob { 50% { transform: translateY(-4px); } }
  @media (prefers-reduced-motion: reduce) {
    .pixel-load-office, .pixel-caret { animation: none; }
  }
</style>
