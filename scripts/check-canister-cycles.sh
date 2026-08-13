#!/bin/bash
# Warn when any CafresoHQ mainnet canister is running low on cycles.
#
# Exists because ydacz (cafresohq_state) hit an actual ZERO balance on
# 2026-08-05: the IC uninstalled its wasm and wiped all stable state —
# vault ciphertext, HQ docs, wallet policies, payroll — permanently, with
# no backup. The failure mode is deceptive: below the freezing reserve,
# queries still answer while every update call silently rejects, so the
# app looks half-alive and the outage reads as an app bug, not a funding
# problem. The cycles-monitor canister deployed after that incident is a
# dashboard only — someone must remember to open it. This script is the
# missing threshold check: run it (manually, from CI, or from any cron
# you like) and it exits non-zero if anything is low.
#
# Threshold notes: `dfx canister status` reports IDLE burn only. Measured
# real burn on ydacz has run ~6x the reported idle figure when the vault
# heap was populated (see docs/PHASE2_STATE_CANISTER.md §5 and the
# 2026-08-05 incident). The default 100B threshold ≈ 2 weeks at that
# worst-case real-burn rate for a ~3.5B/day reported idle. Override with
#   CYCLES_WARN_THRESHOLD=<cycles> scripts/check-canister-cycles.sh
set -u
cd "$(dirname "$0")/.."

THRESHOLD="${CYCLES_WARN_THRESHOLD:-100000000000}"   # 100B cycles
IDENTITY="${DFX_IDENTITY:-default}"
REAL_BURN_MULTIPLIER=6

fail=0

while IFS=$'\t' read -r name cid; do
  out=$(dfx canister status "$cid" --network ic --identity "$IDENTITY" 2>/dev/null)
  if [ -z "$out" ]; then
    echo "WARN  $name ($cid): status call failed — canister unreachable or dfx/identity problem"
    fail=1
    continue
  fi
  balance=$(printf '%s\n' "$out" | sed -n 's/^Balance: \([0-9_]*\) Cycles$/\1/p' | tr -d '_')
  idle=$(printf '%s\n' "$out" | sed -n 's/^Idle cycles burned per day: \([0-9_]*\)$/\1/p' | tr -d '_')
  if [ -z "$balance" ]; then
    echo "WARN  $name ($cid): could not parse balance from dfx output"
    fail=1
    continue
  fi
  human=$(python3 -c "print(f'{$balance/1e9:,.1f}B')")
  if [ -n "$idle" ] && [ "$idle" -gt 0 ]; then
    runway=$(python3 -c "print(f'{$balance/($idle*$REAL_BURN_MULTIPLIER):,.0f}')")
    detail="balance ${human}, ~${runway}d runway at ${REAL_BURN_MULTIPLIER}x reported idle burn"
  else
    detail="balance ${human}"
  fi
  if [ "$balance" -lt "$THRESHOLD" ]; then
    echo "WARN  $name ($cid): $detail — below $(python3 -c "print(f'{$THRESHOLD/1e9:,.0f}B')") threshold. Top up before it freezes."
    fail=1
  else
    echo "ok    $name ($cid): $detail"
  fi
done < <(python3 -c "
import json
for name, nets in json.load(open('canister_ids.json')).items():
    print(f\"{name}\t{nets['ic']}\")
")

exit $fail
