#!/bin/bash
echo "=== identity: ic_admin ==="
dfx identity use ic_admin 2>&1
dfx identity get-principal 2>&1
dfx wallet --network ic balance 2>&1 | head -3
echo ""
echo "=== identity: xip3r_legacy ==="
dfx identity use xip3r_legacy 2>&1
dfx identity get-principal 2>&1
dfx wallet --network ic balance 2>&1 | head -3
echo ""
echo "=== identity: default ==="
dfx identity use default 2>&1
dfx identity get-principal 2>&1
dfx wallet --network ic balance 2>&1 | head -3
echo ""
echo "=== controllers of cafresohq_frontend (v4tdv) ==="
dfx canister --network ic info v4tdv-riaaa-aaaab-agtfa-cai 2>&1 | head -10
