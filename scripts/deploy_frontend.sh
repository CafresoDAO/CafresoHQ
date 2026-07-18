#!/usr/bin/env bash
# deploy_frontend.sh — one-command frontend ship with drift protection.
#
# cafreso.com (cafreso_pages) and ai.cafreso.com (cafresohq_frontend) serve the
# SAME frontend/build. Deploying only one of them once shipped a drift bug
# (Deep Research missing from cafreso.com), so this script:
#   1. builds frontend/ once
#   2. deploys BOTH asset canisters
#   3. fetches each live domain's index.html and verifies the hashed entry
#      bundles (_app/immutable/entry/*.js) match each other AND the local build
#
# Usage:
#   scripts/deploy_frontend.sh          # build + deploy both frontend canisters + verify
#   scripts/deploy_frontend.sh --ui     # ALSO rebuild + deploy cafresohq_ui (hq office app)
#   scripts/deploy_frontend.sh --verify-only   # no build/deploy; just check live parity
set -euo pipefail
cd "$(dirname "$0")/.."

IDENTITY="default"          # memory rule: deploy with `default`, not ic_admin
DOMAINS=(https://cafreso.com https://ai.cafreso.com)
DO_UI=false
VERIFY_ONLY=false
for a in "$@"; do
  case "$a" in
    --ui) DO_UI=true ;;
    --verify-only) VERIFY_ONLY=true ;;
    *) echo "unknown flag: $a" >&2; exit 2 ;;
  esac
done

entries_from_html() {
  # extract the hashed entry bundle names referenced by an index.html
  grep -oE '_app/immutable/entry/[a-zA-Z0-9._-]+\.js' | sort -u
}

if ! $VERIFY_ONLY; then
  echo "==> building frontend/"
  npm --prefix frontend run build

  echo "==> deploying cafresohq_frontend + cafreso_pages (identity: $IDENTITY)"
  dfx deploy --network ic --identity "$IDENTITY" cafresohq_frontend
  dfx deploy --network ic --identity "$IDENTITY" cafreso_pages

  if $DO_UI; then
    echo "==> building + deploying cafresohq_ui"
    python3 scripts/build_hq_ui.py
    dfx deploy --network ic --identity "$IDENTITY" cafresohq_ui
  fi
fi

echo "==> verifying served bundle parity"
LOCAL_ENTRIES="$(entries_from_html < frontend/build/index.html)"
[ -n "$LOCAL_ENTRIES" ] || { echo "FAIL: no entry bundles found in frontend/build/index.html" >&2; exit 1; }

FAIL=0
for d in "${DOMAINS[@]}"; do
  # cache-bust query param so we see what the canister serves NOW
  LIVE="$(curl -fsS --max-time 20 "$d/index.html?cb=$(date +%s)" | entries_from_html || true)"
  if [ -z "$LIVE" ]; then
    echo "FAIL: $d — could not read entry bundles from live index.html"; FAIL=1; continue
  fi
  if [ "$LIVE" = "$LOCAL_ENTRIES" ]; then
    echo "OK:   $d matches local build"
    echo "$LIVE" | sed 's/^/        /'
  else
    echo "FAIL: $d does NOT match local build"
    echo "  local:"; echo "$LOCAL_ENTRIES" | sed 's/^/    /'
    echo "  live:";  echo "$LIVE" | sed 's/^/    /'
    FAIL=1
  fi
done

if $DO_UI; then
  UI_LOCAL="$(grep -oE 'hq-app-[a-f0-9]+\.js' hq-ui/hq.html | sort -u || true)"
  UI_LIVE="$(curl -fsS --max-time 20 "https://ai.cafreso.com/hq.html?cb=$(date +%s)" 2>/dev/null | grep -oE 'hq-app-[a-f0-9]+\.js' | sort -u || true)"
  # hq.html may be served from the cafresohq_ui canister URL instead — try that too
  if [ -z "$UI_LIVE" ]; then
    UI_CANISTER_ID="$(dfx canister --network ic id cafresohq_ui 2>/dev/null || true)"
    [ -n "$UI_CANISTER_ID" ] && UI_LIVE="$(curl -fsS --max-time 20 "https://$UI_CANISTER_ID.icp0.io/hq.html?cb=$(date +%s)" | grep -oE 'hq-app-[a-f0-9]+\.js' | sort -u || true)"
  fi
  if [ -n "$UI_LOCAL" ] && [ "$UI_LOCAL" = "$UI_LIVE" ]; then
    echo "OK:   hq-ui bundle parity ($UI_LOCAL)"
  else
    echo "FAIL: hq-ui bundle mismatch (local: ${UI_LOCAL:-none} live: ${UI_LIVE:-none})"; FAIL=1
  fi
fi

if [ "$FAIL" -ne 0 ]; then
  echo; echo "DRIFT DETECTED — one or more domains serve a different bundle. Re-deploy the failing canister." >&2
  exit 1
fi
echo; echo "All domains serve the same, current build. Ship confirmed."
