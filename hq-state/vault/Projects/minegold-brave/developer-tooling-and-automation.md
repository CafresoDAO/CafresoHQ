---
tags: [project-study, minegold-brave, developer-experience, automation]
---

# Developer Tooling and Automation

Minegold.brave uses a sophisticated multi-tool developer workflow spanning frontend (TypeScript/React), backend (Motoko), and ICP infrastructure. The toolchain is designed for a monorepo structure with separate concerns for each layer.

## Toolchain Overview

### Frontend Stack
- **Build**: Vite 5.4+ with React plugin
- **Language**: TypeScript 5.8+
- **Linter/Formatter**: Biome 1.9+ (modern ESLint/Prettier replacement)
- **Styling**: Tailwind CSS with animations and typography plugins
- **Package Manager**: pnpm 7+ (enforced via npm rejection)

### Backend Stack
- **Language**: Motoko 1.3.0 (compiled via `moc`)
- **Package Manager**: Mops (Motoko package manager)
- **Linter**: lintoko 0.7.0
- **Type System**: ICRC-1 compliant with core 2.2.0

### Infrastructure Tools
- **Deployment**: ICP CLI (`icp` command)
- **Legacy DFX**: Used for some deployment scenarios (see [[mainnet-launch-procedures]])
- **Caffeine Framework**: `@caffeineai/core-infrastructure` for orchestration
- **Bindgen**: `caffeine-bindgen` for TypeScript ↔ Candid interface generation

## Monorepo Structure

The root `package.json` uses pnpm workspaces with recursive script execution:

```json
"scripts": {
  "build": "pnpm -r --if-present run build",
  "typecheck": "pnpm -r --if-present run typecheck",
  "check": "pnpm -r --if-present run check",
  "fix": "pnpm -r --if-present run fix",
  "bindgen": "caffeine-bindgen --did-file ./src/backend/dist/backend.did --out-dir ./src/frontend/src --actor-interface-file --force"
}
```

The `-r --if-present` flags allow workspace members to opt into scripts. Frontend and backend implement their own `build`, `typecheck`, `check`, and `fix` targets.

## Developer Commands (from AGENTS.md)

### Frontend Workflow
Run from `src/frontend/`:

```bash
# 1. Install dependencies (offline-first for speed)
pnpm install --prefer-offline

# 2. Type checking
pnpm typecheck  # runs tsc --noEmit

# 3. Linting and auto-fix
pnpm fix  # runs biome check --write src

# 4. Production build
pnpm build  # runs vite build && node scripts/post-build.mjs

# 5. Dev server (not listed in AGENTS.md but present in package.json)
pnpm dev  # runs vite for hot-reload development
```

### Backend Workflow
Run from `src/backend/`:

```bash
# 1. Install Motoko dependencies
mops install

# 2. Type checking with auto-fix
mops check --fix

# 3. Build canister
mops build  # outputs to src/backend/dist/
```

### Integration Step (Critical)
Run from **root** after backend changes:

```bash
pnpm bindgen
```

**Why this matters**: The frontend imports TypeScript types generated from the backend's Candid IDL file. If you modify backend methods without regenerating bindings, the frontend will call outdated or missing interfaces. This is a common source of "method not found" errors.

## Configuration Files

### caffeine.toml
Defines project metadata and workspace boundaries:

```toml
manifest_version = "0.1.0"

[project]
id = "my-app"
name = "my-app"

[workspace]
include = ["src/**"]

[canisters.frontend]
depends_on = ["backend"]  # Enforces build order
```

The `depends_on` directive ensures the backend canister is compiled before frontend, which is necessary for bindgen to find `backend.did`.

### icp.yaml
Simple canister registry for the ICP CLI:

```yaml
canisters:
  - src/frontend
  - src/backend
```

This tells `icp deploy` where to find canister entry points. The schema is validated against the [official JSON schema](https://github.com/dfinity/icp-cli/raw/refs/heads/main/docs/schemas/icp-yaml-schema.json).

### mops.toml (Backend Configuration)
Key sections:

```toml
[toolchain]
moc = "1.3.0"        # Motoko compiler version (pinned)
lintoko = "0.7.0"    # Linter version

[moc]
args = [
  "--default-persistent-actors",  # Enable stable upgrades
  "--actor-idl=src/backend/system-idl",  # IDL output path
  "--implicit-package=core",  # Auto-import core library
  "-no-check-ir",  # Skip IR validation (faster builds)
  "-E=M0236,M0235,M0223,M0237",  # Enable specific warnings
  "-A=M0198"  # Suppress M0198 warning
]

[dependencies]
core = "2.2.0"
caffeineai-authorization = "0.1.0"
caffeineai-http-outcalls = "0.1.0"
ecdsa = "7.1.0"  # ECDSA signature verification (EIP-191)
sha3 = "0.1.1"   # Keccak-256 hashing
```

**Noteworthy**:
- `--default-persistent-actors` enables [[canister-upgrade-mechanisms|stable memory persistence]].
- The `-E` and `-A` flags fine-tune compiler warnings (see Motoko docs for codes).
- `ecdsa` and `sha3` are used for Ethereum signature verification (see [[security-audit-findings]]).

### tsconfig.json (Frontend)
Standard TypeScript config:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "strict": true,
    "jsx": "react-jsx",
    "moduleResolution": "bundler"
  }
}
```

Vite handles the actual transpilation; `tsc` is only used for type checking.

## Local Deployment Automation

### deploy.sh
A wrapper script that orchestrates the full local deployment:

```bash
#!/bin/bash
set -e  # Exit on any error

# Cleanup trap for Ctrl+C
cleanup() {
    icp network stop
    exit $1
}
trap 'cleanup 1' INT TERM

# 1. Start local ICP replica in daemon mode
icp network start -d

# 2. Create canister IDs (writes to canister_ids.json)
icp canister create --environment local frontend
icp canister create --environment local backend

# 3. Export environment variables for the build
export BACKEND_CANISTER_ID=$(icp canister settings show --environment local --id-only backend)
export STORAGE_GATEWAY_URL=http://localhost:6188
export II_URL=http://rdmx6-jaaaa-aaaaa-aaadq-cai.localhost:8000

# 4. Deploy both canisters
icp deploy --environment local frontend backend

# 5. Keep the script running (replica needs to stay up)
echo "Press Ctrl+C to stop the deployment and exit."
while true; do
    sleep 2
done
```

**Key behaviors**:
- The script blocks indefinitely so the local replica remains running. You must manually Ctrl+C to tear down.
- Environment variables are injected at build time (Vite reads these via `vite-plugin-environment`).
- The `II_URL` points to the local Internet Identity canister for authentication.
- Cleanup trap ensures `icp network stop` runs even if you interrupt the script.

**Why not `dfx`?** The project uses the newer `icp` CLI for local development but still supports `dfx` for mainnet (see [[mainnet-launch-procedures]]). This hybrid approach suggests a migration in progress.

## Build Output Artifacts

### Frontend
```
src/frontend/dist/
├── index.html
├── assets/
│   ├── index-<hash>.js   # Main bundle
│   └── index-<hash>.css  # Tailwind styles
└── .ic-assets.json       # ICP asset manifest
```

The `post-build.mjs` script (referenced in frontend `package.json`) likely generates `.ic-assets.json` for ICP's asset canister.

### Backend
```
src/backend/dist/
├── backend.wasm          # Compiled canister
├── backend.did           # Candid interface (source for bindgen)
└── backend.most          # Type signature file
```

The `.most` file is used by `mops check-stable` to verify upgrade compatibility (see [[canister-upgrade-mechanisms]]).

## Linting Philosophy

### Biome (Frontend)
The project uses **Biome** instead of ESLint + Prettier:
- Single tool for linting + formatting (faster, less config)
- Rust-based (10-100× faster than ESLint)
- Command: `biome check --write src` (lint + format in one pass)

### lintoko (Backend)
Motoko-specific linter integrated with `mops`. No separate config file visible; likely uses defaults from the mops ecosystem.

## Common Gotchas

### 1. Stale Candid Bindings
**Symptom**: Frontend throws `Call failed: MethodNotFound` even though the backend method exists.

**Cause**: You modified the backend but forgot to run `pnpm bindgen`.

**Fix**:
```bash
# From root:
pnpm bindgen
# Then rebuild frontend:
cd src/frontend && pnpm build
```

### 2. pnpm vs npm
The root `package.json` rejects npm:
```json
"engines": {
  "npm": "please use pnpm"
}
```

Running `npm install` will fail with a cryptic error. Always use `pnpm`.

### 3. Offline Installs
The verified command is `pnpm install --prefer-offline`, not plain `pnpm install`. This:
- Speeds up installs by using the local pnpm store
- Avoids registry flakiness during development
- Still falls back to network if a package is missing locally

### 4. Replica Port Conflicts
If `icp network start` fails with "port already in use", a previous replica is still running:
```bash
icp network stop  # Kill any existing replica
icp network start -d  # Try again
```

## Development Workflow (Typical)

```bash
# 1. Start from a clean slate
cd minegold.defi
pnpm install --prefer-offline  # Installs frontend + root deps

# 2. Install backend deps
cd src/backend
mops install
cd ../..

# 3. Backend development cycle
cd src/backend
# (Edit main.mo or other .mo files)
mops check --fix  # Lint + type check
mops build        # Compile to WASM
cd ../..
pnpm bindgen      # Regenerate frontend types

# 4. Frontend development cycle
cd src/frontend
# (Edit React components)
pnpm typecheck  # Verify types
pnpm fix        # Lint + format
pnpm build      # Production build
cd ../..

# 5. Deploy locally
./deploy.sh  # Starts replica, deploys both canisters, blocks
# Visit http://localhost:8000 or the URL printed by the script
# Press Ctrl+C when done
```

For **hot-reload frontend development** without redeploying the backend:
```bash
# Terminal 1: Start replica + deploy canisters
./deploy.sh

# Terminal 2: Run Vite dev server (after deploy.sh finishes)
cd src/frontend
pnpm dev
# Visit http://localhost:5173 (Vite's default port)
```

Vite will proxy canister calls to the local replica but serve frontend assets from its own dev server with instant HMR.

## Comparison to Standard ICP Projects

| Aspect | Standard ICP | Minegold.brave |
|--------|-------------|----------------|
| CLI | `dfx` only | `icp` CLI (local), `dfx` (mainnet) |
| Frontend Build | Plain Webpack/Vite | Vite + Caffeine post-build |
| Backend Packaging | `vessel` or manual | `mops` (modern package manager) |
| Linting | ESLint + Prettier | Biome (frontend), lintoko (backend) |
| Bindgen | Manual or `dfx generate` | `caffeine-bindgen` |
| Monorepo | Single canister or manual | pnpm workspaces |

The Caffeine framework adds significant automation but requires learning its conventions (see [[patterns-and-conventions]]).

## Related
- [[build-and-deploy-process]] — high-level build flow
- [[local-deployment-with-dfx]] — legacy DFX-based workflow
- [[mainnet-launch-procedures]] — production deployment scripts
- [[project-dependencies]] — package version details
- [[containerized-development-environment]] — Docker-based setup