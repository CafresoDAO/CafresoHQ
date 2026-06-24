#!/bin/bash
echo "=== wallet ==="
dfx wallet --network ic balance 2>&1 | head -3
echo ""
echo "=== cafresohq_frontend (v4tdv) status ==="
dfx canister --network ic status v4tdv-riaaa-aaaab-agtfa-cai 2>&1 | head -20
