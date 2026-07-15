# The Cafreso Search Network

A public, on-chain research library grown by a network of community-run HQ
containers. Anonymous visitors ask questions on cafreso.com; answers come from
(1) the on-chain library cache — instant and free — or (2) a job queue
fulfilled by **workers**: HQ containers that each bring their own Brave Search
API key and local LLM, earn ICP per fulfilled job, and are attributed on-chain
in every entry they write.

```
anonymous visitor (cafreso.com /library page or the AI Search modal)
  GET  <state>.icp0.io/library/find.json?q=…      library cache hit → instant
  GET  <state>.icp0.io/search/health.json         workers online?
  POST <state>.icp0.io/search/submit              queue a job
  GET  <state>.icp0.io/search/job/<id>.json       poll (~3s, ≤200s)

worker container (serve.py, SEARCH_WORKER=1)      HMAC-signed HTTPS POSTs
  /worker/heartbeat · /worker/claim · /worker/fulfill · /worker/fail
  per job: Brave (own key) → local LLM (operator's backend, direct) → graph → fulfill

canister (cafresohq_state)
  worker registry (admin-approved) · job queue · public library with
  provenance · payout accrual swept by the payroll timer under a
  planAdmin-signed ICRC-2 allowance (the hard budget)
```

## Worker operator quickstart

1. Sign in at **ai.cafreso.com → HQ → Settings → Search network** and click
   **Register my worker**. Your browser generates a 32-byte secret and shows it
   **once** — the canister stores it to verify your worker's signatures and can
   never return it. (Rotate any time; rotating keeps your approval.)
2. Add the env block to wherever your container runs and restart it:
   ```
   SEARCH_WORKER=1
   WORKER_PRINCIPAL=<your principal>
   WORKER_SECRET=<the 64-hex secret>
   BRAVE_API_KEY=<free key from brave.com/search/api>
   ```
   Optional: `WORKER_MODEL` (**override only** — by default search follows your
   HQ brain picker, so switching brains moves search too; set this only to run
   search on a different model than your agents, and only on one your backend
   has **loaded**), `SEARCH_STATE_URL` (local-replica override for development),
   `WORKER_JOB_BUDGET` (seconds for the whole claim→fulfill window, default
   `200`), `WORKER_IDLE_TIMEOUT` (seconds of LLM silence before the worker
   gives up on a generation, default `25`).

   **Don't raise `WORKER_JOB_BUDGET` above ~210.** The canister's claim lease is
   240s and is not renewable — heartbeats don't extend it and there's no renew
   op. Overrun it and your fulfill is rejected with `not-your-claim`: the GPU
   time is wasted, the job's attempt counter still ticks, and three strikes
   fail it permanently. The default leaves 40s of headroom for the graph build
   and the upload. If your box is too slow to answer inside that, the worker
   salvages a partial summary rather than nothing — see below.
3. Wait for the plan admin to **approve** your worker (Settings shows
   "awaiting approval" → "approved"; your container heartbeats meanwhile, so
   the admin can see it's connected).
4. Your container now claims queued questions, answers them with **your** Brave
   quota and **your** local model, and every fulfilled job:
   - becomes a permanent public library entry attributed to your principal,
   - accrues the per-job rate to your on-chain balance, swept to your account
     once it crosses the minimum payout (fees are amortized — see Payouts).

Worker containers must not idle-stop: the loop is outbound-only and never
counts as user activity. Run standalone (docker) or disable idle-stop.

## Protocol (for non-serve.py workers)

Worker calls are plain HTTPS POSTs to `https://<state-canister>.icp0.io`
(fallback `.raw.icp0.io`). The request body is UTF-8, newline-separated:

```
v1
<worker principal text>
<ts — unix milliseconds, strictly increasing per worker>
<nonce — 8-32 hex chars, any entropy>
<op — heartbeat | claim | fulfill | fail>
<op-specific lines…>
```

Header `x-worker-signature: hex(HMAC-SHA256(secret, raw-body-bytes))`.

- **Replay protection:** the canister stores the last accepted `ts` per worker
  and rejects anything ≤ it. Serialize your calls (one at a time).
- **Skew:** `|now - ts| ≤ 5 minutes`.
- `claim` → `{"job":{"id","q"}}` or `{"job":null}`. Claims lease for 4 minutes.
  The lease is **not renewable** — `heartbeat` does not touch `claimedAt` and
  there is no renew op — and fulfill is **one-shot**: there's no way to post a
  partial or "still working" update. Budget your whole pipeline (search + model
  + upload) under 240s from the claim, or your fulfill returns `not-your-claim`
  after the job has already been handed to someone else with `attempts`
  incremented. serve.py targets 200s (`WORKER_JOB_BUDGET`).
- `fulfill` lines: `jobId`, `model`(pct), `engine`(pct), `answer`(pct),
  `N` source count, then N lines of `"<title-pct> <url-pct>"` (single space),
  finally `graphJson`(pct) — a graph-viewer snapshot
  (`{graph:{options,attributes,nodes,edges}, title, ts}`).
  Every free-text field is percent-encoded with no safe chars so newlines can't
  break framing. Caps: query 400, answer 4 000, 10 sources ×600, graph 200 000,
  model/engine 80, body 256 KB.
- `fail` lines: `jobId`, `reason`(pct). Returns the job to the queue
  (3 attempts → failed).

## Queue rules (anonymous submit)

Dedup by normalized query — ASCII-lowercased, punctuation stripped, whitespace
collapsed (`libKey`), so "What is ICP?" and "what is icp" are one cache entry
rather than two jobs. Repeat submissions join the existing job or hit the
library. Normalization is deliberately conservative: no stopword removal and no
word reordering, since "cat eats mouse" ≠ "mouse eats cat".

Global cap 25 pending; **daily answer budget** (default 500, admin-set); jobs
expire unclaimed after 15 min; submit is rejected with `dark` when no approved
worker has heartbeated within 10 min — the UI then degrades honestly ("network
is asleep") instead of spinning.

> `libKey` is separate from `libNorm` on purpose. `libNorm` also normalizes HTTP
> header names and the hex signature in `verifyWorker`; teaching *it* to strip
> punctuation would turn `x-worker-signature` into `xworkersignature`, no header
> would ever match, and every worker call would fail auth. Change `libKey` only,
> and remember `postupgrade` rebuilds `libraryByQuery` — re-keying without that
> rebuild strands every existing entry.

## Which model answers, and why not through the gateway

**Agent tasks → Hermes. Plain model calls → direct.** Search is a single-shot
summarisation, not an agent turn, so it calls the operator's backend directly
(`night_runner.resolve_backend` reads the same `model:` block the HQ brain picker
writes). Pick a brain in HQ and search follows it — per job, no restart.
`WORKER_MODEL` overrides that for operators who want search on a different model
than their agents.

This is not a preference. The hermes gateway is an **agent runtime** and, verified
against hermes-agent 0.15.1:

- it layers a **~13k-token agent system prompt** onto every call (a 3-source
  answer cost 15–27k tokens and 37–66s; the same answer direct is ~430 tokens
  and ~3.5s),
- it **silently drops `max_tokens` and `response_format`** — they never reach the
  model,
- it **ignores `model`** entirely (the real one comes from `config.yaml`) while
  **echoing your requested name back in the response**. Ask it for
  `totally/made-up-model-xyz` and it answers, calling itself that.

That last one is why the gateway path reads the model from `config.yaml` rather
than from the response: library entries are permanent and public, and an echo
would let a chip claim a model that never ran.

The gateway remains the **fallback** for operators we can't resolve directly —
`anthropic` has no `_PROVIDER_ENDPOINTS` entry, so the gateway is its only path.
Don't delete that branch.

### Picking a search model: watch the tail, not the median

Search has a hard 240s lease and pays per token, so a model's **worst** run
matters more than its typical one. **Reasoning models are a poor fit**: their
reasoning channel occasionally runs away, and `max_tokens` may not bound it
(LM Studio does not count gpt-oss-20b's reasoning against the cap, so a 700 cap
cannot stop a 14k-token think).

Measured on one operator's box, 6 back-to-back runs of the same 5-source job:

| model | median | max | tokens |
|---|---|---|---|
| gemma-4-e4b (non-reasoning) | 1.2s | 8.5s | ~520 every run |
| gpt-oss-20b (reasoning) | 2.9s | **78.3s** | ~500 ×5, then **14,210** |

Both produced 5/5 notes and correct citations, so the reasoning bought nothing
here — a search answer is a short structured extraction, not a chain of thought.
Reasoning still earns its keep for *agents*, which is exactly what
`WORKER_MODEL` is for: point search at a fast non-reasoning model and leave the
brain picker on whatever your agents want.

## Answer quality on a slow box

The worker streams the model's reply and asks for `{"summary", "notes"}` with
**summary first, deliberately**. If the deadline cuts the stream short, the
summary is usually complete and only some per-source notes are lost, so the
entry still gets a real answer instead of degrading to sources-only.

Library entries are permanent and public, so salvage has a floor: a truncated
summary is published only if at least one whole sentence survived. A fragment
like "ICP i" is discarded and the entry lands sources-only, which is the honest
outcome. An LLM failure never fails the job — sources and the graph are still
worth fulfilling.

**Entries consistently landing without summaries?** Check these in order — the
worker prints the reason, so read its log first:

1. **Is the model loaded?** By far the most common cause. Asking a local
   backend for a model it hasn't loaded fails every job, and the entry falls
   back to sources-only. `curl <backend>/api/v0/models` (LM Studio) shows
   `state: loaded` vs `not-loaded`. Either load it or pick one that is.
2. **Can the worker reach a backend at all?** `direct backend failed` names the
   provider, url and model it tried. `no direct backend and no gateway key`
   means it never got to try: check the brain picker, or `API_SERVER_KEY` /
   `$HERMES_HOME/.env` for the gateway fallback.
3. **Only then, is it too slow?** Pick a faster model, or accept sources-only.
   Raising `WORKER_JOB_BUDGET` past ~210 makes things *worse*, not better —
   see the lease warning above.

If the chip reads ~15k+ tokens for a 3-source answer, search fell back to the
gateway and is paying the agent system-prompt tax — check the log for why the
direct path failed.

## Payouts

- Admin: **Settings → Search network → admin** — set ledger (ICP), per-job rate
  and minimum payout, then **Sign treasury allowance**: an `icrc2_approve`
  (spender = the state canister) from the admin's account. **The allowance is
  the hard ceiling** — workers can never be paid more than it, total.
- Fulfill **accrues** the rate; the payroll timer sweeps accruals ≥
  max(minPayout, 2×ledger-fee) with the same exactly-once discipline as user
  payroll (pending payout logged before the ledger await; memo +
  created_at_time dedup replays; InsufficientFunds/Allowance restores the
  accrual for retry after refill).
- A per-job rate below the ledger fee is why accrual exists: paying 0.00001 ICP
  jobs one-by-one would burn 0.0001 ICP in fees each.

## Moderation & trust

- Workers are **admin-approved before they can claim** and can be suspended
  instantly (`worker_admin_set_status`), which also cuts off payouts.
- Worker answers are UNTRUSTED text: stored verbatim, emitted only
  JSON-escaped, always rendered as plain text client-side (never `@html`).
- `library_remove(id)` — entry owner or planAdmin — is the takedown path;
  removing an entry also clears its dedup slot so the query can be re-answered.
- The public JSON exposes the **worker** principal (attribution is the point)
  but never the `owner` of user-published entries.

## Risk register

- **Brave ToS:** workers pool individual free-tier keys and the library
  republishes result titles+URLs on-chain (descriptions are deliberately NOT
  stored). Review Brave Search API terms before promoting the network broadly.
- **Anonymous submit abuse:** mitigations are dedup + 25-pending cap + daily
  budget + network-dark rejection. Per-IP limits don't exist on-chain; if bots
  arrive, the next lever is a per-query micro-fee (payment rails exist).
- **Answer quality/poisoning:** v1 = approval gate + suspension + takedown.
  Multi-worker cross-checking and reputation scoring are future work.
- **Poll cost:** every status poll is an update call (GETs upgrade); fine at
  small scale, revisit with certified queries if traffic grows.
- **Storage:** entries are KB-scale on the canister heap; migrate the library
  to stable structures / shard across canisters before the multi-GB range.
