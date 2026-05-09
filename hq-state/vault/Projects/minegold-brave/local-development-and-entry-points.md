---
tags: [project-study, minegold-brave]
---
# Local Development and Entry Points

The primary entry point for running the project in a local development environment is the `launch.sh` script. It orchestrates the entire process using the DFINITY SDK (`dfx`).

## Local Launch Sequence

The script performs the following steps:

1.  **Prerequisite Check**: Verifies that `dfx`, `node`, and `pnpm` are installed.

2.  **Start Local Replica**: It ensures a local Internet Computer replica is running using `dfx start`. It can also clean the state with the `--clean` flag.

3.  **Build from Source (Optional)**: If the `--rebuild` flag is provided, it rebuilds the backend and frontend:
    *   **Backend**: Runs `mops install && mops build` in `src/backend`.
    *   **Frontend**: Runs `pnpm install && pnpm build` in `src/frontend`.
    By default, the script deploys pre-compiled artifacts.

4.  **Deploy Canisters**: It deploys the project canisters to the local replica using `dfx deploy`. The key canisters are `internet_identity`, `backend`, and `frontend`, as defined in the [[dfx-configuration-and-project-structure]].

5.  **Dynamic Frontend Configuration**: After the backend is deployed, the script generates a configuration file for the frontend. This is a critical step that injects the dynamically assigned `backend_canister_id` into the frontend's environment.
    ```bash
    # from launch.sh
    BACKEND_ID="$(dfx canister id backend)"
    
    cat > src/frontend/dist/env.json <<JSON
    {
      "backend_host": "${REPLICA_HOST}",
      "backend_canister_id": "${BACKEND_ID}",
      ...
    }
    JSON
    ```

6.  **Bootstrap Admin Role**: In a final step, it attempts to make the current user's principal an admin on the backend canister by calling a public method. This is a common pattern for initializing permissions.
    ```bash
    # from launch.sh
    MY_PRINCIPAL="$(dfx identity get-principal)"
    dfx canister call backend assignCallerUserRole "(principal \"${MY_PRINCIPAL}\", variant { admin })"
    ```

This script provides a complete, one-command setup, making it the central piece of the [[developer-scripts-and-launch-automation]].
