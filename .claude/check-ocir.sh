#!/bin/bash
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
    -f /mnt/c/Users/Anthony/Documents/CafresoHQ/oci-fleet/Dockerfile \
    --push \
    /mnt/c/Users/Anthony/Documents/CafresoHQ 2>&1 | tail -8
