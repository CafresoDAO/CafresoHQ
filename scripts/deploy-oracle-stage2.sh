#!/usr/bin/env bash
# Stage 2: add the /stripe/* route to Caddy — both the live /etc/caddy/Caddyfile
# AND the template (so caddy-sync preserves it). Backup first, validate before
# reload, auto-restore on validation failure. Idempotent.
set -uo pipefail
[ -f "$(dirname "$0")/../.env" ] && . "$(dirname "$0")/../.env"
KEY="${GATEWAY_SSH_KEY:-$HOME/.ssh/cafreso_tls_gateway}"
VM="ubuntu@${GATEWAY_IP:?set GATEWAY_IP in <repo>/.env or environment}"
SSHOPT=(-i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)

ssh "${SSHOPT[@]}" "$VM" 'bash -s' <<'REMOTE'
set -uo pipefail
TS=$(date +%Y%m%d-%H%M%S)
LIVE=/etc/caddy/Caddyfile
TMPL=/opt/fleet-api/caddyfile.template

echo "--- backups ($TS) ---"
sudo cp "$LIVE" "/etc/caddy/Caddyfile.bak-$TS" && echo "  backed up $LIVE"
cp "$TMPL" "/opt/fleet-api/caddyfile.template.bak-$TS" && echo "  backed up $TMPL"

echo "--- inserting /stripe/* route into both files ---"
sudo python3 - "$LIVE" "$TMPL" <<'PY'
import sys, io
anchor = "    handle /fleet/* {\n        reverse_proxy localhost:8080\n    }"
stripe = (
    "\n\n"
    "    # Stripe card-payment oracle (Node on localhost:8788). Prefix stripped\n"
    "    # so the service sees /session and /webhook. Static section -> survives\n"
    "    # caddy-sync.\n"
    "    handle_path /stripe/* {\n"
    "        reverse_proxy localhost:8788\n"
    "    }"
)
for path in sys.argv[1:]:
    with io.open(path, "r", encoding="utf-8") as f:
        c = f.read()
    if "handle_path /stripe/*" in c:
        print("  %s: already has /stripe route, skipping" % path); continue
    if anchor not in c:
        print("  %s: FLEET ANCHOR NOT FOUND — not modifying" % path); sys.exit(3)
    c2 = c.replace(anchor, anchor + stripe, 1)  # first (HTTPS) occurrence only
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(c2)
    print("  %s: inserted /stripe route" % path)
PY
rc=$?
if [ $rc -ne 0 ]; then echo "insertion failed (rc=$rc) — restoring"; sudo cp "/etc/caddy/Caddyfile.bak-$TS" "$LIVE"; cp "/opt/fleet-api/caddyfile.template.bak-$TS" "$TMPL"; exit $rc; fi

echo "--- validate live Caddyfile ---"
if ! sudo caddy validate --config "$LIVE" --adapter caddyfile >/tmp/caddyval.log 2>&1; then
  echo "  VALIDATE FAILED — restoring backups"; tail -20 /tmp/caddyval.log
  sudo cp "/etc/caddy/Caddyfile.bak-$TS" "$LIVE"
  cp "/opt/fleet-api/caddyfile.template.bak-$TS" "$TMPL"
  exit 4
fi
echo "  valid"

echo "--- reload caddy ---"
sudo systemctl reload caddy
sleep 1
echo "  caddy: $(systemctl is-active caddy)"

echo "--- verify routes still serve (regression) ---"
curl -s -o /dev/null -w "  /healthz       HTTP %{http_code}\n" https://hq.cafreso.com/healthz
curl -s -o /dev/null -w "  /fleet/health  HTTP %{http_code}\n" https://hq.cafreso.com/fleet/health
echo "--- verify NEW /stripe route (through Caddy, public HTTPS) ---"
curl -s -w "  -> HTTP %{http_code}\n" https://hq.cafreso.com/stripe/health
echo "--- confirm /stripe is NOT on plain :80 (expect not 200) ---"
curl -s -o /dev/null -w "  http://127.0.0.1/stripe/health  HTTP %{http_code}\n" http://127.0.0.1/stripe/health
REMOTE
rc=$?
echo "===== stage2 exit $rc ====="
exit $rc
