#!/bin/bash
echo "=== identity ==="
dfx identity whoami
echo ""
echo "=== principal ==="
dfx identity get-principal
echo ""
echo "=== wallet balance (mainnet) ==="
dfx wallet --network ic balance 2>&1 || echo "no wallet on mainnet?"
echo ""
echo "=== existing canisters in this project ==="
cat /mnt/c/Users/Anthony/Documents/CafresoHQ/canister_ids.json 2>/dev/null
