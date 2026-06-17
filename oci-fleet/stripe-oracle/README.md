# CafresoHQ Stripe Oracle (self-hosted on the gateway VM)

Card money lives off-chain in Stripe, so the order canister (`bek5d`) can't
observe a card payment directly. This service is the trusted **oracle**: it
verifies Stripe's signed webhook and calls `confirmCardOrder` on-chain. It only
**confirms** orders — it never moves crypto. Worst case if the oracle key leaks
is *free plans*, never theft.

This is the self-hosted twin of `docs/stripe-worker.js` (a Cloudflare Worker).
We run it on the OCI gateway VM so there's no extra vendor/login. The money
logic is identical and was adversarially reviewed; only the runtime shell
differs (Node `http.createServer` adapter instead of the Workers runtime).

## Where it runs

```
Browser (ai.cafreso.com) ─POST /stripe/session─┐
Stripe servers ───────────POST /stripe/webhook─┤
                                               ▼
        Caddy on hq.cafreso.com  (handle_path /stripe/*  → strips prefix)
                                               ▼
        stripe-oracle.service  →  node server.js  →  127.0.0.1:8788
                                               ▼
                         @dfinity/agent → bek5d.confirmCardOrder  (mainnet)
```

- **Service:** `/opt/stripe-oracle/` · systemd unit `stripe-oracle.service` · port `127.0.0.1:8788`.
- **Runtime:** Node 20 (NodeSource). Isolated from `fleet-api` — a payment hiccup can't take down the gateway.
- **Secrets:** `/etc/cafresoai/stripe-oracle.env` (root, mode 600). Inert until `STRIPE_SECRET_KEY` is set.
- **Caddy route:** lives in the **static** section of `caddyfile.template` (above `__USER_ROUTES__`), so `fleet-manager.py caddy-sync` preserves it.

Public paths (HTTPS only; deliberately not on `:80`):

| path | →service | who calls it |
|---|---|---|
| `POST https://hq.cafreso.com/stripe/session` | `/session` | the browser |
| `POST https://hq.cafreso.com/stripe/webhook` | `/webhook` | Stripe |
| `GET  https://hq.cafreso.com/stripe/health`  | `/health`  | liveness |

## Deploy / redeploy

From the Hermez repo (WSL, gateway SSH key):

```
bash scripts/deploy-oracle-stage1.sh   # node + service files + npm + start (inert)
bash scripts/deploy-oracle-stage2.sh   # caddy /stripe route (backup + validate + reload)
```

Both are idempotent. To push only a code change to `server.js`, re-run stage 1.

## Go-live checklist

**Status:** service is **deployed + live + inert** (returns 503 on `/session`
until configured). Frontend keeps `PUBLIC_CARD_PAYMENTS=off`, so no card button
shows yet. Canister card methods (`confirmCardOrder`, `setOraclePrincipal`,
`createCardOrder`) are written + compile but are **not yet deployed** to `bek5d`.

### You (external — just Stripe, nothing else)
1. Create a Stripe account; grab the **test** secret key (`sk_test_…`).
2. Stripe → Developers → Webhooks → Add endpoint:
   - URL: `https://hq.cafreso.com/stripe/webhook`
   - Event: `checkout.session.completed`
   - Copy the signing secret (`whsec_…`).
3. Send me the `sk_test_…` and `whsec_…` (or paste them straight into
   `/etc/cafresoai/stripe-oracle.env` on the VM yourself and `sudo systemctl
   restart stripe-oracle`).

### Me (on-chain + config — gated on the two Stripe values)
4. Generate the oracle Ed25519 seed on the VM, store it in the env file, derive
   its principal (`print-principal.mjs`).
5. Deploy `bek5d` card methods (identity `xip3r_legacy`, dfx 0.32).
6. `setOraclePrincipal(<derived principal>)` on `bek5d`. (Plan prices
   `$9 / $29` are already set on-chain from the ICP path.)
7. `PUBLIC_STRIPE_WORKER_URL=https://hq.cafreso.com/stripe/session`, redeploy
   frontend.
8. Test-mode end-to-end with card `4242 4242 4242 4242`: order flips to `paid`
   on-chain, plan applies. Then flip `PUBLIC_CARD_PAYMENTS=on` and switch the
   Stripe key to `sk_live_…`.
