#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
cd $REPO_ROOT

# Clean any stale state
pkill -f 'ic-https-outcalls' 2>/dev/null || true
pkill -f replica 2>/dev/null || true
pkill -f dfx 2>/dev/null || true
sleep 1

echo "▶ dfx start (background)…"
dfx start --background --clean --host 127.0.0.1:4943 2>&1 | tail -30 &
DFX_PID=$!

# Wait up to 120s for the replica
for i in $(seq 1 40); do
    if dfx ping local >/dev/null 2>&1; then
        echo "  replica is up after ${i}x3s"
        break
    fi
    sleep 3
done

if ! dfx ping local >/dev/null 2>&1; then
    echo "✗ replica failed to start"
    exit 1
fi

echo ""
echo "▶ dfx canister create cafresohq_keys --network local"
dfx canister create cafresohq_keys --network local

echo ""
echo "▶ dfx build cafresohq_keys --network local"
# Note: build needs the local replica metadata (canister id) to wire imports.
dfx build cafresohq_keys --network local

echo ""
echo "▶ dfx canister install cafresohq_keys --network local --mode reinstall"
yes yes | dfx canister install cafresohq_keys --network local --mode reinstall

echo ""
echo "▶ dfx canister id cafresohq_keys"
KEYS_ID=$(dfx canister id cafresohq_keys --network local)
echo "  $KEYS_ID"

echo ""
echo "▶ Smoke test: cycle_balance + key_config"
dfx canister call cafresohq_keys cycle_balance --network local
dfx canister call cafresohq_keys key_config --network local

echo ""
echo "▶ Smoke test: vault_public_key (anon)"
dfx canister call cafresohq_keys vault_public_key --network local || echo "(expected to fail with no vetkd subnet on local replica)"

echo ""
echo "✓ Local deploy complete"
echo "  Canister: $KEYS_ID"
