# Pre-Launch TODO (pinned)

Deferred hardening/wiring before public launch. None block the current private
beta; the security model (container auth Phase A+B) + ICP billing are live.

1. **Gate `/fleet/provision`** — currently dev-mode/open; anyone could spam
   container creation (A1 pool abuse). Require a session token or rate-limit.
   *(Largest open surface.)*
2. **Set `FLEET_API_SECRET`** on the gateway — activates the admin override path
   and locks the legacy `set-plan`. (Secure plan-token path already works without it.)
3. **Stripe → `confirmOrder`** — card payments need the Stripe Worker to confirm
   the order on-chain so `mintPlanToken` accepts them (ICP works today).
4. **Enable `reap-idle` cron** — the profitability lever (stop idle containers).
   Left off until auto-restart-on-access is verified so users aren't stranded.
5. **`fleet.json` → real DB** — local/gateway copies diverged once (reconciled);
   a datastore prevents recurrence + race conditions.
6. **Rotate keys** pasted in earlier chat (OpenRouter `sk-or-v1-…`, Groq `gsk_…`).
