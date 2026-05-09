#!/bin/bash
cd /mnt/c/Users/Anthony/Documents/CafresoHQ
echo "▶ vault_encrypted_key with a 48-byte zero transport pubkey (just verifies the canister is reachable & cycles flow)"
echo "  expected: 96-byte encrypted_key blob OR a clean reject for invalid transport key"
dfx canister --network ic call cafresoai_keys vault_encrypted_key "(blob \"$(printf '\\\\00%.0s' {1..48})\")" 2>&1 | head -20
