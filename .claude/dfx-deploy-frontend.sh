#!/bin/bash
set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
cd $REPO_ROOT

echo "▶ verify frontend/build/ is fresh"
ls -la frontend/build/index.html 2>&1 | head -2

echo ""
echo "▶ cycles available"
dfx cycles balance --network ic 2>&1 | tail -3

echo ""
echo "▶ cafresoai_frontend canister status before deploy"
dfx canister --network ic status cafresoai_frontend 2>&1 | grep -E 'Status|Balance|Module' | head -5

echo ""
echo "▶ deploy cafresoai_frontend (assets canister) to mainnet"
dfx deploy --network ic cafresoai_frontend --no-wallet --yes 2>&1 | tail -30

echo ""
echo "▶ verify deploy"
dfx canister --network ic status cafresoai_frontend 2>&1 | grep -E 'Module|Balance' | head -3

echo ""
echo "✓ frontend deployed"
echo "  Live at: https://v4tdv-riaaa-aaaab-agtfa-cai.icp0.io/"
echo "  Custom domain: https://ai.cafreso.com (if DNS is set)"
