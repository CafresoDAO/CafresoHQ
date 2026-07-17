<script>
  /* Wallet-style signing sheet — renders whatever approvalSheet.js holds.
     Mounted once (hq/app page) above the fullscreen iframe. Cancel is the
     data-autofocus default: pressing Enter reflexively must never sign. */
  import { approvalRequest, settleApproval } from '$lib/stores/approvalSheet.js';
  import Modal from './Modal.svelte';

  $: req = $approvalRequest;
</script>

<Modal
  open={!!req}
  on:close={() => settleApproval(false)}
  z="sheet"
  labelledby="approval-sheet-title"
  panelClass="card w-full max-w-md p-6 shadow-2xl"
>
  {#if req}
      <div class="page-kicker">{req.kicker || 'Signature required'}</div>
      <h2 id="approval-sheet-title" class="mt-2 text-xl font-semibold">{req.title}</h2>

      {#if req.rows?.length}
        <dl class="mt-4 divide-y divide-ink-700/40 rounded-xl border border-ink-700/40">
          {#each req.rows as row}
            <div class="flex items-baseline justify-between gap-4 px-4 py-2.5">
              <dt class="shrink-0 text-xs uppercase tracking-wide text-ink-400">{row.label}</dt>
              <dd class="min-w-0 break-all text-right text-sm {row.mono ? 'font-mono text-[13px]' : 'font-medium'}">
                {row.value}
              </dd>
            </div>
          {/each}
        </dl>
      {/if}

      {#if req.warning}
        <p class="mt-4 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm leading-6 text-amber-700 dark:text-amber-300">
          {req.warning}
        </p>
      {/if}

      {#if req.note}
        <p class="mt-3 text-xs leading-5 text-ink-400">{req.note}</p>
      {/if}

      <div class="mt-5 flex justify-end gap-2">
        <button class="btn-ghost" data-autofocus on:click={() => settleApproval(false)}>
          {req.declineLabel || 'Cancel'}
        </button>
        <button
          class={req.danger
            ? 'rounded-full bg-red-600 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-red-500'
            : 'btn-primary'}
          on:click={() => settleApproval(true)}
        >
          {req.confirmLabel || 'Approve'}
        </button>
      </div>
  {/if}
</Modal>
