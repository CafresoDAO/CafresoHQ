<script>
  import { burnTarget, goldBalance, tweaks, confirmGoldTip, refreshGoldBalance } from '$lib/stores/blog.js';
  import { isAuthenticated, login } from '$lib/stores/auth.js';
  import { burnTip } from '$lib/api/devlog.js';
  import { transfer } from '$lib/api/icrc1.js';
  import { getTreasury } from '$lib/api/store.js';
  import { goldToRaw, fmtGold } from '$lib/gold.js';
  import { prices } from '$lib/stores/prices.js';
  import Icon from './Icon.svelte';
  import Modal from './Modal.svelte';
  import GoldCoin from './GoldCoin.svelte';
  import Button from './Button.svelte';

  // Real gold: tips move sGLDT on the ledger (buyer → DAO treasury), then the
  // devlog canister records the RAW e8s amount for counters + leaderboard.
  const PRESETS = [0.01, 0.1, 1, 5, 25];
  const TIP_MAX = 25;

  let amount = 0.1;
  let phase = 'choose'; // 'choose' | 'burning' | 'done' | 'error'
  let errorMsg = '';
  let holdProgress = 0;
  let holdTimer = null;

  $: usdApprox = $prices?.sGLDT > 0 ? amount * $prices.sGLDT : null;
  $: balance = $goldBalance ?? 0;

  $: if ($burnTarget) {
    phase = 'choose';
    errorMsg = '';
    amount = 0.1;
    holdProgress = 0;
  }

  function close() {
    burnTarget.set(null);
    if (holdTimer) {
      clearInterval(holdTimer);
      holdTimer = null;
    }
    holdProgress = 0;
  }

  let lastBlock = null;

  async function doConfirm() {
    const slug = $burnTarget;
    if (!$isAuthenticated) { errorMsg = 'Sign in with Internet Identity to tip gold.'; phase = 'error'; return; }
    if (!(amount > 0)) return;
    if (amount > balance) { errorMsg = `That's more sGLDT than you hold (${fmtGold(balance)}).`; phase = 'error'; return; }
    phase = 'burning';

    const treasury = await getTreasury();
    if (!treasury) { errorMsg = 'DAO treasury is not configured yet — ask an admin to set it on /admin/store.'; phase = 'error'; return; }

    // 1) Move real sGLDT on the ledger.
    const raw = goldToRaw(amount);
    const t = await transfer({
      tokenKey: 'sGLDT',
      toPrincipalText: treasury,
      amount: raw,
      memoText: `cafreso-tip-${slug}`.slice(0, 32)
    });
    if (t.err) { errorMsg = t.err; phase = 'error'; return; }
    lastBlock = t.ok;

    // 2) Record it on the devlog canister (raw e8s) with the ledger block as proof.
    const [res] = await Promise.all([
      burnTip(slug, raw, t.ok),
      new Promise((r) => setTimeout(r, 900))
    ]);
    if (res?.err) console.warn('[tip] ledger transfer ok but recordBurn failed:', res.err);
    phase = 'done';
    confirmGoldTip(slug, amount);
    refreshGoldBalance();
    await new Promise((r) => setTimeout(r, 1200));
    close();
  }

  function startHold() {
    if (holdTimer) return;
    const start = Date.now();
    holdTimer = setInterval(() => {
      holdProgress = Math.min(1, (Date.now() - start) / 1500);
      if (holdProgress >= 1) {
        clearInterval(holdTimer);
        holdTimer = null;
        doConfirm();
      }
    }, 16);
  }
  function stopHold() {
    if (holdTimer) {
      clearInterval(holdTimer);
      holdTimer = null;
    }
    if (holdProgress < 1) holdProgress = 0;
  }

  const C = 2 * Math.PI * 58;
</script>

<Modal
  open={!!$burnTarget}
  on:close={close}
  ariaLabel="Tip gold (sGLDT)"
  backdropClass="fade-up flex items-center justify-center"
  backdropStyle="background: hsl(24 48% 8% / 0.55); backdrop-filter: blur(6px); padding: 16px;"
  panelClass="relative overflow-hidden rounded-2xl"
  panelStyle="
    max-width: 440px; width: 100%; padding: 28px;
    background: hsl(var(--pg-surface));
    border: 1px solid hsl(var(--pg-border));
    box-shadow: 0 28px 60px -20px hsl(24 40% 8% / 0.55);
  "
>
      <button
        on:click={close}
        aria-label="Close"
        class="absolute bg-transparent border-none cursor-pointer"
        style="top: 14px; right: 14px; width: 32px; height: 32px; border-radius: 8px; color: hsl(var(--pg-fg-muted));"
      >
        <Icon name="x" size={18} />
      </button>

      {#if phase === 'choose'}
        <div class="text-center mb-4">
          <div
            class="uppercase font-bold mb-2"
            style="font-size: 11px; letter-spacing: 0.12em; color: hsl(32 72% 50%);"
          >Tip gold</div>
          <h2 style="font-size: 28px; font-weight: 800; margin: 0 0 8px; letter-spacing: -0.02em;">
            Tipping sGLDT
          </h2>
          <p class="m-0 mx-auto" style="font-size: 13.5px; color: hsl(var(--pg-fg-muted)); line-height: 1.5; max-width: 40ch;">
            Real gold-backed sGLDT moves to the DAO treasury on the ledger, then the
            post's tip counter and your leaderboard rank update on-chain.
          </p>
        </div>

        {#if $tweaks.burnModel === 'quick'}
          <div class="grid mb-4" style="grid-template-columns: repeat(5, 1fr); gap: 8px;">
            {#each PRESETS as n}
              <button
                on:click={() => (amount = n)}
                class="flex flex-col items-center gap-0.5 cursor-pointer"
                style="
                  padding: 12px 0; border-radius: 10px;
                  background: {amount === n ? 'hsl(45 95% 62%)' : 'hsl(var(--pg-elevated))'};
                  border: 1px solid {amount === n ? 'hsl(32 72% 50%)' : 'hsl(var(--pg-border))'};
                  font-family: inherit; font-size: 13px; font-weight: 600;
                "
              >
                <GoldCoin size={18} /> {fmtGold(n)}
              </button>
            {/each}
          </div>
        {/if}

        {#if $tweaks.burnModel === 'slider'}
          <div class="mb-4">
            <div class="text-center mb-3.5">
              <div
                class="inline-flex items-center gap-2"
                style="font-size: 42px; font-weight: 800; letter-spacing: -0.03em;"
              >
                {fmtGold(amount)} <GoldCoin size={32} />
              </div>
              <div style="font-size: 12px; color: hsl(var(--pg-fg-muted));">
                {#if usdApprox !== null}≈ ${usdApprox.toFixed(2)} USD · {/if}{balance > 0 ? Math.round((amount / balance) * 100) : 0}% of your balance
              </div>
            </div>
            <input
              type="range"
              min={0.01}
              max={Math.max(0.01, Math.min(TIP_MAX, balance || TIP_MAX))}
              step={0.01}
              bind:value={amount}
              aria-label="Amount of sGLDT to tip"
              aria-valuetext="{fmtGold(amount)} sGLDT"
              style="width: 100%; accent-color: hsl(32 72% 50%);"
            />
            <div class="flex justify-between text-[11px] mt-1" style="color: hsl(var(--pg-fg-muted));">
              <span>0.01</span><span>{fmtGold(Math.min(TIP_MAX, balance || TIP_MAX))}</span>
            </div>
          </div>
        {/if}

        {#if $tweaks.burnModel === 'hold'}
          <div class="text-center mb-3.5">
            <div class="text-[13px] mb-3.5" style="color: hsl(var(--pg-fg-muted));">Amount to tip (sGLDT)</div>
            <div class="flex gap-2 justify-center mb-5">
              {#each PRESETS as n}
                <button
                  on:click={() => (amount = n)}
                  class="cursor-pointer"
                  style="
                    padding: 8px 16px; border-radius: 999px;
                    background: {amount === n ? 'hsl(24 48% 12%)' : 'hsl(var(--pg-elevated))'};
                    color: {amount === n ? 'white' : 'hsl(var(--pg-fg))'};
                    border: 1px solid {amount === n ? 'hsl(24 48% 12%)' : 'hsl(var(--pg-border))'};
                    font-family: inherit; font-size: 13px; font-weight: 600;
                  "
                >{fmtGold(n)}</button>
              {/each}
            </div>
            <div class="relative mx-auto mb-3.5" style="width: 150px; height: 150px;">
              <svg viewBox="0 0 130 130" width="150" height="150">
                <circle cx="65" cy="65" r="58" fill="none" stroke="hsl(var(--pg-border))" stroke-width="5" />
                <circle
                  cx="65" cy="65" r="58" fill="none"
                  stroke="hsl(32 72% 50%)" stroke-width="5" stroke-linecap="round"
                  stroke-dasharray={C}
                  stroke-dashoffset={C * (1 - holdProgress)}
                  transform="rotate(-90 65 65)"
                  style="transition: stroke-dashoffset .1s linear;"
                />
              </svg>
              <button
                on:mousedown={startHold}
                on:mouseup={stopHold}
                on:mouseleave={stopHold}
                on:touchstart={startHold}
                on:touchend={stopHold}
                class="absolute cursor-pointer flex items-center justify-center font-bold text-center select-none"
                style="
                  inset: 14px; border-radius: 50%;
                  background: radial-gradient(circle at 30% 30%, hsl(45 95% 70%), hsl(45 95% 55%));
                  border: 2px solid hsl(32 72% 45%);
                  font-family: inherit; font-size: 13px; color: hsl(24 48% 12%);
                  box-shadow: inset 0 -4px 10px hsl(32 72% 35% / 0.3), 0 6px 14px -4px hsl(32 72% 40% / 0.4);
                  transform: {holdProgress > 0 ? `scale(${1 - holdProgress * 0.04})` : 'scale(1)'};
                  transition: transform .1s linear;
                "
              >
                <div style="line-height: 1.15;">
                  <Icon name="fire" size={26} weight="fill" /><br />
                  <span class="uppercase" style="font-size: 11px; letter-spacing: 0.08em;">Hold to tip</span>
                </div>
              </button>
            </div>
            <div style="font-size: 12.5px; color: hsl(var(--pg-fg-muted));">
              Hold the button until the ring fills.
            </div>
          </div>
        {/if}

        {#if $tweaks.burnModel !== 'hold'}
          <Button
            variant="default"
            size="lg"
            class="!w-full !bg-[hsl(45_95%_62%)] !text-[hsl(24_48%_12%)] !border !border-[hsl(32_72%_50%)]"
            on:click={doConfirm}
          >
            <Icon name="fire" size={16} /> Tip {fmtGold(amount)} sGLDT
          </Button>
        {/if}

        <div
          class="flex justify-between items-center mt-3.5 pt-3.5 text-xs"
          style="border-top: 1px dashed hsl(var(--pg-border)); color: hsl(var(--pg-fg-muted));"
        >
          <span>Your balance</span>
          <span class="inline-flex items-center gap-1 font-semibold text-primary">
            <GoldCoin size={13} /> {$goldBalance === null ? 'sign in' : `${fmtGold($goldBalance)} sGLDT`}
          </span>
        </div>
      {/if}

      {#if phase === 'burning'}
        <div class="text-center" style="padding: 20px 0;">
          <div class="relative mx-auto mb-4" style="width: 110px; height: 110px;">
            <div
              class="spin"
              style="width: 100%; height: 100%; border: 4px solid hsl(var(--pg-border)); border-top-color: hsl(32 72% 50%); border-radius: 50%;"
            ></div>
            <GoldCoin size={56} style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);" />
          </div>
          <h3 style="font-size: 22px; font-weight: 800; margin: 0 0 6px;">
            Sending {fmtGold(amount)} sGLDT
          </h3>
          <p class="m-0 text-[13px]" style="color: hsl(var(--pg-fg-muted));">
            Moving gold on the ledger, then recording your tip on-chain…
          </p>
        </div>
      {/if}

      {#if phase === 'error'}
        <div class="text-center" style="padding: 20px 0;">
          <div
            class="mx-auto mb-3.5 flex items-center justify-center rounded-full"
            style="width: 72px; height: 72px; background: hsl(4 72% 92%);"
          >
            <Icon name="x" size={36} style="color: hsl(4 72% 45%);" />
          </div>
          <h3 style="font-size: 20px; font-weight: 800; margin: 0 0 6px;">Tip didn't go through</h3>
          <p class="m-0 mb-4 text-[13px]" style="color: hsl(var(--pg-fg-muted)); max-width: 42ch; margin-inline: auto;">
            {errorMsg} No gold left your wallet unless a ledger block is shown.
          </p>
          {#if !$isAuthenticated}
            <Button variant="default" size="sm" on:click={login}>Sign in with Internet Identity</Button>
          {:else}
            <Button variant="default" size="sm" on:click={() => (phase = 'choose')}>Try again</Button>
          {/if}
        </div>
      {/if}

      {#if phase === 'done'}
        <div class="text-center" style="padding: 20px 0;">
          <div
            class="animate-pop mx-auto mb-3.5 flex items-center justify-center rounded-full"
            style="width: 88px; height: 88px; background: hsl(var(--brand-leaf));"
          >
            <Icon name="check" size={44} weight="fill" style="color: white;" />
          </div>
          <h3 style="font-size: 22px; font-weight: 800; margin: 0 0 6px;">Gold tipped</h3>
          <p class="m-0 mb-2.5 text-[13.5px]" style="color: hsl(var(--pg-fg-muted));">
            {#if lastBlock !== null}Ledger block <code>#{lastBlock.toLocaleString()}</code> · {/if}the leaderboard just updated.
          </p>
        </div>
      {/if}
</Modal>
