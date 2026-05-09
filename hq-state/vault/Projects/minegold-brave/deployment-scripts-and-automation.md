---
tags: [project-study, minegold-brave, deployment, automation, devops]
---

# Deployment Scripts and Automation

Minegold.brave includes three shell scripts at the project root for deploying to different environments. These scripts represent different approaches to ICP deployment, using both the modern `icp` CLI and the canonical `dfx` SDK.

## Script Overview

| Script | Purpose | CLI Tool | Environment | Execution Mode |
|--------|---------|----------|-------------|----------------|
| `deploy.sh` | Quick local deployment | `icp` | Local | Foreground with cleanup |
| `launch.sh` | Full-featured local deployment | `dfx` | Local | Background replica |
| `launch-mainnet.sh` | Mainnet deployment | `dfx` | IC Mainnet | One-shot |

## deploy.sh — ICP CLI Local Deployment

**Purpose**: Minimal local deployment using the newer `icp` CLI (part of the [[caffeine-platform-integration]] toolchain).

### Features
- **Process management**: Runs replica in foreground (`-d` flag) with cleanup trap
- **Automatic cleanup**: Stops network on script exit or interruption (Ctrl+C)
- **Environment variables**: Exports `BACKEND_CANISTER_ID`, `STORAGE_GATEWAY_URL`, `II_URL`
- **Keep-alive loop**: Blocks until user interrupts

### Workflow
```bash
icp network start -d                                    # Start local replica (foreground)
icp canister create --environment local frontend       # Create canister placeholders
icp canister create --environment local backend
export BACKEND_CANISTER_ID=$(icp canister settings show --environment local --id-only backend)
icp deploy --environment local frontend backend        # Deploy both canisters
```

### Key Characteristic
This script is designed for **ephemeral development sessions**. The foreground replica and cleanup trap ensure the network stops when you're done, preventing orphaned processes.

## launch.sh — DFX Local Deployment (Recommended)

**Purpose**: Production-quality local deployment script with comprehensive validation, multiple modes, and admin bootstrapping. This is the canonical way to run minegold.brave locally.

### Command-Line Flags

```bash
./launch.sh                 # Standard deploy (uses pre-built artifacts)
./launch.sh --clean         # Stop replica, wipe .dfx state, redeploy fresh
./launch.sh --reinstall     # Force reinstall canisters (LOSES STATE)
./launch.sh --rebuild       # Rebuild frontend + backend from source first
```

Flags can be combined: `./launch.sh --clean --rebuild`

### Deployment Workflow

#### 1. Prerequisite Validation
Checks for required tools and displays versions:
```bash
▸ Checking prerequisites
  dfx  0.23.0
  node v22.11.0
  pnpm 9.15.0
```

Missing tools trigger an error with a pointer to `LAUNCH.md`.

#### 2. Optional Rebuild (`--rebuild`)
If `--rebuild` is passed, the script:
1. Rebuilds backend: `cd src/backend && mops install && mops build`
2. Rebuilds frontend: `cd src/frontend && pnpm install --prefer-offline && pnpm build`

This requires `mops` to be installed globally (`npm i -g ic-mops`).

#### 3. Build Artifact Verification
Validates that pre-built artifacts exist:
- ✓ `src/backend/dist/backend.wasm` (shows size in KiB)
- ✓ `src/backend/dist/backend.did`
- ✓ `src/frontend/dist/index.html`

If artifacts are missing, the script exits with instructions to run `--rebuild`.

#### 4. Replica Management

The script intelligently manages the local replica:

```bash
if dfx ping local >/dev/null 2>&1; then
  echo "replica already running"  # Reuse existing replica
else
  dfx start --clean --background --host 127.0.0.1:4943
  # Polling loop: wait up to 30 seconds for replica to accept connections
  for i in {1..30}; do
    dfx ping local >/dev/null 2>&1 && break
    sleep 1
  done
fi
```

**Key insight**: Unlike `deploy.sh`, this uses `--background` to run the replica as a daemon. The polling loop ensures the replica is ready before deploying.

If `--clean` is passed:
```bash
dfx stop || true      # Kill any running replica
rm -rf .dfx           # Wipe local state (canister IDs, data, logs)
```

#### 5. Canister Deployment Sequence

```bash
dfx deploy internet_identity   # Official II canister for auth
dfx deploy backend             # Main business logic
dfx deploy frontend            # Asset canister
```

If `--reinstall` is passed, adds `--mode reinstall -y` to all `dfx deploy` calls. This **destroys canister state** but allows code downgrades (see [[canister-upgrade-mechanisms]]).

#### 6. Frontend Environment Injection

After deploying the backend, the script generates `src/frontend/dist/env.json` with deployed canister IDs:

```json
{
  "backend_host": "http://127.0.0.1:4943",
  "backend_canister_id": "<actual-backend-id>",
  "project_id": "minegold-defi-local",
  "ii_derivation_origin": "undefined"
}
```

This file is then **re-uploaded** to the frontend asset canister when `dfx deploy frontend` runs. The frontend reads this at runtime to know which backend to call.

#### 7. Admin Bootstrapping

The script attempts to assign the deploying identity as an admin:

```bash
MY_PRINCIPAL="$(dfx identity get-principal)"
dfx canister call backend assignCallerUserRole \
  "(principal \"${MY_PRINCIPAL}\", variant { admin })" >/dev/null 2>&1
```

**Why this often fails**: The backend's `main.mo` hardcodes a specific `ADMIN_PRINCIPAL`. If your local identity doesn't match, this call will be rejected. The script detects this and prints:

```
⚠ assignCallerUserRole failed — main.mo hardcodes a specific ADMIN_PRINCIPAL.
   Local admin features won't be reachable unless you edit
   src/backend/main.mo → ADMIN_PRINCIPAL and rebuild (--rebuild).
   Your identity principal is: <your-principal>
```

This is a **known limitation** documented in [[edge-cases-and-gotchas]]. To fix: copy your principal, edit `src/backend/main.mo`, and run `./launch.sh --reinstall --rebuild`.

#### 8. Success Output

```
════════════════════════════════════════════════════════════════════════
  minegold.defi is LIVE on your local replica
════════════════════════════════════════════════════════════════════════

  Frontend:            http://<frontend-id>.localhost:4943
  Backend canister:    <backend-id>
  Internet Identity:   http://<ii-id>.localhost:4943
  Candid UI:           http://127.0.0.1:4943/?canisterId=<candid-ui>&id=<backend-id>

  Your principal:      <your-principal>

  Stop the replica:    dfx stop
  Tail backend logs:   dfx canister logs backend
```

The Candid UI link allows interactive testing of backend methods (see [[api-and-endpoints]]).

### Pretty Output Helpers

The script defines terminal color functions for readability:

```bash
b() { printf '\033[1m%s\033[0m\n' "$*"; }    # Bold
g() { printf '\033[32m%s\033[0m\n' "$*"; }   # Green (success)
y() { printf '\033[33m%s\033[0m\n' "$*"; }   # Yellow (warning)
r() { printf '\033[31m%s\033[0m\n' "$*" >&2; } # Red (error to stderr)
step() { echo; b "▸ $*"; }                    # Section header
```

This creates a professional, scannable deployment log.

## launch-mainnet.sh — Mainnet Deployment

**Purpose**: Deploy to the Internet Computer mainnet with safety checks for hardcoded principals and cycles validation.

### Critical Pre-Deployment Consideration

The backend's `main.mo` hardcodes:
```motoko
let TREASURY_PRINCIPAL : Principal = Principal.fromText("72fnc-ziaaa-aaaai-axk4q-cai");
```

This value **MUST** equal the backend canister's actual principal on mainnet, otherwise all ICRC-1 treasury calls will target the wrong account. You have two options:

1. **Upgrade existing canister** (`--upgrade`): Requires you to control canister `72fnc-ziaaa-aaaai-axk4q-cai`
2. **Fresh deploy** (`--fresh`): You must first edit `main.mo` to use the new canister ID (which you don't know until after deploy — this requires a build → deploy → rebuild → upgrade cycle)

See [[mainnet-launch-procedures]] for the full safe deployment pattern.

### Command-Line Modes

```bash
./launch-mainnet.sh --upgrade          # Upgrade existing backend at 72fnc-...
./launch-mainnet.sh --fresh            # Create NEW canister IDs
./launch-mainnet.sh --fresh --rebuild  # + rebuild from source first
```

**You must choose `--upgrade` OR `--fresh`** — the script will error if neither is provided.

### Workflow

#### 1. Prerequisites & Identity Check
```bash
▸ Checking prerequisites
  identity:  my-mainnet-identity
  principal: aaaaa-bbbbb-ccccc-ddddd-cai
```

The script verifies:
- `dfx`, `node`, `pnpm` are installed
- Current dfx identity (this identity will pay cycles and become the deployer)

#### 2. Cycles Validation

```bash
▸ Checking mainnet connectivity & cycles
  wallet:    xxxxx-xxxxx-xxxxx-xxxxx-cai
  balance:   12.345 TC
```

The script:
1. Pings the Internet Computer (`dfx ping ic`)
2. Checks if a cycles wallet is linked
3. Displays wallet balance if available

If no wallet exists, it warns:
```
⚠ No cycles wallet linked. dfx will try to charge the identity directly.
   Get cycles: https://internetcomputer.org/docs/current/developer-docs/getting-started/cycles/cycles-faucet
```

**Minimum cycles needed**: ~4 TC for a fresh deploy (~1 TC per canister for backend + frontend + overhead).

#### 3. Hardcoded Principal Sanity Check

The script parses `src/backend/main.mo` to extract hardcoded principals:

```bash
▸ Hardcoded-principal sanity check in src/backend/main.mo
  ADMIN_PRINCIPAL    = <extracted-admin-principal>
  TREASURY_PRINCIPAL = 72fnc-ziaaa-aaaai-axk4q-cai
  YOUR dfx principal = <your-principal>
```

In `--fresh` mode, it prompts:
```
--fresh mode: make sure you edited main.mo so TREASURY_PRINCIPAL
matches the NEW canister id once dfx assigns it, otherwise every
ICRC-1 treasury call will target the wrong account. See LAUNCH.md.
Continue? [y/N]
```

This is a **critical safety check** — deploying with the wrong `TREASURY_PRINCIPAL` will break all token operations.

#### 4. Mainnet Deployment

```bash
dfx deploy backend --network ic [--mode upgrade]
BACKEND_ID="$(dfx canister id backend --network ic)"
```

In `--upgrade` mode, adds `--mode upgrade` flag (standard canister upgrade).

In `--fresh` mode, dfx creates new canister IDs.

#### 5. Frontend env.json for Mainnet

```json
{
  "backend_host": "https://icp-api.io",
  "backend_canister_id": "<actual-backend-id>",
  "project_id": "minegold-defi-ic",
  "ii_derivation_origin": "undefined"
}
```

Note the differences from local:
- `backend_host`: `https://icp-api.io` (mainnet API endpoint)
- `project_id`: `minegold-defi-ic` (vs `minegold-defi-local`)

#### 6. Post-Launch Checklist

The script outputs critical next steps:

```
Post-launch checklist (see LAUNCH.md for details):
  1. Call  dfx canister call --network ic backend selfInitializeMinterAddress
  2. Fund the treasury with sGLDT — send to principal <backend-id>
     on the sGLDT ledger (i2s4q-syaaa-aaaan-qz4sq-cai).
  3. Fund the canister with cycles:
       dfx cycles top-up --network ic <backend-id> 2_000_000_000_000
```

**Why these steps matter**:
1. **selfInitializeMinterAddress**: Initializes the backend's internal ICRC-1 minter identity (see [[state-management]])
2. **Treasury funding**: The backend needs sGLDT tokens to operate (see [[data-flow-and-transaction-lifecycle]])
3. **Cycles top-up**: Mainnet canisters need cycles to pay for compute/storage

These are **manual post-deployment steps** not automated by the script (to prevent accidental cycle burns or token transfers).

## Key Differences: `icp` vs `dfx` CLI

| Aspect | `icp` CLI (`deploy.sh`) | `dfx` CLI (`launch.sh`, `launch-mainnet.sh`) |
|--------|-------------------------|----------------------------------------------|
| **Source** | Caffeine framework | DFINITY SDK (canonical) |
| **Maturity** | Newer, less documented | Official, well-documented |
| **Replica** | `icp network start` | `dfx start` |
| **Deployment** | `icp deploy` | `dfx deploy` |
| **Use case** | Quick prototyping | Production deployments |
| **Community support** | Limited | Extensive |

The project maintains both tools for flexibility, but **`dfx` is the recommended path** for local development (per [[developer-tooling-and-automation]]) and the only option for mainnet.

## Common Deployment Patterns

### Pattern 1: Fresh Local Development
```bash
./launch.sh --clean --rebuild
```
Use when: Starting a new feature, wiping test data, or troubleshooting canister state issues.

### Pattern 2: Iterative Frontend Development
```bash
cd src/frontend
pnpm build
dfx deploy frontend  # No need for full ./launch.sh
```
Use when: Only frontend code changed, backend unchanged.

### Pattern 3: Backend Method Changes
```bash
cd src/backend
mops build
pnpm bindgen  # Run from root!
dfx deploy backend --mode upgrade
```
Use when: Backend logic changed but state schema unchanged (see [[canister-upgrade-mechanisms]]).

### Pattern 4: Breaking Backend Changes (State Schema)
```bash
./launch.sh --reinstall --rebuild
```
Use when: Stable variable types changed, requiring canister reinstall (⚠ loses all data).

### Pattern 5: Mainnet Canister Upgrade
```bash
./launch-mainnet.sh --upgrade --rebuild
```
Use when: Deploying new code to existing mainnet canisters.

## Related Documentation
- [[build-and-deploy-process]] — Overview of the build pipeline
- [[local-deployment-with-dfx]] — dfx-specific deployment details
- [[mainnet-launch-procedures]] — Full mainnet launch guide
- [[canister-upgrade-mechanisms]] — Upgrade vs reinstall modes
- [[caffeine-platform-integration]] — icp CLI tooling
- [[developer-tooling-and-automation]] — pnpm/mops/bindgen workflow