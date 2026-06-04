# Per-Container Authentication — Security Design

> **Status:** IMPLEMENTED (canister-minted token), pending go-live deploy.
> Code is merged + crypto-verified; flip it on with `oci-fleet/DEPLOY_AUTH.md`.
> **Goal:** gate every `https://hq.cafreso.com/u/<slug>/*` request so only the
> Internet Identity that owns the container can reach it.
>
> **Chosen mechanism (resolves §3): canister-minted HMAC token.** Ownership is
> proven natively by the IC — the signed-in user calls `mintHqSession()` on the
> `cafresoai_keys` canister, which (since `msg.caller` is the unforgeable II
> principal) HMAC-signs `v1.<principal>.<exp>` with a secret shared only with the
> gateway. The shell installs that token as an `HttpOnly; Secure; SameSite=None`
> cookie via `POST /fleet/session`; Caddy `forward_auth` → `verifier.py` (:9090)
> re-checks the HMAC + `exp` and that `sha256(principal)[:16] == slug` before
> proxying. No Node sidecar, no secret in the browser, no delegation-chain
> verification needed on the server. Crypto verified against FIPS/RFC vectors.
>
> Components shipped: `src/cafresoai_keys/Sha256.mo` (vendored SHA-256/HMAC),
> `mintHqSession`/`setHqSessionSecret` in the keys canister, `oci-fleet/hq_token.py`,
> `oci-fleet/verifier.py` (+`verifier.service`), `POST /fleet/session` in fleet-api,
> `forward_auth` in both Caddy renderers, `frontend/src/lib/api/hqSession.js`
> wired into the HQ app page.

---

## 1. The vulnerability (confirmed)

Anonymous, unauthenticated requests succeed against any container:

| Request (no auth, no II) | Result |
|---|---|
| `GET /u/<slug>/hq.html` | 200 — full app loads |
| `GET /u/<slug>/vault/list` | 200 — vault API responds |
| `GET /u/<slug>/hermes/v1/models` | 200 — agent API (terminal-capable) reachable |

**Root cause:** authentication lives entirely in the ai.cafreso.com SvelteKit
shell (II login gates the *UI*). The Caddy gateway does a bare
`handle_path /u/<slug>/* → reverse_proxy container:8787` with **no auth check**,
and the slug is `sha256(principal)[:16]` — derived from the *public* principal,
so it is **guessable/derivable, not secret**. Net: security-through-obscurity.

**Impact:** vault contents (once populated), the Hermes agent API (which can run
terminal commands in the user's container), and the per-principal
`API_SERVER_KEY`-backed surface are all exposed to the public internet.

---

## 2. Chosen approach — II-bound signed token + Caddy `forward_auth`

The frontend already authenticates with Internet Identity (`@dfinity/auth-client`,
30-day delegation, ecosystem-shared principal via `derivationOrigin`). We bind the
container to that identity:

```
┌─ ai.cafreso.com (SvelteKit, II login) ─┐
│  After II login, mint a short-lived     │
│  session token bound to the principal   │
└──────────────┬──────────────────────────┘
               │  token (cookie or Authorization header)
               ▼
┌─ hq.cafreso.com (Caddy gateway) ────────┐
│  handle /u/<slug>/* {                    │
│    forward_auth verifier:9090 {          │
│      uri /verify?slug=<slug>             │
│      copy_headers ...                    │
│    }                                     │
│    reverse_proxy container:8787          │
│  }                                       │
└──────────────┬──────────────────────────┘
               │  (only if verifier returns 2xx)
               ▼            container serve.py :8787
```

### Token design
- **Mint:** after II `login()` succeeds, frontend calls the fleet API
  (`POST /fleet/session`) presenting a **signed assertion of its principal**
  (see §3 on proving principal ownership). Fleet API returns a token:
  - `JWT` (HS256) or signed cookie, claims: `sub=<principal>`, `slug=<slug>`,
    `iat`, `exp` (short — e.g. 15 min), `aud=hq.cafreso.com`.
  - Signed with a server-side secret (`FLEET_SESSION_SECRET`, env, never shipped).
- **Carry:** set as an `HttpOnly; Secure; SameSite=None` cookie scoped to
  `hq.cafreso.com` (so the iframe to `/u/<slug>/*` sends it automatically), OR
  an `Authorization: Bearer` header on fetches (iframe can't set headers → cookie
  is required for the embedded-app case).
- **Verify:** Caddy `forward_auth` → verifier service validates signature, `exp`,
  and that the token's `slug`/`sub` matches the requested `/u/<slug>/`.
  Mismatch or missing → 401/403, request never reaches the container.
- **Refresh:** frontend re-mints before `exp` using the still-valid II delegation.

### Why cookie (not just bearer)
The HQ app loads in an **iframe** (`routes/hq/app/+page.svelte` →
`<iframe src={endpoint}/hq.html>`). Iframe sub-requests can't carry custom
Authorization headers, but **do** send cookies for `hq.cafreso.com`. So the
container session must be a cookie on the gateway origin.

---

## 3. Proving principal ownership (the hard part)

The mint step must verify the caller actually controls the principal — not just
claims it. Options, strongest first:

1. **II delegation verification (correct):** frontend sends its II delegation
   chain; the fleet API verifies the chain cryptographically (via
   `@dfinity/identity` server-side or the IC verification logic) and extracts the
   principal. Guarantees the caller holds the II session.
2. **Canister-attested challenge:** frontend signs a nonce with its II identity;
   server verifies the signature against the principal’s public key.
3. **Interim/weaker:** trust the authenticated XHR from the shell origin +
   `FLEET_API_SECRET`. Stops anonymous URL access but not a determined attacker
   who can call the fleet API. Acceptable only as a stepping stone.

> The slug alone must **never** be the credential — it's derived from the public
> principal. The token (signed, expiring, ownership-proven) is the credential.

---

## 4. Components to build

| Component | Change |
|---|---|
| **Verifier service** | New small HTTP service on the gateway VM (`:9090`). `GET /verify?slug=` → reads the session cookie, validates JWT signature/exp, checks `slug` claim matches. 200/401. Stateless. |
| **Caddy template** | `oci-fleet/caddyfile.template`: wrap each `handle_path /u/<slug>/*` with `forward_auth localhost:9090`. Re-rendered by `fleet-manager.py` / `fleet-api.py` `_render_caddyfile`. |
| **Fleet API** | `oci-fleet/fleet-api.py`: add `POST /fleet/session` (verify principal per §3, mint JWT, `Set-Cookie`). Add `FLEET_SESSION_SECRET`. |
| **Frontend** | After II login (`auth.js`), call `/fleet/session`; on 401 from container, re-mint. `endpoint.js` / `ProvisionPanel` flow unchanged otherwise. |
| **serve.py (defense-in-depth)** | Optional: also require a header/cookie inside the container so a gateway bypass (direct container IP) still fails. Container public IP `:8787` is currently open too — see §5. |

---

## 5. Also close: direct container IP exposure — DONE (Phase B)

The container had a **public IP** serving `:8787` directly, bypassing the gateway
(`http://<container-ip>:8787/hq.html` was open even with gateway auth).

**Fixed (network, no container recreate):**
- Gateway and containers share the VCN (gateway subnet `10.0.1.0/24`, container
  subnet `10.0.0.0/24`). Caddy now proxies to each container's **private** IP
  (`fleet.json.private_ip`; renderers prefer it — fleet-manager + fleet-api).
- The container subnet's security list rule for `:8787` was changed from
  `0.0.0.0/0` → `10.0.1.0/24`, so only the gateway subnet can reach `:8787`.
  Verified: public internet → `:8787` now times out (000); gateway → private IP
  still 200; HQ serves. Containers are also isolated from each other on `:8787`.

**Remaining (optional, deeper defense-in-depth — needs container recreate):**
- serve.py could additionally require a gateway-injected `X-Gateway-Auth` secret
  header so even an in-VCN attacker can't hit `:8787`. Code path noted; deferred
  because applying it to live containers needs a recreate.
- SSH `:22` on the container subnet is still `0.0.0.0/0` (separate hardening).

---

## 6. Rollout (when beta opens up)

1. Add `FLEET_SESSION_SECRET` to gateway env; deploy verifier service (systemd).
2. Add `POST /fleet/session` to fleet-api.py; keep old open routes during cutover.
3. Update `caddyfile.template` with `forward_auth`; `caddy-sync`; verify a valid
   session passes and anonymous gets 401.
4. Frontend: mint-on-login + refresh; redeploy `cafresoai_frontend`.
5. Lock the container network path (§5): NSG to gateway-only, drop public IP.
6. Remove any interim open-access allowances.

---

## 7. Threat model summary

| Threat | Before | After |
|---|---|---|
| Anonymous reads vault/agent via guessed slug | **open** | blocked (no valid token) |
| Attacker derives slug from public principal | **open** | blocked (slug ≠ credential) |
| Direct container-IP access bypassing gateway | **open** | blocked (§5 NSG + app check) |
| Stolen short-lived token | n/a | limited blast radius (≤ exp; revocable via secret rotation) |
| XSS on shell steals token | n/a | mitigated by `HttpOnly` cookie |
