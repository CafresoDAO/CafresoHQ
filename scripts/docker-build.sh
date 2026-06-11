#!/usr/bin/env bash
# ── CafresoAI — Multi-platform Docker build + push ───────────────────────────
# Builds a fat manifest covering linux/amd64 + linux/arm64 so the image runs
# natively on x86-64 Linux servers, OCI Fleet nodes, AND Apple Silicon Macs
# without any "platform mismatch" warning or QEMU emulation penalty.
#
# Usage:
#   bash scripts/docker-build.sh                     # build + push :latest
#   bash scripts/docker-build.sh --tag v1.2.0        # also tag a version
#   bash scripts/docker-build.sh --dry-run           # print commands, don't run
#
# Requirements:
#   docker buildx (bundled with Docker Desktop; `docker buildx version` to check)
#   Logged into Docker Hub: `docker login`

set -euo pipefail

IMAGE="docker.io/anthonycf1/cafresoai-serve"
PLATFORMS="linux/amd64,linux/arm64"
EXTRA_TAG=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)       EXTRA_TAG="$2"; shift 2 ;;
    --dry-run)   DRY_RUN=true; shift ;;
    *)           echo "Unknown arg: $1"; exit 1 ;;
  esac
done

run() {
  echo "» $*"
  $DRY_RUN || "$@"
}

# ── 1. Ensure a multi-platform builder exists ─────────────────────────────────
if ! docker buildx inspect multiarch >/dev/null 2>&1; then
  echo "Creating buildx builder 'multiarch'…"
  run docker buildx create --name multiarch --driver docker-container --bootstrap
fi
run docker buildx use multiarch

# ── 2. Build + push both platforms in one shot ────────────────────────────────
# --push uploads the manifest + both layer sets to the registry atomically.
# Without --push you'd need --load (which only works for a single platform).
TAGS="--tag ${IMAGE}:latest"
[[ -n "$EXTRA_TAG" ]] && TAGS="$TAGS --tag ${IMAGE}:${EXTRA_TAG}"

run docker buildx build \
  --platform "$PLATFORMS" \
  $TAGS \
  --push \
  -f oci-fleet/Dockerfile \
  .

echo ""
echo "✓ Pushed multi-arch manifest: ${IMAGE}:latest  [${PLATFORMS}]"
[[ -n "$EXTRA_TAG" ]] && echo "  also tagged:               ${IMAGE}:${EXTRA_TAG}"
echo ""
echo "Users can now run:"
echo "  docker run -d --name cafresohq -p 8787:8787 \\"
echo "    -v cafresohq-data:/data \\"
echo "    ${IMAGE}:latest"
echo ""
echo "Docker will automatically pull the correct architecture for their machine."
