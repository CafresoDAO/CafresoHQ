---
tags: [project-study, minegold-brave, devops, automation, deployment]
---

# Developer Scripts & Launch Automation

**Related:** [[deployment-scripts-and-automation]] · [[mainnet-launch-procedures]] · [[developer-tooling-and-automation]] · [[containerized-development-environment]]

## Overview

Minegold.defi provides **three launch scripts** and **five npm workspace commands** for local development, testing, and mainnet deployment. The tooling emphasizes **zero-configuration local deploys** using prebuilt artifacts and **safety-first mainnet launches** with hardcoded principal validation.

---

## Shell Scripts

### 1. `deploy.sh` — Legacy ICP-CLI Local Deploy

**Purpose:** Quick local deployment using the deprecated `icp` CLI (not `dfx`)  
**Status:** ⚠️ **Legacy tool** — `icp` is not the canonical DFINITY SDK  
**Usage:** `./deploy.sh`

#### What It Does

```bash
# deploy.sh:16-23
icp network start -d
icp canister create --environment local frontend
icp canister create --environment local backend
export BACKEND_CANISTER_ID=$(icp canister settings show --environment local --id-only backend)
export STORAGE_GATEWAY_URL=http://localhost:6188
export II_URL=http://rdmx6-jaaaa-aaaaa-aaadq-cai.localhost:8000
icp deploy --environment local frontend backend
```

**Steps:**
1. Starts local ICP network in daemon mode (`-d`)
2. Creates frontend + backend canisters
3. Exports environment variables for frontend config
4. Deploys both canisters
5. **Keeps replica running** with infinite loop (`while true; do sleep 2; done`)

#### Cleanup on Exit

```bash
# deploy.sh:6-10
cleanup() {
    icp network stop
    exit $1
}
trap 'cleanup 1' INT TERM
```

Ctrl+C triggers `icp network stop` before exiting.

**Limitations:**
- Uses non-standard `icp` CLI instead of `dfx`
- No flags for clean deploys or reinstalls
- Hardcoded Internet Identity URL (may be outdated)
- No admin role bootstrapping

---

### 2. `launch.sh` — Canonical Local Deployment Script

**Purpose:** Production-quality local deployment using `dfx` and prebuilt artifacts  
**Usage:**
```bash
./launch.sh                 # Standard local deploy
./launch.sh --clean         # Stop replica, wipe state, redeploy
./launch.sh --reinstall     # Force reinstall canisters (lose state)
./launch.sh --rebuild       # Rebuild backend + frontend from source first
```

#### Prerequisites

```bash
# launch.sh:44-53
dfx   # DFINITY Canister SDK
node  # JavaScript runtime (frontend build)
pnpm  # Package manager (workspace support)

# Only required with --rebuild:
mops  # Motoko package manager (npm i -g ic-mops)
moc   # Motoko compiler (bundled with dfx)
```

**Checks on startup:**
- Verifies all three tools are installed
- Prints versions for troubleshooting
- Exits with install instructions if missing

#### Key Features

**1. Prebuilt Artifact Validation**

```bash
# launch.sh:72-77
[[ -f src/backend/dist/backend.wasm ]] || {
  r "Missing src/backend/dist/backend.wasm — run: ./launch.sh --rebuild"
  exit 1
}
[[ -f src/backend/dist/backend.did ]] || { r "Missing backend.did"; exit 1; }
[[ -f src/frontend/dist/index.html ]] || { r "Missing frontend/dist"; exit 1; }
```

**Why this matters:** Avoids requiring developers to install Motoko toolchain (`moc`, `mops`) for routine local testing — just use the committed WASM.

**2. Smart Replica Management**

```bash
# launch.sh:86-96
if dfx ping local >/dev/null 2>&1; then
  echo "replica already running"
else
  dfx start --clean --background --host 127.0.0.1:4943
  # Wait for replica to accept connections (max 30 sec)
  for i in {1..30}; do
    dfx ping local >/dev/null 2>&1 && break
    sleep 1
  done
fi
```

- **Idempotent:** Reuses existing replica if already running
- **Background mode:** Returns control to script immediately
- **Health check:** Polls `dfx ping` before proceeding with deploy

**3. Dynamic Frontend Environment Injection**

```bash
# launch.sh:108-120
BACKEND_ID="$(dfx canister id backend)"
II_ID="$(dfx canister id internet_identity)"
REPLICA_HOST="http://127.0.0.1:4943"

cat > src/frontend/dist/env.json <<JSON
{
  "backend_host": "${REPLICA_HOST}",
  "backend_canister_id": "${BACKEND_ID}",
  "project_id": "minegold-defi-local",
  "ii_derivation_origin": "undefined"
}
JSON
```

**Generated *after* backend deployment** so canister IDs are live and accurate.

**4. Admin Role Bootstrapping**

```bash
# launch.sh:129-142
MY_PRINCIPAL="$(dfx identity get-principal)"
dfx canister call backend assignCallerUserRole \
  "(principal \"${MY_PRINCIPAL}\", variant { admin })" >/dev/null 2>&1
RC=$?
if (( RC == 0 )); then
  g "✓ ${MY_PRINCIPAL} now has admin role"
else
  y "⚠ assignCallerUserRole failed — main.mo hardcodes ADMIN_PRINCIPAL."
  y "   Edit src/backend/main.mo and rebuild (--rebuild)."
fi
```

**Why it can fail:**  
- `main.mo:66` hardcodes `ADMIN_PRINCIPAL = "YOUR_PRINCIPAL_HERE"`
- If deployer's principal ≠ hardcoded value, admin role assignment is rejected
- Script **continues anyway** (non-fatal) but admin features won't work

#### Success Output

```
════════════════════════════════════════════════════════════════════════
  minegold.defi is LIVE on your local replica
════════════════════════════════════════════════════════════════════════

  Frontend:            http://<frontend-id>.localhost:4943
  Backend canister:    <backend-id>
  Internet Identity:   http://<ii-id>.localhost:4943
  Candid UI:           http://127.0.0.1:4943/?canisterId=<candid-ui>&id=<backend-id>

  Your principal:      <dfx-identity-principal>

  Stop the replica:    dfx stop
  Tail backend logs:   dfx canister logs backend
```

**Access Points:**
- **Frontend UI:** Click the URL to open the web app
- **Candid playground:** Test backend methods interactively
- **Internet Identity:** Local auth for testing login flows

---

### 3. `launch-mainnet.sh` — Production Deployment Script

**Purpose:** Deploy to the Internet Computer mainnet with safety checks  
**Usage:**
```bash
./launch-mainnet.sh --upgrade          # Upgrade existing canisters
./launch-mainnet.sh --fresh            # Deploy NEW canister IDs
./launch-mainnet.sh --fresh --rebuild  # + rebuild from source first
```

#### Critical Safety: TREASURY_PRINCIPAL Validation

**The Problem:**
```motoko
// src/backend/main.mo:67 (hardcoded)
let TREASURY_PRINCIPAL : Principal = Principal.fromText("72fnc-ziaaa-aaaai-axk4q-cai");

// All treasury ICRC-1 calls use this principal:
sgldtLedger.icrc1_balance_of({ owner = TREASURY_PRINCIPAL; subaccount = null })
```

If you deploy a **fresh backend** (new canister ID) without updating this hardcoded value, every treasury balance check and transfer will **target the wrong account** (the old canister's ID).

**Script Warning:**

```bash
# launch-mainnet.sh:100-112
if [[ "$MODE" == "fresh" ]]; then
  y "⚠ --fresh mode: make sure you edited main.mo so TREASURY_PRINCIPAL"
  y "  matches the NEW canister id once dfx assigns it, otherwise every"
  y "  ICRC-1 treasury call will target the wrong account. See LAUNCH.md."
  read -r -p "  Continue? [y/N] " ok
  [[ "$ok" =~ ^[Yy]$ ]] || exit 1
fi
```

**The workflow for `--fresh` deploys:**
1. Run `./launch-mainnet.sh --fresh --rebuild` once (fails or uses wrong treasury)
2. Note the assigned backend canister ID from output
3. Edit `src/backend/main.mo:67` → set `TREASURY_PRINCIPAL` to new ID
4. Run `./launch-mainnet.sh --fresh --rebuild` again (now correct)

**For `--upgrade` mode:** No change needed — reuses existing canister ID.

#### Prerequisites Check

```bash
# launch-mainnet.sh:69-83
if ! dfx ping ic >/dev/null 2>&1; then
  r "Cannot reach the Internet Computer. Check your network."
  exit 1
fi

if dfx identity get-wallet --network ic >/dev/null 2>&1; then
  WALLET="$(dfx identity get-wallet --network ic)"
  BALANCE="$(dfx wallet --network ic balance 2>/dev/null || echo 'unknown')"
  echo "  wallet:    ${WALLET}"
  echo "  balance:   ${BALANCE}"
else
  y "⚠ No cycles wallet linked. dfx will charge the identity directly."
  y "   Get cycles: https://internetcomputer.org/docs/.../cycles-faucet"
fi
```

**Required:**
- `dfx` logged in with mainnet identity
- **~4 TC (trillion cycles)** for fresh deploy (~1 TC per canister)
- Either a cycles wallet OR direct cycles in identity (dfx 0.16+)

#### Deployment Flow

**1. Deploy Backend**
```bash
# launch-mainnet.sh:120-123
dfx deploy backend --network ic [--mode upgrade]
BACKEND_ID="$(dfx canister id backend --network ic)"
```

**2. Inject Mainnet Config**
```bash
# launch-mainnet.sh:126-134
cat > src/frontend/dist/env.json <<JSON
{
  "backend_host": "https://icp-api.io",
  "backend_canister_id": "${BACKEND_ID}",
  "project_id": "minegold-defi-ic",
  "ii_derivation_origin": "undefined"
}
JSON
```

**Key difference from local:**
- `backend_host`: Local uses `http://127.0.0.1:4943`, mainnet uses `https://icp-api.io`
- `project_id`: `minegold-defi-ic` (vs `minegold-defi-local`)

**3. Deploy Frontend Asset Canister**
```bash
# launch-mainnet.sh:136-138
dfx deploy frontend --network ic
FRONTEND_ID="$(dfx canister id frontend --network ic)"
```

#### Post-Launch Checklist

```
Post-launch checklist (see LAUNCH.md for details):
  1. Call  dfx canister call --network ic backend selfInitializeMinterAddress
  2. Fund the treasury with sGLDT — send to principal <BACKEND_ID>
     on the sGLDT ledger (i2s4q-syaaa-aaaan-qz4sq-cai).
  3. Fund the canister with cycles:
       dfx cycles top-up --network ic <BACKEND_ID> 2_000_000_000_000
```

**Why these steps matter:**
1. **`selfInitializeMinterAddress`**: Sets up ckUNI minting permissions (see [[canister-upgrade-mechanisms]])
2. **Treasury funding**: Without sGLDT balance, `verifyAndPayUNIDeposit` will fail
3. **Cycles top-up**: Prevents canister from freezing due to compute/storage costs

---

## NPM/PNPM Workspace Scripts

Defined in root `package.json` — **delegates to child packages** (`src/frontend`, `src/backend`) via pnpm workspaces.

### 1. `pnpm build`

```json
// package.json:10
"build": "pnpm -r --if-present run build"
```

**Runs:** `pnpm run build` in every workspace package that defines it  
**Effect:** 
- `src/frontend/package.json:build` → Vite/React build → `src/frontend/dist/`
- `src/backend` has no `build` script (Motoko compiled via `mops build`)

**Used by:** `./launch.sh --rebuild`, CI/CD pipelines

### 2. `pnpm typecheck`

```json
"typecheck": "pnpm -r --if-present run typecheck"
```

**Runs:** TypeScript compiler in check-only mode (`tsc --noEmit`)  
**Purpose:** Catch type errors without generating output files  
**Typical location:** `src/frontend/package.json`

### 3. `pnpm check`

```json
"check": "pnpm -r --if-present run check"
```

**Purpose:** Linting + formatting checks (ESLint, Prettier, Biome, etc.)  
**Returns non-zero exit code** on violations (useful in CI)

### 4. `pnpm fix`

```json
"fix": "pnpm -r --if-present run fix"
```

**Purpose:** Auto-fix linting errors and apply formatting  
**Typical implementation:** `eslint --fix` + `prettier --write`

### 5. `pnpm bindgen`

```json
"bindgen": "caffeine-bindgen --did-file ./src/backend/dist/backend.did --out-dir ./src/frontend/src --actor-interface-file --force"
```

**Purpose:** Generate TypeScript types from Candid interface  
**Input:** `src/backend/dist/backend.did` (Motoko → Candid IDL)  
**Output:** `src/frontend/src/<actor-interface>.ts`  
**Tool:** `caffeine-bindgen` (from `@caffeineai/core-infrastructure`)

**When to run:**
- After changing backend public methods (`public shared func`)
- After `mops build` (regenerates `.did` file)
- Before frontend development (ensures type safety)

**Example:**
```bash
cd src/backend && mops build       # backend.did updated
cd ../.. && pnpm bindgen           # TypeScript types regenerated
cd src/frontend && pnpm typecheck  # Verify no type errors
```

---

## Script Comparison Matrix

| Feature | `deploy.sh` | `launch.sh` | `launch-mainnet.sh` |
|---------|------------|------------|--------------------|
| **Target** | Local (icp CLI) | Local (dfx) | Mainnet (dfx) |
| **Prebuilt artifacts** | ❌ Rebuilds always | ✅ Uses `.wasm`/`.did` | ✅ Uses `.wasm`/`.did` |
| **Replica mgmt** | Starts + cleanup | Smart reuse | N/A (IC mainnet) |
| **Internet Identity** | Hardcoded URL | Deployed locally | Uses mainnet II |
| **Admin bootstrap** | ❌ No | ✅ Automatic | ⚠️ Manual (see LAUNCH.md) |
| **Treasury check** | ❌ No | ❌ No | ✅ Interactive prompt |
| **Rebuild flag** | ❌ No | `--rebuild` | `--rebuild` |
| **Clean deploy** | ❌ No | `--clean` | `--fresh` |
| **Status** | Legacy | **Recommended** | Production-ready |

---

## Common Workflows

### First-Time Local Setup

```bash
# 1. Install dependencies
pnpm install

# 2. Rebuild backend + frontend from source (one-time)
./launch.sh --rebuild

# 3. Subsequent deploys (reuses built artifacts)
./launch.sh
```

### Backend Code Change

```bash
# 1. Edit src/backend/main.mo
vim src/backend/main.mo

# 2. Rebuild Motoko → WASM + DID
cd src/backend && mops build

# 3. Regenerate frontend types
cd ../.. && pnpm bindgen

# 4. Redeploy with reinstall (lose canister state)
./launch.sh --reinstall
```

**Why `--reinstall`?**  
Motoko stable variables preserve state across upgrades, but **breaking schema changes** (adding/removing stable var fields) can cause deserialization errors. Reinstall wipes state cleanly.

### Frontend-Only Change

```bash
# 1. Edit src/frontend/src/App.tsx (example)
vim src/frontend/src/App.tsx

# 2. Rebuild frontend
cd src/frontend && pnpm build

# 3. Redeploy frontend canister only
dfx deploy frontend
```

**No backend deploy needed** — saves cycles and time.

### Testing Admin Functions Locally

```bash
# 1. Get your dfx principal
dfx identity get-principal
# Output: abc123-def456-...

# 2. Edit backend to set ADMIN_PRINCIPAL
vim src/backend/main.mo
# Change line 66:
# let ADMIN_PRINCIPAL = Principal.fromText("abc123-def456-...");

# 3. Rebuild + redeploy
./launch.sh --rebuild --reinstall

# 4. Now you can call admin methods
dfx canister call backend adminSetUniExchangeRate '(250_000_000 : nat)'
```

### Mainnet Deploy (Upgrade Existing Canister)

```bash
# Prerequisite: You are already a controller of the backend/frontend canisters

# 1. Rebuild from source (optional but recommended)
./launch-mainnet.sh --upgrade --rebuild

# OR use prebuilt artifacts
./launch-mainnet.sh --upgrade

# 2. Follow post-launch checklist from script output
```

### Mainnet Deploy (Fresh Canister IDs)

```bash
# WARNING: Requires editing TREASURY_PRINCIPAL in main.mo after first deploy

# 1. First deploy (assigns new canister IDs)
./launch-mainnet.sh --fresh --rebuild

# 2. Note the backend canister ID from output
# Example: backend canister id: xyz789-abc123-...

# 3. Edit main.mo to use NEW backend ID as treasury
vim src/backend/main.mo
# Line 67:
# let TREASURY_PRINCIPAL = Principal.fromText("xyz789-abc123-...");

# 4. Rebuild and upgrade
./launch-mainnet.sh --upgrade --rebuild

# 5. Complete post-launch checklist
```

---

## Gotchas & Edge Cases

### 1. `deploy.sh` Uses Deprecated `icp` CLI

**Problem:** `icp` is not the canonical DFINITY SDK  
**Solution:** Use `launch.sh` instead (uses `dfx`)

**When to use `deploy.sh`:**  
Only if you have legacy tooling that depends on `icp` CLI behavior.

### 2. Admin Role Fails Silently on Local Deploy

**Symptom:**
```bash
./launch.sh
# Output: ⚠ assignCallerUserRole failed — main.mo hardcodes ADMIN_PRINCIPAL.
```

**Root cause:** Your `dfx identity get-principal` ≠ `main.mo:66 ADMIN_PRINCIPAL`

**Impact:**
- Admin endpoints return "Unauthorized: admin only"
- Cannot call `adminSetUniExchangeRate`, `verifyEthTransaction`, etc.

**Fix:**
```bash
dfx identity get-principal  # Copy this
vim src/backend/main.mo     # Paste into ADMIN_PRINCIPAL
./launch.sh --rebuild --reinstall
```

### 3. Frontend Shows "Canister Not Found" After Deploy

**Symptom:** Browser shows `canister <id> not found` or 404 errors

**Causes:**
1. **env.json outdated**: Run `./launch.sh` again (regenerates env.json with live IDs)
2. **Replica stopped**: `dfx ping local` → if failed, run `dfx start --clean --background`
3. **Cached browser state**: Hard refresh (Ctrl+Shift+R) or clear browser storage

### 4. Mainnet Deploy: "Insufficient Cycles"

**Symptom:**
```
Error: Canister creation failed: insufficient cycles
```

**Required cycles:**
- Fresh backend canister: ~1 TC
- Fresh frontend asset canister: ~1 TC
- Upgrade: ~0.01 TC (negligible)

**Fix:**
```bash
# Option 1: Use a funded cycles wallet
dfx identity get-wallet --network ic
dfx wallet --network ic balance
# If balance < 4 TC, get more cycles from faucet

# Option 2: Direct cycles (dfx 0.16+)
dfx cycles balance --network ic
# Convert ICP to cycles via NNS or faucet
```

### 5. `pnpm bindgen` Fails: "backend.did Not Found"

**Symptom:**
```
Error: ENOENT: no such file or directory 'src/backend/dist/backend.did'
```

**Fix:**
```bash
cd src/backend
mops install  # Install Motoko deps
mops build    # Generates dist/backend.wasm + dist/backend.did
cd ../..
pnpm bindgen  # Now works
```

### 6. Mainnet Frontend Shows Local Backend ID

**Symptom:** Mainnet frontend tries to call `http://127.0.0.1:4943`

**Root cause:** `src/frontend/dist/env.json` not regenerated after mainnet deploy

**Fix:**
```bash
# launch-mainnet.sh automatically regenerates env.json
# If you deployed manually:
dfx deploy frontend --network ic
# Then manually edit src/frontend/dist/env.json or re-run launch-mainnet.sh
```

---

## Related Documentation

- **Deployment details**: [[deployment-scripts-and-automation]]
- **Mainnet procedures**: [[mainnet-launch-procedures]]
- **Docker alternative**: [[containerized-development-environment]]
- **Canister upgrades**: [[canister-upgrade-mechanisms]]
- **Admin functions**: [[api-and-endpoints#Admin Endpoints]]

---

## Key Takeaways

✅ **Use `launch.sh` for local development** (not `deploy.sh`)  
✅ **Prebuilt artifacts** (`backend.wasm`) avoid requiring Motoko toolchain for routine work  
✅ **Admin principal must match** `main.mo:66` or local admin features fail  
✅ **Mainnet `--fresh` deploys** require updating `TREASURY_PRINCIPAL` after first deploy  
✅ **Post-mainnet checklist** is critical: minter init + treasury funding + cycles top-up  
✅ **`pnpm bindgen`** keeps frontend types in sync with backend Candid interface