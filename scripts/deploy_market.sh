#!/usr/bin/env bash
# deploy_market.sh — the founder's one command to open the hiring hall on
# the Internet Computer. docs/AGENT_MARKETPLACE.md §7.
#
# This is the ONE step the office never takes for you: it creates a canister
# on mainnet and spends cycles. It refuses to guess — the pinned toolchain,
# the deploy identity and a compile check come first, and it asks before it
# deploys unless you pass --yes. `--dry-run` shows the plan and deploys
# nothing.
#
#   scripts/deploy_market.sh --dry-run
#   scripts/deploy_market.sh            # asks, then deploys with the default identity
#   NETWORK=local scripts/deploy_market.sh --yes   # a local replica, for the first end-to-end job
#
# After it runs, the id is in canister_ids.json and the script prints the
# two places that need it (the shell's build env and, optionally, the fleet
# container env).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

NETWORK="${NETWORK:-ic}"
IDENTITY="${IDENTITY:-default}"
DRY=0
YES=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --yes) YES=1 ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "deploy_market.sh: unknown argument $a" >&2; exit 2 ;;
  esac
done

# ── 1. the pinned toolchain, not whatever is on PATH ──────────────────────
PIN="$(tr -d '[:space:]' < .dfx-version 2>/dev/null || true)"
PIN="${PIN:-0.24.3}"
export DFX_VERSION="$PIN"
if ! command -v dfx >/dev/null 2>&1; then
  echo "deploy_market.sh: dfx is not on PATH — install dfxvm, then: dfxvm install $PIN" >&2
  exit 1
fi
HAVE="$(dfx --version 2>/dev/null | awk '{print $2}')"
if [ "$HAVE" != "$PIN" ]; then
  echo "deploy_market.sh: dfx $HAVE answered, but this repo pins $PIN (main.mo is written for its moc)." >&2
  echo "  fix: dfxvm install $PIN   (DFX_VERSION=$PIN is already exported here)" >&2
  exit 1
fi

# ── 2. the deploy identity ─────────────────────────────────────────────────
if [ "$IDENTITY" = "ic_admin" ]; then
  echo "deploy_market.sh: refusing to deploy as ic_admin — canisters here are deployed with the default identity." >&2
  exit 1
fi
# `dfx identity list` can abort outright where the OS keyring is not
# reachable (a non-interactive shell); that is not a verdict on the
# identity, so only a LISTED absence refuses here — dfx itself refuses at
# deploy time if the identity is missing.
if IDS="$(dfx identity list 2>/dev/null)"; then
  if ! grep -qx "$IDENTITY" <<<"$IDS"; then
    echo "deploy_market.sh: no dfx identity named '$IDENTITY' (have: $(tr '\n' ' ' <<<"$IDS"))" >&2
    exit 1
  fi
else
  echo "(could not list dfx identities from this shell — dfx will refuse at deploy time if '$IDENTITY' is missing)"
fi

# ── 3. it compiles, before anything touches a network ─────────────────────
echo "▸ compile check (no network): dfx build cafresohq_market --check"
dfx build cafresohq_market --check

# ── 4. the plan ────────────────────────────────────────────────────────────
echo
echo "plan: deploy cafresohq_market  network=$NETWORK  identity=$IDENTITY"
echo "      then claim plan admin with that identity (market_admin_claim)"
if [ "$DRY" = 1 ]; then
  echo "dry run: nothing deployed."
  exit 0
fi
if [ "$YES" != 1 ]; then
  printf 'This creates a canister on %s and spends cycles. Deploy? [y/N] ' "$NETWORK"
  read -r ans
  [ "$ans" = "y" ] || [ "$ans" = "Y" ] || { echo "not deployed."; exit 1; }
fi

# ── 5. deploy + claim ──────────────────────────────────────────────────────
if ! dfx deploy cafresohq_market --network "$NETWORK" --identity "$IDENTITY"; then
  echo "deploy_market.sh: dfx deploy failed. On mainnet a NEW canister needs cycles from the identity's" >&2
  echo "  cycles wallet or cycles ledger — see \`dfx cycles balance --network ic --identity $IDENTITY\`." >&2
  exit 1
fi
ID="$(dfx canister id cafresohq_market --network "$NETWORK")"
if ! dfx canister call cafresohq_market market_admin_claim --network "$NETWORK" --identity "$IDENTITY"; then
  echo "(plan admin not claimed by this call — if it was claimed earlier, check with amPlanAdmin)" >&2
fi

cat <<EOT

✔ cafresohq_market is at $ID on $NETWORK  (dfx wrote it to canister_ids.json)

Next, by hand:
  1. The shell (cafreso-pages): build with VITE_CANISTER_ID_CAFRESOHQ_MARKET=$ID
     (or pin it as the fallback in frontend/src/lib/api/marketActor.js), then
     deploy both frontend canisters with that repo's scripts/deploy.sh.
  2. Fleet containers, optional: CAFRESOHQ_MARKET_CANISTER=$ID pre-points an
     operator's office at the hall (the Offer tab sets it anyway).
  3. Watch its cycles next to cafresohq_state:
       dfx canister status cafresohq_market --network $NETWORK --identity $IDENTITY
  4. The first job, with 0.01 ICP and two offices: docs/AGENT_MARKETPLACE.md §7b.
EOT
