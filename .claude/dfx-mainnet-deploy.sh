#!/bin/bash
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
cd $REPO_ROOT

echo "▶ identity"
dfx identity get-principal

echo ""
echo "▶ wallet balance"
dfx wallet --network ic balance

echo ""
echo "▶ cycles ledger balance"
dfx cycles balance --network ic

echo ""
echo "▶ create cafresohq_keys canister on mainnet (0.6 TC, paid from cycles ledger)"
# --no-wallet uses the cycles ledger directly (the modern path)
# 0.6 TC = enough for canister creation fee (0.5 TC) + 0.1 TC starting balance
dfx canister create cafresohq_keys --network ic --no-wallet --with-cycles 600000000000

echo ""
echo "▶ build cafresohq_keys"
dfx build cafresohq_keys --network ic

echo ""
echo "▶ install cafresohq_keys"
dfx canister install cafresohq_keys --network ic --mode install

echo ""
KEYS_ID=$(dfx canister id cafresohq_keys --network ic)
echo "▶ deployed canister id: $KEYS_ID"

echo ""
echo "▶ smoke test 1: key_config (query, free)"
dfx canister --network ic call cafresohq_keys key_config

echo ""
echo "▶ smoke test 2: cycle_balance (query, free)"
dfx canister --network ic call cafresohq_keys cycle_balance

echo ""
echo "▶ smoke test 3: vault_public_key (update, calls management canister)"
echo "   This verifies vetKD is reachable from this subnet for key_1."
dfx canister --network ic call cafresohq_keys vault_public_key || \
    echo "   ⚠ vault_public_key failed — vetKD may not be enabled, or key_id mismatch"

echo ""
echo "▶ generate Candid declarations for the frontend"
dfx generate cafresohq_keys

echo ""
echo "✓ mainnet deploy complete"
echo "  Canister id: $KEYS_ID"
echo "  Update frontend/.env.local with VITE_CAFRESOHQ_KEYS_CANISTER_ID=$KEYS_ID"
