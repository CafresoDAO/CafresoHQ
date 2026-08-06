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
nothing. `serve.py` (5,147 lines) hard-wires each backend differently:

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
| `gemini-cli` | cli | detection exists; streaming route to be built **against the contract from day one** |
| `hermes` | http | `/hermes/*` proxy + gateway lifecycle + config/env management, all private to the driver |
| `ollama` / `lmstudio` | http | the `ROUTES` relay entries, wrapped to emit contract events |
| `openrouter` | http | `night_runner`'s HTTP client, promoted out of the scheduler into a shared driver both night missions and live tasks use |
| `trial-brain` | http | managed default brain (operator-config gated), same contract |
| `marketplace` | remote | **future, Phase C** — transport is the on-chain job queue (§6) |

## 3. Detection-driven defaults

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
   `gemini_cli.py`.
3. ✅ **done 2026-08-05** — **Hermes last** — most privileged today, most
   plumbing to fold inward. Done-criterion met: zero hermes config/env/gateway
   knowledge outside `drivers/hermes.py` (the four gateway-restart call sites
   collapsed to one `gateway_restart()`; serve.py's /hermes/* routes keep only
   HTTP shape + host policy — trial metering, key-regex/base_url validation).
4. ✅ **done 2026-08-05** — `night_runner` switched from its private HTTP
   client to drivers (llm_call → `run_task_text` over the local-HTTP family;
   groq + gemini-api drivers added so no provider was lost). Bonus: keyless
   LOCAL backends now work for night missions — the old client refused them.
5. Fix the `_re` NameError properly during extraction (module-scope import in
   the extracted module), and stop relying on build-time concatenation order.

Each step ships independently; the UI consumes the contract from step 1 and
never learns backend specifics again.

## 6. The marketplace driver (Phase C sketch)

The "hire an agent from the network" product (North Star §6, Phase C) is **just
another driver** — same manifest, same events, different transport:

- `startTask` → writes a job (with declared budget + capability tier) to the
  `cafresohq_state` job queue; escrow holds payment.
- The operator's worker (evolved search-worker container) claims it, executes
  on their GPU/model, streams events back (relay or poll), submits result.
- `done` → escrow releases; the canister appends to the agent's **résumé
  ledger** (jobs completed, disputes, re-hire rate) — the on-chain reputation
  that makes this a labor market instead of a FLOPs market.
- Privacy boundary from day one: tasks are `private` (own drivers only) or
  `marketplace-ok` (explicitly marked shareable); the vault is structurally
  unreachable from marketplace jobs.

Because approvals, artifacts, XP, and animations all ride the contract, a hired
network coworker looks and behaves exactly like your own — which is the product.

## 7. Non-goals

- **Not an MCP replacement.** MCP tools can later be exposed *through* a
  driver's tool surface; the contract governs agent runtimes, not tools.
- **Ship-to-chain is parked, not forgotten** (founder-flagged 2026-08-05): a
  host tool — `publish(dir) → ICP asset canister` — offered to every driver
  through the same tool/approval surface, so any coworker can deploy what it
  just built to a real on-chain URL after one user approval. Recorded in North
  Star §5; not part of Phase A.
- **Not on-chain inference.** Execution stays where GPUs are (see the serve.py
  ICP-portability audit); canisters hold state, identity, payment, reputation.
- **Not a plugin store (yet).** Third-party driver *code* is out of scope until
  the marketplace's remote isolation model covers it — remote agents are the
  safe third-party surface first.
