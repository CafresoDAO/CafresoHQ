---
tags: [project-study, minegold-brave]
---
# Build and Deploy Process

Minegold.brave utilizes a combination of `dfx` (DFINITY SDK) and custom shell scripts for building and deploying its frontend and backend canisters. There are distinct processes for local development and mainnet deployment.

## Local Deployment (`launch.sh`)

The `launch.sh` script provides a comprehensive workflow for local development and testing. It handles:

1.  **Prerequisite Checks**: Ensures `dfx`, `node`, and `pnpm` are installed.
2.  **Optional Rebuild (`--rebuild`)**: If specified, it rebuilds the Motoko backend using `mops` and the frontend using `pnpm`.
    ```bash
    (cd src/backend && mops install && mops build)
    (cd src/frontend && pnpm install --prefer-offline && pnpm build)
    ```
3.  **Replica Management**: Can stop and wipe the local replica state (`--clean`) or start a new one if not already running.
4.  **Canister Deployment**: Deploys the Internet Identity, backend, and frontend (asset) canisters to the local `dfx` replica. It supports reinstalling canisters (`--reinstall`) which wipes their state.
5.  **Frontend Configuration**: Dynamically generates `src/frontend/dist/env.json` with the local backend and Internet Identity canister IDs and the replica host.
    ```json
    {
      "backend_host": "${REPLICA_HOST}",
      "backend_canister_id": "${BACKEND_ID}",
      "project_id": "minegold-defi-local",
      "ii_derivation_origin": "undefined"
    }
    ```
6.  **Admin Bootstrap**: Attempts to assign the deploying identity the `admin` role on the backend canister, though it notes a potential hardcoded `ADMIN_PRINCIPAL` in `src/backend/main.mo` that might override this.
7.  **Output**: Provides local access URLs for the frontend, backend, Internet Identity, and Candid UI.

## Mainnet Deployment (`launch-mainnet.sh`)

The `launch-mainnet.sh` script is designed for deploying to the live Internet Computer network. It emphasizes careful consideration due to hardcoded principals and cycles management.

1.  **Mode Selection**: Requires either `--upgrade` (to update existing canisters) or `--fresh` (to deploy new canisters).
2.  **Prerequisite Checks**: Verifies `dfx`, `node`, `pnpm` and checks mainnet connectivity and cycles wallet balance.
3.  **Optional Rebuild (`--rebuild`)**: Similar to local deployment, it can rebuild the backend and frontend from source.
4.  **Artifact Verification**: Ensures `backend.wasm` and `frontend/dist` artifacts are present.
5.  **Treasury Sanity Check**: Crucially, it warns about hardcoded `TREASURY_PRINCIPAL` and `ADMIN_PRINCIPAL` in `src/backend/main.mo`. For `--fresh` deployments, these values *must* be updated to match the new canister IDs post-deployment to ensure correct functionality, especially for ICRC-1 treasury calls.
6.  **Canister Deployment**: Deploys or upgrades the backend and frontend canisters to the `ic` network.
7.  **Frontend Configuration**: Generates `src/frontend/dist/env.json` with the mainnet backend canister ID and `https://icp-api.io` as the host.
    ```json
    {
      "backend_host": "https://icp-api.io",
      "backend_canister_id": "${BACKEND_ID}",
      "project_id": "minegold-defi-ic",
      "ii_derivation_origin": "undefined"
    }
    ```
8.  **Post-Launch Checklist**: Provides essential steps after deployment, including initializing the minter address, funding the treasury with sGLDT, and topping up canister cycles.

## `deploy.sh` (Alternative/Helper Script)

The `deploy.sh` script appears to be a more simplified deployment script, possibly for quick local testing or specific CI/CD environments. It uses `icp-cli` (an alternative to `dfx` for some operations) to:

1.  Start a local `icp-cli` network.
2.  Create frontend and backend canisters.
3.  Set `BACKEND_CANISTER_ID`, `STORAGE_GATEWAY_URL`, and `II_URL` environment variables.
4.  Deploy both frontend and backend.
5.  Keeps the network running until manually interrupted.

This script seems to be an alternative or complementary method to `launch.sh` for local deployments, focusing on `icp-cli` rather than `dfx` for the core operations.