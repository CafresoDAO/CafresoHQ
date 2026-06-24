#!/bin/bash
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
echo "=== docker config auths ==="
cat ~/.docker/config.json 2>&1 | python3 -c '
import json, sys
d = json.load(sys.stdin)
auths = d.get("auths", {})
print("hosts:", list(auths.keys()))
for h, v in auths.items():
    a = v.get("auth", "")
    print("  " + h + ": has-auth=" + str(bool(a)) + " len=" + str(len(a)))
'
echo ""
echo "=== test push (without re-login) ==="
docker buildx build \
    --builder cafresoai-builder \
    --platform linux/arm64 \
    --provenance=false \
    -t iad.ocir.io/idwv6126novh/cafresoai-serve:latest \
    -f $REPO_ROOT/oci-fleet/Dockerfile \
    --push \
    $REPO_ROOT 2>&1 | tail -8
