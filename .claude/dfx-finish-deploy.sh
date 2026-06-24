#!/bin/bash
set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
cd $REPO_ROOT

KEYS_ID=vhw7q-lqaaa-aaaab-agthq-cai

echo "▶ topping up cafresohq_keys with 0.3 TC from cycles ledger"
dfx cycles top-up $KEYS_ID 300000000000 --network ic

echo ""
echo "▶ canister cycle balance after top-up"
dfx canister status $KEYS_ID --network ic 2>&1 | grep -E 'Balance|Status'

echo ""
echo "▶ install cafresohq_keys"
dfx canister install cafresohq_keys --network ic --mode install

echo ""
echo "▶ smoke test 1: key_config (query, free)"
dfx canister --network ic call cafresohq_keys key_config

echo ""
echo "▶ smoke test 2: cycle_balance (query, free)"
dfx canister --network ic call cafresohq_keys cycle_balance

echo ""
echo "▶ smoke test 3: vault_public_key (update, calls management canister)"
echo "   Verifies vetKD subnet has key_1 enabled."
dfx canister --network ic call cafresohq_keys vault_public_key 2>&1 | head -5 || echo "   ⚠ failed"

echo ""
echo "▶ generate Candid declarations for the frontend"
dfx generate cafresohq_keys 2>&1 | tail -5

echo ""
echo "✓ Deploy complete: $KEYS_ID"
