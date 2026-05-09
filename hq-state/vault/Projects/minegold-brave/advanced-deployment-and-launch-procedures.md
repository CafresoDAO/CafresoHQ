---
tags: [project-study, minegold-brave]
---
# Advanced Deployment and Launch Procedures

This project includes two primary shell scripts for deployment: `launch.sh` for local development and `launch-mainnet.sh` for deploying to the ICP mainnet. The `LAUNCH.md` guide provides a detailed walkthrough for both scenarios.

### Local Deployment (`launch.sh`)

The local launch script is the recommended first step for developers. It automates the process of setting up a complete, local version of the dApp.

**Execution Steps:**
1.  Starts a clean local `dfx` replica.
2.  Deploys Internet Identity, the backend canister, and the frontend assets.
3.  Injects the new canister IDs into the frontend's environment configuration (`src/frontend/dist/env.json`).
4.  Attempts to grant the caller's dfx identity the `admin` role.

Useful flags for the script include:
- `--clean`: Wipes the local `.dfx` state and starts from scratch.
- `--reinstall`: Reinstalls canister code, clearing their state.
- `--rebuild`: Rebuilds the Motoko backend and the frontend assets before deploying.

**Key Local Caveats:**
- The frontend is hardcoded to query **mainnet** ICRC-1 ledgers, so you will see live treasury data even on a local replica.
- Full admin functionality is locked to a hardcoded `ADMIN_PRINCIPAL` in `src/backend/main.mo`. To gain full admin rights locally, you must edit this principal to match your local dfx identity and then run the launch script with `--rebuild`.

```motoko
// src/backend/main.mo
let ADMIN_PRINCIPAL : Principal = Principal.fromText("<your-dfx-principal>");
```

### Mainnet Deployment (`launch-mainnet.sh`)

Deploying to the mainnet requires a dfx identity with cycles and presents two distinct paths.

#### Path 1: Upgrade an Existing Canister
This path is for users migrating from a previous Caffeine-hosted deployment. By running `./launch-mainnet.sh --upgrade`, the script performs an upgrade of the existing canister, which preserves its state and, most importantly, its Principal ID. This ensures the hardcoded `TREASURY_PRINCIPAL` remains valid.

#### Path 2: Fresh Sovereign Deployment
This path is for creating a new, independent instance of the application on the mainnet. It is **critical** to modify the source code before the first deploy to ensure your new canister controls its own treasury.

**Pre-launch Steps for a Fresh Deploy:**
1.  Create the backend canister on the network to get its ID: `dfx canister --network ic create backend`
2.  Edit `src/backend/main.mo` to update the hardcoded principals:
    - `ADMIN_PRINCIPAL`: Set this to your own dfx identity's principal.
    - `TREASURY_PRINCIPAL`: Set this to the newly created backend canister's ID.
3.  Run the launch script with the `--fresh` and `--rebuild` flags: `./launch-mainnet.sh --fresh --rebuild`

> [!warning] Treasury Invariant
> If you perform a fresh deploy without updating the `TREASURY_PRINCIPAL`, all funds will be credited to the original Caffeine-owned canister, resulting in a loss of assets for your users and your dApp.