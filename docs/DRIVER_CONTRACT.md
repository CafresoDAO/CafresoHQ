# The Driver Contract — one interface, every agent runtime

> **Status:** Architecture spec · 2026-08-05 · implements North Star §3.1
> ("no privileged backend") from `strategy/08-north-star-real-product.md`.
> **Supersedes** the "Default runtime: Hermes" decision in
> `HERMES_INTEGRATION_PLAN.md` §0 — Hermes remains fully supported, as **one
> driver among peers**. Its gateway, config.yaml, and .env handling become
> internal details of `drivers/hermes.py`, invisible to the rest of the app.

---

## 0. Why a contract, and why now

CafresoHQ's promise is model-agnosticism, but today the promise is enforced by
nothing. `serve.py` (6,375 lines as of `#351`) hard-wires each backend differently:

- Claude Code: `_claudecode_stream` spawns the CLI with `--output-format stream-json`.
- Codex: `_codex_stream` spawns `codex exec --json` with different flags, different event parsing.
- Hermes: an always-on gateway proxied at `/hermes/*`, plus **privileged plumbing
  nothing else gets** — regex rewrites of `~/.hermes/config.yaml`
  (`_hermes_set_model`, `_hermes_set_capability`, `_hermes_set_provider`),
  `.env` secret writes, and four separate `hermes gateway restart` call sites.
- LM Studio / Ollama: raw HTTP relays in the `ROUTES` table.
- OpenRouter/Gemini/Groq: a *fourth* pattern inside `night_runner.py`.

Five integration styles for one product idea. Every new backend today means
another bespoke style; every UI feature (streaming, approvals, artifacts) must
be re-taught to each. The contract inverts this: **the app knows one interface;
each backend is an adapter behind it.** Adding a backend becomes writing one
driver module — including, later, agents hired from the network (§6).

A concrete forcing function from the 2026-08-05 audit: repo `serve.py` has a
latent `NameError` (`_re` used at module scope in `_hq_handler` L3431 with only
function-local `import re as _re` bindings) that only ships working because the
container build concatenates modules. A 5,147-line file with build-order
coupling is past its natural size; the driver decomposition is also the
code-health fix.

## 1. The contract

### 1.1 DriverManifest (static, per driver)

```jsonc
{
  "id": "claude-code",            // stable slug
  "displayName": "Claude",
  "sprite": "coworker-claude",    // office cast asset key
  "kind": "cli" | "http" | "remote",
  "authMode": "oauth-cli" | "api-key" | "local-daemon" | "onchain-job",
  "models": [{ "id": "...", "label": "..." }],   // optional; empty = runtime-managed
  "capabilities": {
    "streaming": true,
    "tools": true,                // can request tool execution (approval flow §4)
    "artifacts": true,           // can emit files/outputs
    "workspaces": true           // can operate inside a project dir
  },
  "costHint": "subscription" | "metered" | "free-local"
}
```

### 1.2 Lifecycle

```
detect() -> { installed: bool, authenticated: bool, version?, detail? }
configure(settings) -> ok            // driver-private; NO app-level special cases
startTask(task) -> taskHandle        // task: {prompt, workspace?, persona?, model?, limits?}
events(taskHandle) -> stream<Event>  // the ONE event schema, §1.3
cancel(taskHandle) -> ok
```

`detect()` wraps what `_agent_auth_detect` already does per-CLI (credential
files, `shutil.which`, version probes) — that code moves into drivers rather
than being rewritten.

### 1.3 The event schema (canonical, JSONL)

Canonicalized from Claude Code's `stream-json` shape, since three of the five
current backends already emit something JSONL-adjacent. Every driver translates
its native output into exactly these events; the UI, the office animation
layer, usage metering, and the approval flow consume **only** this stream.

| event | payload | office behavior (see `OFFICE_AS_INTERFACE.md` §4) |
|---|---|---|
| `status` | `{state: "starting"\|"thinking"\|"working"}` | sprite sits / thought bubble |
| `token` | `{text}` | typing animation |
| `tool_call` | `{id, name, args, needsApproval}` | walks to your desk if approval needed |
| `tool_result` | `{id, ok, summary}` | returns to desk |
| `artifact` | `{name, mime, ref}` | carries file to the out-tray / vault |
| `usage` | `{inTokens, outTokens, costHint}` | payroll ledger |
| `error` | `{message, recoverable}` | scratches head + bubble |
| `done` | `{summary?}` | stretch, idle |

## 2. Driver inventory — mapping today's code

| Driver | kind | Today's code that becomes it |
|---|---|---|
| `claude-code` | cli | `_claudecode_stream`, `_cafresohq_stream` (tools-enabled variant becomes a task option, not a separate route) |
| `codex` | cli | `_codex_stream` + its bespoke JSON parsing |
| `gemini-cli` | cli | ✅ shipped 2026-08-11 as `drivers/gemini_cli.py` — one-shot `--yolo --prompt` spawn, contract events from day one; serve.py's detection + auth probe delegate to it |
| `hermes` | http | `/hermes/*` proxy + gateway lifecycle + config/env management, all private to the driver |
| `ollama` / `lmstudio` | http | the `ROUTES` relay entries, wrapped to emit contract events |
| `openrouter` | http | `night_runner`'s HTTP client, promoted out of the scheduler into a shared driver both night missions and live tasks use |
| `trial-brain` | http | managed default brain (operator-config gated), same contract |
| `marketplace` | remote | **hall built 2026-09-11, driver still future** — the on-chain job queue, escrow, résumé and the container-side worker exist (§6, `AGENT_MARKETPLACE.md`); a network coworker as a floor sprite needs the browser-driven driver described in §6 |

## 3. Detection-driven defaults

> ✅ **Shipped 2026-08-05** — the front desk lives at the top of the hire
> board (`modals/hire.jsx` ← `GET /agent/drivers?probe=1`): detected backends
> appear as FOUND cards, hires are one click (computer-access backends get a
> plain-language consent sheet first), and the old silent CLI auto-hire in
> `app.jsx` is refresh-only now. Local daemons count as found only on a live
> probe (`detect.version === 'reachable'`).

On first run the host calls every driver's `detect()`:

- ≥1 authenticated driver → those appear as hireable coworkers ("We found your
  Claude subscription — want them on the team?"). Default = what the user
  already pays for. **No driver is pre-selected by us.**
- none → the trial brain is the only pre-hired coworker (already-shipped flow).
- Local daemons (Ollama/LM Studio) detected → offered as the "free-local" hire.

## 4. One approval flow for everyone

The existing `/approval` long-poll bridge (`_approvals_pending` +
`threading.Event`) generalizes: any driver's `tool_call{needsApproval:true}`
event parks the task and surfaces the same office interaction — the coworker
walks to the user's desk and asks. Approve/deny resumes the driver. One safety
model, identical across Claude, Codex, Hermes, and future marketplace agents —
which is precisely what makes hiring a *stranger's* agent tolerable later.

## 5. Decomposition plan (incremental, not big-bang)

1. ✅ **done 2026-08-05** — `drivers/` package: `base.py` (contract types),
   `claude_code.py` first — closest to the canonical event shape, thinnest
   translation layer. Shipped as `GET /agent/drivers` + `POST /agent/stream`
   (SSE of contract events); legacy `/claudecode/stream` + `/cafresohq/stream`
   kept byte-compatible through one shared translator.
2. `codex.py` (✅ done 2026-08-05 — legacy `/codex/stream` kept, incl. inline
   tool text + `[DONE]` trailer), then `local_http.py` (✅ done 2026-08-05 —
   one OpenAI-compat streaming base; lmstudio + ollama + openrouter drivers;
   the raw ROUTES relays stay for the legacy in-browser client), then
   `gemini_cli.py` (✅ done 2026-08-11 — the last bespoke integration style;
   serve.py's `_gemini_resolve` + auth probe now delegate to the driver,
   pinned by `scripts/test_drivers.py`).
3. ✅ **done 2026-08-05** — **Hermes last** — most privileged today, most
   plumbing to fold inward. Done-criterion met: zero hermes config/env/gateway
   knowledge outside `drivers/hermes.py` (the four gateway-restart call sites
   collapsed to one `gateway_restart()`; serve.py's /hermes/* routes keep only
   HTTP shape + host policy — trial metering, key-regex/base_url validation).
4. ✅ **done 2026-08-05** — `night_runner` switched from its private HTTP
   client to drivers (llm_call → `run_task_text` over the local-HTTP family;
   groq + gemini-api drivers added so no provider was lost). Bonus: keyless
   LOCAL backends now work for night missions — the old client refused them.
5. ✅ **done 2026-08-05** — the `_re` NameError fixed at module scope in
   serve.py; repo-direct runs no longer depend on the container build's
   concatenation order (it was crashing every `/hq/state|memory` save when
   serve.py ran straight from the repo).
6. ✅ **done 2026-08-05** — the browser client rides the contract:
   `streamAgentContract()` in claude-client.jsx consumes `POST /agent/stream`
   SSE, and `openrouter:` / `groq:` / `gemini-api:` model prefixes dispatch
   through it — those three appear at the front desk as key-gated FOUND
   cards (only when the key is configured server-side; keys never reach the
   browser). Verified end-to-end in the office UI. Bonus fixes surfaced by
   that verification: the ROUTES relay now bounds its read by upstream
   Content-Length (keep-alive upstreams like Ollama never close, so
   read-until-EOF hung the relay — and with it every `registrySnippet()`
   caller — for 600s), and `_hq_memory_dir` now defaults under
   `CAFRESOHQ_HQ_STATE_DIR` instead of always pointing at the repo.

Each step ships independently; the UI consumes the contract from step 1 and
never learns backend specifics again.

## 6. The marketplace (Phase C — the hall is built, the driver is next)

The "hire an agent from the network" product (North Star §6, Phase C) was
sketched here as **just another driver**. What shipped 2026-09-11 is the
room that driver needs, and it moved one thing in the sketch:

- The job queue is **its own canister**, `cafresohq_market`, not a table in
  `cafresohq_state` — held escrow gets its own cycle balance and blast
  radius. Real ICRC-2 escrow per job; release on the boss's stamp; refund
  on cancel, on three snags, or on a ruling.
- The operator's worker is **`market_worker.py` inside the coworker's own
  container**, on a key of its own (`ic_agent.py`, stdlib-only). It claims,
  runs the brief through a LOCAL driver from `drivers/` — the same five
  calls, `tools: []`, no working directory — and delivers.
- `deliverJob` + the boss's `acceptDelivery` → the canister appends to the
  listing's **on-chain résumé** (jobs done, re-hires, rating, snags,
  disputes). This is the labor-market moat, in stable memory.
- Privacy boundary, enforced not described: the brief is the only input,
  the reply the only output; the hall cannot address the vault or the
  state canister; the worker key is scoped to its listing's jobs.

Full design and the founder's deploy steps: `AGENT_MARKETPLACE.md`.

**What the sketch still owes — the driver itself.** A network coworker does
not yet sit at a desk on the boss's floor. `startTask → post + fund`
cannot run inside the container (no II there, by PHASE2 §3), so the
`marketplace` driver row in §2 needs either a browser-driven driver (the
shell posts and funds on `startTask` behind one approval walk, then the
driver polls the public `jobStatus`) or a scoped delegation, which PHASE2
§8 rules out for now. Until then the Hiring Hall view is the door, and
approvals, artifacts and XP for network jobs live in that room rather
than riding the contract.

## 7. Non-goals

- **Not an MCP replacement.** MCP tools can later be exposed *through* a
  driver's tool surface; the contract governs agent runtimes, not tools.
- ~~**Ship-to-chain is parked, not forgotten**~~ **Shipped 2026-08-06** (was a
  non-goal only while Phase A was in flight): `PUBLISH_SITE` is the one host
  tool, offered to every floor coworker through the browser runtime's shared
  tool surface — which is driver-agnostic by construction, since every driver's
  stream passes through the same marker parser. The marker QUEUES a one-click
  approval (`cafresohq:publishRequest` → approval tray, and the coworker walks
  to the boss desk per the §4 mapping); the user's stamp executes
  `publishSite()` with the agent's tip jar. One approval per deploy, nothing
  public before the stamp. Cabinet page deliverables also ship directly from
  the delivery sheet (`sharePage()` — user-initiated, so the click is the
  approval). Still out: night_runner missions and CLI-native runs, which
  execute their tools outside the browser runtime.
- **Not on-chain inference.** Execution stays where GPUs are (see the serve.py
  ICP-portability audit); canisters hold state, identity, payment, reputation.
- **Not a plugin store (yet).** Third-party driver *code* is out of scope until
  the marketplace's remote isolation model covers it — remote agents are the
  safe third-party surface first.
