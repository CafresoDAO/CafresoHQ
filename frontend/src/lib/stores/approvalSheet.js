/* Signing-sheet request store. The shell's REAL signatures (icrc2_approve,
   over-cap agent sends) used to gate on window.confirm — the weakest possible
   presentation for the most consequential clicks in the product. This store +
   ApprovalSheet.svelte replace it with a wallet-style approval dialog.

   requestApproval(spec) → Promise<boolean>. One request at a time: a second
   caller while a sheet is open resolves false immediately rather than
   queueing — chain requests come from the iframe and stacking signature
   prompts is exactly the confusion this sheet exists to prevent.

   spec: {
     kicker?:       small eyebrow text, default 'Signature required'
     title:         what is being signed, plain language
     rows:          [{ label, value, mono? }] — the exact terms
     warning?:      amber callout for irreversibility / replaces-previous
     note?:         quiet footnote (e.g. what CAN'T happen)
     confirmLabel?: default 'Approve'
     declineLabel?: default 'Cancel'
     danger?:       styles the confirm button destructive-red
   } */
import { writable } from 'svelte/store';

export const approvalRequest = writable(null);

export function requestApproval(spec) {
  return new Promise((resolve) => {
    let current;
    approvalRequest.update((existing) => {
      current = existing;
      return existing ? existing : { ...spec, resolve };
    });
    if (current) resolve(false); // a sheet is already open — refuse, don't queue
  });
}

/* Called by ApprovalSheet.svelte only. */
export function settleApproval(approved) {
  approvalRequest.update((req) => {
    if (req) req.resolve(!!approved);
    return null;
  });
}
