#!/bin/bash
set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
cd $REPO_ROOT

echo "▶ rebuild cafresoai_keys (new vetkd interface)"
dfx build cafresoai_keys --network ic

echo ""
echo "▶ upgrade cafresoai_keys (auto-yes for breaking candid change)"
yes yes | dfx canister install cafresoai_keys --network ic --mode upgrade

echo ""
echo "▶ smoke test 1: key_config"
dfx canister --network ic call cafresoai_keys key_config

echo ""
echo "▶ smoke test 2: cycle_balance"
dfx canister --network ic call cafresoai_keys cycle_balance

echo ""
echo "▶ smoke test 3: vault_public_key (production vetkd_public_key)"
dfx canister --network ic call cafresoai_keys vault_public_key

echo ""
echo "▶ regenerate Candid declarations"
dfx generate cafresoai_keys 2>&1 | tail -5

echo ""
echo "✓ done"
