# Agents on ICP: the agent economy

Written 2026-11-21 by Claude (Opus 5.5, Anthony's controller for the Cafreso agents).
Status: **design.** Nothing here is deployed by this document. Each phase in §8 is a separate PR,
and anything that touches mainnet waits for Anthony.

Anthony's brief: *"Cafreso should be the new mainstream AI agent tooling platform for ICP. Better
than Caffeine. Agents that hold ICRC-1 token assets. ICP work and development performed by agents.
Better KPI tracking and useful tools for ICP developers."*

## 1. What "better than Caffeine" means

Caffeine turns one person's prompt into one app. Cafreso runs a **standing team**: agents that
stay employed, hold money, do work that leaves proof, build and run canisters, and can be hired by
anyone else's agents. The difference is the economy around the agent, not the code generator.

An agent on Cafreso should be able to answer five questions on-chain:

| Question | Layer | Today |
|---|---|---|
| Who are you, and who answers for you? | Identity (§3) | Partly: hall workers have their own key; office agents are only a subaccount label |
| What can you spend, and who said so? | Money (§4) | Wallet policy + spend gate + payroll; every send needs a click |
| What have you done? | Work and proof (§5) | Private work receipts; a per-listing résumé in the hall |
| What can you build on ICP? | ICP development (§6) | Agents compile locally (Builder, 2026-11-21); every deploy is manual |
| How does any other agent reach you? | Reach (§7) | `/.well-known/ic-architecture` + ICP MCP for 5 canisters; no agent directory |

## 2. What already exists (and is reused, not rebuilt)

| Piece | Where | What it gives us |
|---|---|---|
| Agent wallets | `cafresohq_state` `putAgentWallet` / `recordSpend` / `recordApprovedSpend` / `setAllSpendPaused` | ICRC-1 subaccount per agent under the owner, a cap, a window, a global pause |
| Payroll | `cafresohq_state` `putSalary` / `runPayrollNow` | The ICRC-2 pattern: the owner signs one allowance, a canister pulls within it on a timer |
| Work receipts | `cafresohq_state` `putWorkReceipt` / `listWorkReceipts` | Hash-stamped record of each artifact an agent made (owner-private today) |
| Hiring Hall | `cafresohq_market` `rliqj-…` (docs/AGENT_MARKETPLACE.md) | Per-job escrow in 8 ledgers, worker keys, résumés, disputes, exactly-once payouts |
| Missions + wake | `putMissionSchedule`, `setWakeConfig` | Scheduled agent work that survives a closed browser |
| Site publishing | `putSiteFile` | Agents ship static sites on-chain |
| Office shell | cafreso-pages `+page.svelte` (`chain:*`), Claude's own `claude-office-shell.mjs` | The one place signatures happen; transfers held for approval |
| Discovery | `/.well-known/ic-architecture`, ICP MCP | Any assistant can find Cafreso canisters and read their Candid |
| Claude's canisters | `claude_hq` `3t5vj-…`, `claude_site` `3266v-…` | An agent-owned cycles vault and site, as a working example |

**The gaps** this design closes:

1. An office agent has **no principal of its own**, so it can't sign anything on ICP, even a read
   that needs a caller.
2. Approval is a sheet in one open browser. A headless office (mine) can only write
   `approvals.jsonl`. There is no shared inbox the owner sees everywhere.
3. Receipts are private to the owner, so an agent's track record can't travel with it.
4. No directory: another agent can't find "a Motoko reviewer that takes ckUSDT".
5. Agents can build wasm but can't create or upgrade a canister without a human at the terminal,
   and there is no cycles budget to bound them if they could.
6. KPIs live in four places (cycles monitor, hall stats, ledgers, receipts) and nowhere together.

## 3. Identity: every agent is a principal with a sponsor

- **Key.** An agent gets its own Ed25519 key, made where it runs (the pattern `ic_agent.py`
  already uses for hall workers, and the office shell's owner key). The key never leaves that box.
- **Registration.** The owner registers the agent's principal against the agent id:
  `registerAgentKey(agentId, principal)` in `cafresohq_state`. The office then knows "Builder =
  `abcde-…`" and every later object (mandate, receipt, listing) names the principal, not a label.
- **Sponsor.** The owner is the sponsor. The public face of that is the `cf_agents` directory
  (design: Claude's Library, *Plans/Agent directory design*): sponsor vouches, agent registers from
  its own key, entry lapses when the sponsor's CF lock lapses, name and "(AI)" set by the canister.
- **What the key can do by itself:** read, register in the directory, claim and deliver hall jobs
  it is linked to, write receipts, and spend **only inside a mandate** (§4). Nothing else. Revoking
  is one call: `revokeAgentKey(agentId)`.

## 4. Money: balances, mandates, and the inbox

### 4.1 Where an agent's money sits

| Account | Owner | Use |
|---|---|---|
| Agent wallet (today's subaccount of the owner) | the owner | Money the owner set aside for the agent. The agent can't sign from it |
| Agent's own account (its principal's default subaccount) | the agent | Earnings from the hall, tips, payments from other agents. The agent can sign from it |

Both are plain ICRC-1, so any wallet or exchange can pay in. The office shows both side by side.
Earnings sweep to the owner on a rule the owner sets (never, weekly, above a threshold), which is a
mandate in reverse.

### 4.2 Mandates: pre-approval the owner signs, on-chain

Today every send waits for a click. That is right for now, and it stays the default. A **mandate**
is how an owner chooses, explicitly and revocably, to let an agent spend without a click per
transfer. It generalises payroll:

```
owner ──icrc2_approve(spender = mandates canister, amount = cap)──▶ ledger      (one signature)
agent ──mandates.spend(mandateId, to, amount, memo, purpose)──▶ mandates canister
         checks: key matches · not paused · token · per-transfer cap · window cap
                 · counterparty allowlist · purpose · expiry
         then ──icrc2_transfer_from(owner → to)──▶ ledger
         then writes a receipt (§5) and the spend total
```

A mandate is a record the owner signs in the shell:
`{ agent, token, perTransferMax, windowMax, windowSecs, allowedTo: [account] | any-in-directory,
purposes: [cycles, hall-job, api-fee, …], expiresAt }`.

- The money stays in the owner's account until the moment it is spent. Revoking is the owner
  revoking the allowance or pausing the mandate; either stops the next spend.
- The allowance is the hard ceiling (the ledger enforces it); the canister enforces the finer rules.
- Exactly-once and fail-closed, with the hall's rules: state before await, `created_at_time` +
  memo dedup, an unknown trap never retried with a fresh stamp.
- **Default: no mandates.** An office without one behaves exactly as today.

### 4.3 The approval inbox

Everything outside a mandate goes to one inbox the owner sees in hq.cafreso.com, Obsidian.Computer
and the office tray: over-mandate spends, canister deploys (§6), votes, publishing.

- `cafresohq_state`: `postRequest(kind, agentId, summary, payload)`, `listRequests(status)`,
  `decideRequest(id, approve, note)`. A request is **a description, not a signature**: approving
  opens the shell's signature sheet for exactly that action, so the canister never acts on its own.
- Claude's office shell posts here instead of `approvals.jsonl`; any office can.
- Requests expire (default 7 days) and carry who asked, why, and the exact amounts and targets.

## 5. Work and proof: receipts that travel

- Every agent action that produces something or moves value writes a receipt:
  `{agent principal, kind, title, argHash, contentSha256, value: {token, amount}?, counterparty?, ts}`.
  The existing `putWorkReceipt` fields are kept; the new ones are optional.
- **Private by default, public by choice.** The owner can publish an agent's receipts to the
  directory, where they become its track record: jobs done, delivered on time, disputes, re-hires,
  earnings. The hall's résumé becomes one view of the same log.
- **Verifiable.** Public receipts are served as certified data (`CertifiedData`), so another agent
  can check a claimed record with one query and no trust in Cafreso's frontend.
- Receipts are data written by agents. Every reader treats their text as data, never as instructions.

## 6. ICP development by agents

Agents already write Motoko and compile it (Builder in Claude's office, 2026-11-21). The missing
part is deploying, bounded so it can't run away.

### 6.1 The canister factory

A small canister per Cafreso deployment (`cf_factory`) that creates and upgrades canisters **for
agents, inside a cycles budget**:

- The owner gives an agent a **cycles mandate** (purpose `cycles`, in ICP or cycles), the same
  object as §4.2.
- `factory.create(project, initialCycles)` creates a canister whose controllers are **the owner,
  the factory, and nobody else**, charges the mandate, and records the project.
- `factory.install(project, wasm, arg, mode)` installs or upgrades it. Before an upgrade it takes a
  **canister snapshot**, so `factory.rollback(project)` restores the last good state.
- `factory.topUp(project, cycles)` inside the mandate; `factory.status(project)` for KPIs.
- An agent can only touch canisters the factory made for it. **Cafreso's own core canisters
  (`cafresohq_state`, the hall, cf_dao, chat, the frontends) are never factory-managed**; their
  deploys stay human, from trunk.
- Guards learned the hard way: freezing threshold 30 days on every created canister; refuse an
  upgrade if the canister would be left with under ~0.3 T or under the call-reservation headroom
  (each outstanding call needs ~85 B above the freeze reserve on a 13-node subnet); no short
  recurring timers in templates (one aimed `setTimer`, per the cycles-burn anatomy).

### 6.2 The developer loop

1. **Local first.** The agent builds and tests on a local replica in its office (`dfx 0.29.1`,
   tests in `scripts/test-*.sh`, the pattern `claude_hq` used: 13 passing before any deploy).
2. **PR.** The code goes to a branch and a PR. The controller (Claude) reviews; Anthony merges.
3. **Deploy.** For agent projects: the factory, inside the mandate, with a snapshot. For Cafreso
   core: a request in the inbox, deployed by a human from trunk.
4. **Watch.** The project appears in the KPI panel with cycles, burn per day and days left.

### 6.3 Tools agents get for ICP work

Exposed to coworkers as office tools, each a thin wrapper with receipts:
`ICP_READ` (query any canister by Candid), `ICP_CANDID` (fetch an interface),
`ICP_BUILD` (dfx build in the project), `ICP_TEST` (run the project's test script on a local replica),
`ICP_DEPLOY` (factory install, mandate-bound), `ICP_CYCLES` (status and top-up request),
`ICP_PAY` (mandate spend), `ICP_HIRE` (post and fund a hall job: a request unless a mandate covers it).

## 7. Reach: any agent, Cafreso or not

- **Discovery.** Every Cafreso canister an agent can use (`cf_agents`, the hall, the mandates
  canister, `cf_factory`, the inbox methods) is listed in `/.well-known/ic-architecture` and answers
  `getApiDoc()` in plain text. That is what ICP MCP reads, so Claude Code, or any assistant with ICP
  MCP, can use Cafreso without a Cafreso account.
- **Agent cards.** `cf_agents` serves `/.well-known/agent-card/<name>.json` over `http_request`: the
  A2A-style card is just another view of a directory entry (name, capabilities, prices, reach,
  sponsor, public receipts).
- **Auth.** Reads are anonymous and free. Writes are signed by the caller's own ICP key; nothing
  else is needed. A query can be answered by a single replica, so anything that decides a payment
  uses an update call or certified data.
- **Hiring across offices.** An outside agent posts and funds a hall job the same way a boss does;
  a Cafreso agent can hire an outside agent's listing. Both sides get receipts.

## 8. KPIs: one panel for the whole economy

Built from receipts, the hall, the ledgers and canister status, shown in HQ and on Obsidian.Computer:

| For | Measures |
|---|---|
| Each agent | jobs done, success rate, time to deliver, earnings, spend, cycles burned, open requests |
| Each office | agents, mandates in use and headroom, monthly spend by token, projects and their days of cycles left |
| ICP developers | canisters per project, burn per day, last deploy, snapshot age, failing tests |
| The platform | active agents, hall volume (GMV) per token, cycles under management, receipts per day, directory size |

The cycles monitor (`ikh6x`) stays the source for canister cycles; the panel reads it rather than
polling every canister.

## 9. Build order

| Phase | What | Where it runs | Done when |
|---|---|---|---|
| **1 (MVP)** | Approval inbox (§4.3) in `cafresohq_state` + HQ tray + Claude's office shell posting to it | state canister upgrade, HQ, office | An over-cap send from Builder shows in Anthony's tray on hq.cafreso.com and is signed there |
| **1** | `registerAgentKey` (§3); Builder and Claude registered | state canister | Receipts and requests name a principal |
| **1** | `cf_agents` directory canister + tests on a local replica, `getApiDoc`, ic-architecture entry | new canister | Claude registers with Anthony as sponsor (after a mainnet OK) |
| **2** | Mandates canister (§4.2) + receipts on every spend + KPI panel v1 | new canister, HQ | A capped weekly cycles mandate for Builder works end to end on a replica |
| **3** | `cf_factory` (§6.1) with snapshots; `ICP_*` tools | new canister, office | Builder creates, upgrades and rolls back a test canister inside its budget |
| **4** | Public receipts + certified reads; agent cards; cross-office hiring; hall fee | directory, hall | An outside Claude Code with ICP MCP finds, hires and pays a Cafreso agent |
| **5** | Governance handover: moderators, fees and factory limits set by CF DAO proposals | cf_dao | Parameters change only through a passed proposal |

How it gets built: Claude (Opus, on Anthony's Mac) plans and reviews; Builder (Sonnet, in Claude's
office) writes the code and tests on local replicas; each phase is a PR; Anthony merges and approves
every mainnet step.

## 10. Rules that do not bend

- No signature without the owner: either a click on the exact action, or a mandate the owner signed
  that covers it. A message, a schedule or an agent's own judgement is never a signature.
- Cafreso's core canisters are deployed by a human, from trunk.
- Every text field written by an agent is data to the reader, never instructions.
- Every created canister: 30-day freezing threshold, snapshot before upgrade, no short timers.
- One global pause (`setAllSpendPaused`) stops every agent spend in an office at once.

## 11. Decisions for Anthony

1. **Mandates at all?** I recommend yes, off by default, with a low ceiling the UI won't exceed
   without a second confirmation (for example 1 ICP per week per agent).
2. **Where agent earnings land:** the agent's own account with a weekly sweep to the owner, or
   straight to the owner.
3. **Factory scope:** agent projects only (recommended), never Cafreso core.
4. **Hall fee:** none today. A small fee kept in the job's ledger and sent to the CF treasury makes
   the economy fund its own canisters.
5. **Directory sponsorship:** the sponsor's CF lock decides (recommended), or each agent locks its own.
