---
title: dfx
type: concept
status: stable
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/tool/dfx
source:
  - https://internetcomputer.org/docs/building-apps/developer-tools/dfx/
  - https://github.com/dfinity/sdk
related:
  - "[[canisters]]"
  - "[[local-replica]]"
  - "[[mainnet-deploy]]"
  - "[[motoko]]"
  - "[[rust-cdk]]"
  - "[[cycles]]"
  - "[[cycles-wallet]]"
  - "[[principals]]"
  - "[[candid]]"
  - "[[asset-canister]]"
difficulty: beginner
open_questions:
  - Current stable `dfx` version and its default Motoko toolchain — pin both in CI.
  - Exact current `dfx cycles` subcommand surface (convert / top-up / transfer flags) — drifts with releases.
---

# dfx

> `dfx` is the ICP command-line toolchain — it scaffolds projects, builds Wasm, runs a [[local-replica]], manages identities, and installs/upgrades [[canisters]] on local or mainnet networks.

## Why it exists

Building a canister involves compiling Wasm, generating Candid, creating/ installing/ upgrading with the management canister, and signing requests as a [[principals|principal]]. `dfx` is the glue that wraps those steps into one tool so developers don't assemble them by hand.

## How it works

- **Project scaffold** — `dfx new <name>` generates a project with `dfx.json` (the build/deploy manifest), a backend canister, and typically a frontend asset canister.
- **Local replica** — `dfx start` boots a single-node local replica plus supporting services; `dfx stop` tears it down. See [[local-replica]].
- **Build** — `dfx build` reads `dfx.json`, invokes the right compiler (Motoko, cargo for Rust, etc.), and produces a Wasm module plus a [[candid|Candid]] interface per canister. `dfx canister metadata <id> candid:service` extracts the Candid interface embedded in a deployed Wasm.
- **Deploy** — `dfx deploy` creates the canister on the target network (if needed) and installs/upgrades the Wasm. `--network ic` targets mainnet; default is local. See [[mainnet-deploy]].
- **Identity** — `dfx identity` manages keypairs. Each identity maps to a [[principals|principal]] used as the caller for `dfx canister call`. Mainnet deploys typically use a dedicated identity distinct from the default one.
- **Interaction** — `dfx canister call <name> <method> '(<candid args>)'` invokes a method and prints the Candid reply. `dfx canister status`, `dfx canister id`, and `dfx canister update-settings` cover the management-canister surface for controllers / balances / module hashes.
- **Cycles & wallets** — `dfx cycles` talks to the cycles-ledger canister (balance, convert ICP → cycles, top-up a canister, transfer to another principal); `dfx wallet` talks to the legacy per-developer wallet canister. DFINITY's current guidance is `dfx cycles` for new projects; `dfx wallet` remains for legacy continuity. See [[cycles-wallet]].
- **Ledger** — `dfx ledger` talks to the ICP ledger (balance, transfer, account-id derivation). `dfx info` prints environment and networking details.

### `dfx.json` essentials

The manifest's load-bearing keys:

- **`canisters.<name>.type`** — picks the build pipeline: `motoko`, `rust`, `custom` (bring-your-own Wasm), `assets` (frontend asset canister), `pull` (depend on a canister already on the network).
- **`canisters.<name>.main` / `.package` / `.source` / `.wasm` / `.candid`** — per-type inputs: Motoko entry file, Rust cargo package, asset source dirs, prebuilt Wasm path, Candid interface path.
- **`canisters.<name>.dependencies`** — other canisters in the project that must be built/deployed first; `dfx` uses this to order `dfx deploy` and to surface dependency IDs to the dependent canister.
- **`networks`** — named networks (`local`, `ic`, plus any custom). Each has `providers` (gateway URLs) and `type`. A `networks.json` in `~/.config/dfx/` can override per-machine.
- **`defaults.build`** — overrides for the build pipeline (e.g. `packtool` for Motoko package managers).
- **`dfx`** — pins the dfx version expected to build this project (read on `dfx build`).

The schema is versioned — consult the `dfx.json` reference on internetcomputer.org for the exact key list and any recent additions.

## Example

```bash
dfx new hello                      # scaffold a Motoko project
cd hello
dfx start --background             # local replica in the background
dfx deploy                         # build + install on local
dfx canister call hello greet '("world")'
```

## Gotchas

- `dfx.json` is the source of truth; hand-edit it when adding canisters, changing build commands, or pinning a Motoko version.
- The local replica's state lives under `.dfx/` — `dfx start --clean` wipes it. Mainnet state is untouched by anything local.
- Identities default to an unencrypted keystore unless you opt into a password-protected one; treat the default identity as dev-only.
- `dfx deploy` will upgrade in place; a breaking Candid change will fail the upgrade check. Use `--mode reinstall` only when losing state is acceptable (local/dev).

## See also

- [[canisters]]
- [[local-replica]]
- [[mainnet-deploy]]
- [[motoko]]
- [[rust-cdk]]
- [[cycles]]
- [[cycles-wallet]]
- [[principals]]
- [[asset-canister]]
