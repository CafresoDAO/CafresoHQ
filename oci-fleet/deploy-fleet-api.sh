#!/usr/bin/env bash
# ── Deploy fleet-api.py to the CafresoAI TLS gateway VM ─────────────────────
# Run from Windows via WSL:
#   wsl -d Ubuntu-24.04 -- bash -lc "bash /mnt/c/Users/Anthony/Documents/CafresoHQ/oci-fleet/deploy-fleet-api.sh"
#
# Prerequisites:
#   - Gateway VM SSH key at ~/.ssh/cafreso_tls_gateway (or /mnt/c/Users/Anthony/.ssh/...)
#   - OCI config at ~/.oci/config + key file
#   - fleet.json with gateway info
set -euo pipefail

GATEWAY_IP="129.80.230.53"
SSH_USER="ubuntu"
SSH_KEY_WIN="/mnt/c/Users/Anthony/.ssh/cafreso_tls_gateway"
SSH_KEY="/tmp/_deploy_gw_key"
FLEET_DIR="/mnt/c/Users/Anthony/Documents/CafresoHQ/oci-fleet"
OCI_CONFIG="/mnt/c/Users/Anthony/.oci/config"
OCI_KEY="/mnt/c/Users/Anthony/.oci/oci_api_key.pem"

# Copy SSH key with correct perms
cp "$SSH_KEY_WIN" "$SSH_KEY"
chmod 600 "$SSH_KEY"

SSH_CMD="ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
SCP_CMD="scp -i $SSH_KEY -o StrictHostKeyChecking=accept-new"

echo "═══ CafresoAI Fleet API Deployment ═══"
echo "  Target: $SSH_USER@$GATEWAY_IP"
echo ""

# ── 1. Install pip + OCI SDK ─────────────────────────────────────────────────
echo "1/5  Installing pip + OCI Python SDK on gateway..."
$SSH_CMD $SSH_USER@$GATEWAY_IP bash -s <<'REMOTE_INSTALL'
set -e
if ! command -v pip3 &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3-pip python3-venv
fi

# Use a venv so we don't pollute system Python
if [ ! -d /opt/fleet-api/venv ]; then
    sudo mkdir -p /opt/fleet-api
    sudo chown ubuntu:ubuntu /opt/fleet-api
    python3 -m venv /opt/fleet-api/venv
fi

# Install OCI SDK in the venv
/opt/fleet-api/venv/bin/pip install --quiet oci
echo "  OCI SDK installed: $(/opt/fleet-api/venv/bin/python3 -c 'import oci; print(oci.__version__)')"
REMOTE_INSTALL
echo "  done."

# ── 2. Copy fleet files ─────────────────────────────────────────────────────
echo ""
echo "2/5  Uploading fleet files..."
$SCP_CMD "$FLEET_DIR/fleet-api.py" $SSH_USER@$GATEWAY_IP:/opt/fleet-api/fleet-api.py
$SCP_CMD "$FLEET_DIR/fleet-manager.py" $SSH_USER@$GATEWAY_IP:/opt/fleet-api/fleet-manager.py
$SCP_CMD "$FLEET_DIR/fleet.json" $SSH_USER@$GATEWAY_IP:/opt/fleet-api/fleet.json
$SCP_CMD "$FLEET_DIR/caddyfile.template" $SSH_USER@$GATEWAY_IP:/opt/fleet-api/caddyfile.template
echo "  done."

# ── 3. Copy OCI credentials ─────────────────────────────────────────────────
echo ""
echo "3/5  Uploading OCI credentials..."
$SSH_CMD $SSH_USER@$GATEWAY_IP "mkdir -p ~/.oci && chmod 700 ~/.oci"
$SCP_CMD "$OCI_CONFIG" $SSH_USER@$GATEWAY_IP:~/.oci/config
$SCP_CMD "$OCI_KEY" $SSH_USER@$GATEWAY_IP:~/.oci/oci_api_key.pem
$SSH_CMD $SSH_USER@$GATEWAY_IP "chmod 600 ~/.oci/config ~/.oci/oci_api_key.pem"

# Fix the key_file path in the config (Windows path → Linux path)
$SSH_CMD $SSH_USER@$GATEWAY_IP "sed -i 's|key_file.*=.*|key_file = ~/.oci/oci_api_key.pem|' ~/.oci/config"
echo "  done."

# ── 3b. Copy Docker/OCIR credentials (for container image pull secrets) ─────
echo ""
echo "3b/5  Copying OCIR pull credentials..."
# Read from WSL's Docker config (where ocir-login writes)
DOCKER_CFG=$(wsl -d Ubuntu-24.04 -- cat /home/anthony/.docker/config.json 2>/dev/null || echo "")
if [ -n "$DOCKER_CFG" ]; then
    echo "$DOCKER_CFG" | $SSH_CMD $SSH_USER@$GATEWAY_IP "mkdir -p ~/.docker && cat > ~/.docker/config.json && chmod 600 ~/.docker/config.json"
    echo "  OCIR credentials copied."
else
    echo "  WARNING: No Docker config found in WSL — OCIR pull secrets won't work."
    echo "  Run 'python oci-fleet/fleet-manager.py ocir-login' first."
fi

# ── 3c. Grant ubuntu user NOPASSWD sudo for Caddyfile updates ───────────────
echo ""
echo "3c/5  Granting ubuntu NOPASSWD sudo for Caddyfile + reload..."
$SSH_CMD $SSH_USER@$GATEWAY_IP sudo bash -s <<'REMOTE_SUDO'
cat > /etc/sudoers.d/cafresoai-fleet-api <<EOF
# Allows fleet-api.py to re-render the Caddyfile when a new user is provisioned
# without prompting. Only specific commands — not blanket sudo.
ubuntu ALL=(root) NOPASSWD: /usr/bin/cp /tmp/cafresoai_Caddyfile.new /etc/caddy/Caddyfile
ubuntu ALL=(root) NOPASSWD: /usr/bin/systemctl reload caddy
ubuntu ALL=(root) NOPASSWD: /usr/sbin/caddy validate --config /tmp/cafresoai_Caddyfile.new
EOF
chmod 440 /etc/sudoers.d/cafresoai-fleet-api
visudo -c -f /etc/sudoers.d/cafresoai-fleet-api && echo "  sudoers entry valid"
REMOTE_SUDO
echo "  done."

# ── 4. Create systemd service ───────────────────────────────────────────────
echo ""
echo "4/5  Creating systemd service..."
$SSH_CMD $SSH_USER@$GATEWAY_IP sudo bash -s <<'REMOTE_SERVICE'
cat > /etc/systemd/system/fleet-api.service <<EOF
[Unit]
Description=CafresoAI Fleet API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/fleet-api
ExecStart=/opt/fleet-api/venv/bin/python3 /opt/fleet-api/fleet-api.py
Restart=on-failure
RestartSec=5
Environment=FLEET_API_PORT=8080
Environment=FLEET_API_SECRET=
Environment=FLEET_API_ALLOWED_ORIGINS=http://localhost:5174,http://127.0.0.1:5174,https://v4tdv-riaaa-aaaab-agtfa-cai.icp0.io,https://ai.cafreso.com,https://cafreso.com,http://129.80.230.53
Environment=PYTHONUTF8=1
StandardOutput=journal
StandardError=journal
SyslogIdentifier=fleet-api

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable fleet-api
systemctl restart fleet-api
sleep 2
systemctl is-active fleet-api && echo "  fleet-api is ACTIVE" || echo "  fleet-api FAILED to start"
REMOTE_SERVICE
echo "  done."

# ── 5. Update Caddy to route /fleet/* ────────────────────────────────────────
echo ""
echo "5/5  Updating Caddyfile with fleet API routes..."
# Re-render Caddyfile from the local template + fleet.json
# (The template now includes /fleet/* -> localhost:8080 routes)
# We do a quick manual render here since fleet-manager.py caddy-sync
# expects Windows paths
$SSH_CMD $SSH_USER@$GATEWAY_IP bash -s <<'REMOTE_CADDY'
# Read the current Caddyfile and check if /fleet/* route already exists
if grep -q 'reverse_proxy localhost:8080' /etc/caddy/Caddyfile; then
    echo "  Fleet API route already in Caddyfile — skipping"
else
    # Insert the fleet API route before the "no route" fallback in both blocks
    sudo sed -i '/respond "no route/i\    # Fleet API — self-service provisioning\n    handle /fleet/* {\n        reverse_proxy localhost:8080\n    }\n' /etc/caddy/Caddyfile
    sudo sed -i '/respond 404/i\    # Fleet API — self-service provisioning\n    handle /fleet/* {\n        reverse_proxy localhost:8080\n    }\n' /etc/caddy/Caddyfile
    sudo caddy validate --config /etc/caddy/Caddyfile && echo "  Caddyfile valid" || echo "  Caddyfile INVALID"
    sudo systemctl reload caddy
    echo "  Caddy reloaded with fleet API routes"
fi
REMOTE_CADDY
echo "  done."

# ── Verify ──────────────────────────────────────────────────────────────────
echo ""
echo "═══ Verification ═══"
echo "  Testing fleet API health via gateway..."
HEALTH=$(curl -sf --max-time 5 "http://$GATEWAY_IP/fleet/health" 2>/dev/null || echo "FAILED")
echo "  Response: $HEALTH"
echo ""
echo "  Fleet API is now reachable at:"
echo "    http://$GATEWAY_IP/fleet/health"
echo "    https://hq.cafreso.com/fleet/health  (once DNS is set)"
echo ""
echo "  Next steps:"
echo "    1. Set DNS:  hq.cafreso.com  A  $GATEWAY_IP"
echo "    2. Update SvelteKit fleetClient.js default URL"
echo "    3. Set FLEET_API_SECRET for production auth"

rm -f "$SSH_KEY"
