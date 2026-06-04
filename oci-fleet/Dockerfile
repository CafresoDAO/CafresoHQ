# ── CafresoAI — OCI Fleet Container Image ────────────────────────────────────
# Builds a self-contained serve.py image that runs inside OCI Container Instances.
# Each user gets their own isolated instance of this image.
#
# Build:
#   docker build -t cafresoai-serve:latest -f oci-fleet/Dockerfile .
#
# Push to OCI Registry (OCIR):
#   docker tag cafresoai-serve:latest iad.ocir.io/idwv6126novh/cafresoai-serve:latest
#   docker push iad.ocir.io/idwv6126novh/cafresoai-serve:latest
#
# Or use fleet-manager:  python oci-fleet/fleet-manager.py image-push

FROM python:3.11-slim-bookworm

# ── System deps ──────────────────────────────────────────────────────────────
# build-essential + python3-dev: so user code-agent sessions (Claude Code / Codex)
#   can compile native npm/pip modules. ripgrep: Claude Code uses `rg` for fast
#   search and degrades/ warns without it. Without these the CLIs *start* but
#   real coding workloads fail mid-task.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates gnupg jq procps bash \
    build-essential python3-dev ripgrep less unzip \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js 20 LTS ───────────────────────────────────────────────────────────
# Kept in the base image so Claude Code / Codex can be installed ON-DEMAND
# (npm i -g) from HQ Settings — the image ships Hermes-first and lean, and users
# add the coding agents they want after provisioning (POST /agents/install).
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# NOTE: Claude Code + Codex are intentionally NOT baked in. They install on
# demand via serve.py POST /agents/install (Settings → Agents). This keeps the
# image small + provisioning fast; Hermes is the always-present default runtime.

# ── Python deps for serve.py OCI vault backend ───────────────────────────────
COPY oci-fleet/requirements-serve.txt /tmp/requirements-serve.txt
RUN pip install --no-cache-dir -r /tmp/requirements-serve.txt

# ── Hermes Agent (Nous Research) — the DEFAULT agent runtime ─────────────────
# Provides the `hermes` CLI + gateway + OpenAI-compatible API server. The
# entrypoint runs `hermes gateway` alongside serve.py; serve.py proxies
# /hermes/* → 127.0.0.1:8642 (same container = same netns). Pinned to the
# researched/verified version.
#
# aiohttp is REQUIRED for the OpenAI-compatible API server adapter — the lean
# `hermes-agent` wheel does not pull it, and without it the gateway logs
# "API Server: aiohttp not installed" and the :8642 endpoint never binds
# (verified via local container test). Keep it pinned alongside hermes-agent.
RUN pip install --no-cache-dir "hermes-agent==0.15.1" aiohttp

# ── App files — copy only what serve.py needs to serve ───────────────────────
WORKDIR /app

COPY serve.py                 ./serve.py
COPY hq.html ./hq.html
COPY styles.css               ./styles.css
COPY app.jsx                  ./app.jsx
COPY ui.jsx                   ./ui.jsx
COPY views.jsx                ./views.jsx
COPY modals.jsx               ./modals.jsx
COPY features.jsx             ./features.jsx
COPY missions.jsx             ./missions.jsx
COPY agent_runner.jsx         ./agent_runner.jsx
COPY claude-client.jsx        ./claude-client.jsx
COPY sprites.jsx              ./sprites.jsx
COPY tweaks-panel.jsx         ./tweaks-panel.jsx
COPY mock-data.jsx            ./mock-data.jsx
COPY sw.js                    ./sw.js
COPY manifest.webmanifest     ./manifest.webmanifest

# ── Container entrypoint + Hermes bootstrap ──────────────────────────────────
COPY oci-fleet/entrypoint.sh      ./entrypoint.sh
COPY oci-fleet/hermes-bootstrap.py ./hermes-bootstrap.py
RUN chmod +x entrypoint.sh

# ── Runtime data dirs (override with OCI Block Volume or Object Storage) ─────
# /root/Documents is in the Codex/Openclaw allowed-dirs sandbox; create it so
# code-agent sessions have a valid working directory (was a "badDir" otherwise).
RUN mkdir -p /data/hq-state /data/vault /data/hermes /root/Documents

# ── Environment ──────────────────────────────────────────────────────────────
# These defaults are overridden per-container by fleet-manager.py
LABEL org.opencontainers.image.title="CafresoAI Serve"
LABEL org.opencontainers.image.description="CafresoAI — AI Agent Fleet Node"
LABEL org.opencontainers.image.vendor="Cafreso"

ENV OPENCLAW_FLEET_MODE=oci-fleet
ENV OPENCLAW_VAULT_BACKEND=oci
ENV OPENCLAW_HQ_STATE_DIR=/data/hq-state
ENV OPENCLAW_VAULT=/data/vault
ENV PORT=8787

# Hermes Agent state (config.yaml, memories/, cron/, .env) on the data volume
# so persistent memory + cron survive container restarts. The API server runs
# on loopback inside the container; serve.py proxies /hermes/* to it.
ENV HERMES_HOME=/data/hermes
ENV API_SERVER_ENABLED=true
ENV HERMES_API_HOST=127.0.0.1
ENV HERMES_API_PORT=8642

# ── Agent CLI keys — override at runtime via fleet-manager or docker run -e ──
# Leave blank here; fleet-manager.py injects per-user values at provisioning.
# Users can also supply their own keys via HQ Settings (BYOK); serve.py
# injects them per-request without touching these container-wide vars.
ENV ANTHROPIC_API_KEY=""
ENV OPENAI_API_KEY=""

# Expose serve.py port
EXPOSE 8787

# Liveness check — fleet-manager and OCI health monitor both hit this
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:8787/health | python3 -c \
        "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='ok' else 1)"

# ── Entrypoint ────────────────────────────────────────────────────────────────
# entrypoint.sh configures CLI auth from env vars, then execs serve.py.
ENTRYPOINT ["./entrypoint.sh"]
