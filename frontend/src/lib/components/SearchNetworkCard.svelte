<script>
  /* Search-network operations card (hq/settings).
     Three audiences in one card:
       · anyone signed-in → register their container as a worker (the browser
         generates the 32-byte HMAC secret and shows it ONCE — the canister
         stores it for verification but never returns it);
       · a registered operator → live status, jobs done, accrued/earned;
       · the plan admin → approve/suspend workers, set the per-job rate, and
         SIGN the search-treasury allowance (the hard payout budget). */
  import { onMount } from 'svelte';
  import { isAuthenticated } from '$lib/stores/auth.js';
  import { getStateActor, stateCanisterId } from '$lib/api/stateActor.js';
  import { approve, TOKENS } from '$lib/api/icrc1.js';
  import { requestApproval } from '$lib/stores/approvalSheet.js';
  import ApprovalSheet from '$lib/components/ApprovalSheet.svelte';
  import { get } from 'svelte/store';

  let me = null;              // my Worker record | null
  let loading = true;
  let unavailable = false;    // canister predates the network (pre-upgrade)
  let isAdmin = false;
  let workers = [];
  let payStatus = null;

  // Registration
  let name = '';
  let freshSecret = '';       // shown exactly once
  let registering = false;
  let regError = '';

  // Admin pay config
  let rateInput = '0.00001';  // ICP per job
  let minInput = '0.001';
  let budgetInput = '500';
  let treasuryInput = '0.05';
  let adminMsg = '';

  async function load() {
    loading = true;
    unavailable = false;
    try {
      const actor = await getStateActor();
      const [myRes, admin] = await Promise.all([actor.worker_my_status(), actor.amPlanAdmin()]);
      me = myRes.length ? myRes[0] : null;
      isAdmin = admin;
      if (isAdmin) {
        [workers, payStatus] = await Promise.all([actor.worker_admin_list(), actor.search_pay_status()]);
        budgetInput = String(payStatus.budgetPerDay);
      } else {
        payStatus = await actor.search_pay_status();
      }
    } catch (e) {
      if (/has no (update|query) method|not found/i.test(e?.message || '')) unavailable = true;
    } finally {
      loading = false;
    }
  }
  onMount(() => { if (get(isAuthenticated)) load(); });
  $: if ($isAuthenticated && loading) load();

  function hex(bytes) { return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join(''); }

  async function register() {
    if (registering) return;
    regError = '';
    registering = true;
    try {
      const secretBytes = crypto.getRandomValues(new Uint8Array(32));
      const secretHex = hex(secretBytes);
      const actor = await getStateActor();
      await actor.worker_register((name || 'my-hq-worker').trim().slice(0, 64), secretHex, '');
      freshSecret = secretHex;   // one-time display; never retrievable again
      await load();
    } catch (e) {
      regError = e?.message || String(e);
    } finally {
      registering = false;
    }
  }

  function envSnippet() {
    return [
      'SEARCH_WORKER=1',
      `WORKER_PRINCIPAL=${me ? me.principal.toText() : '<your principal>'}`,
      `WORKER_SECRET=${freshSecret}`,
      'BRAVE_API_KEY=<your free key from brave.com/search/api>'
    ].join('\n');
  }

  async function setStatus(p, status) {
    try {
      const actor = await getStateActor();
      await actor.worker_admin_set_status(p, status);
      workers = await actor.worker_admin_list();
    } catch (e) { adminMsg = e?.message || String(e); }
  }

  const E8S = 100_000_000;
  async function savePay() {
    adminMsg = '';
    try {
      const actor = await getStateActor();
      await actor.search_admin_set_pay(
        // ICP ledger; the rail every worker payout rides.
        (await import('@dfinity/principal')).Principal.fromText(TOKENS.ICP.canister),
        BigInt(Math.round(parseFloat(rateInput || '0') * E8S)),
        BigInt(Math.round(parseFloat(minInput || '0') * E8S))
      );
      await actor.search_admin_set_budget(BigInt(parseInt(budgetInput || '500', 10)));
      payStatus = await actor.search_pay_status();
      adminMsg = 'Saved.';
    } catch (e) { adminMsg = e?.message || String(e); }
  }

  async function signTreasury() {
    adminMsg = '';
    const amt = parseFloat(treasuryInput || '0');
    if (!(amt > 0)) { adminMsg = 'Enter a treasury amount.'; return; }
    const ok = await requestApproval({
      title: 'Approve the search treasury',
      rows: [
        { label: 'Token', value: 'ICP' },
        { label: 'Hard budget', value: `${amt} ICP` },
        { label: 'Pays', value: 'search-network workers, per fulfilled job' },
        { label: 'Spender', value: get(stateCanisterId), mono: true }
      ],
      warning: 'This REPLACES any previous search-treasury allowance. Workers can never be paid more than this in total, no matter how many jobs they fulfill.',
      note: 'Independent of your payroll allowance. Start tiny — you can always raise it.',
      confirmLabel: `Approve ${amt} ICP`
    });
    if (!ok) return;
    const res = await approve({
      tokenKey: 'ICP',
      spenderPrincipalText: get(stateCanisterId),
      amount: amt,
      noExpiry: true
    });
    adminMsg = res?.err ? `Allowance failed: ${res.err}` : 'Treasury allowance signed.';
  }

  function e8sToIcp(n) { return (Number(n) / E8S).toLocaleString(undefined, { maximumFractionDigits: 8 }); }
  function fmtAgo(ns) {
    const ms = Number(ns) / 1e6;
    if (!ms) return 'never';
    const s = (Date.now() - ms) / 1000;
    if (s < 90) return 'just now';
    if (s < 3600) return `${Math.round(s / 60)}m ago`;
    if (s < 86400) return `${Math.round(s / 3600)}h ago`;
    return `${Math.round(s / 86400)}d ago`;
  }
</script>

<div class="card space-y-5 p-6">
  <div>
    <div class="page-kicker">Search network</div>
    <h2 class="mt-1 text-xl font-semibold">Put your HQ to work</h2>
    <p class="mt-2 text-sm leading-6 text-ink-300">
      Your container can join the research network: it answers public library queries with its own
      Brave key and local model, every answer is attributed to you on-chain — and fulfilled jobs
      earn ICP once the admin funds the treasury.
    </p>
  </div>

  {#if !$isAuthenticated}
    <p class="text-sm text-ink-400">Sign in to register a worker.</p>
  {:else if loading}
    <p class="text-sm text-ink-400">Loading worker status…</p>
  {:else if unavailable}
    <p class="text-sm text-ink-400">
      The search network activates with the next state-canister upgrade — registration opens then.
    </p>
  {:else}
    {#if !me}
      <div class="space-y-3">
        <div class="flex flex-col gap-2 sm:flex-row">
          <input class="input flex-1" placeholder="Worker name (e.g. anthony-macbook)" bind:value={name} maxlength="64" />
          <button class="btn-primary" on:click={register} disabled={registering}>
            {registering ? 'Registering…' : 'Register my worker'}
          </button>
        </div>
        {#if regError}<p class="text-sm text-rose-600">{regError}</p>{/if}
      </div>
    {:else}
      <div class="flex flex-wrap items-center gap-2 text-sm">
        <span class="font-semibold">{me.name}</span>
        {#if me.status === 'approved'}<span class="pill-ok">approved</span>
        {:else if me.status === 'pending'}<span class="pill-warn">awaiting approval</span>
        {:else}<span class="rounded-full bg-rose-500/15 px-2 py-0.5 text-xs font-semibold text-rose-600">suspended</span>{/if}
        <span class="text-xs text-ink-400">last seen {fmtAgo(me.lastSeen)}</span>
      </div>
      <div class="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div><div class="text-xs uppercase tracking-wide text-ink-400">Jobs done</div><div class="font-semibold">{me.jobsDone}</div></div>
        <div><div class="text-xs uppercase tracking-wide text-ink-400">Failed</div><div class="font-semibold">{me.jobsFailed}</div></div>
        <div><div class="text-xs uppercase tracking-wide text-ink-400">Accrued</div><div class="font-semibold">{e8sToIcp(me.accruedE8s)} ICP</div></div>
        <div><div class="text-xs uppercase tracking-wide text-ink-400">Paid out</div><div class="font-semibold">{e8sToIcp(me.earnedE8s)} ICP</div></div>
      </div>
      <button class="btn-ghost text-xs" on:click={register} disabled={registering}>
        {registering ? 'Rotating…' : 'Rotate secret'}
      </button>
    {/if}

    {#if freshSecret}
      <div class="space-y-2 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4">
        <p class="text-sm font-semibold">Your worker secret — shown once, copy it now.</p>
        <p class="text-xs leading-5 text-ink-400">
          Add these to the environment where your container runs, then restart it. The canister
          stores this secret to verify your worker's signatures; it can never be read back.
        </p>
        <pre class="overflow-x-auto rounded-lg bg-ink-900/90 p-3 font-mono text-xs leading-5 text-ink-100">{envSnippet()}</pre>
        <button class="btn-ghost text-xs" on:click={() => { try { navigator.clipboard.writeText(envSnippet()); } catch {} }}>
          Copy env block
        </button>
      </div>
    {/if}

    {#if payStatus}
      <p class="text-xs text-ink-400">
        Network pay: {payStatus.rateE8s > 0
          ? `${e8sToIcp(payStatus.rateE8s)} ICP per fulfilled job (min payout ${e8sToIcp(payStatus.minE8s)} ICP)`
          : 'not configured yet — jobs are volunteer until the admin sets a rate'}
        · daily budget {payStatus.budgetPerDay} answers
      </p>
    {/if}

    {#if isAdmin}
      <div class="space-y-4 border-t border-ink-700/30 pt-4">
        <div class="page-kicker">Admin · network operations</div>

        {#if workers.length === 0}
          <p class="text-sm text-ink-400">No workers registered yet.</p>
        {:else}
          <div class="overflow-x-auto">
            <table class="w-full text-left text-sm">
              <thead>
                <tr class="text-xs uppercase tracking-wide text-ink-400">
                  <th class="py-1 pr-3">Worker</th><th class="py-1 pr-3">Status</th>
                  <th class="py-1 pr-3">Seen</th><th class="py-1 pr-3">Done</th>
                  <th class="py-1 pr-3">Accrued</th><th class="py-1"></th>
                </tr>
              </thead>
              <tbody>
                {#each workers as w (w.principal.toText())}
                  <tr class="border-t border-ink-700/20">
                    <td class="py-2 pr-3">
                      <div class="font-medium">{w.name}</div>
                      <div class="font-mono text-[10px] text-ink-400">{w.principal.toText().slice(0, 20)}…</div>
                    </td>
                    <td class="py-2 pr-3">{w.status}</td>
                    <td class="py-2 pr-3 text-xs">{fmtAgo(w.lastSeen)}</td>
                    <td class="py-2 pr-3">{w.jobsDone}</td>
                    <td class="py-2 pr-3 text-xs">{e8sToIcp(w.accruedE8s)}</td>
                    <td class="py-2 text-right">
                      {#if w.status !== 'approved'}
                        <button class="btn-primary btn-sm text-xs" on:click={() => setStatus(w.principal, 'approved')}>Approve</button>
                      {:else}
                        <button class="btn-ghost btn-sm text-xs" on:click={() => setStatus(w.principal, 'suspended')}>Suspend</button>
                      {/if}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}

        <div class="grid gap-3 sm:grid-cols-3">
          <label class="text-xs text-ink-400">Rate (ICP / job)
            <input class="input mt-1 w-full" bind:value={rateInput} inputmode="decimal" />
          </label>
          <label class="text-xs text-ink-400">Min payout (ICP)
            <input class="input mt-1 w-full" bind:value={minInput} inputmode="decimal" />
          </label>
          <label class="text-xs text-ink-400">Daily answer budget
            <input class="input mt-1 w-full" bind:value={budgetInput} inputmode="numeric" />
          </label>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button class="btn-ghost" on:click={savePay}>Save network config</button>
          <input class="input w-28" bind:value={treasuryInput} inputmode="decimal" aria-label="Treasury amount in ICP" />
          <button class="btn-primary" on:click={signTreasury}>Sign treasury allowance</button>
        </div>
        {#if adminMsg}<p class="text-sm text-ink-300">{adminMsg}</p>{/if}
      </div>
    {/if}
  {/if}
</div>

<ApprovalSheet />
