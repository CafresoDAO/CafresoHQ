<script>
  /* Operator control plane (planAdmin only). One card in /hq/settings that
     writes the network-wide switch blob to cafresohq_state.operator_set_config.
     Every client (and each container's serve.py) reads the resulting public
     /operator/config.json and gates features / shows the operator's messages.
     Nothing here is per-user — these are the levers that affect ALL clients. */
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import { isAuthenticated } from '$lib/stores/auth.js';
  import { getStateActor } from '$lib/api/stateActor.js';
  import { refreshOperatorConfig } from '$lib/stores/operator.js';

  let loading = true;
  let unavailable = false;    // canister predates the operator config (pre-upgrade)
  let isAdmin = false;
  let saving = false;
  let msg = '';

  // Editable form (mirrors the JSON shape). Sensible defaults = everything on.
  let gpuEnabled = true, gpuLabel = '', gpuMessage = 'The GPU node is currently down — back shortly.';
  let searchEnabled = true;
  let trialEnabled = true, trialCap = 25;
  let moneyEnabled = true, publishEnabled = true;

  async function load() {
    loading = true; unavailable = false;
    try {
      const actor = await getStateActor();
      isAdmin = await actor.amPlanAdmin();
      if (!isAdmin) { loading = false; return; }
      const raw = await actor.operator_config();
      const c = raw ? JSON.parse(raw) : {};
      const g = c.gpuNode || {}, s = c.searchNetwork || {}, t = c.trialBrain || {},
            m = c.money || {}, p = c.publish || {};
      gpuEnabled = g.enabled !== false;
      gpuLabel = g.label || '';
      gpuMessage = g.downMessage || gpuMessage;
      searchEnabled = s.enabled !== false;
      trialEnabled = t.enabled !== false;
      trialCap = Number.isFinite(t.dailyCap) ? t.dailyCap : 25;
      moneyEnabled = m.enabled !== false;
      publishEnabled = p.enabled !== false;
    } catch (e) {
      if (/has no (update|query) method|operator_config|not found/i.test(e?.message || '')) unavailable = true;
      else if (!/plan admin/i.test(e?.message || '')) msg = e?.message || String(e);
    } finally { loading = false; }
  }
  onMount(() => { if (get(isAuthenticated)) load(); });
  $: if ($isAuthenticated && loading) load();

  async function save() {
    if (saving) return;
    saving = true; msg = '';
    const config = {
      gpuNode: { enabled: gpuEnabled, label: (gpuLabel || '').slice(0, 60),
                 downMessage: (gpuMessage || '').slice(0, 240) },
      searchNetwork: { enabled: searchEnabled },
      trialBrain: { enabled: trialEnabled, dailyCap: Math.max(1, Math.floor(+trialCap) || 25) },
      money: { enabled: moneyEnabled },
      publish: { enabled: publishEnabled },
    };
    try {
      const actor = await getStateActor();
      await actor.operator_set_config(JSON.stringify(config));
      await refreshOperatorConfig(true);
      msg = 'Saved — clients pick this up within a minute.';
    } catch (e) { msg = e?.message || String(e); }
    finally { saving = false; }
  }
</script>

{#if $isAuthenticated && !loading && isAdmin}
  <div class="card space-y-5 p-6">
    <div>
      <div class="page-kicker">Operator · network controls</div>
      <h2 class="mt-1 text-xl font-semibold">Feature switches for every client</h2>
      <p class="mt-2 text-sm leading-6 text-ink-300">
        Network-wide toggles. Flip one and every client — even signed-out visitors — respects it
        within a minute. Nothing here is per-user.
      </p>
    </div>

    {#if unavailable}
      <p class="text-sm text-ink-400">Operator controls activate with the next state-canister upgrade.</p>
    {:else}
      <!-- GPU node -->
      <div class="space-y-2 border-t border-ink-700/30 pt-4">
        <label class="flex items-center gap-3 text-sm font-medium">
          <input type="checkbox" bind:checked={gpuEnabled} />
          GPU inference node available
        </label>
        <p class="text-xs text-ink-400">
          Off = your local model is down. The search worker self-pauses (no SSH needed) and clients
          see your message below instead of routing to it.
        </p>
        <input class="input w-full" placeholder="Node label (e.g. Anthony's 5070 Ti)" bind:value={gpuLabel} maxlength="60" />
        <input class="input w-full" placeholder="Down message shown to clients" bind:value={gpuMessage} maxlength="240" />
      </div>

      <!-- Search network -->
      <div class="space-y-1 border-t border-ink-700/30 pt-4">
        <label class="flex items-center gap-3 text-sm font-medium">
          <input type="checkbox" bind:checked={searchEnabled} />
          Public search network enabled
        </label>
        <p class="text-xs text-ink-400">Off pauses new anonymous questions network-wide — a clean maintenance / abuse kill switch.</p>
      </div>

      <!-- Trial brain -->
      <div class="space-y-2 border-t border-ink-700/30 pt-4">
        <label class="flex items-center gap-3 text-sm font-medium">
          <input type="checkbox" bind:checked={trialEnabled} />
          Free trial brain for new users
        </label>
        <p class="text-xs text-ink-400">Off makes new HQs require the user's own key. The cap throttles the shared cost live — no redeploy.</p>
        <label class="flex items-center gap-2 text-xs text-ink-400">
          Daily free messages per user
          <input class="input w-24" type="number" min="1" bind:value={trialCap} disabled={!trialEnabled} />
        </label>
      </div>

      <!-- Money & publish -->
      <div class="space-y-1 border-t border-ink-700/30 pt-4">
        <label class="flex items-center gap-3 text-sm font-medium">
          <input type="checkbox" bind:checked={moneyEnabled} />
          Money module allowed (agent wallets · payroll)
        </label>
        <label class="mt-1 flex items-center gap-3 text-sm font-medium">
          <input type="checkbox" bind:checked={publishEnabled} />
          Publish-to-web allowed
        </label>
        <p class="text-xs text-ink-400">Network kill switches — off refuses these operations for all clients, overriding their per-user settings.</p>
      </div>

      <div class="flex items-center gap-3 border-t border-ink-700/30 pt-4">
        <button class="btn-primary" on:click={save} disabled={saving}>{saving ? 'Saving…' : 'Save network config'}</button>
        {#if msg}<span class="text-sm text-ink-300">{msg}</span>{/if}
      </div>
    {/if}
  </div>
{/if}
