---
title: Mainnet Deploy
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/mainnet-deploy
  - icp/deployment/mainnet
source:
  - https://internetcomputer.org/docs/building-apps/developer-tools/dfx/
  - https://internetcomputer.org/docs/building-apps/getting-started/deploy-and-manage
  - https://github.com/dfinity/sdk
related:
  - "[[dfx]]"
  - "[[local-replica]]"
  - "[[canisters]]"
  - "[[cycles]]"
  - "[[cycles-wallet]]"
  - "[[principals]]"
  - "[[asset-canister]]"
difficulty: intermediate
open_questions:
  - Current exact `dfx deploy --network ic` cycles-funding behavior — whether new canisters are funded from `dfx cycles` (cycles ledger) by default or still via a registered wallet in the latest dfx release.
  - Current minimum cycles required to create a canister on a 13-node application subnet (NNS-set, drifts over time).
---

# Mainnet Deploy

> Deploying a [[canisters|canister]] to mainnet means creating it on a specific [[subnets|subnet]] of the Internet Computer, installing its Wasm, and registering the [[principals|principal]] of record that will control it thereafter — typically done with `dfx deploy --network ic`.

## Why it exists

A canister running on [[local-replica|the local replica]] is disposable: its ID is local, its cycles are free, and its state disappears with `.dfx/`. A mainnet canister is the opposite — a permanent, publicly addressable object whose control graph, cycle balance, and code lineage all matter. `dfx deploy --network ic` is the transition from "disposable sandbox" to "real on-chain service", and everything about it (who the controller is, where cycles come from, which Wasm goes in) is load-bearing from that point forward.

## How it works

- **Network target** — by default `dfx deploy` targets the local network. `--network ic` (or `--network <named-network>` with an entry in `networks.json`) switches the target to mainnet. All subsequent resolution of canister IDs, controllers, and cycles goes through the mainnet state, not `.dfx/local/`.
- **Identity** — every mainnet call is signed by a [[principals|principal]], derived from the current `dfx identity`. Convention is to create a dedicated mainnet identity (password-encrypted or hardware-backed) rather than reuse the default dev identity. `dfx identity use <name>` switches; `dfx identity get-principal` prints the principal. See [[dfx]].
- **First-deploy create step** — for a canister that does not yet exist on mainnet, `dfx` calls the management canister's `create_canister` with an initial cycles balance and controller list, receives a fresh canister ID (a [[principals|principal]]), and records it in `canister_ids.json` at the project root.
- **Cycles funding** — `create_canister` must be funded from somewhere. Two established paths exist:
  - The **cycles-ledger** path: the dev principal holds cycles on the cycles ledger canister (ICRC-1/2-based); `dfx` creates the canister by spending from that balance. This is DFINITY's current direction for new projects. See [[cycles-wallet]].
  - The **cycles wallet** path: the dev principal owns a personal *wallet canister*; the wallet funds the new canister on the dev's behalf. This is the older pattern and is still supported.
- **Install / upgrade** — after create, `dfx` calls `install_code` with the built Wasm. Subsequent deploys run `install_code --mode upgrade`; an incompatible [[candid|Candid]] surface will fail the upgrade check. `--mode reinstall` exists but wipes canister state and is unsafe in production. See [[upgrade-hooks]].
- **Controllers / principal of record** — at create time, the controller set is usually `{ dev_principal }` (or `{ dev_principal, wallet_principal }` when the wallet is the funder). Controllers can install code, upgrade, stop/start, and delete the canister. They can be changed later via `dfx canister update-settings --controller <principal>`. For SNS handoff or multisig operation, controllers migrate from the dev principal to an SNS Root principal or a multisig canister; see [[sns]].
- **Verify** — `dfx canister --network ic status <name>` returns controller list, module hash, memory size, and cycles balance. `dfx canister --network ic id <name>` prints the canister's principal. Frontend/asset canisters are additionally reachable at `https://<canister-id>.icp0.io`.

## Example

```bash
# One-time: create and switch to a dedicated mainnet identity.
dfx identity new mainnet-deploy --storage-mode password-protected
dfx identity use mainnet-deploy
dfx identity get-principal

# Fund the identity's cycles balance via the cycles ledger (e.g. `dfx cycles convert` from ICP)
# — exact command varies by dfx release; see [[cycles-wallet]].

# Deploy the project to mainnet. First run creates canisters, later runs upgrade.
dfx deploy --network ic

# Confirm.
dfx canister --network ic id my_backend
dfx canister --network ic status my_backend
```

## Gotchas

- **Controllers are power.** The controller set at the moment of `install_code` can replace the canister's Wasm at will. Do not leave a shared CI identity as the sole controller of a production canister; use a dedicated mainnet principal (and plan for rotation).
- **First deploy is irreversible in the sense that matters.** The canister ID it allocates is the one users will reach forever; committing `canister_ids.json` to source control is the idiomatic way to preserve it.
- **Cycle starvation at create time.** A new canister is funded at creation with a fixed initial balance; a busy canister with no top-up mechanism will freeze. Plan a top-up strategy (manual `dfx canister deposit-cycles`, a cycles-ops canister, or CI monitoring) before launch, not after.
- **Principal of the wallet vs. principal of the dev.** When using the wallet pattern, `caller` inside a canister is often the *wallet's* principal, not the dev's. Authorisation logic that compares `caller` to a hardcoded dev principal will reject itself. See [[cycles-wallet]].
- **Candid drift breaks upgrades.** `dfx deploy --network ic` runs upgrade-compatibility checks on the Candid interface; removing a method or narrowing an argument type will fail the upgrade. Version the Candid intentionally.
- **Frontend URLs differ from local.** Mainnet frontend canisters are at `https://<canister-id>.icp0.io`; hard-coded `localhost` URLs from [[local-replica|local]] development will not work. See [[asset-canister]].

## See also

- [[dfx]]
- [[local-replica]]
- [[canisters]]
- [[cycles]]
- [[cycles-wallet]]
- [[principals]]
- [[asset-canister]]
