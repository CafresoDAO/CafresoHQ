#!/usr/bin/env bash
# ── CafresoHQ search-network worker — Multi-platform Docker build + push ────
# Same pattern as scripts/docker-build.sh, pointed at the standalone,
# minimal search-worker image (search_worker_service/) instead of the full
# HQ monolith. Separate Docker Hub repo on purpose — independent tag
# history, and lets an operator pull just the worker without wading through
# the monolith's tags.
#
# Usage:
#   bash scripts/docker-build-worker.sh                # build + push :latest
#   bash scripts/docker-build-worker.sh --tag v1.0.0    # also tag a version
#   bash scripts/docker-build-worker.sh --dry-run       # print commands, don't run
#
# Requirements:
#   docker buildx (bundled with Docker Desktop; `docker buildx version` to check)
#   Logged into Docker Hub: `docker login`

set -euo pipefail

IMAGE="docker.io/anthonycf1/cafreso-search-worker"
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
TAGS="--tag ${IMAGE}:latest"
[[ -n "$EXTRA_TAG" ]] && TAGS="$TAGS --tag ${IMAGE}:${EXTRA_TAG}"

run docker buildx build \
  --platform "$PLATFORMS" \
  $TAGS \
  --push \
  -f search_worker_service/Dockerfile \
  .

echo ""
echo "✓ Pushed multi-arch manifest: ${IMAGE}:latest  [${PLATFORMS}]"
[[ -n "$EXTRA_TAG" ]] && echo "  also tagged:               ${IMAGE}:${EXTRA_TAG}"
echo ""
echo "Operators can now run:"
echo "  docker run -d --name cafreso-search-worker -p 8788:8788 \\"
echo "    --env-file worker.env \\"
echo "    -v cafreso-search-worker-data:/data \\"
echo "    ${IMAGE}:latest"
echo ""
echo "Docker will automatically pull the correct architecture for their machine."
