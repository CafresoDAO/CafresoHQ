#!/usr/bin/env bash
# Stage 1: stand up the Stripe oracle Node service on the gateway VM, isolated
# from Caddy (no gateway change). Installs Node 20 if missing, deploys files,
# npm install, systemd unit, starts it INERT (no Stripe secrets yet), verifies
# localhost:8788/health.
set -uo pipefail
KEY=/home/anthony/.ssh/cafreso_tls_gateway
VM=ubuntu@129.80.230.53
SRC=/mnt/c/Users/Anthony/Desktop/CafresoHQHermez/oci-fleet/stripe-oracle
SSHOPT=(-i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)

echo "===== uploading oracle files to /tmp on VM ====="
scp "${SSHOPT[@]}" \
  "$SRC/server.js" "$SRC/package.json" "$SRC/print-principal.mjs" \
  "$SRC/stripe-oracle.service" "$SRC/stripe-oracle.env.example" \
  "$VM:/tmp/" || { echo "SCP FAILED"; exit 1; }

echo "===== remote setup ====="
ssh "${SSHOPT[@]}" "$VM" 'bash -s' <<'REMOTE'
set -uo pipefail
echo "--- node check ---"
if ! command -v node >/dev/null 2>&1; then
  echo "node not found — installing Node 20 (NodeSource)…"
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - >/tmp/nodesource.log 2>&1 \
    || { echo "NodeSource setup failed"; tail -20 /tmp/nodesource.log; exit 1; }
  sudo apt-get install -y nodejs >/tmp/nodeinstall.log 2>&1 \
    || { echo "apt install nodejs failed"; tail -20 /tmp/nodeinstall.log; exit 1; }
fi
echo "node: $(node --version)   npm: $(npm --version)"

echo "--- deploy files to /opt/stripe-oracle ---"
sudo mkdir -p /opt/stripe-oracle
sudo cp /tmp/server.js /tmp/package.json /tmp/print-principal.mjs /opt/stripe-oracle/
sudo chown -R ubuntu:ubuntu /opt/stripe-oracle

echo "--- npm install (prod deps only) ---"
cd /opt/stripe-oracle
npm install --omit=dev --no-audit --no-fund >/tmp/npm-oracle.log 2>&1 \
  || { echo "npm install FAILED"; tail -30 /tmp/npm-oracle.log; exit 1; }
echo "installed $(ls node_modules/@dfinity 2>/dev/null | tr '\n' ' ')"

echo "--- import smoke test (does @dfinity load + identity derive?) ---"
node -e "import('@dfinity/identity').then(m=>{const id=m.Ed25519KeyIdentity.generate(new Uint8Array(32));console.log('identity OK', id.getPrincipal().toText());}).catch(e=>{console.error('IMPORT FAIL',e);process.exit(1);})" \
  || { echo "import smoke FAILED"; exit 1; }

echo "--- ensure /etc/cafresoai exists + env stub (inert until secrets added) ---"
sudo mkdir -p /etc/cafresoai
if [ ! -f /etc/cafresoai/stripe-oracle.env ]; then
  sudo install -m 600 -o root -g root /tmp/stripe-oracle.env.example /etc/cafresoai/stripe-oracle.env
  echo "created /etc/cafresoai/stripe-oracle.env (empty secrets)"
else
  echo "/etc/cafresoai/stripe-oracle.env already exists — left as-is"
fi

echo "--- systemd unit ---"
sudo cp /tmp/stripe-oracle.service /etc/systemd/system/stripe-oracle.service
sudo systemctl daemon-reload
sudo systemctl enable stripe-oracle >/dev/null 2>&1
sudo systemctl restart stripe-oracle
sleep 2
echo "service state: $(systemctl is-active stripe-oracle)"

echo "--- liveness probe (localhost:8788) ---"
curl -s -o /dev/null -w "health HTTP %{http_code}\n" http://127.0.0.1:8788/health
echo "session-without-config (expect 503):"
curl -s -X POST http://127.0.0.1:8788/session -H 'Content-Type: application/json' \
  -d '{"metadata":{"plan":"cafresohq-pro","icOrderId":"1"}}' -w "  (HTTP %{http_code})\n"

echo "--- recent journal ---"
sudo journalctl -u stripe-oracle --no-pager -n 8 2>/dev/null | sed 's/^/  /'
REMOTE
rc=$?
echo "===== stage1 exit $rc ====="
exit $rc
