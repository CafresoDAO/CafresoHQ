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
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates gnupg jq procps bash \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js 20 LTS (required for Claude Code CLI + Codex CLI) ────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Claude Code CLI ──────────────────────────────────────────────────────────
RUN npm install -g @anthropic-ai/claude-code@latest

# ── Codex CLI (optional — comment out if not needed) ─────────────────────────
RUN npm install -g @openai/codex@latest || true

# ── Python deps for serve.py OCI vault backend ───────────────────────────────
COPY oci-fleet/requirements-serve.txt /tmp/requirements-serve.txt
RUN pip install --no-cache-dir -r /tmp/requirements-serve.txt

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

# ── Container entrypoint ──────────────────────────────────────────────────────
COPY oci-fleet/entrypoint.sh  ./entrypoint.sh
RUN chmod +x entrypoint.sh

# ── Runtime data dirs (override with OCI Block Volume or Object Storage) ─────
RUN mkdir -p /data/hq-state /data/vault

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

# ── Agent CLI keys — override at runtime via fleet-manager or docker run -e ──
# Leave blank here; fleet-manager.py injects per-user values at provisioning.
# Users can also supply their own keys via HQ Settings (BYOK); serve.py
# injects them per-request without touching these container-wide vars.
ENV ANTHROPIC_API_KEY=""
ENV OPENAI_API_KEY=""
ENV OCA_API_KEY=""

# Expose serve.py port
EXPOSE 8787

# Liveness check — fleet-manager and OCI health monitor both hit this
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:8787/health | python3 -c \
        "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('status')=='ok' else 1)"

# ── Entrypoint ────────────────────────────────────────────────────────────────
# entrypoint.sh configures CLI auth from env vars, then execs serve.py.
ENTRYPOINT ["./entrypoint.sh"]
