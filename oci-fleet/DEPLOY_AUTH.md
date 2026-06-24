# Container Auth — Go-Live Runbook

Closes the open-container hole: every `https://hq.cafreso.com/u/<slug>/*` request
(except `/health`) now requires an HQ session cookie whose token was minted
**on-chain** for the signed-in principal. See `docs/CONTAINER_AUTH_DESIGN.md` for
the design; this is the ordered deploy.

> **Ordering matters.** The frontend blocks the iframe for gateway endpoints until
> a session is installed. So the canister secret + gateway env must be in place
> *before* the new frontend is the only way in. Follow the order below.

## 0. Generate the shared secret (once)

```bash
openssl rand -hex 32        # → SECRET (64 hex chars / 32 bytes)
```

Use the SAME value in steps 1 and 2.

## 1. Canister: deploy + set the secret

The upgrade only ADDS methods (`mintHqSession`, `setHqSessionSecret`,
`hqSessionConfigured`) and an empty stable var — non-breaking.

```bash
# from repo root, WSL (deploy identity tzw3r-… is a controller + allowed setter)
dfx deploy cafresohq_keys --network ic
dfx canister call cafresohq_keys setHqSessionSecret '("<SECRET>")' --network ic
dfx canister call cafresohq_keys hqSessionConfigured --network ic    # → (true)
```

## 2. Gateway VM: env + verifier service

```bash
sudo mkdir -p /etc/cafresoai
sudo tee /etc/cafresoai/hq.env >/dev/null <<EOF
HQ_SESSION_SECRET=<SECRET>
FLEET_API_SECRET=<existing fleet secret>
EOF
sudo chmod 600 /etc/cafresoai/hq.env

# deploy code (oci-fleet/) to /opt/cafresoai/oci-fleet, then:
sudo cp /opt/cafresoai/oci-fleet/verifier.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now verifier
curl -s localhost:9090/health        # → ok

# fleet-api must ALSO have HQ_SESSION_SECRET (it validates /fleet/session).
# Add EnvironmentFile=/etc/cafresoai/hq.env to its unit, then:
sudo systemctl restart fleet-api
```

## 3. Caddy: re-render with forward_auth

```bash
# from repo root, WSL — pushes the new auth-gated Caddyfile to the gateway
python oci-fleet/fleet-manager.py caddy-sync --host hq.cafreso.com
```

Verify (replace <slug>):

```bash
# anonymous → 401 now (was 200)
curl -s -o /dev/null -w '%{http_code}\n' https://hq.cafreso.com/u/<slug>/hq.html
# health still open
curl -s https://hq.cafreso.com/u/<slug>/health
```

## 4. Frontend: redeploy the shell

```bash
npm --prefix frontend run build
dfx deploy cafresohq_frontend --network ic
```

Sign in at https://ai.cafreso.com/hq/app → the shell mints a token, installs the
cookie, and the iframe loads. Anonymous/other-principal access 401s.

## 5. (Phase B) Lock the container network path

The container still has a public IP on :8787 (bypasses the gateway). Close it:
- OCI NSG/security-list: allow `:8787` only from the gateway private IP; drop the
  container's public IP (`is_public_ip_assigned=False` in fleet-manager).
- serve.py defense-in-depth: require the gateway-injected `X-Hq-Principal` +
  a gateway-shared header before serving sensitive routes.

## Rollback

- Revert the Caddyfile (`git checkout` the template, re-run caddy-sync) → routes
  open again.
- Or `dfx canister call cafresohq_keys setHqSessionSecret '("")'` is NOT allowed
  (min length); instead stop `verifier` and remove forward_auth to fully open.
