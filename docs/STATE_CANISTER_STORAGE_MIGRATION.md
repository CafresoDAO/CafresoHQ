# cafresohq_state: heap → stable-memory vault storage (Track 2 plan)

*Written 2026-08-13. Companion to the cycle-burn work: `getStorageStats()`
(main.mo, commit 37cfef0) and `scripts/check-canister-cycles.sh` are Track 1
(observability, done). This doc is the not-yet-started Track 2.*

## Problem

`vaultChunks` / `vaultMetas` hold vetKeys-encrypted vault ciphertext in
heap-resident `stable var` `OrderedMap`s (main.mo:125-126). Every GC pass and
every upgrade touches the whole resident set. With ~106 MB of heap state this
measured **~20B cycles/day real burn against ~3.57B/day reported idle** — the
gap that drained ydacz to zero on 2026-08-05 and cost all user data. The
scaffold's own header comment (main.mo:20-24) says to migrate the chunk store
to `mo:stable-structures` before scaling past a few GB.

## The 2026-08-13 window: the hard part is currently free

`getStorageStats()` on mainnet returns **all zeros** — 0 principals with vault
data, 0 chunks, 0 bytes — because the 08-05 wipe destroyed everything and no
user has re-uploaded since. While that holds, the staged dual-write → backfill
→ verify dance (the safe path for live data) is unnecessary *for the vault
store specifically*: swapping the two vault stable vars for stable-memory
structures is an ordinary upgrade in which the discarded vars are provably
empty. **Re-check `getStorageStats()` immediately before starting; if it is
non-zero, use the staged path below instead.**

The other ~30 stable vars (payroll, wallets, library, search jobs, receipts)
stay heap-resident OrderedMaps — they are small, and they are not the burn.

## Prerequisites (why this was not done same-session)

- **No mops setup exists.** No `mops.toml`, no lock, `dfx.json` `packtool` is
  empty. Adding `mo:stable-structures` is a first-time dependency bootstrap.
  No precedent anywhere in the Cafreso family (cafreso-pages uses
  canscale/StableHeapBTreeMap + CanDB — a different stack; do not copy it).
- **This repo's Motoko compiles only under dfx 0.24.3** (0.29.1 hits ~50
  pre-existing M0219 implicitly-transient errors). Verify the chosen
  stable-structures version supports that moc before writing any code.
- There is no `preupgrade` hook today (only `postupgrade`, which re-arms
  timers). Whatever structure is chosen must not need one.

## Plan A — empty-window swap (preferred while stats are zero)

1. Bootstrap mops (`mops init`, add `stable-structures` or equivalent
   `Region`-backed store; set `packtool` in dfx.json). Compile-check under
   dfx 0.24.3 before touching main.mo.
2. Replace `vaultChunks`/`vaultMetas` with stable-memory equivalents keyed
   identically (`Principal` → per-user map). Keep the public Candid interface
   byte-identical — callers must not notice.
3. Snapshot the canister first (standing rule from the bek5d upgrade work),
   diff `dfx canister metadata ydacz-riaaa-aaaal-qxeja-cai motoko:stable-types`
   pre/post, deploy as an **upgrade** (never reinstall — reinstall re-triggers
   the ~301B-cycle storage reservation from the 08-05 recovery).
4. Post-deploy: `getStorageStats()` still zeros; smoke a full
   putVaultMeta → putVaultChunk → sealVault → read cycle with a test
   principal; watch `Idle cycles burned per day` in `dfx canister status`
   as data accumulates — the number should now track chunk bytes at the
   stable-memory rate, not the heap rate.

## Plan B — staged migration (if users have re-populated vaults)

Mirrors §6 of PHASE2_STATE_CANISTER.md, applied internally: add the new
stable-memory store alongside the old vars → dual-write new writes to both →
admin-triggered batch backfill old → verify byte-for-byte (sha256 per chunk)
→ cut reads over → remove the old vars in a later deploy. Every stage rolls
back by reading from the old vars, which are never deleted until the end.

## Not in scope

Snapshot/backup cadence (founder deferred: "we will decide on a method
later") and alerting automation beyond the check script — the cycles-monitor
canister remains dashboard-only.
