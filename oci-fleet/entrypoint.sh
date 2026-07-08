#!/bin/sh
# ── CafresoHQ container entrypoint ──────────────────────────────────────────
# Configures CLI tool auth from environment variables, then starts serve.py.
# This runs on every container start, so auth setup is always fresh.
#
# Auth precedence:
#   1. Server env vars (ANTHROPIC_API_KEY, OPENAI_API_KEY) — set by fleet-manager
#      or docker-compose for whole-container auth (all users share the key).
#   2. Per-request BYOK keys — user supplies their own key via HQ Settings.
#      serve.py injects them into the subprocess env only for that request.
#      Server env always wins over BYOK keys (admin can lock the backend).
#
# Shared FREE-TRIAL brain (optional, operator-set on the image/fleet):
#   CAFRESOHQ_TRIAL_KEY       a shared free-tier LLM key. When a fresh HQ has NO
#                             user key, hermes-bootstrap.py falls back to this so
#                             a brand-new user's agents WORK on first launch with
#                             zero third-party signup. It writes a trial marker;
#                             serve.py meters it (per-principal daily cap) and
#                             clears it the instant the user brings their own key.
#   CAFRESOHQ_TRIAL_PROVIDER  openrouter (default) | gemini | groq. Put ~$10 on the
#                             shared OpenRouter account to lift :free 50→1000 req/day,
#                             or use gemini (1500/day). MUST be its own var — never
#                             reuse a standard provider var, or the trial can't be
#                             told apart from a real user key.
#   CAFRESOHQ_TRIAL_MODEL     optional model override for the trial provider.
#   CAFRESOHQ_TRIAL_DAILY_CAP per-principal free messages/day before the upsell
#                             (default 25). Also live-settable from the operator
#                             admin panel once that ships.

set -e

# ── Self-host (docker run) auto-configuration ───────────────────────────────
# Fleet containers get a full env from fleet-manager.py: OCI vault credentials,
# a per-principal API_SERVER_KEY, fleet mode. The self-host one-liner
# (`docker run -d -p 8787:8787 -v cafresohq-data:/data …`) sets none of that,
# so detect the bare run and fall back to local-friendly defaults — otherwise
# the vault points at Object Storage it can't reach (writes hang) and the
# Hermes gateway never starts (no API key).
# Discriminate on OCI_VAULT_NAMESPACE, NOT OCI_TENANCY_OCID: fleet-manager
# always sets the namespace from its own env config, whereas it derives the
# tenancy OCID from a ~/.oci/config read that can FAIL (leaving it empty while
# still provisioning a real fleet container). Keying on tenancy would flip such
# a fleet container to ephemeral fs storage → silent vault DATA LOSS on the next
# container replacement, and would defeat serve.py's instance-principal auth
# fallback. Do NOT key on CAFRESOHQ_FLEET_MODE — the image bakes it to
# 'oci-fleet' for everyone, self-host included.
if [ "${CAFRESOHQ_VAULT_BACKEND}" = "oci" ] && [ -z "${OCI_VAULT_NAMESPACE}" ]; then
  echo "[entrypoint] No OCI vault namespace — self-host run: vault backend → fs, mode → local"
  export CAFRESOHQ_VAULT_BACKEND=fs
  export CAFRESOHQ_FLEET_MODE=local
fi
if [ -z "${API_SERVER_KEY}" ]; then
  # Reuse the key persisted on the data volume from a prior boot, else mint one.
  # The gateway requires a non-empty key to serve its OpenAI-compatible API;
  # serve.py's /hermes proxy injects it as the Bearer token, so the value never
  # needs to leave the container.
  _envf="${HERMES_HOME:-/root/.hermes}/.env"
  if [ -f "${_envf}" ]; then
    API_SERVER_KEY="$(sed -n 's/^API_SERVER_KEY=//p' "${_envf}" | head -1)"
  fi
  if [ -z "${API_SERVER_KEY}" ]; then
    API_SERVER_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
    echo "[entrypoint] Generated API_SERVER_KEY for the Hermes gateway (persists in ${_envf})"
  else
    echo "[entrypoint] Reusing API_SERVER_KEY from ${_envf}"
  fi
  export API_SERVER_KEY
fi

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
# CafresoHQ — codex CLI base config
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

# ── npm environment for on-demand agent installs ────────────────────────────
# POST /agents/install runs `npm i -g`; serve.py inherits this env for its
# subprocesses, so make the prefix/cache/HOME explicit + writable here. Without
# this, root's npm guesses an unwritable prefix or a missing cache and installs
# fail with EACCES. (Dockerfile pre-creates the dirs; this guarantees the env.)
export HOME="${HOME:-/root}"
export npm_config_prefix="${npm_config_prefix:-/usr/local}"
export npm_config_cache="${npm_config_cache:-/root/.npm}"
if command -v npm >/dev/null 2>&1; then
  echo "[entrypoint] npm $(npm --version) prefix=$(npm config get prefix) cache=$(npm config get cache)"
fi

# ── Start serve.py (foreground / PID 1) ──────────────────────────────────────
exec python -u serve.py
