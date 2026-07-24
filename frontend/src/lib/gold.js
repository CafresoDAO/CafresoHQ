// Gold (sGLDT) display + conversion helpers.
//
// The economy anchor is USD cents on products; the gold amount is computed at
// render/pay time from the live sGLDT/USD price (lib/stores/prices.js polls
// the ICPSwap pool). Burn amounts recorded on the devlog canister are RAW e8s
// (sGLDT has 8 decimals) — legacy $nanas-era rows recorded whole test tokens,
// so after this switch old counters read as ~0 and the boards restart in gold.

/** e8s (bigint/number) → whole sGLDT (float). */
export function goldFromRaw(raw) {
  if (raw === null || raw === undefined) return 0;
  return Number(raw) / 1e8;
}

/** whole sGLDT → e8s (bigint), carry-safe for fractional amounts. */
export function goldToRaw(amount) {
  const n = Number(amount);
  if (!Number.isFinite(n) || n <= 0) return 0n;
  const [whole, frac = ''] = n.toFixed(8).split('.');
  return BigInt(whole) * 100000000n + BigInt(frac.padEnd(8, '0'));
}

/** Format a whole-sGLDT amount for display: trims to the precision that matters. */
export function fmtGold(amount, dp = 2) {
  const n = Number(amount);
  if (!Number.isFinite(n)) return '—';
  // Tiny tips (0.01) keep their cents; larger amounts drop trailing noise.
  const digits = n !== 0 && n < 0.1 ? 4 : dp;
  return n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: digits });
}

/** USD cents → sGLDT amount at the given USD price per sGLDT (0 if unknown). */
export function usdCentsToGold(cents, sgldtUsd) {
  const price = Number(sgldtUsd);
  if (!(price > 0)) return 0;
  return cents / 100 / price;
}
