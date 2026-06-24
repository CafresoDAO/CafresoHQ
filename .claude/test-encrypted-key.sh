#!/bin/bash
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
cd $REPO_ROOT
echo "▶ vault_encrypted_key with a 48-byte zero transport pubkey (just verifies the canister is reachable & cycles flow)"
echo "  expected: 96-byte encrypted_key blob OR a clean reject for invalid transport key"
dfx canister --network ic call cafresohq_keys vault_encrypted_key "(blob \"$(printf '\\\\00%.0s' {1..48})\")" 2>&1 | head -20
