# Deploy tonight — final ops to a public-beta-ready CafresoHQ

The build work is done and live; what's left is **deployment/ops**. This is the ordered
checklist. Most of it is gated on regaining access to the Caddy gateway VM
(`hq.cafreso.com`) — but several items need **no gateway** and can be done first/in parallel.

Source of the gaps: the multi-agent dapp assessment (2026-06-24). Detailed auth steps live in
[`oci-fleet/DEPLOY_AUTH.md`](../oci-fleet/DEPLOY_AUTH.md); design in `oci-fleet/CONTAINER_AUTH_DESIGN.md`.

---

## A. No gateway needed — do these first (≈30–60 min)

- [ ] **Push the rebuilt container image** (already built + smoke-tested healthy locally, tagged):
  ```bash
  docker push docker.io/anthonycf1/cafresoai-serve:renamed-20260624
  docker push docker.io/anthonycf1/cafresoai-serve:latest
  ```
  (Carries the CafresoHQ rename onto the compute side. The env shim already bridges running containers.)

- [ ] **Rotate the leaked LLM keys** (LAUNCH_TODO #6 — pasted in chat, not in git, but live):
  - OpenRouter `sk-or-v1-…` → revoke at openrouter.ai/keys, issue new.
  - Groq `gsk_…` → revoke at console.groq.com/keys, issue new.
  - Update wherever they're set (fleet env / `oci-fleet/.env` / container secrets). With BYO-key default, prefer per-user keys.

- [ ] **Make "one login, every app" real** — populate `/.well-known/ii-alternative-origins` on the
  Banking.Brave anchor canister (`cqyto-tiaaa-aaaau-agppa-cai`) with every ecosystem domain
  (`https://cafreso.com`, `https://ai.cafreso.com`, `https://minegold.defi`, …), then redeploy `cqyto`.
  Until this lists the custom domains, the ecosystem-shared principal silently falls back per-origin.

---

## B. Gateway VM required — the security close (the big one)

### B0. Regain access to the gateway VM
- [ ] Recover `hq.cafreso.com` via **OCI serial console** (reset SSH key / add a new authorized key), **or**
- [ ] Rebuild the gateway from [`oci-fleet/caddy-cloud-init.yaml`](../oci-fleet/caddy-cloud-init.yaml)
  (re-provision the instance; DNS A-record `hq.cafreso.com` → new IP; re-issue Let's Encrypt).
  > Record the new IP / SSH key in `oci-fleet/.env` (`GATEWAY_IP`, `GATEWAY_SSH_KEY`) — never commit them.

### B1–B4. Deploy container auth (closes the open-container hole)
Follow [`oci-fleet/DEPLOY_AUTH.md`](../oci-fleet/DEPLOY_AUTH.md) in order — summary:
- [ ] **Secret:** `openssl rand -hex 32` → use the SAME value below.
- [ ] **Canister:** `dfx deploy cafresohq_keys --network ic` → `setHqSessionSecret('<SECRET>')` → `hqSessionConfigured` returns `(true)`.
- [ ] **Gateway:** write `/etc/cafresoai/hq.env` (`HQ_SESSION_SECRET` + existing `FLEET_API_SECRET`), deploy `oci-fleet/` to `/opt/cafresoai/oci-fleet`, `systemctl enable --now verifier`, add `EnvironmentFile=/etc/cafresoai/hq.env` to fleet-api + restart.
- [ ] **Caddy:** `python oci-fleet/fleet-manager.py caddy-sync --host hq.cafreso.com` (adds `forward_auth`). Verify anonymous `/u/<slug>/hq.html` → **401** (was 200); `/health` still open.
- [ ] **Frontend:** `npm --prefix frontend run build` → `dfx deploy cafresohq_frontend --network ic`. Sign in at ai.cafreso.com/hq/app → token mints, cookie installs, iframe loads.
- [ ] **Set `FLEET_API_SECRET`** on the gateway so the fleet-api fail-closed gate (already shipped) actually authenticates admin routes.

### B5. Phase B — close the container network bypass
- [ ] OCI NSG/security-list: allow container `:8787` only from the gateway private IP; drop the container public IP (`is_public_ip_assigned=False` in fleet-manager).
- [ ] serve.py defense-in-depth: require the gateway-injected `X-Hq-Principal` (+ shared header) on sensitive routes (`/vault`, `/hermes`, `/terminal`, `/cafresohq`, `/agents`). *(Verify whether serve.py already enforces this; the assessment flagged it as not visible.)*

---

## C. Close the money loop (1–2 wks, mostly post-gateway)

- [ ] **Meter usage:** replace the spoofable `X-User-Principal` header on `/fleet/*` with the on-chain
  session-token-derived principal; aggregate `hermes-usage.log` into a real sink (OCI Autonomous DB or
  the IndexCanister) and surface it in a `/usage` endpoint + billing UI.
- [ ] **Quota gates:** enforce free-tier caps (tokens / active-hours) before provisioning; `cafresohq_state`
  already enforces vault-byte quotas per plan.
- [ ] **Idle auto-reap:** wire `reap-idle` (LAUNCH_TODO #4) to stop idle containers + start-on-login —
  now safe to validate against the Phase-2 stateless state. Highest-leverage cost control (≈8× reduction).

---

## D. Make the product claim real (parallel track)

- [ ] **One live agent loop:** replace ONE mock agent path (`mock-data.jsx` `agentStream`) with a real
  end-to-end run — user task → real Claude call → result persisted to the vetKeys vault — to back the
  "agent command center" thesis before scaling the UI. Until then, either expose the real HQ UI in the
  ecosystem-nav iframe or hide the "HQ" link so it isn't a dead end.

---

### Order of operations tonight
1. **A** (no gateway) — push image, rotate keys, fill ii-alternative-origins.
2. **B0** — get into the VM.
3. **B1–B4** — deploy container auth (the single biggest security win), in the exact order in `DEPLOY_AUTH.md`.
4. **B5 / C / D** — schedule across the next 1–2 weeks.

Done with A + B = safe to open a public beta.
