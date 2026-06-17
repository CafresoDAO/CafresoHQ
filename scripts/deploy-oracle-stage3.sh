#!/usr/bin/env bash
# Stage 3: apply the adversarial-review hardening fixes —
#   server.js  (body cap, timeouts, error-path guard, process guards, /session
#               rate-limit + outbound timeout)
#   stripe-oracle.service (MemoryMax/CPUQuota/TasksMax + syscall/ns hardening)
#   Caddy /stripe block (request_body max_size, edge defense-in-depth)
# Auto-rolls-back the unit + server.js if the service fails to start. Idempotent.
set -uo pipefail
KEY=/home/anthony/.ssh/cafreso_tls_gateway
VM=ubuntu@129.80.230.53
SRC=/mnt/c/Users/Anthony/Desktop/CafresoHQHermez/oci-fleet/stripe-oracle
SSHOPT=(-i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)

echo "===== upload hardened files ====="
scp "${SSHOPT[@]}" "$SRC/server.js" "$SRC/stripe-oracle.service" "$VM:/tmp/" \
  || { echo "SCP FAILED"; exit 1; }

ssh "${SSHOPT[@]}" "$VM" 'bash -s' <<'REMOTE'
set -uo pipefail
TS=$(date +%Y%m%d-%H%M%S)

echo "--- pre-check ---"
echo "  state: $(systemctl is-active stripe-oracle)   MemoryCurrent: $(systemctl show -p MemoryCurrent --value stripe-oracle) bytes"

echo "--- backup + deploy service code + unit ---"
sudo cp /opt/stripe-oracle/server.js "/opt/stripe-oracle/server.js.bak-$TS"
sudo cp /etc/systemd/system/stripe-oracle.service "/etc/systemd/system/stripe-oracle.service.bak-$TS"
sudo cp /tmp/server.js /opt/stripe-oracle/server.js
sudo chown ubuntu:ubuntu /opt/stripe-oracle/server.js
sudo cp /tmp/stripe-oracle.service /etc/systemd/system/stripe-oracle.service
sudo systemctl daemon-reload
sudo systemctl restart stripe-oracle
sleep 2
ST=$(systemctl is-active stripe-oracle)
echo "  service: $ST"
if [ "$ST" != "active" ]; then
  echo "  !! FAILED TO START — rolling back unit + server.js"
  sudo journalctl -u stripe-oracle -n 25 --no-pager | sed 's/^/    /'
  sudo cp "/opt/stripe-oracle/server.js.bak-$TS" /opt/stripe-oracle/server.js
  sudo cp "/etc/systemd/system/stripe-oracle.service.bak-$TS" /etc/systemd/system/stripe-oracle.service
  sudo systemctl daemon-reload; sudo systemctl restart stripe-oracle; sleep 1
  echo "  rolled back; service now: $(systemctl is-active stripe-oracle)"
  exit 1
fi

echo "--- verify effective resource caps ---"
systemctl show -p MemoryMax -p MemoryHigh -p CPUQuotaPerSecUSec -p TasksMax -p LimitNOFILE stripe-oracle | sed 's/^/  /'

echo "--- functional: /health (200) ---"
curl -s -o /dev/null -w "  health HTTP %{http_code}\n" http://127.0.0.1:8788/health

echo "--- functional: /session through Caddy (exercises egress UNDER the new syscall sandbox) ---"
RESP=$(curl -s -X POST https://hq.cafreso.com/stripe/session -H 'Content-Type: application/json' -H 'Origin: https://ai.cafreso.com' \
  -d '{"metadata":{"plan":"cafresohq-pro","icOrderId":"999002","principal":"2vxsx-fae"},"successUrl":"https://ai.cafreso.com/hq/plans","cancelUrl":"https://ai.cafreso.com/hq/plans"}')
if echo "$RESP" | grep -q 'checkout.stripe.com'; then echo "  SESSION_OK (DNS+TLS egress works under hardening)"; else echo "  SESSION_FAIL: $(echo "$RESP" | head -c 200)"; fi

echo "===== patch Caddy /stripe block: request_body max_size ====="
LIVE=/etc/caddy/Caddyfile
TMPL=/opt/fleet-api/caddyfile.template
sudo cp "$LIVE" "/etc/caddy/Caddyfile.bak-$TS"
cp "$TMPL" "/opt/fleet-api/caddyfile.template.bak-$TS"
sudo python3 - "$LIVE" "$TMPL" <<'PY'
import sys, io
old = "    handle_path /stripe/* {\n        reverse_proxy localhost:8788\n    }"
new = ("    handle_path /stripe/* {\n"
       "        request_body {\n"
       "            max_size 256KB\n"
       "        }\n"
       "        reverse_proxy localhost:8788\n"
       "    }")
for path in sys.argv[1:]:
    with io.open(path, "r", encoding="utf-8") as f: c = f.read()
    if "request_body" in c and "max_size 256KB" in c:
        print("  %s: already has request_body cap, skipping" % path); continue
    if old not in c:
        print("  %s: stripe block anchor not found — skipping" % path); continue
    with io.open(path, "w", encoding="utf-8") as f: f.write(c.replace(old, new, 1))
    print("  %s: added request_body max_size" % path)
PY

echo "--- validate + reload caddy (rollback on failure) ---"
if sudo caddy validate --config "$LIVE" --adapter caddyfile >/tmp/cv.log 2>&1; then
  sudo systemctl reload caddy; sleep 1
  echo "  caddy: $(systemctl is-active caddy)"
else
  echo "  VALIDATE FAILED — restoring Caddy backups"; tail -15 /tmp/cv.log
  sudo cp "/etc/caddy/Caddyfile.bak-$TS" "$LIVE"; cp "/opt/fleet-api/caddyfile.template.bak-$TS" "$TMPL"
fi

echo "--- verify: oversized body rejected (expect 413), small ok, gateway regression-clean ---"
head -c 300000 </dev/zero | tr '\0' a > /tmp/big.txt
curl -s -o /dev/null -w "  300KB POST /stripe/webhook  HTTP %{http_code} (expect 413)\n" -X POST https://hq.cafreso.com/stripe/webhook --data-binary @/tmp/big.txt
rm -f /tmp/big.txt
curl -s -o /dev/null -w "  /stripe/health              HTTP %{http_code} (expect 200)\n" https://hq.cafreso.com/stripe/health
curl -s -o /dev/null -w "  /healthz                    HTTP %{http_code} (expect 200)\n" https://hq.cafreso.com/healthz
curl -s -o /dev/null -w "  /fleet/health               HTTP %{http_code} (expect 200)\n" https://hq.cafreso.com/fleet/health
REMOTE
rc=$?
echo "===== stage3 exit $rc ====="
exit $rc
