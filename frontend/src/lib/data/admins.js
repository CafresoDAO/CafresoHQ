// Frontend-only admin allowlist.
//
// The devlog canister is the true source of authority — it enforces admin
// gating on `upsertPost`. This file just controls *UI visibility* (showing
// the "Write" button, unlocking `/blog/new`). Keeping them in sync is a
// manual step; if a principal is in the canister but not here, they can
// still publish by typing `/blog/new` — the server still succeeds.
//
// To allowlist a new admin: add their principal here, then
// `dfx canister --network ic call devlog_backend addAdmin '(principal "…")'`
// to mirror it on the canister.

export const DEVLOG_ADMINS = new Set([
  // Anthony / default dfx identity — first deployer, bootstrap admin on the
  // devlog canister per main.mo:109.
  'xip3r-mhzcr-csb7y-ilqf5-4tpge-dka64-jv2ow-zon7z-key3x-77kf3-mae',
  // Anthony's II-anchored principal (added via `addAdmin` 2026-04-20).
  'rc62u-qypnw-bbkkp-d56wk-tnzaq-vwhi2-cqqay-q56hw-gsqbp-6wegl-jae'
]);

export function isDevlogAdmin(principalText) {
  if (!principalText) return false;
  return DEVLOG_ADMINS.has(principalText);
}
