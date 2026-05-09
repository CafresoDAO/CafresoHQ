#!/bin/bash
echo "=== wallet (legacy) ==="
dfx wallet --network ic balance 2>&1 | tail -3
echo ""
echo "=== cycles ledger (modern) ==="
dfx cycles balance --network ic 2>&1 | tail -3
echo ""
echo "=== ICP ledger (account) ==="
dfx ledger --network ic balance 2>&1 | tail -3
