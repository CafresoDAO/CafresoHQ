---
tags: [project-study, minegold-brave, deployment]
---
# Local Deployment with DFX

`minegold.defi` can be deployed locally using the `launch.sh` script, which leverages the DFINITY SDK (`dfx`). This script provides a comprehensive workflow for starting a local replica, deploying canisters, and configuring the frontend.

## Usage

```bash
./launch.sh                 # full local deploy
./launch.sh --clean         # stop replica, wipe state, redeploy
./launch.sh --reinstall     # force reinstall of canisters (lose state)
./launch.sh --rebuild       # rebuild frontend & backend from source first
```

## Prerequisites

The script checks for the following tools:
- `dfx`: DFINITY Canister SDK
- `node`: Node.js
- `pnpm`: Performant Node.js package manager

## Deployment Steps

The `launch.sh` script orchestrates the following:

1.  **Optional Rebuild (`--rebuild` flag):**
    -   If specified, it rebuilds the backend (Motoko) using `mops install` and `mops build` from `src/backend`.
    -   It then rebuilds the frontend using `pnpm install` and `pnpm build` from `src/frontend`.

2.  **Verify Build Artifacts:**
    -   Ensures that `src/backend/dist/backend.wasm`, `src/backend/dist/backend.did`, and `src/frontend/dist/index.html` exist.

3.  **Replica Management:**
    -   If `--clean` is used, it stops any running `dfx` replica and removes the `.dfx` state directory.
    -   Starts a local `dfx` replica in the background if one isn't already running.

4.  **Canister Deployment:**
    -   Deploys the `internet_identity` canister.
    -   Deploys the `backend` canister.
    -   Deploys the `frontend` (asset) canister.
    -   The `--reinstall` flag can be used to force a reinstallation, losing existing canister state.

5.  **Frontend Configuration:**
    -   Generates `src/frontend/dist/env.json` with the dynamically assigned `backend_canister_id` and `replica_host`.

    ```json
    {
      "backend_host": "http://127.0.0.1:4943",
      "backend_canister_id": "<BACKEND_CANISTER_ID>",
      "project_id": "minegold-defi-local",
      "ii_derivation_origin": "undefined"
    }
    ```

6.  **Admin Role Bootstrap:**
    -   Attempts to assign the current `dfx` identity's principal as an admin to the backend canister using `assignCallerUserRole`.
    -   Notes a potential gotcha: if `src/backend/main.mo` hardcodes an `ADMIN_PRINCIPAL`, this step might fail, requiring manual modification and rebuild.

## Key Takeaways

-   `launch.sh` is the primary script for local development and testing, offering robust control over the deployment lifecycle.
-   It automates the setup of the DFINITY local replica and the deployment of all necessary canisters.
-   The dynamic generation of `env.json` ensures the frontend correctly communicates with the locally deployed backend.
-   Admin bootstrapping is attempted, but developers should be aware of potential conflicts with hardcoded principals in the backend logic.

Documented local deployment with DFX. Next iteration could explore the `icp-cli` deployment via `deploy.sh` or dive into the `dfx.json` configuration.