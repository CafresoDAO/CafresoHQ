#!/bin/sh
# ── CafresoAI container entrypoint ──────────────────────────────────────────
# Configures CLI tool auth from environment variables, then starts serve.py.
# This runs on every container start, so auth setup is always fresh.
#
# Auth precedence:
#   1. Server env vars (ANTHROPIC_API_KEY, OPENAI_API_KEY) — set by fleet-manager
#      or docker-compose for whole-container auth (all users share the key).
#   2. Per-request BYOK keys — user supplies their own key via HQ Settings.
#      serve.py injects them into the subprocess env only for that request.
#      Server env always wins over BYOK keys (admin can lock the backend).

set -e

# ── Claude Code CLI ─────────────────────────────────────────────────────────
# `claude --print` reads ANTHROPIC_API_KEY directly from env — no file config.
if [ -n "${ANTHROPIC_API_KEY}" ]; then
  echo "[entrypoint] ANTHROPIC_API_KEY present — claude CLI will use API key auth"
else
  echo "[entrypoint] No ANTHROPIC_API_KEY — users must supply their own via HQ Settings (BYOK)"
fi

# ── Codex CLI ───────────────────────────────────────────────────────────────
# Create a minimal ~/.codex/config.toml on first start.
# Per-request provider/model flags in serve.py override these defaults.
mkdir -p /root/.codex
if [ ! -f /root/.codex/config.toml ]; then
  cat > /root/.codex/config.toml << 'TOML'
# CafresoAI — codex CLI base config
# Provider and model are overridden per-request by serve.py via -c flags.
# Codex talks directly to OpenAI; the user supplies OPENAI_API_KEY via HQ
# Settings (BYOK) or the operator sets it in the container env.
model = "gpt-4.1"
approval_policy = "untrusted"
TOML
  echo "[entrypoint] Created /root/.codex/config.toml"
fi

# ── Hermes Agent (DEFAULT runtime) ───────────────────────────────────────────
# Seed $HERMES_HOME (config.yaml + .env) then start `hermes gateway` in the
# background. The gateway boots the OpenAI-compatible API server on
# 127.0.0.1:8642; serve.py proxies /hermes/* to it (same container = same
# network namespace). serve.py stays PID 1 / foreground so the container's
# liveness check (/health on :8787) governs restarts; the app shell is served
# even if the gateway is slow to come up.
if command -v hermes >/dev/null 2>&1; then
  echo "[entrypoint] Bootstrapping Hermes (HERMES_HOME=${HERMES_HOME:-/root/.hermes})"
  python -u hermes-bootstrap.py || echo "[entrypoint] hermes-bootstrap warned (non-fatal)"

  if [ -z "${API_SERVER_KEY}" ]; then
    echo "[entrypoint] WARN API_SERVER_KEY empty — Hermes API server requires it; skipping gateway start"
  else
    echo "[entrypoint] Starting hermes gateway (API server :${HERMES_API_PORT:-8642})…"
    mkdir -p /data
    nohup hermes gateway run >/data/hermes-gateway.log 2>&1 &
    # Poll for the API server to bind (non-fatal; serve.py serves regardless).
    i=0
    while [ "$i" -lt 30 ]; do
      if curl -sf -o /dev/null "http://127.0.0.1:${HERMES_API_PORT:-8642}/v1/models" \
           -H "Authorization: Bearer ${API_SERVER_KEY}"; then
        echo "[entrypoint] Hermes API server is up on :${HERMES_API_PORT:-8642}"
        break
      fi
      i=$((i + 1))
      sleep 1
    done
    [ "$i" -ge 30 ] && echo "[entrypoint] WARN Hermes API server not up after 30s — see /data/hermes-gateway.log"
  fi
else
  echo "[entrypoint] WARN hermes CLI not found in image — /hermes proxy will 502 until installed"
fi

# ── Start serve.py (foreground / PID 1) ──────────────────────────────────────
exec python -u serve.py
