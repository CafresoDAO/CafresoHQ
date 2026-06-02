# CafresoHQ — SaaS MVP & Profitability Plan

> Goal: ship the smallest thing that's a real paid SaaS **and profitable from day
> one**. The economics are already in our favor — this doc locks the model and the
> last engineering steps to get there.

---

## 1. Why this is profitable off the jump (the structural edge)

Two decisions we already shipped make the margin work before we write a billing line:

1. **BYO-key (OpenRouter default).** The LLM cost — normally the killer variable
   cost of any AI SaaS — is **$0 to us.** The user brings their own free key.
2. **Idle auto-stop (`reap-idle` + `/idle`, just shipped).** Compute is billed per
   OCPU-hour and **stopped containers cost $0 and free the pool.** A mostly-idle
   user costs cents, not $14.

So our **only real cost per user is active container-hours.** Price a flat monthly
fee above that, and every plan is gross-margin positive by construction.

### Unit economics (per paying user / month)
| Item | Cost to us |
|---|---|
| LLM tokens | **$0** (BYO OpenRouter key) |
| Container compute, ~2 active hrs/day w/ idle-stop | ~$1.20 |
| Object storage (vault, capped) | ~$0.05 |
| Gateway/LB/egress (amortized) | ~$0.10 |
| **Total COGS** | **≈ $1.40 / user / mo** |

At **$9/mo** that's an **~84% gross margin** before scale discounts. Even a
heavy/always-on user (~$14 compute) is break-even at $14 and we'd put them on a
higher tier. **The model is profitable at the very first paying user.**

---

## 2. The plan (what we charge)

Keep it to **three tiers** — simplicity sells and is easy to enforce with what we have.

| Plan | Price | Compute | Limits | Who |
|---|---|---|---|---|
| **Free / Beta** | $0 | Shared or idle-stopped dedicated; auto-stops after 20 min idle | BYO OpenRouter key required · 1 HQ · community support | Try-before-buy, the funnel |
| **Pro** | **$9/mo** | Dedicated container, idle-stop after 60 min, fast start-on-login | BYO key · full toolset (capability=full) · vault to 5 GB · model quick-switch | Individual power users |
| **Team / Always-On** | **$29/mo** | Dedicated, **no idle-stop** (always warm) · priority capacity | Higher vault · multiple agents · email support · (later) seats | Daily/professional use |

**Why this shape:**
- Free tier is the growth engine and costs ~cents (idle-stop + BYO-key).
- Pro's only real cost is ~2 active hrs/day of compute → ~84% margin at $9.
- Always-On is the one tier where compute could approach $14 — priced at $29 so
  it's still ~50%+ margin and self-selects the heavy users into paying more.
- **No usage-based LLM billing to manage** — BYO-key externalizes it. Huge ops win.

---

## 3. What's already done (MVP building blocks shipped)

- ✅ Per-user isolated HQ (OCI container) — the product.
- ✅ **OpenRouter default + per-user key** (`/hermes/openrouter-key`) — $0 LLM cost.
- ✅ **Capability tiers** (lite/full) — maps directly to Free vs Pro.
- ✅ **Model quick-switch** (incl. Nemotron) — a Pro/Team perk.
- ✅ **Idle tracking + `reap-idle`** — the profitability lever.
- ✅ **`prune` + `capacity`** — keep the free pool from silently filling (we hit this).
- ✅ **Container hardened** (build tools, ripgrep, code-agent ready).
- ✅ **Auto-retry provisioning** — fewer failed signups.
- ✅ Onboarding tutorial with key setup — activation flow.

## 4. What's left for a chargeable MVP (ordered by necessity)

**Must-have to charge money (the gate):**
1. **Container auth** (JWT + Caddy forward_auth, private IPs) — *cannot* sell access
   to currently-open containers. `docs/CONTAINER_AUTH_DESIGN.md` is the spec. **#1 blocker.**
2. **Billing integration** — Stripe Checkout + webhook → plan flag on the principal.
   The SvelteKit shell already does ICP identity; add a `plan` field (canister or the
   registry DB) and gate provisioning/capability on it. ~1-2 days.
3. **Plan enforcement** — map plan → container behavior:
   - Free → `reap-idle --minutes 20` + capability=lite
   - Pro → idle 60 + capability=full
   - Always-On → exempt from reap-idle
   This is a few lines in `reap-idle` (read plan from registry) + provision.
4. **Registry → real DB** (`fleet.json` → OCI Autonomous DB) — needed the moment
   concurrent signups + billing state exist; JSON file races otherwise.

**Should-have (fast follow, not a launch blocker):**
5. **Start-on-login** — when a Pro user opens HQ and their container is INACTIVE,
   auto-start + wait healthy. Pairs with idle-stop for the seamless feel.
6. **Cron the housekeeping** — `reap-idle` every 10 min + `prune` hourly (gateway
   crontab). Turns the levers from manual to automatic.
7. **Capacity guard at signup** — if A1 pool full, queue/waitlist instead of a raw
   LimitExceeded. (`capacity` command already exposes the number.)

**Nice-to-have (post-revenue):**
8. Warm pool (sub-second HQ start), multi-tenant free tier, OKE, multi-region,
   per-seat Teams. Build when a constraint demands it.

---

## 5. Scaling the cloud architecture for SaaS (keep the split, tighten seams)

- **ICP** keeps identity + shell + vault (scales itself, near-zero ops). Add the
  **`plan` field** here or in the DB.
- **OCI** is the flexing layer:
  - Free A1 pool is only **4 OCPU** — so **free users must idle-stop aggressively**
    and/or move to a **shared multi-tenant container** once free signups exceed ~4
    concurrent. (The shared free tier is the single biggest cost-saver at scale.)
  - **Paid users get dedicated containers** — and paid users fund expanding past the
    free pool (each extra is ~$14 compute, covered 2-3x by a $29 plan or ~6x at $9
    with idle-stop).
  - **Gateway:** move to private IPs + one LB/Caddy with auth (also closes the
    security gate). Put the gateway on a free AMD micro VM to preserve all 4 A1 OCPU.
  - **Builds:** native-ARM CI, SHA-tagged images (stop the 40-min emulated-build pain).

**The capacity → revenue flywheel:** free users cost ~cents (idle-stop/shared) →
some convert to Pro/Team → paid revenue funds dedicated containers beyond the free
pool → more capacity for more free users. It compounds, and it's positive-margin at
every step.

---

## 6. 2-week cut to "we can charge"

- **Day 1-3:** Container auth (JWT + forward_auth) + private IPs. *(the gate)*
- **Day 4-5:** Stripe Checkout + webhook → `plan` on principal; gate provision/capability.
- **Day 6-7:** Plan enforcement in `reap-idle`/provision (Free 20m/lite, Pro 60m/full, Always-On exempt) + cron the housekeeping.
- **Day 8-9:** `fleet.json` → Autonomous DB; `fleet-api` reads/writes plan + state.
- **Day 10:** Start-on-login + capacity-guard waitlist.
- **Day 11-14:** Native-ARM CI builds; polish onboarding→checkout funnel; soft launch to beta list.

After this, CafresoHQ is a chargeable SaaS with **~84% gross margin at $9/mo from the
first customer**, free-tier costs measured in cents, and a clear path to scale where
**paying users fund the capacity that serves free users.**
