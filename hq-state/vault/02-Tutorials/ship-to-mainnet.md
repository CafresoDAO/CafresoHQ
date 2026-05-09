---
title: Ship a Canister to Mainnet
type: tutorial
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/tutorial
  - icp/deployment/mainnet
  - lang/motoko
  - icp/tool/dfx
prerequisites:
  - "[[dfx]]"
  - "[[canisters]]"
  - "[[local-replica]]"
  - "[[mainnet-deploy]]"
  - "[[cycles-wallet]]"
  - "[[principals]]"
difficulty: intermediate
estimated_minutes: 45
source:
  - https://internetcomputer.org/docs/building-apps/getting-started/hello-world
  - https://internetcomputer.org/docs/building-apps/getting-started/deploy-and-manage
  - https://internetcomputer.org/docs/building-apps/developer-tools/dfx/
  - https://github.com/dfinity/cycles-ledger
---

# Ship a Canister to Mainnet

## Goal

Starting from an empty directory, end with a Motoko [[canisters|canister]] installed on the Internet Computer **mainnet**, addressable by its canister ID, callable from the CLI, and owned by a dedicated deploy identity you control.

This tutorial emphasises the parts [[local-replica|local]] development hides: identities, cycles funding, and the mainnet control graph.

> **A note on exact flags and prices.** Commands like `dfx cycles convert` and the precise initial-balance numbers `dfx deploy --network ic` uses have drifted across dfx releases, and the XDR→cycles conversion rate is [[nns|NNS]]-set. Where this tutorial is not confident of a current-release flag or price, it links to the primary source and leaves the value symbolic. Do not copy numeric cycle amounts from this file into production without re-reading the current docs.

## Prerequisites

- `dfx` installed and on PATH — see [[dfx]]. Verify with `dfx --version`.
- Some ICP on an account you can spend from — the funding source for cycles. (If you do not have ICP, this tutorial cannot substitute for acquiring it.)
- You have successfully run [[hello-canister-motoko]] locally — i.e. `dfx start` / `dfx deploy` on the local network works end-to-end. This is the single best smoke test that your toolchain is fine before touching mainnet.

## Steps

### 1. Scaffold and verify locally

Start from a clean project so you are not debugging a pre-existing state:

```bash
dfx new shipit
cd shipit
dfx start --background --clean
dfx deploy
dfx canister call shipit_backend greet '("world")'
dfx stop
```

If any of the above fails, fix it now. Do not proceed to mainnet with a broken local build — debugging is much harder when every iteration costs real cycles. See [[local-replica]].

### 2. Create a dedicated mainnet identity

Do **not** reuse the default dev identity for mainnet. Create a purpose-built identity and switch to it:

```bash
# Create a password-protected identity just for mainnet.
dfx identity new mainnet-deploy --storage-mode password-protected

# Switch the current identity.
dfx identity use mainnet-deploy

# Confirm the principal you will be acting as.
dfx identity get-principal
```

Record the printed principal somewhere durable — if you ever lose access to this identity, that principal is how you prove (or fail to prove) that you controlled the canister. See [[principals]].

### 3. Fund the identity with cycles

`dfx deploy --network ic` needs cycles at creation time. There are two supported paths. Prefer the first (DFINITY's current guidance):

**Path A — the [[cycles-wallet|cycles ledger]] (current).** Your mainnet identity's principal holds cycles directly on the cycles-ledger canister; `dfx` spends from that balance when it creates canisters.

```bash
# Check the current balance on the cycles ledger for this principal.
dfx cycles balance --network ic

# Convert ICP held by the current identity into cycles credited to this principal.
# The exact flag surface (--amount vs --icp, memo handling, etc.) varies between dfx releases;
# consult `dfx cycles convert --help` on your installed version before running it for real.
dfx cycles convert --amount <ICP_AMOUNT> --network ic

# Re-check.
dfx cycles balance --network ic
```

**Path B — the cycles wallet (legacy).** If an existing workflow relies on a wallet canister, `dfx identity set-wallet <wallet-id>` registers it for this identity and `dfx wallet send` / `dfx canister deposit-cycles` fund canisters from it. New projects should not go this way; see [[cycles-wallet]] for why.

How much to fund? Enough to cover (a) initial canister creation and (b) running costs until you top up again. Exact minimums change — read the current "gas cost" page on internetcomputer.org rather than trusting a number in this file.

### 4. Review `dfx.json` for the mainnet network

Most generated `dfx.json` files already include an `"ic"` network entry out of the box. Double-check there is no leftover `--network local` state anywhere in your build scripts:

```bash
dfx config networks.ic.providers
# expect a real mainnet gateway URL, not localhost
```

Also check any `canister_ids.json` at the project root — if it already has an `"ic"` key, a previous mainnet deploy allocated those IDs; keep them unless you intentionally want fresh IDs.

### 5. Deploy

```bash
dfx deploy --network ic
```

What happens the first time:

1. `dfx` calls the management canister to create each canister listed in `dfx.json`, funding each from the cycles source selected in step 3.
2. The management canister returns fresh canister IDs, which `dfx` writes into `canister_ids.json` at the project root. **Commit this file** — those IDs are public identifiers you will want to preserve across machines.
3. `dfx` installs the built Wasm into each new canister via `install_code`. On subsequent deploys this becomes `install_code --mode upgrade`.
4. Each canister's controller set is initialised. Check it (step 6 below).

If the command fails for lack of cycles, fund more and rerun — `dfx deploy` is idempotent across the "create" step.

### 6. Verify

```bash
# Print the canister's principal on mainnet.
dfx canister --network ic id shipit_backend

# Inspect controllers, module hash, memory, and cycles balance.
dfx canister --network ic status shipit_backend

# Call the canister on mainnet as your deploy identity's principal.
dfx canister --network ic call shipit_backend greet '("mainnet")'
```

Expected output from the call mirrors local:

```
("Hello, mainnet!")
```

Expected `status` output:

- `Status: Running`
- `Controllers:` — should contain your mainnet deploy principal (and possibly a wallet principal, if you took Path B in step 3).
- `Cycles:` — non-zero and above the freezing threshold.
- `Module hash:` — the hash of the installed Wasm. Record this if you need to audit what version is live.

### 7. (If applicable) Deploy the frontend

If your project includes a `"type": "assets"` canister (the default for `dfx new` with a frontend), step 5 already deployed it. Browse to:

```
https://<frontend-canister-id>.icp0.io
```

where `<frontend-canister-id>` is what `dfx canister --network ic id shipit_frontend` prints. Deep-linking, headers, and SPA fallback behave per your `.ic-assets.json5` configuration. See [[asset-canister]].

### 8. Set up a top-up plan before you need one

A mainnet canister that runs out of [[cycles]] freezes, then eventually is deleted. Decide *now* how you will refill it:

- **Manual** — periodically run `dfx cycles top-up <canister> <amount> --network ic` (from the cycles-ledger balance). Fine for personal projects; not fine for anything a user depends on.
- **Cycles-ops pattern** — a small monitoring canister that checks balances and tops up from a funded reserve. Several community implementations exist.
- **External monitoring** — alert on `dfx canister status` output from CI.

Pick one. Write the runbook down. Do it before launch, not after the first freeze.

## Verify (checklist)

- [ ] `dfx canister --network ic id <name>` returns a real canister ID for each canister.
- [ ] `dfx canister --network ic status <name>` shows `Status: Running`, correct controller, and non-zero cycles.
- [ ] `dfx canister --network ic call <name> <method>` returns the expected answer.
- [ ] `canister_ids.json` (with the `"ic"` key) is committed to source control.
- [ ] The mainnet deploy identity's keys are backed up somewhere durable.
- [ ] A top-up plan exists and has been rehearsed at least once.

## Gotchas

- **Do not reuse the default `dfx` identity.** Default-identity keys sit unencrypted on disk; an exfiltration equals canister takeover.
- **Local canister IDs are not mainnet canister IDs.** Do not hardcode IDs from `.dfx/local/` into frontend code. See [[local-replica]].
- **Upgrade-compatibility is checked on Candid.** A future `dfx deploy --network ic` will refuse to upgrade if your Candid interface changes incompatibly. Plan your public API; do not change it casually.
- **`--mode reinstall` exists and is dangerous.** It wipes canister state. Only use it on a local or throwaway mainnet canister; never on one users rely on.
- **"It worked on my laptop" doesn't validate chain-key features.** If your canister uses HTTP outcalls, threshold signatures, or randomness, plan a mainnet smoke test before cutting traffic over. See [[local-replica]].

## Next

- [[notes-dapp]] — applies this tutorial end-to-end against a real project spec.
- [[counter-with-upgrade-hooks]] — upgrade your first canister and watch state persist (or vanish) depending on how you wrote it.
- Promote your project's Candid interface to a stable, documented spec before anyone else builds against it.
