<script>
  import { burnTarget, nanasBalance, tweaks, confirmBurn } from '$lib/stores/blog.js';
  import { burnTip } from '$lib/api/devlog.js';
  import Icon from './Icon.svelte';
  import NanasCoin from './NanasCoin.svelte';
  import Button from './Button.svelte';
  import { trapFocus } from '$lib/actions/trapFocus.js';

  let amount = 500;
  let phase = 'choose'; // 'choose' | 'burning' | 'done'
  let holdProgress = 0;
  let holdTimer = null;

  $: if ($burnTarget) {
    phase = 'choose';
    amount = 500;
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
    phase = 'burning';
    const slug = $burnTarget;
    // Fire the canister call in parallel with the minimum-visible spin duration.
    const [res] = await Promise.all([
      burnTip(slug, amount),
      new Promise((r) => setTimeout(r, 1400))
    ]);
    if (res?.ok?.block) lastBlock = res.ok.block;
    phase = 'done';
    confirmBurn(slug, amount);
    await new Promise((r) => setTimeout(r, 1100));
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

{#if $burnTarget}
  <div
    on:click={close}
    on:keydown={(e) => e.key === 'Escape' && close()}
    role="presentation"
    class="fade-up fixed inset-0 z-[50] flex items-center justify-center"
    style="background: hsl(24 48% 8% / 0.55); backdrop-filter: blur(6px); padding: 16px;"
  >
    <div
      on:click|stopPropagation
      use:trapFocus
      role="dialog"
      aria-modal="true"
      aria-label="Burn $nanas to tip"
      class="relative overflow-hidden bg-white rounded-2xl"
      style="
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
          >Burn to tip</div>
          <h2 style="font-size: 28px; font-weight: 800; margin: 0 0 8px; letter-spacing: -0.02em;">
            Burning $nanas
          </h2>
          <p class="m-0 mx-auto" style="font-size: 13.5px; color: hsl(var(--pg-fg-muted)); line-height: 1.5; max-width: 40ch;">
            Your burn is atomic — it writes the post's tip counter and your leaderboard rank in the same on-chain call.
          </p>
        </div>

        {#if $tweaks.burnModel === 'quick'}
          <div class="grid mb-4" style="grid-template-columns: repeat(4, 1fr); gap: 8px;">
            {#each [100, 500, 1000, 5000] as n}
              <button
                on:click={() => (amount = n)}
                class="flex flex-col items-center gap-0.5 cursor-pointer"
                style="
                  padding: 12px 0; border-radius: 10px;
                  background: {amount === n ? 'hsl(45 95% 62%)' : 'hsl(var(--pg-elevated))'};
                  border: 1px solid {amount === n ? 'hsl(32 72% 50%)' : 'hsl(var(--pg-border))'};
                  font-family: inherit; font-size: 14px; font-weight: 600;
                "
              >
                <NanasCoin size={18} /> {n}
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
                {amount.toLocaleString()} <NanasCoin size={32} />
              </div>
              <div style="font-size: 12px; color: hsl(var(--pg-fg-muted));">
                ≈ ${(amount * 0.0015).toFixed(2)} USD · {Math.round((amount / $nanasBalance) * 100)}% of your balance
              </div>
            </div>
            <input
              type="range"
              min={50}
              max={Math.min(10000, $nanasBalance)}
              step={50}
              bind:value={amount}
              aria-label="Amount of $nanas to burn"
              aria-valuetext="{amount.toLocaleString()} $nanas"
              style="width: 100%; accent-color: hsl(32 72% 50%);"
            />
            <div class="flex justify-between text-[11px] mt-1" style="color: hsl(var(--pg-fg-muted));">
              <span>50</span><span>10,000</span>
            </div>
          </div>
        {/if}

        {#if $tweaks.burnModel === 'hold'}
          <div class="text-center mb-3.5">
            <div class="text-[13px] mb-3.5" style="color: hsl(var(--pg-fg-muted));">Amount to burn</div>
            <div class="flex gap-2 justify-center mb-5">
              {#each [100, 500, 1000, 5000] as n}
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
                >{n.toLocaleString()}</button>
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
                  <span class="uppercase" style="font-size: 11px; letter-spacing: 0.08em;">Hold to burn</span>
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
            <Icon name="fire" size={16} /> Burn {amount.toLocaleString()} $nanas
          </Button>
        {/if}

        <div
          class="flex justify-between items-center mt-3.5 pt-3.5 text-xs"
          style="border-top: 1px dashed hsl(var(--pg-border)); color: hsl(var(--pg-fg-muted));"
        >
          <span>Your balance</span>
          <span class="inline-flex items-center gap-1 font-semibold text-primary">
            <NanasCoin size={13} /> {$nanasBalance.toLocaleString()} $nanas
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
            <NanasCoin size={56} style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);" />
          </div>
          <h3 style="font-size: 22px; font-weight: 800; margin: 0 0 6px;">
            Burning {amount.toLocaleString()} $nanas
          </h3>
          <p class="m-0 text-[13px]" style="color: hsl(var(--pg-fg-muted));">
            Writing to canister <code style="font-size: 12px;">chkoj-v…cai</code>
          </p>
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
          <h3 style="font-size: 22px; font-weight: 800; margin: 0 0 6px;">Burned</h3>
          <p class="m-0 mb-2.5 text-[13.5px]" style="color: hsl(var(--pg-fg-muted));">
            Block <code>#{(lastBlock ?? 4821971).toLocaleString()}</code> · the leaderboard just updated.
          </p>
        </div>
      {/if}
    </div>
  </div>
{/if}
