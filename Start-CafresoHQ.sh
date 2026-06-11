#!/bin/sh
# ── CafresoHQ local launcher (unix / WSL) ───────────────────────────────────
# Mirrors oci-fleet/entrypoint.sh for local development: seed Hermes, make sure
# the gateway (OpenAI-compatible API server) is up, then run serve.py in the
# foreground. Because this runs on a unix host (WSL on Windows, or native
# Linux/macOS), every agent CLI — hermes, claude, codex, gemini — is native and
# the Projects terminal uses the stdlib PTY. One code path everywhere.
#
# Env overrides: PORT (default 8787), HERMES_API_PORT (8642), HERMES_HOME.
set -e

# cd to the directory this script lives in (the repo root), regardless of caller.
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

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
    [ -f oci-fleet/hermes-bootstrap.py ] && python3 oci-fleet/hermes-bootstrap.py || true
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

# serve.py auto-provisions a localhost TLS cert in local mode and serves HTTPS,
# so the app can be embedded inside https://ai.cafreso.com. For a *trusted* cert
# (no browser warning, seamless embed) install mkcert; otherwise serve.py falls
# back to a self-signed cert (works after a one-time trust, or for direct use).
if command -v mkcert >/dev/null 2>&1; then
  echo "[start] mkcert found — HQ will get a browser-trusted HTTPS cert (embeds cleanly in ai.cafreso.com)"
else
  echo "[start] TIP: install mkcert for a browser-trusted local HTTPS cert →"
  echo "        https://github.com/FiloSottile/mkcert  (without it, the cert is self-signed)"
fi

# serve.py binds 127.0.0.1 by default in local mode (loopback-only = safe, no key
# needed). To reach HQ from another device you must expose it AND set a key — the
# terminal is effectively remote code execution:
#   OPENCLAW_BIND=0.0.0.0 OPENCLAW_API_KEY=<secret> sh Start-CafresoHQ.sh
echo "[start] serving CafresoHQ on :${PORT}  (loopback-only; serve.py prints the exact URL + scheme)"
exec python3 serve.py
