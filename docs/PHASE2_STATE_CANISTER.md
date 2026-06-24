I'll evaluate the three candidates against the decisive constraints and produce the final design. Let me note the key facts that settle this before writing.

The decisive constraint is stated plainly: **the container has no II delegation** and holds only `USER_PRINCIPAL` as text. That immediately means the only unforgeable writer to any canister is the browser (`msg.caller` verified by the IC). All three candidates accept this. The differentiators are: per-canister cost/ops at 10k+ users, blast radius, and whether the container needs *any* secret/credential at all.

Here is my decision and the implementation-ready design.

---

# FINAL RECOMMENDED DESIGN — Phase-2 On-Chain Per-User State

## 0. Decision

**Primary approach: Candidate A (single shared, principal-keyed `cafresohq_state` canister with chunked vault), hardened with two elements borrowed from C, and explicitly rejecting B.**

The recommended design is **Candidate A as the base**, with two deliberate modifications drawn from Candidate C:

1. **Drop A's token-gated container read path (`*ForToken` query methods) for the default deployment.** Adopt C's *browser-mediated, container-has-zero-canister-authority* model. The container gets **no** canister credential, not even a read token. This is strictly safer and removes the hardest-to-reason-about part of A (uncertified query reads behind a mirrored HMAC secret).
2. **Keep A's single shared canister (reject C's 4-shard-from-day-one).** At 10k users with realistic vault sizes, one canister is correct; sharding is *designed-in but deferred* exactly as A proposes.

### Why A wins over B (decisive)

| Criterion | A (shared map) | B (factory, 1 canister/user) |
|---|---|---|
| **Auth model under "no II delegation"** | Browser writes via `msg.caller`; **container needs no credential** | Same browser path, **but** invents a *new* `mintContainerCap` credential + container Ed25519 identity + `openSession` — a real, long-lived-ish secret on the box we are trying to make disposable |
| **Cost @ 10k users** | ~$900/mo storage, **$0 per-user creation, $0 parked float** | ~$900/mo storage **+ ~$6.75k one-time creation + ~$20k parked cycles float** + perpetual top-up bank |
| **Ops @ 10k+ users** | One canister to monitor/upgrade | 10k canisters to monitor, refuel, and fan-out-upgrade (throttled, resumable orchestration required) |
| **lossless stop/start/recreate** | Yes (all state keyed by principal on-chain) | Yes — but only after building the cap/session machinery |
| **Implementation complexity** | ~400 LOC Motoko + 1 actor file | Factory + child actor-class + cap minting + session table + fleet refueler |
| **Blast radius** | Shared (mitigated by per-user quota + designed-in shard split) | Per-user isolation (the one genuine B win) |
| **Migration risk** | Browser-driven backfill, reversible | Same backfill **plus** provisioning 10k canisters |

B's only real advantage is hard per-user isolation and independent 500 GiB headroom. **Neither is needed here**: HQ docs are tiny, vaults are E2E-encrypted ciphertext the canister cannot read, per-user quotas + a 400 GiB shard watermark bound blast radius, and no single user approaches 500 GiB. B pays a 5-figure cycle float and a permanent fleet-refueling burden to buy isolation the threat model doesn't require. **Rejected.**

### Why the C-flavored auth (not A's token path)

A's `*ForToken` methods reuse the existing HMAC token as a *third verifier* and serve uncertified `query` reads to the container. That works, but it (a) mirrors `hqSecret` into a second canister (atomic 3-way rotation hazard), and (b) relies on E2E encryption + 30-min TTL to make uncertified reads acceptable. C's insight is cleaner and is the right default: **the browser is the only caller of the canister, in both directions.** The container keeps an ephemeral `/data` cache + an op-log, and the browser couriers state on-chain and re-hydrates the container on boot. The container then holds **no** canister credential and **no** mirrored secret — the smallest possible secret surface, which is the whole point of Phase-2.

We retain A's data model, chunking, quota, and single-canister scaling verbatim.

---

## 1. Data Model

One canister, `cafresohq_state`, Motoko + `mo:stable-structures` with `MemoryManager`, enhanced orthogonal persistence (no `pre/post_upgrade`). All bulk data lives in stable memory; heap holds only BTree node cache.

```motoko
import Map  "mo:stable-structures/BTreeMap";
import MM   "mo:stable-structures/MemoryManager";
import Principal "mo:base/Principal";

// ── Memory partitions (MemoryId) ──────────────────────────────
//  0 -> hqDocs       per-user HQ JSON docs
//  1 -> vaultMeta    per vault object metadata
//  2 -> vaultChunks  per (principal,objId,ix) ciphertext slice (<=1.9 MiB)
//  3 -> usage        per-user byte/object counters (quota, no scans)
let mm = MM.init(region);

// Compound keys are ordered (owner first) so a half-open range
// scan [owner, owner+1) returns exactly one user's rows, chunks in ix order.
type DocKey      = { owner : Principal; name : Text };   // name: "tasks","projects","missions","receipts","messages","agents","memory/<x>"
type HqDoc       = { body : Blob; sha256 : Blob; version : Nat; updatedAt : Int };

type VaultKey    = { owner : Principal; objId : Text };
type VaultMeta   = { totalSize : Nat; chunkCount : Nat; sha256 : Blob; sealed : Bool; version : Nat; updatedAt : Int };

type ChunkKey    = { owner : Principal; objId : Text; ix : Nat }; // value: Blob <=1.9 MiB

type Usage       = { docBytes : Nat; vaultBytes : Nat; objCount : Nat; quotaBytes : Nat; plan : Text; migratedAt : Int };

let hqDocs      = Map.init<DocKey,    HqDoc>    (mm.get(0));
let vaultMeta   = Map.init<VaultKey,  VaultMeta>(mm.get(1));
let vaultChunks = Map.init<ChunkKey,  Blob>     (mm.get(2));
let usage       = Map.init<Principal, Usage>    (mm.get(3));
```

Key points:
- **HQ docs** = the *same UTF-8 JSON bytes* serve.py writes to disk today (`tasks`, `projects`, `missions`, `receipts`, `messages`, `agents`, `memory/*`). Non-secret app state, stored whole, versioned per `(owner,name)` for optimistic concurrency.
- **Vault** = exactly the base64-decoded ciphertext (`[iv||AES-GCM ct+tag]`) the browser produces today via `vaultKey.js`. The encrypted index (`objId = "iiii…"`) is just another vault object. The canister never decrypts; the vetKeys master key never leaves the browser. **vetKeys/`vaultKey.js`/`cafresohq_keys` derivation is untouched.**
- **`sealed`** lets writers publish atomically: write chunks first, set `sealed=true` last; readers ignore objects with `sealed=false` or fewer stored chunks than `chunkCount`.
- **Usage** carries `quotaBytes`/`plan` (set from the existing HMAC plan token) and a `migratedAt` cursor for the backfill.

---

## 2. Full Candid Interface

No `*ForToken` methods (the container never calls the canister). Every method is caller-authed by `msg.caller`; there is **no principal argument anywhere**, so no caller can address another user's rows.

```candid
type HqDoc      = record { body: blob; sha256: blob; version: nat; updatedAt: int };
type DocSummary = record { name: text; version: nat; sha256: blob; updatedAt: int };
type VaultMeta  = record { totalSize: nat; chunkCount: nat; sha256: blob; sealed: bool; version: nat; updatedAt: int };
type Usage      = record { docBytes: nat; vaultBytes: nat; objCount: nat; quotaBytes: nat; plan: text; migratedAt: int };

type PutResult  = variant { ok: record { version: nat }; conflict: record { current: nat }; quota: text };

service : {
  // ── HQ state docs (key = msg.caller) ──────────────────────────
  putHqDoc    : (name: text, body: blob, sha256: blob, expectVersion: nat) -> (PutResult);
  getHqDoc    : (name: text) -> (opt HqDoc) query;
  listHqDocs  : () -> (vec DocSummary) query;          // boot manifest / change-detection
  hqVersion   : () -> (nat) query;                     // cheap "anything changed?" counter
  deleteHqDoc : (name: text) -> ();

  // ── Vault ciphertext, chunked (key = msg.caller) ──────────────
  putVaultMeta  : (objId: text, totalSize: nat, chunkCount: nat, sha256: blob, expectVersion: nat) -> (PutResult); // sealed=false
  putVaultChunk : (objId: text, version: nat, ix: nat, data: blob) -> ();   // data <= 1.9 MiB; idempotent on (objId,version,ix)
  sealVault     : (objId: text, version: nat) -> (PutResult);               // publish
  getVaultMeta  : (objId: text) -> (opt VaultMeta) query;
  getVaultChunk : (objId: text, ix: nat) -> (opt blob) query;
  listVaultMeta : () -> (vec record { text; VaultMeta }) query;
  deleteVault   : (objId: text) -> ();

  // ── Quota / plan ──────────────────────────────────────────────
  myUsage : () -> (Usage) query;
  setPlan : (planToken: text) -> ();   // re-verifies the existing v1plan.<principal>.<plan>.<exp>.<hmac> HMAC canister-side

  // ── Admin (HQ_ADMIN | HQ_DEPLOYER only) ───────────────────────
  shardId        : () -> (text) query;
  cycleBalance   : () -> (nat) query;
  setPlanSecret  : (secretHex: text) -> ();   // ONLY for setPlan verification; NOT used for any container auth
  planConfigured : () -> (bool) query;
}
```

Notes:
- Anonymous callers rejected on every non-admin method (mirrors `vault_encrypted_key`).
- `setPlanSecret` mirrors `hqSecret` **only** to validate plan-tier quota (defense-in-depth against client-side quota tampering). It is *not* on any auth path for the container — if you want to avoid even this one mirror, make `setPlan` trust the browser and drop `setPlanSecret`. Recommended to keep it; rotation hazard is limited because it gates only quota, never data access.

---

## 3. Auth Model — End to End

**The container is given no II delegation, no canister credential, and no mirrored data-access secret. The browser is the only entity that ever calls `cafresohq_state`.**

Three independent layers, all already in the repo except the new browser→canister actor:

**Layer 1 — Browser → `cafresohq_state` (NEW, native IC auth).**
The browser builds an authenticated actor exactly like `keysActor.js`: `new HttpAgent({ identity, host })` + `Actor.createActor(stateIdl, { agent, canisterId })`, cached per principal, reset in `auth.js _adopt` on principal change. The IC verifies the II delegation and sets `msg.caller`. Every storage key derives from `Principal.toBlob(msg.caller)`. **Unforgeable, no shared secret, no header trust** — the same model already trusted for `vault_encrypted_key`/`mintHqSession`. This is the *only* authority path for canister state.

**Layer 2 — Browser → Container (UNCHANGED HMAC session + slug).**
Browser mints `v1.<principal>.<exp>.<hmac>` via `cafresohq_keys.mintHqSession()` → `POST /fleet/session` → `hq_session` cookie → Caddy `forward_auth` → `verifier.py` checks HMAC and `slug_for(principal)==slug` → container receives `X-Hq-Principal`. The container uses this **only** to gate HTTP read/write of its *ephemeral local cache* (`/data` working copy + op-log), never to prove identity to the chain. This is byte-for-byte the existing flow (`hq_token.py`, `verifier.py`, `hqSession.js`) — no new verifier, no mirrored `hqSecret` for data access.

**Layer 3 — `setPlan` plan-token re-verification (optional defense-in-depth).**
The canister re-verifies the existing `v1plan.<principal>.<plan>.<exp>.<hmac>` token with a mirrored secret so a user cannot self-grant a higher quota. Gates quota only, never data.

**Why the container holding nothing is correct:** moving durability on-chain does not expand what the container can see. It already holds HQ JSON (non-secret) and vault ciphertext it never had the key for. By making the container call *nothing* on-chain, a fully compromised/recreated container leaks **only its own ephemeral cache of one user's data** — exactly what it has today — and can never forge canister state or reach another user, because it has no agent to call with and no method takes a principal argument.

**The one genuine limitation (accepted, see §8):** agent-originated writes while no browser is open cannot reach the chain directly. They append to the container's durable op-log; the browser drains it on next focus. Full headless autonomy would require a scoped delegation — explicitly out of scope, same as A's and C's stance.

---

## 4. Sync Protocol — Sequence of Calls

Roles: **BROWSER** = identity + courier; **CONTAINER** = stateless compute, ephemeral `/data` cache + append-only op-log; **CANISTER** = durable source of truth.

**A. BOOT / RECREATE (the lossless win) — container `/data` empty:**
1. Browser signs in (II), derives vetKeys master (unchanged), mints HQ session, installs `hq_session` cookie.
2. Browser `GET /hq/sync/state` → container reports its local `hqVersion` (or "empty").
3. Browser calls canister `hqVersion()` + `myUsage()` (queries, free).
4. If container empty/behind: browser `listHqDocs()` + `getHqDoc(name)` for each of the 6–7 docs, then `PUT /hq/state/<name>` (and `/hq/memory/<name>`) into the container. (~7 queries + ~7 small PUTs, <1s.)
5. Vault: lazy. On first `GET /vault/blob/<id>` cache miss the container 404s; the browser fetches `getVaultMeta(id)` + `getVaultChunk(id,ix)` for `ix=0..count-1`, concatenates, base64-encodes, decrypts locally, and back-fills the container cache via `PUT /vault/blob/<id>`. No full-vault download on boot.

**B. STEADY-STATE WRITE — HQ doc (browser is authoritative writer):**
6. User edits → browser `PUT /hq/state/tasks` to container (immediate local use) **and** `putHqDoc("tasks", bytes, sha256, expectVersion)` on canister.
7. `conflict { current }` → browser `getHqDoc`, 3-way merge arrays by record `id` (LWW per id on `updatedAt`, honor tombstones), retry. Canister is authoritative.

**C. STEADY-STATE WRITE — vault (browser, chunked, meta-last/seal):**
8. Browser encrypts (`vaultKey.js`, unchanged), splits ciphertext into ≤1.9 MiB chunks.
9. `putVaultMeta(objId, total, count, sha256, expectVersion)` (sealed=false) → `putVaultChunk(objId, version, ix, slice)` for each ix (bounded ~5 in flight, idempotent on `(objId,version,ix)` so retries are safe) → `sealVault(objId, version)` LAST. The encrypted index object (`iiii…`) is written the same way, sealed after its referenced blobs — preserving the existing index-after-blob discipline so no dangling reference is ever visible.
10. Browser also `PUT /vault/blob/<id>` to the container cache so in-container agents can read it. Delete: `deleteVault(objId)` + index update.

**D. CONTAINER-ORIGINATED CHANGES (agents write while browser may be closed):**
11. Container cannot call the chain. It writes its RAM/`/data` cache and appends `{seq,name,sha256,ts}` to a durable op-log under `/data`.
12. On next browser visit: `GET /hq/sync/oplog?since=<lastSeq>`; for each entry the browser reads the container's current JSON and commits via `putHqDoc`. The container's JSON is the merge base; the browser couriers it on-chain.
13. Always-on plan: a single delegated "keeper" context the *user* runs (pinned tab / headless agent holding the delegation) performs D on an interval. Autonomy = keeping one delegated courier alive, never trusting the box.

**E. PERIODIC RECONCILE (while a browser is open):** every N min compare container `hqVersion` vs canister `hqVersion()` (one int): container ahead → flush (D); canister ahead (another device) → pull (A4). Effectively free.

**F. DIRECT BROWSER→CANISTER fallback:** critical state (vault index, settings) can be written browser→canister directly, correct even if the container is down — maximal on-chain posture.

---

## 5. Chunking / Sharding + Size & Cost Limits (with numbers)

**Hard limits (2026) and how they're handled:**
- **2 MiB ingress arg + 2 MiB response:** vault chunks capped at **1.9 MiB** raw ciphertext (Candid framing headroom). `getVaultChunk` returns one chunk/call. HQ docs are tiny; `putHqDoc` body capped at 1.9 MiB and rejected above (matches real tasks/messages JSON). A 300 MB vault object → ~158 chunks; a 50 MB object → ~27 chunks.
- **4 GiB heap:** nothing large on heap — all docs/chunks in stable memory via `MemoryManager`; heap holds only BTree node cache. Irrelevant.
- **40 B-instruction update limit:** every update touches exactly one doc or one chunk (one BTree insert). `sealVault` flips a flag. No server-side iteration over a user's chunks. Trivially within budget.
- **500 GiB stable trap / 750 GiB subnet reserved-balance:** per-user quota in partition 3 (defaults: **2 GiB vault + 4 MB docs**, plan-tier-scaled via `setPlan`). `putVaultChunk`/`putHqDoc` return the `quota` variant before approaching limits. A **canister watermark at 400 GiB** flips *new-user onboarding* to a fresh shard (existing users untouched).

**Capacity of one shared canister:** HQ docs ~0.5–1 MB/user; vaults realistically 10 MB–2 GiB. One 500 GiB canister serves **~250–2,000 heavy-vault users** or **100k+ docs-only/light users**. **At the 10k-user target with typical 50–200 MB vaults (~1–2 TB aggregate) you will need 2–4 shards** — but only as pure capacity addition, see below.

**Sharding (designed-in, deferred — split when the 400 GiB watermark trips):** A tiny `cafresohq_router` (or reuse the IndexCanister PK→canister mapping) maps `shardIndex = first 2 bytes of sha256(principalBlob) mod N` and **pins each principal to one shard forever** (stable in the router). The frontend resolves the shard once per session (cached in localStorage next to the endpoint URL) and talks directly to that shard. Because every record is principal-keyed and self-contained (no cross-user joins), **adding a shard is capacity addition with zero rebalancing** — new principals route to the newest non-full shard, all of one user's data stays co-located, single-user reads never fan out. Recommendation: **deploy 1 shard now**; add the router + shard 1 the first time the watermark trips.

**Cost (2026; 13-node app subnet ≈ $0.45/GiB/month; 1T cycles = 1 XDR ≈ $1.35):**
- Storage: light user (1 MB) ≈ $0.0004/mo; 50 MB vault ≈ $0.022/mo; 1 GB ≈ $0.45/mo; 2 GB cap ≈ $0.90/mo.
- Writes (update calls): ~1.9 MiB chunk put ≈ 1–3 B cycles ≈ $0.0014–$0.004; full 50 MB initial upload (~27 chunks) ≈ $0.05–$0.11 one-time; HQ doc write ≈ ~1.5 M cycles (negligible). Queries free.
- **No vetKD spend in this canister** (derivation stays in `cafresohq_keys`).
- **Fleet @ 10k users** (illustrative 70% light@50 MB, 25% @2 GB, 5% @20 GB w/ quota): storage ≈ **~$900/mo** + a few tens of $/mo writes. **No per-canister creation fee, no parked float** (the explicit A-over-B win). Budget +20% headroom for the freezing threshold; top up per active GiB.

---

## 6. Migration Plan from `/data` + OCI Object Storage (reversible)

Container keeps serving its existing HTTP API throughout; only *where durability lives* changes. Dual-write never deletes from OCI/disk until the final step, so **every stage rolls back**.

0. **Scaffold (no behavior change).** Add `cafresohq_state` to `dfx.json` (`type motoko`, declarations → `frontend/src/lib/declarations/cafresohq_state`) next to `cafresohq_keys`; copy `Sha256.mo` for `setPlan` verification. Implement the Candid above. `dfx deploy cafresohq_state --network ic`; record id in `canister_ids.json`. Add `stateActor.js` (clone `keysActor.js`); reset it in `auth.js _adopt`. (Optionally) `setPlanSecret(<same hex>)`; verify `planConfigured()`.

1. **Shard pin (no-op at N=1).** Browser resolves/caches shard id on login (trivial at one shard; router added later).

2. **Dual-write (canister = verified mirror; OCI/disk authoritative).** Feature flag `PUBLIC_STATE_CANISTER=mirror`. Every existing `PUT /hq/state/<name>` and vault `PUT /vault/blob/<id>` *also* writes to the canister (`putHqDoc`; `putVaultMeta`→`putVaultChunk`→`sealVault`) **after** the existing write succeeds; failures logged, non-fatal. Bake ~1–2 weeks; compare `sha256`/etags.

3. **Backfill (cover inactive users / cold blobs).** Browser-driven, since only the browser has the II identity *and* can decrypt the index to enumerate file ids. On each user's next login: enumerate the decrypted vault index; for every file id present in OCI but missing a canister meta, `GET /vault/blob/<id>` from the container (still reading OCI), chunk verbatim (**ciphertext moves byte-for-byte; no re-encryption, vault stays server-blind**), `putVaultMeta`/`putVaultChunk`/`sealVault`. Push all HQ docs. Idempotent by `sha256`; set `usage.migratedAt` on completion. Verify `objCount`/`vaultBytes` vs OCI prefix listing.

4. **Read cutover.** Flip `PUBLIC_STATE_CANISTER=primary`. Boot/re-hydrate (§4-A) now pulls from the canister into the container on recreate. OCI/`/data` downgraded to read-through fallback behind the flag. **Acceptance test:** `docker kill` + recreate a test container, confirm browser re-hydrate restores byte-identical state (diff `/data` before/after).

5. **Make container stateless.** Once metrics show 100% reads served from canister: remove OCI write paths and OCI persistence; switch serve.py vault backend to ephemeral local cache only; **delete `OCI_KEY_B64`/`OCI_VAULT_*` from container env** (eliminates the OCI API-key secret — a security win). Keep OCI buckets read-only archived for a 30-day rollback window, then decommission and remove the OCI SDK code from serve.py.

**Rollback at any step before 5:** set flag back to `mirror`/off; OCI + disk remain authoritative.

---

## 7. New Files + serve.py Integration Points

**New canister (mirror `src/cafresohq_keys`):**
- `src/cafresohq_state/main.mo` — actor implementing the Candid in §2 (~400 LOC).
- `src/cafresohq_state/Sha256.mo` — copied from `cafresohq_keys` (for `setPlan` HMAC verify only).
- *(deferred)* `src/cafresohq_router/main.mo` — principal→shard pin map; add at first watermark trip.

**dfx.json** — add under `canisters`:
```json
"cafresohq_state": {
  "type": "motoko",
  "main": "src/cafresohq_state/main.mo",
  "declarations": { "node_compatibility": true, "output": "frontend/src/lib/declarations/cafresohq_state" }
}
```
`dfx deploy` regenerates `frontend/src/lib/declarations/cafresohq_state/` and updates `canister_ids.json`.

**Frontend:**
- `frontend/src/lib/api/stateActor.js` — clone of `keysActor.js`: per-principal cached `HttpAgent({ identity, host })`, `Actor.createActor(stateIdl, …)`, `fetchRootKey()` on local, `resetStateActor()`.
- `auth.js _adopt` — call `resetStateActor()` alongside `resetKeysActor()`/`lockVault()` on principal change.
- `frontend/src/lib/stores/vault.js` — add canister read/write (chunk/seal/reassemble) per §4-C/§4-A-5, gated by `PUBLIC_STATE_CANISTER`.
- HQ shell state save path — add `putHqDoc` dual-write + conflict/merge per §4-B.

**serve.py integration points (file:line from grounding):**
- `_load_hq_state` (serve.py:1105–1116) — unchanged surface; on cutover it serves the browser-hydrated `/data` cache (browser pulled from canister in §4-A4). No canister client in serve.py.
- `PUT /hq/state/<name>` / `/hq/memory/<name>` (serve.py:5366–5380) — unchanged write surface; additionally **append to the op-log** (`/hq/sync/oplog`) for agent-originated writes (§4-D).
- **New endpoints:** `GET /hq/sync/state` (report local `hqVersion`) and `GET /hq/sync/oplog?since=<seq>` (§4-A2, §4-D12).
- Vault routes (serve.py:5469–5571) — unchanged `PUT|GET|DELETE /vault/blob/<id>` surface; backend switched from OCI/FS to **ephemeral local cache only** at step 5; on `GET` miss, return 404 so the browser hydrates from canister and back-fills (§4-A5).
- OCI config block (serve.py:297–361) and container OCI creds — **deleted** at step 5.
- `USER_PRINCIPAL`/`X-Hq-Principal` (serve.py:362–365) — still used only to gate the local HTTP cache; serve.py never calls the chain.

**Crucially: serve.py never gets a canister client or any canister credential.** All canister I/O is in the browser (`stateActor.js`/`vault.js`).

---

## 8. Open Risks

1. **Offline/agent-only autonomy (the accepted core limitation).** Agent writes while no browser/keeper is open live only in the container's durable op-log until the next browser drain. Durable on disk, but **at risk if the container is destroyed before the first post-recreate flush**. Mitigation: always-on plans run a delegated keeper context; document that recent agent writes are "on-chain on next sync." A scoped per-container delegation is the only full fix and is **out of scope**.
2. **Large-vault upload latency/cost.** A 300 MB object = ~158 sequential ingress update-calls vs one OCI PUT. Needs client progress UI, bounded concurrency, and resume-on-failure (idempotent `(objId,version,ix)` + seal-last makes this safe).
3. **Shared-canister blast radius.** A bug/trap affects all users in a shard. Mitigated by per-user quota + 400 GiB watermark shard split, but a buggy upgrade is still a single point of failure; require staged canary upgrades.
4. **Cross-device concurrency** resolved by LWW-per-record-id; can drop a near-simultaneous field edit. Fine for tasks/notes; **not** for anything needing strong consistency — flag such docs for the browser-direct certified write path.
5. **`setPlanSecret` mirror** (if kept) reintroduces a small rotation-coordination surface (keys canister + state canister). Scoped to quota only, never data; or drop it and trust the browser for quota.
6. **Cold-boot latency** for a user with a large vault is gated by lazy chunked reads; mitigated by on-demand fetch + local cache, but first access to a big file is slower than OCI.
7. **Cycle ops.** Each shard burns storage cycles continuously; needs monitoring + top-up via the existing admin principal, with alerting before the freezing threshold and before 400/500 GiB.

---

**Bottom line:** ship Candidate A's single shared `cafresohq_state` canister and chunked vault, but use Candidate C's browser-only call model so the container holds *no* canister credential at all — the strongest possible answer to the "no II delegation" constraint, at ~$900/mo storage for 10k users with no per-canister float, ~400 LOC of Motoko, and a fully reversible browser-driven migration off OCI.