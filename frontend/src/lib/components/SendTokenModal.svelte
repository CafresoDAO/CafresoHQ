<svelte:options runes={true} />

<script>
  import { Principal } from '@dfinity/principal';
  import Icon from './Icon.svelte';
  import Button from './Button.svelte';
  import { TOKENS, transfer, getFee, formatBalance } from '$lib/api/icrc1.js';

  // Props. Modal is "controlled" — parent owns open/close state.
  let {
    open = $bindable(false),
    tokenKey = 'nanas',
    rawBalance = null,
    onSent = () => {}
  } = $props();

  const token = $derived(TOKENS[tokenKey] || TOKENS.nanas);

  let fee = $state(null);
  let loadingFee = $state(false);
  let recipient = $state('');
  let amount = $state('');
  let memo = $state('');
  let phase = $state('idle'); // idle | sending | done | error
  let err = $state(null);
  let blockIndex = $state(null);

  // Reload fee when the token switches (e.g. user opens send for a different row).
  let lastLoadedToken = null;
  $effect(() => {
    if (!open) return;
    if (lastLoadedToken === tokenKey) return;
    lastLoadedToken = tokenKey;
    loadingFee = true;
    getFee(tokenKey).then((f) => {
      fee = f;
      loadingFee = false;
    });
  });

  function reset() {
    recipient = '';
    amount = '';
    memo = '';
    phase = 'idle';
    err = null;
    blockIndex = null;
  }

  function close() {
    reset();
    open = false;
  }

  // Max = balance - fee, formatted for the amount input. Gives the user a
  // one-tap "send everything" flow without surprising them by overdrafting.
  function setMax() {
    if (rawBalance == null || fee == null) return;
    const net = rawBalance - fee;
    if (net <= 0n) {
      amount = '0';
      return;
    }
    const whole = Number(net) / 10 ** token.decimals;
    amount = whole.toString();
  }

  function validate() {
    if (!recipient.trim()) return 'Enter a recipient principal.';
    try {
      Principal.fromText(recipient.trim());
    } catch {
      return 'Recipient principal is not valid.';
    }
    const parsed = Number.parseFloat(amount);
    if (!Number.isFinite(parsed) || parsed <= 0) return 'Enter an amount greater than 0.';
    if (memo && memo.length > 32) return 'Memo is capped at 32 bytes.';
    return null;
  }

  async function submit(e) {
    e.preventDefault();
    err = null;
    const bad = validate();
    if (bad) {
      err = bad;
      return;
    }
    phase = 'sending';
    const res = await transfer({
      tokenKey,
      toPrincipalText: recipient.trim(),
      amount: Number.parseFloat(amount),
      memoText: memo.trim() || undefined
    });
    if (res.err) {
      phase = 'error';
      err = res.err;
      return;
    }
    phase = 'done';
    blockIndex = res.ok;
    onSent({ tokenKey, to: recipient.trim(), amount: Number.parseFloat(amount), block: res.ok });
  }

  const feeFormatted = $derived(fee == null ? '—' : formatBalance(fee, token.decimals, token.decimals >= 8 ? 8 : 4));
  const balanceFormatted = $derived(rawBalance == null ? '—' : formatBalance(rawBalance, token.decimals, token.decimals >= 8 ? 4 : 2));
</script>

{#if open}
  <div
    class="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
    style="background: hsl(222 47% 11% / 0.5);"
    on:click={close}
    on:keydown={(e) => e.key === 'Escape' && close()}
    role="dialog"
    aria-modal="true"
    tabindex="-1"
  >
    <div
      class="w-full sm:max-w-[460px] rounded-t-[18px] sm:rounded-[16px] p-5 sm:p-6 max-h-[92vh] overflow-y-auto"
      style="background: hsl(var(--pg-elevated)); border-top: 1px solid hsl(var(--pg-border));"
      on:click|stopPropagation
      on:keydown|stopPropagation
      role="document"
    >
      <!-- Header -->
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-2.5 min-w-0">
          <div
            class="w-9 h-9 rounded-full flex items-center justify-center shrink-0 overflow-hidden"
            style="background: hsl(42 80% 92%); border: 1px solid hsl(42 70% 78%);"
          >
            {#if token.logo}
              <img src={token.logo} alt="" class="w-[22px] h-[22px] object-contain" loading="lazy" decoding="async" />
            {:else}
              <span class="text-[10.5px] font-bold" style="color: hsl(32 56% 25%);">
                {token.symbol.replace('$', '').slice(0, 3).toUpperCase()}
              </span>
            {/if}
          </div>
          <div class="min-w-0">
            <div class="font-bold text-[16px] leading-tight" style="color: hsl(var(--pg-fg));">
              Send {token.symbol}
            </div>
            <div class="text-[11.5px] truncate" style="color: hsl(var(--pg-fg-muted));">
              Balance: <span class="tabular-nums">{balanceFormatted}</span> {token.symbol}
            </div>
          </div>
        </div>
        <button
          type="button"
          on:click={close}
          class="w-8 h-8 rounded-full flex items-center justify-center cursor-pointer bg-transparent border-none shrink-0"
          aria-label="Close"
        >
          <Icon name="x" size={16} />
        </button>
      </div>

      {#if phase === 'done'}
        <!-- Success -->
        <div
          class="rounded-[12px] p-4 mb-4 text-[13.5px]"
          style="background: hsl(142 50% 94%); color: hsl(142 70% 25%); border: 1px solid hsl(142 45% 70%);"
        >
          <div class="flex items-center gap-2 font-semibold mb-1">
            <Icon name="check-circle" size={15} /> Transfer confirmed
          </div>
          <div class="text-[12.5px]" style="color: hsl(215 25% 25%);">
            Sent <b class="tabular-nums">{amount}</b> {token.symbol} to
            <span class="font-mono">{recipient.slice(0, 5)}…{recipient.slice(-3)}</span>
          </div>
          <div class="text-[11.5px] font-mono mt-1" style="color: hsl(var(--pg-fg-muted));">
            Ledger block #{blockIndex}
          </div>
        </div>
        <div class="flex flex-col sm:flex-row gap-2">
          <Button on:click={reset} variant="outline" class="flex-1">Send another</Button>
          <Button on:click={close} class="flex-1">Done</Button>
        </div>
      {:else}
        <!-- Form -->
        <form on:submit={submit} class="space-y-3">
          <div>
            <label class="block text-[11.5px] font-semibold uppercase tracking-wide mb-1.5" style="color: hsl(var(--pg-fg-muted));" for="send-to">
              Recipient principal
            </label>
            <input
              id="send-to"
              bind:value={recipient}
              placeholder="e.g. rc62u-qypnw-…-jae"
              class="w-full text-[13px] font-mono bg-white rounded-[10px] px-3 py-2 outline-none"
              style="background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border)); color: hsl(var(--pg-fg));"
              autocomplete="off"
              spellcheck="false"
              disabled={phase === 'sending'}
            />
          </div>

          <div>
            <div class="flex items-center justify-between mb-1.5">
              <label class="text-[11.5px] font-semibold uppercase tracking-wide" style="color: hsl(var(--pg-fg-muted));" for="send-amount">
                Amount
              </label>
              <button
                type="button"
                on:click={setMax}
                disabled={rawBalance == null || fee == null}
                class="text-[10.5px] font-semibold uppercase cursor-pointer bg-transparent border-none"
                style="color: hsl(38 85% 30%);"
              >
                Max (balance − fee)
              </button>
            </div>
            <div
              class="flex items-center gap-2 rounded-[10px] px-3 py-2"
              style="background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border));"
            >
              <input
                id="send-amount"
                bind:value={amount}
                type="number"
                step="any"
                min="0"
                placeholder="0.00"
                class="flex-1 border-none bg-transparent text-[16px] font-semibold tabular-nums outline-none"
                disabled={phase === 'sending'}
              />
              <span class="text-[12px] font-semibold" style="color: hsl(32 56% 25%);">{token.symbol}</span>
            </div>
            <div class="text-[11px] mt-1.5 flex items-center gap-1.5" style="color: hsl(var(--pg-fg-muted));">
              <Icon name="info" size={12} />
              Network fee:
              <span class="tabular-nums">{loadingFee ? '…' : feeFormatted}</span>
              {token.symbol}
              {#if fee != null}
                <span class="opacity-60">(auto-deducted)</span>
              {/if}
            </div>
          </div>

          <div>
            <label class="block text-[11.5px] font-semibold uppercase tracking-wide mb-1.5" style="color: hsl(var(--pg-fg-muted));" for="send-memo">
              Memo <span class="font-normal normal-case" style="color: hsl(var(--pg-fg-subtle));">(optional, 32 bytes max)</span>
            </label>
            <input
              id="send-memo"
              bind:value={memo}
              placeholder="e.g. order-0042"
              maxlength="32"
              class="w-full text-[13px] bg-white rounded-[10px] px-3 py-2 outline-none"
              style="background: hsl(var(--pg-elevated)); border: 1px solid hsl(var(--pg-border)); color: hsl(var(--pg-fg));"
              disabled={phase === 'sending'}
            />
          </div>

          {#if err}
            <div
              class="rounded-[10px] px-3 py-2 text-[12.5px] flex items-start gap-2"
              style="background: hsl(var(--pg-danger-bg)); color: hsl(var(--pg-danger-fg)); border: 1px solid hsl(var(--pg-danger-border));"
            >
              <Icon name="warning" size={13} />
              <span>{err}</span>
            </div>
          {/if}

          <div class="flex flex-col sm:flex-row gap-2 pt-1">
            <Button type="button" variant="ghost" on:click={close} disabled={phase === 'sending'} class="flex-1">
              Cancel
            </Button>
            <Button type="submit" disabled={phase === 'sending'} class="flex-1">
              {#if phase === 'sending'}
                <Icon name="spinner-gap" size={14} /> Sending…
              {:else}
                <Icon name="paper-plane-tilt" size={14} /> Send
              {/if}
            </Button>
          </div>

          <p class="text-[11px] text-center pt-1" style="color: hsl(var(--pg-fg-muted));">
            Transfer is signed with your Internet Identity and lands directly on the {token.symbol} ICRC-1 ledger. This dapp never custodies the funds.
          </p>
        </form>
      {/if}
    </div>
  </div>
{/if}
