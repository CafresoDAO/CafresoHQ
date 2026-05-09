---
tags: [project-study, minegold-brave]
---

# Mainnet Deployment and Operational Playbook

The primary mechanism for deploying the Minegold project to the Internet Computer mainnet is the `launch-mainnet.sh` script. This script automates the deployment of both the backend and frontend canisters and serves as a playbook for live operations.

## Deployment Modes

The script operates in two distinct modes, specified by a command-line flag:

- `--upgrade`: This mode is used to upgrade the code of existing, live canisters. It requires the `dfx` identity to be a controller of the target canisters.
- `--fresh`: This mode creates entirely new backend and frontend canisters. This is used for the initial launch or for deploying to a new environment.

An optional `--rebuild` flag can be added to either mode to rebuild the project from source using `mops` and `pnpm` before deploying.

## Critical Pre-Deployment Checks

Before deploying, the script performs several crucial checks.

### 1. Hardcoded Principals

The most significant check is a sanity check for hardcoded principals within the backend Motoko source code (`src/backend/main.mo`). The script specifically looks for `ADMIN_PRINCIPAL` and `TREASURY_PRINCIPAL`.

```bash
HARDCODED_TREASURY="$(awk '/TREASURY_PRINCIPAL[[:space:]]*:/,/Principal\.fromText/' src/backend/main.mo | grep -oE 'fromText\("[^"]+"\)' | head -1 | sed 's/.*"\(.*\)".*/\1/' || true)"
```

This is a critical design constraint. When performing a `--fresh` deploy, the developer **must** edit these values in the source code to match the new canister IDs that `dfx` will assign. Failure to do so will result in the treasury logic targeting the wrong canister, as noted in the script's comments.

### 2. Configuration Syncing

After the backend canister is deployed, the script dynamically creates an `env.json` file for the frontend. This file injects the newly created backend canister ID, ensuring the frontend knows which canister to communicate with. This is a key part of the [[frontend-backend-configuration-syncing]] process.

```bash
# Injects canister IDs into frontend env.json
cat > src/frontend/dist/env.json <<JSON
{
  "backend_host": "https://icp-api.io",
  "backend_canister_id": "${BACKEND_ID}",
  "project_id": "minegold-defi-ic",
  "ii_derivation_origin": "undefined"
}
JSON
```

## Post-Deployment Checklist

After the canisters are live, the script prints a list of mandatory manual steps to fully initialize the application:

1.  **Initialize Minter Address**: A canister call must be made to `selfInitializeMinterAddress`.
2.  **Fund Treasury**: The backend canister's principal ID must be sent `sGLDT` tokens on the sGLDT ledger canister.
3.  **Fund with Cycles**: The canisters must be topped up with cycles to pay for computation and storage. The script suggests a top-up of 2 Trillion cycles.

This checklist highlights that deployment is not the final step; manual operational tasks are required to bring the system to a fully functional state. This process is also referenced in [[verified-build-commands-and-dev-workflow]].