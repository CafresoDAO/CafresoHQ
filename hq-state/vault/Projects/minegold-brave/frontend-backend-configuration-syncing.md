---
tags: [project-study, minegold-brave]
---

# Frontend-Backend Configuration Syncing

The project uses a shell script, `scripts/sync-env.sh`, to synchronize the frontend with the correct backend canister configuration for different networks. This is a crucial step after any deployment to ensure the frontend application knows which canister to communicate with.

### How It Works

The script determines the active network (`local` by default, or `ic` for mainnet) and uses the `dfx` command-line tool to fetch the canister ID for the `backend` service on that network.

It then generates a JSON configuration file at `src/frontend/dist/env.json`.

```bash
#!/usr/bin/env bash
# Regenerate src/frontend/dist/env.json with the canister IDs from
# the active dfx network. Call this after any manual `dfx deploy`.

# ... (network selection logic)

BACKEND_ID="$(dfx canister id backend --network "$NETWORK")"

cat > src/frontend/dist/env.json <<JSON
{
  "backend_host": "${HOST}",
  "backend_canister_id": "${BACKEND_ID}",
  "project_id": "${PROJECT}",
  "ii_derivation_origin": "undefined"
}
JSON
```

### Usage

As noted in the script's comments, it should be run after any manual deployment of the canisters to update the frontend's configuration.

-   **For local development:**
    ```shell
    ./scripts/sync-env.sh
    ```
-   **For the IC mainnet:**
    ```shell
    ./scripts/sync-env.sh --ic
    ```

This script is a key part of the [[verified-build-commands-and-dev-workflow]] and is an example of the project's [[developer-scripts-and-launch-automation]].