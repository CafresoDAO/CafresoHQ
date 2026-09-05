#!/bin/sh
# ── CafresoHQ local launcher (unix / WSL) ───────────────────────────────────
# Mirrors docker/entrypoint.sh for local development: seed Hermes, make sure
# the gateway (OpenAI-compatible API server) is up, then run serve.py in the
# foreground. Because this runs on a unix host (WSL on Windows, or native
# Linux/macOS), every agent CLI — hermes, claude, codex, gemini — is native and
# the Projects terminal uses the stdlib PTY. One code path everywhere.
#
# Env overrides: PORT (default 8787), HERMES_API_PORT (8642), HERMES_HOME.
set -e

# cd to the directory this script lives in (the repo root), regardless of caller.
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

# ── Prerequisite preflight ──────────────────────────────────────────────────
# `## 405.` — the README names "Node 18+ and Python 3" and nothing checked for
# either. This script already explained a missing `npm`; its LAST line was a
# bare `exec python3 serve.py`, so a machine without python3 ended the whole
# launch on `Start-CafresoHQ.sh: python3: not found` — the shell's words, not
# the product's, with no version, no URL, and no next step. Check both here,
# before any work, so the tester learns what to install while they still have
# an empty terminal instead of after a two-minute npm install.
if ! command -v python3 >/dev/null 2>&1; then
  echo "[start] ERROR python3 is not on PATH, and serve.py — the whole backend — is a"
  echo "        Python program. Nothing in CafresoHQ can start without it."
  echo "        Install Python 3 (https://www.python.org/downloads/, or"
  echo "        \`brew install python3\` / \`apt install python3\`), then re-run this script."
  exit 1
fi

# Node's floor is declared in ONE place — package.json's engines.node — so this
# reads it rather than repeating the number. npm enforces the same floor at
# install time via .npmrc's engine-strict; this catches the case where npm is
# never reached because dist-ui/ already exists but node is still too old.
if command -v node >/dev/null 2>&1; then
  _node_floor="$(sed -n 's/.*"node": *">=\([0-9][0-9]*\)".*/\1/p' package.json | head -1)"
  _node_have="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo '')"
  if [ -n "$_node_floor" ] && [ -n "$_node_have" ] && [ "$_node_have" -lt "$_node_floor" ]; then
    echo "[start] ERROR Node $(node -v) is too old — CafresoHQ needs Node ${_node_floor}+ to build its UI."
    echo "        Install Node ${_node_floor} or newer (https://nodejs.org), or"
    echo "        \`nvm install ${_node_floor} && nvm use ${_node_floor}\`, then re-run this script."
    exit 1
  fi
fi

# ── UI preflight ────────────────────────────────────────────────────────────
# dist-ui/ and node_modules/ are both gitignored, so a fresh clone has neither
# and serve.py can only answer /hq.html with a 500. This script is what testers
# are pointed at, so it does the two steps itself rather than handing the 500
# page the job of teaching them.
if [ ! -f dist-ui/manifest.json ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "[start] ERROR the HQ UI is not built (dist-ui/manifest.json is missing) and"
    echo "        npm is not on PATH, so it cannot be built here. Install Node.js 18+"
    echo "        (https://nodejs.org), then run: npm install && npm run build"
    exit 1
  fi
  if [ ! -d node_modules ]; then
    echo "[start] installing UI dependencies (npm install) — first run only…"
    npm install || { echo "[start] ERROR npm install failed — see the output above"; exit 1; }
  fi
  echo "[start] building the HQ UI bundle (npm run build) — first run only…"
  npm run build || { echo "[start] ERROR npm run build failed — see the output above"; exit 1; }
fi

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_API_PORT="${HERMES_API_PORT:-8642}"
PORT="${PORT:-8787}"

# Share the gateway's bearer key with serve.py's /hermes proxy. Both read the
# same ~/.hermes/.env here, so they always agree (no manual env var needed).
if [ -z "${API_SERVER_KEY:-}" ] && [ -f "$HERMES_HOME/.env" ]; then
  API_SERVER_KEY="$(grep -m1 '^API_SERVER_KEY=' "$HERMES_HOME/.env" | cut -d= -f2-)"
  export API_SERVER_KEY
fi

_gateway_up() {
  curl -sf -o /dev/null \
    -H "Authorization: Bearer ${API_SERVER_KEY:-}" \
    "http://127.0.0.1:${HERMES_API_PORT}/v1/models" 2>/dev/null
}

if command -v hermes >/dev/null 2>&1; then
  if _gateway_up; then
    echo "[start] hermes gateway already up on :${HERMES_API_PORT}"
  else
    echo "[start] hermes gateway not responding — starting it…"
    [ -f docker/hermes-bootstrap.py ] && python3 docker/hermes-bootstrap.py || true
    nohup hermes gateway run >"${HERMES_HOME}/gateway.log" 2>&1 &
    i=0
    while [ "$i" -lt 30 ]; do
      if _gateway_up; then echo "[start] hermes gateway is up on :${HERMES_API_PORT}"; break; fi
      i=$((i + 1)); sleep 1
    done
    [ "$i" -ge 30 ] && echo "[start] WARN gateway not up after 30s — see ${HERMES_HOME}/gateway.log"
  fi
else
  echo "[start] WARN hermes CLI not installed — /hermes will 502 until you install it (Settings → Agents)"
fi

# serve.py serves HTTPS in local mode ONLY when it can get a browser-TRUSTED
# cert, which today means mkcert on PATH. Without mkcert it stays on plain
# HTTP — it does NOT fall back to a self-signed cert. (`## 405.` corrected this
# paragraph, which claimed the opposite; serve.py's `_ensure_local_tls` is
# called with `allow_selfsigned=_tls_forced`, and that is false unless the
# tester sets CAFRESOHQ_TLS_AUTO=1. The reason is written at the call site: a
# TLS-only server with a cert the browser rejects is unreachable, which is
# worse than HTTP, and http://localhost is already a secure context.)
# HTTP is fine for using HQ directly; the embed in https://ai.cafreso.com and
# the iOS service worker are what need the trusted cert.
if command -v mkcert >/dev/null 2>&1; then
  echo "[start] mkcert found — HQ will get a browser-trusted HTTPS cert (embeds cleanly in ai.cafreso.com)"
else
  echo "[start] serving over plain HTTP (fine for local use). For the ai.cafreso.com embed"
  echo "        or the iOS service worker, HQ needs a browser-TRUSTED cert: install mkcert →"
  echo "        https://github.com/FiloSottile/mkcert  then re-run this script."
  echo "        (Without it there is no HTTPS at all here — not a self-signed one. Set"
  echo "         CAFRESOHQ_TLS_AUTO=1 if you want the self-signed fallback and will trust it.)"
fi

# serve.py binds 127.0.0.1 by default in local mode (loopback-only = safe, no key
# needed). To reach HQ from another device you must expose it AND set a key — the
# terminal is effectively remote code execution:
#   CAFRESOHQ_BIND=0.0.0.0 CAFRESOHQ_API_KEY=<secret> sh Start-CafresoHQ.sh
echo "[start] serving CafresoHQ on :${PORT}  (loopback-only; serve.py prints the exact URL + scheme)"
exec python3 serve.py
