---
tags: [project-study, minegold-brave]
---
# Entry Points and Local Deployment

The `launch.sh` script is the primary entry point for deploying and running the `minegold.defi` project locally using the DFINITY SDK (`dfx`). It orchestrates the setup of a local Internet Computer (IC) replica, deployment of canisters, and configuration of the frontend.

## Key Steps in `launch.sh`

1.  **Prerequisite Check**: Ensures `dfx`, `node`, and `pnpm` are installed.

    ```bash
    command -v dfx  >/dev/null 2>&1 || missing+=("dfx")
    command -v node >/dev/null 2>&1 || missing+=("node")
    command -v pnpm >/dev/null 2>&1 || missing+=("pnpm")
    ```

2.  **Optional Rebuild (`--rebuild`)**: If specified, it rebuilds the backend (Motoko) and frontend (TypeScript/React).
    *   Backend: Uses `mops install` and `mops build` in `src/backend`.
    *   Frontend: Uses `pnpm install` and `pnpm build` in `src/frontend`.

3.  **Verify Build Artifacts**: Checks for the existence of `backend.wasm`, `backend.did`, and `index.html` to ensure pre-built or newly built artifacts are present.

4.  **Replica Management**: 
    *   `--clean`: Stops any running `dfx` replica and wipes its state (`.dfx` folder).
    *   Starts a local `dfx` replica if one isn't already running.

5.  **Canister Deployment**: Deploys the following canisters:
    *   `internet_identity` (a standard IC service for user authentication).
    *   `backend` (the Motoko-based smart contract).
    *   `frontend` (an asset canister serving the web interface).

    The `--reinstall` flag forces a reinstallation, losing canister state.

6.  **Frontend Configuration**: Generates `src/frontend/dist/env.json` with the dynamically assigned canister IDs for `backend` and `internet_identity`, allowing the frontend to communicate with the correct local canisters.

    ```json
    {
      "backend_host": "http://127.0.0.1:4943",
      "backend_canister_id": "<BACKEND_ID>",
      "project_id": "minegold-defi-local",
      "ii_derivation_origin": "undefined"
    }
    ```

7.  **Admin Bootstrap**: Attempts to assign the current `dfx` identity as an admin to the `backend` canister using `assignCallerUserRole`. A warning is issued if the backend's `ADMIN_PRINCIPAL` is hardcoded, preventing dynamic assignment.

## Canister Definitions (`dfx.json`)

The `dfx.json` file, though not directly read in this iteration, is implicitly used by `dfx` commands in `launch.sh` to define the project's canisters and their properties. It specifies the `backend` (Motoko), `frontend` (assets), and `internet_identity` canisters, along with their build and deployment configurations. This file is crucial for [[local-deployment-with-dfx]].

## Accessing the Local Application

Upon successful deployment, the script outputs URLs for accessing the frontend, backend, Internet Identity, and Candid UI on the local replica.

```bash
Frontend:            http://<FRONTEND_ID>.localhost:4943
Backend canister:    <BACKEND_ID>
Internet Identity:   http://<II_ID>.localhost:4943
Candid UI:           http://127.0.0.1:4943/?canisterId=__Candid_UI&id=<BACKEND_ID>
```
