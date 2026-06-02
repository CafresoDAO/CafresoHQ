# CafresoHQ — Scaling Strategy (the entrepreneur's view)

> How I'd scale this from "4 free containers" to a real product, what to change in
> the MVP, and how to evolve the double-cloud (ICP + OCI) architecture so growth is
> cheap and boring instead of a fire drill. Grounded in what we actually learned:
> per-user always-on containers, OpenRouter default, OCI free A1 pool, open
> containers, no metering/billing.

---

## 0. The core tension (name it before solving it)

The product's magic — **a private, isolated, always-on agent HQ per user** — is also its
**unit-economics trap**: one always-on 1 vCPU/6 GB container ≈ **$14/user/month** with
**zero revenue** and a hard ceiling of **4 free**. Every scaling decision below is really
one question: *how do I keep the "your own private HQ" feeling while not paying $14/mo for
users who are mostly idle and not paying me?*

The whole strategy is three moves:
1. **Decouple "has an HQ" from "is consuming compute"** (idle = $0).
2. **Make cost a function of usage, and usage a function of revenue** (metering → billing, or BYO-compute/BYO-key).
3. **Turn the per-user container from a pet into cattle** (stateless, reproducible, schedulable).

---

## 1. Stages of scale (don't over-build for users you don't have)

| Stage | Users | Architecture | Cost posture |
|---|---|---|---|
| **0 — Beta (now)** | 1–4 concurrent | What we have + **idle auto-stop** + gateway off-Ampere | $0 (free A1 pool) |
| **1 — Early access** | ~5–50 | Idle-stop + on-login-start; **BYO OpenRouter key** (done); container pool reuse | ~$0–50/mo; cost only when active |
| **2 — Paid launch** | 50–500 | Metering→billing; warm pool + scheduler; private IPs + 1 LB; secrets in OCI Vault | Cost tracks revenue per user |
| **3 — Growth** | 500–5k | Kubernetes (OKE) or session-per-pod; multi-region; tiered plans (free=shared, paid=dedicated) | Margin-positive; infra is a % of rev |
| **4 — Scale** | 5k+ | Multi-tenant "serverless agent" tier for free users; dedicated only for premium | Free tier is shared & cheap; $ from dedicated |

**Rule:** each stage is a *response to a constraint you actually hit*, not a pre-build. The
only thing to build *now* that pays off at every stage is **idle auto-stop** — it's the
difference between "4 users" and "hundreds."

---

## 2. MVP changes that unlock scaling

These are ordered by **leverage ÷ effort**.

### 2.1 Idle auto-stop + start-on-login  🔑 (highest leverage, do first)
- The OCI free grant is **3,000 OCPU-hrs/month**, not "4 instances." Stopped Container
  Instances **pause billing and free the A1 pool**.
- Add: a serve.py idle timer (no request in N min → signal) + `fleet-manager stop`; and
  on the shell side, **start-on-login** (`/fleet/provision` already returns existing; add
  "if STOPPED → start, wait for healthy, then iframe").
- Impact: **4 concurrent → dozens of registered beta users** for free. Same lever halves
  cost at every paid stage.

### 2.2 Stateless container = "cattle, not pets"
Right now state lives in three places (container `/data`, ICP vault, fleet.json). For a
container to be safely stop/start/recreate/reschedule, **nothing important may live only in
the container**:
- Vault → already ICP/Object Storage ✓
- `~/.hermes` (config, memory, cron, the user's OpenRouter key) → **must persist off-box**:
  mount an OCI **Block Volume** per user, or sync `~/.hermes` to Object Storage on
  change. Today a recreate **loses the user's key + memory** — that blocks stop/start UX.
- HQ state (`/data/hq-state`) → same.
- **Action:** make `/data` a mounted volume (or object-store-backed) so recreate is lossless.
  This is the single change that turns the container into a schedulable unit.

### 2.3 Metering → billing (you already have the tap)
- `_record_hermes_usage` writes per-principal token usage to `/data/hermes-usage.log`.
  It's the seed of a business model — but it's **per-container, unverified, and not
  aggregated**.
- **Action:** ship usage events to a central sink (small collector service or an ICP
  canister), keyed to the *verified* principal (needs the auth fix, §3). Then: free tier =
  N tokens/mo or M active-hrs/mo; paid = more. Now compute cost has a revenue ceiling.

### 2.4 BYO-key as the default growth hack (mostly done)
- We made **OpenRouter (user's own free key)** the default. This is huge for scaling: the
  *LLM cost is the user's*, not yours. Your only cost is the container.
- **Action:** lean into it — onboarding *requires* a free key (done in tutorial), and a
  "bring your own Anthropic/OpenAI for power mode" upsell. Keeps your variable cost ≈ just
  compute.

### 2.5 Collapse the backend duplication (from the review)
- 4× duplicated stream handlers, duplicated fleet logic (`_render_caddyfile`,
  `_principal_slug` in two files that already diverged). At 1 dev this is "annoying"; at
  scale it's "every change is two changes and a bug." The `docs/production-grade/`
  refactors (`agent_stream.py`, `fleet_common.py`) are ready to merge — do it before the
  team grows.

---

## 3. Security must-precede-scale (you can't onboard strangers onto open containers)
From `CONTAINER_AUTH_DESIGN.md` — these become **blocking** the moment real users sign up:
- **Containers are open** (public IP + no gateway auth + derivable slug). Fine for 4
  friends; a breach waiting at 50 strangers.
- **Action before paid launch:** private IPs only → one Caddy/LB front → **JWT
  forward_auth** (principal-bound). Bonus: removing per-container public IPs also enables
  §4's load-balancer consolidation.

---

## 4. Double-cloud (ICP + OCI) — how to evolve it for easy scaling

The split is actually *good* and worth keeping — but tighten the seams.

### Keep on ICP (it scales itself, near-zero ops):
- Identity (Internet Identity), the SvelteKit shell (asset canister), the zero-knowledge
  vault/keys canister. These are **stateless-to-you and globally served** — let ICP carry
  the user-facing, trust-critical layer. No scaling work needed.

### Change on OCI (the part that costs money and needs to flex):

**4.1 One gateway, not N public IPs.**
Today: every container has a public IP, Caddy routes by slug. At scale that's IP sprawl +
the open-container risk. Move to: **private container IPs + a single OCI Flexible Load
Balancer / Caddy** doing auth + routing. One front door, horizontally scalable, and the
free tier even includes 1 LB.

**4.2 Registry: `fleet.json` → a real datastore.**
A single JSON file with no locking is a race waiting to happen at concurrent signups.
Move to **OCI Autonomous DB (Always Free)** or even SQLite-on-a-volume for stage 1, then
Postgres. `fleet-api.py` becomes a thin API over it.

**4.3 Provisioning: imperative script → control loop.**
`fleet-manager.py` is a great CLI but it's *you* running commands. For self-serve, the
**`fleet-api` provision worker** (already exists) is the seed of a **reconciler**: desired
state (DB: who should have a running HQ) vs actual (OCI), with retries (we just added
them), idle-stop, and warm-pool management. This is the thing that lets users self-serve
without you in the loop.

**4.4 Warm pool (latency + UX).**
Cold provision is ~60–90s — bad first impression. Keep a small **pool of pre-warmed
containers** (generic, no user state) and *attach* a user's `/data` volume on login. With
stateless containers (§2.2), "give me an HQ" becomes "grab a warm one + mount your volume"
= a few seconds.

**4.5 The big architectural fork at stage 3: shared vs dedicated.**
- **Free/casual users → multi-tenant "serverless agent"**: one (or a few) shared
  containers running Hermes, requests namespaced by principal, vault stays per-user via
  ICP. Kills the $14/idle-user problem entirely for the free tier.
- **Paid/power users → dedicated container** (today's model): the premium, isolated,
  always-on experience they pay for.
- This **tiering is the business model**: free = shared & cheap, paid = dedicated. Build
  it when free-tier compute cost starts to hurt (stage 2→3), not before.

**4.6 Image pipeline (dev velocity).**
The emulated ARM builds on a Windows box took 30-40 min and caused half our deploy pain
(stale cache, cancelled pushes). **Action:** move builds to a **native-ARM CI runner**
(OCI Ampere build instance or GitHub ARM runner) → minutes, reliable, no QEMU. Tag images
with the git SHA (not just `:latest`) so deploys are deterministic and rollbackable.

---

## 5. Cost model at a glance (why these moves matter)

| Scenario | Cost/user/mo | Notes |
|---|---|---|
| Today: always-on dedicated | **~$14** | 4 free, then $14 each. Brutal for idle/free users. |
| + idle auto-stop (3 active hrs/day) | **~$1.7** | 8× cheaper; dozens fit in free grant |
| + shared free tier (stage 3) | **~$0.10–0.50** | free users amortized across one container |
| Paid dedicated tier | $14 cost → **price at $20–30** | margin-positive; the premium SKU |
| LLM cost | **$0 to you** (BYO OpenRouter) | the structural win we already shipped |

**The headline:** with **idle-stop + BYO-key**, your marginal cost per free user drops from
$14 to roughly *cents*, and dedicated-container becomes a paid feature people happily buy.
That's a scalable business, not a money pit.

---

## 6. What I'd do in the next 30 days (concrete)

1. **Ship idle auto-stop + start-on-login.** (the runway lever)
2. **Make `/data` persistent (volume or object-store sync).** (enables stop/start losslessly)
3. **Container auth (JWT + forward_auth) + private IPs + secrets→OCI Vault.** (gate to public)
4. **`fleet.json` → Autonomous DB; fleet-api becomes the reconciler.** (self-serve, no races)
5. **Native-ARM CI image builds, SHA-tagged.** (stop fighting deploys)
6. **Wire metering→central sink; define free vs paid limits.** (turn usage into revenue)

Everything else (multi-tenant free tier, OKE, multi-region) waits until a real constraint
demands it. Scale the *constraints you hit*, in order — and the first one is always cost-
per-idle-user, which idle-stop + BYO-key already crush.
```
