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
# BYOK: if the user supplies OPENAI_API_KEY via HQ Settings, serve.py routes
#       codex directly to OpenAI (model_provider=openai).
# Fleet: if OCA_API_KEY is set server-side, serve.py routes via the local
#        OCA proxy (model_provider=oca, base_url=http://localhost:8787/oca/v1).
model = "gpt-4o"
approval_policy = "untrusted"
TOML
  echo "[entrypoint] Created /root/.codex/config.toml"
fi

# ── OCA key forwarding (fleet default) ─────────────────────────────────────
# Codex reads OPENAI_API_KEY; serve.py already mirrors OCA_API_KEY → OPENAI_API_KEY
# in the subprocess env, but doing it here too lets other tools in the container
# (e.g. curl tests) use the OCA gateway without extra config.
if [ -z "${OPENAI_API_KEY}" ] && [ -n "${OCA_API_KEY}" ]; then
  export OPENAI_API_KEY="${OCA_API_KEY}"
  echo "[entrypoint] Mirrored OCA_API_KEY → OPENAI_API_KEY for container-wide access"
fi

# ── Start serve.py ──────────────────────────────────────────────────────────
exec python -u serve.py
