# Claude as an operator of CafresoHQ and Obsidian.Computer

Written 2026-11-20. Status: steps 1–3 are in code on `feat/approval-only-sends` (not merged, not deployed).
Everything past that is a plan.

## The one rule everything hangs on

Claude never moves money, deploys, upgrades a canister or votes on its own.
It reads, proposes and prepares; Anthony signs. The office enforces this in code where it can:

- **Sends:** every agent send returns `needsApproval` in the shell (`cafreso-pages`
  `walletServices.js#agentSend`) and opens the signature sheet. The spend cap no longer
  auto-authorizes anything. The transfer is signed by Anthony's Internet Identity in the shell, so
  an agent on its own cannot produce a signature at all.
- **Publishing:** `PUBLISH_SITE` already queues a one-click approval.
- **Deploys and upgrades:** stay manual (`deploy.sh`, `dfx deploy`), run by Anthony.

## What is built (this branch)

1. **Approval-only sends.** The fix to open bug 1 is described above. Approved sends are metered
   with a new state-canister method `recordApprovedSpend(agentId, token, amount)`. It only takes
   effect after `ydacz` is upgraded, and until then the shell's call fails silently.
2. **Claude holds tokens.** The Claude front-desk card (`modals/hire.jsx`, `a_cli_claude`) now
   claims `wallet`. Once the Wallet service is on and a policy exists for that agent in
   Settings → ICP Services, Claude has its own HQ wallet (an agent subaccount of Anthony's
   principal) and can check balances and *ask* to send.
3. **Claude runs the front desk.** Settings → Brain → **Front desk brain** has a new
   `ceoModel` setting. "Let Claude run it" pins the chief of staff to `anthropic:claude-opus-5-5`.
   Use `claudecode:opus` for the subscription instead. When the pin is a Claude brain, the
   chief of staff's system prompt opens by saying it is Claude, an AI made by Anthropic, and that
   sends, deploys and votes wait for the boss.

Chatting with Claude works the way it does with any coworker: DM the Claude agent, or talk to the
front desk once it runs on Claude.

## Turning it on (Anthony's steps)

1. Review and merge the two PRs (CafresoHQ, cafreso-pages); deploy from trunk only.
2. Approve the `cafresohq_state` upgrade for `recordApprovedSpend`. It needs dfx 0.29.1 and
   `--wasm-memory-persistence keep`; check cycles and the 30-day freezing threshold first.
3. In the office: hire Claude from the front desk, enable the Wallet service, set Claude's wallet
   policy, fund it with a small amount, and pin the front desk brain.

## Obsidian.Computer: what "Claude operates it" should mean

The autonomy ladder:

| Level | Claude does | Who acts |
|---|---|---|
| Watch | Health reads: canister cycles (cycles-monitor `--check`, read-only), gateway and desk VM reachability, Storage backups, Linux image version | Claude, no approval |
| Report | A daily status note in the Library, plus a Developer Chat post as a clearly named AI | Claude, no approval once the account exists |
| Propose | Top-ups, restarts, image rollouts, PRs with fixes | Claude drafts, Anthony approves each one |
| Act | Executes an approved item exactly as approved | Anthony's signature or command |

Known operating facts Claude needs (all in the memory index):

- The gateway VM is locked out. The fleet runs from the `ubuntuserver` Hyper-V VM, whose disk is on G:.
  Ask before restarting shared services there.
- Canisters freeze quietly: `cafresohq_state` was wiped twice, and NANAS froze. Watching cycles
  is the highest-value job.
- Every Cafreso Linux desktop already ships `claude` (Claude Code) in `/opt/agents`. So the
  `claudecode:` brain can run inside a member's own desktop, which is the "agents roam free in
  each member's Linux" direction.

## Next build steps, in order

1. **Read-only ops agent.** A scheduled job that runs the health reads above and files
   `Ops/<date>.md` in the Library, with no write access to anything else.
2. **Developer Chat bot account.** A named AI principal that posts the daily note. It needs the
   chat canister's posting API and its own identity, which must not be `ic_admin` or `default`.
3. **Proposals queue.** Ops findings become approval cards in the HQ tray, the same tray sends use.
4. **Votes.** Claude drafts a recommendation per proposal, and Anthony casts the vote unless he sets a
   standing rule in writing.
5. **Own-canister deploys** for members: a per-member canister created from their Internet Identity.

## Not available yet

- The ICP MCP mentioned in the 2026-11-20 handoff was not connected in this session, so nothing
  here depends on it.
- Hosted office (hq.cafreso.com) can't run `claudecode:`, which needs the CLI on the machine. There it is
  `anthropic:` with a key.
