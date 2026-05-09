---
tags: [project-study, minegold-brave]
---

# Package Management and Dependencies

Minegold.brave uses a **dual package management system** to handle both Motoko backend dependencies and JavaScript/TypeScript frontend dependencies. This hybrid approach reflects the Internet Computer Platform's architecture where backend canisters (smart contracts) run Motoko code while frontends use standard web technologies.

## Package Managers

### Backend: Mops (Motoko Package Manager)

**Mops** is the official package manager for Motoko, similar to npm/yarn for JavaScript or cargo for Rust.

**Configuration**: `mops.toml`
```toml
[package]
name = "backend"
version = "0.1.0"

[build]
outputDir = "src/backend/dist"
args = [ "--release" ]

[canisters.backend]
main = "src/backend/main.mo"

  [canisters.backend.check-stable]
  path = ".old/src/backend/dist/backend.most"

[toolchain]
moc = "1.3.0"      # Motoko compiler version
lintoko = "0.7.0"   # Motoko linter version
```

**Lock file**: `mops.lock` (JSON format, ~29KB)
- Contains exact dependency tree with content hashes for reproducible builds
- Includes transitive dependencies automatically resolved
- Version 3 format with SHA-256 hashes for integrity verification

### Frontend: pnpm

**pnpm** is used for workspace management and frontend dependencies, chosen for:
- Efficient disk space usage (content-addressable storage)
- Strict dependency isolation
- Fast installation times
- Native monorepo/workspace support

**Root configuration**: `package.json`
```json
{
  "engines": {
    "node": ">=16.0.0",
    "pnpm": ">=7.0.0",
    "npm": "please use pnpm"  // Enforces pnpm usage
  }
}
```

**Workspace**: `pnpm-workspace.yaml` defines monorepo structure

## Core Dependencies

### Motoko Standard Library

**`core@2.2.0`** - The Motoko standard library, providing:
- Data structures: `Array`, `Map`, `Set`, `Queue`, `PriorityQueue`, `Stack`
- Primitives: `Blob`, `Text`, `Int`, `Nat`, `Float`, `Bool`, `Char`
- Utilities: `Iter`, `Option`, `Result`, `Random`, `Time`, `Timer`
- IC-specific: `Principal`, `Cycles`, `Region`, `CertifiedData`
- Pure functional variants: `pure/List`, `pure/Map`, `pure/Queue`

**Why this version**: 2.2.0 is the latest stable release with reliable data structure implementations and IC platform integration.

### Caffeine AI Platform Integration

**`caffeineai-authorization@0.1.0`**
- **Purpose**: Role-based access control (RBAC) mixin for canisters
- **Key modules**: 
  - `MixinAuthorization.mo` - Main authorization logic
  - `access-control.mo` - Core access control primitives
- **Lint rules**: Prevents redeclaration of critical auth functions
- **Usage**: Mixed into the main canister for admin/user role management
- **Reference**: See [[caffeine-platform-integration]] for integration details

**`caffeineai-http-outcalls@0.1.0`**
- **Purpose**: HTTP outcall abstractions for external API requests
- **Key module**: `outcall.mo` - Wrapper around IC's management canister HTTP API
- **Why needed**: Internet Computer canisters can't directly make HTTP requests; requires special API

### Cryptographic Primitives

**`ecdsa@7.1.0`** - ECDSA signature verification on secp256k1 curve
- **Purpose**: EIP-191 Ethereum signature verification (front-running protection)
- **Use case**: Verifying wallet-signed bind messages from users
- **Modules**: `Binary.mo`, `Field.mo` for elliptic curve operations
- **Status**: Active library, last updated 2025-09
- **Reference**: See [[security-audit-findings]] for context on signature verification requirements

**`sha3@0.1.1`** - Low-level Keccak-f[1600] round function
- **Purpose**: Foundation for Keccak-256 hashing
- **Implementation**: Custom `_keccak256` helper built on top in `main.mo`
- **Why needed**: Ethereum-compatible hashing for EIP-191 signatures

**Transitive dependencies**:
- `sha2@0.1.6` - SHA-2 family hashing (pulled by ecdsa)
- `asn1@3.1.0` - ASN.1 encoding/decoding for signature formats
- `xtended-numbers@2.1.0` - Extended numeric types for crypto operations
- `base-x-encoder@2.1.0` - Base encoding utilities

## Toolchain Configuration

### Motoko Compiler Options (`[moc]` in mops.toml)

```toml
args = [
  "--default-persistent-actors",        # Enable stable memory by default
  "--actor-idl=src/backend/system-idl", # Output Candid IDL files
  "--implicit-package=core",            # Auto-import core library
  "-no-check-ir",                       # Skip IR validation (faster builds)
  "-E=M0236,M0235,M0223,M0237",        # Suppress specific warnings
  "-A=M0198"                            # Allow specific warning as error
]
```

**Why these flags**:
- `--default-persistent-actors`: Ensures canister upgrades preserve state
- `--actor-idl`: Generates Candid interface for frontend bindings
- `-no-check-ir`: Trade-off for faster dev iteration (production builds may re-enable)
- Warning suppressions: Likely for legacy code or intentional patterns

### Stable Memory Check

```toml
[canisters.backend.check-stable]
path = ".old/src/backend/dist/backend.most"
```

**Purpose**: Verifies stable memory compatibility between canister versions during upgrades. The `.most` file contains the stable type signature from the previous build.

**Why critical**: Incompatible stable memory changes can brick a canister during upgrade. See [[canister-upgrade-mechanisms]] for upgrade safety details.

## Root-Level Scripts

```json
"scripts": {
  "build": "pnpm -r --if-present run build",       // Recursive workspace build
  "typecheck": "pnpm -r --if-present run typecheck", // Type checking all workspaces
  "check": "pnpm -r --if-present run check",        // Lint/check all workspaces  
  "fix": "pnpm -r --if-present run fix",            // Auto-fix linting issues
  "bindgen": "caffeine-bindgen ..."                 // Generate TS bindings from Candid
}
```

**`bindgen` command breakdown**:
```bash
caffeine-bindgen \
  --did-file ./src/backend/dist/backend.did \      # Input: Candid interface
  --out-dir ./src/frontend/src \                    # Output: Frontend src
  --actor-interface-file \                          # Generate TypeScript interfaces
  --force                                           # Overwrite existing files
```

**Critical for development**: Frontend TypeScript code depends on auto-generated types from the backend Candid interface. This must run after backend builds and before frontend type-checking.

## Dependency Resolution Strategy

### Version Pinning

| Package Type | Strategy | Rationale |
|-------------|----------|----------|
| **Mops packages** | Exact versions in `mops.toml` | Deterministic builds, security |
| **Lock files** | Content hashes | Integrity verification |
| **Frontend deps** | Locked in `pnpm-lock.yaml` | Reproducibility |

### Transitive Dependency Tree

```
core@2.2.0 (direct)
  └─ (no deps, it's the stdlib)

caffeineai-authorization@0.1.0 (direct)
  └─ (minimal deps, mostly self-contained)

caffeineai-http-outcalls@0.1.0 (direct)
  └─ (minimal deps)

ecdsa@7.1.0 (direct)
  ├─ sha2@0.1.6
  ├─ asn1@3.1.0
  ├─ xtended-numbers@2.1.0
  │   └─ xtended-iter@1.1.0
  ├─ base-x-encoder@2.1.0
  └─ (other crypto primitives)

sha3@0.1.1 (direct)
  └─ iterext (from GitHub)
```

**GitHub dependency**: `iterext` pulled directly from `https://github.com/timohanke/motoko-iterext#v2.0.0`
- Used by `sha3` for iterator extensions
- Pinned to specific git tag for stability

## Development Workflow

### Installing Dependencies

**Backend**:
```bash
cd src/backend/
mops install      # Reads mops.toml, updates mops.lock
```

**Frontend** (if exists):
```bash
cd src/frontend/
pnpm install --prefer-offline  # Uses local cache when possible
```

**Root** (bootstrapping):
```bash
pnpm install      # Sets up workspace, installs root deps
```

### Type Checking

**Backend**:
```bash
mops check --fix  # Type-check Motoko, auto-fix simple issues
```

**Frontend**:
```bash
pnpm typecheck    # Run TypeScript compiler in check mode
```

### Building

**Correct order** (due to binding generation dependency):

1. **Backend build**: `mops build` → produces `backend.did` and `backend.wasm`
2. **Generate bindings**: `pnpm bindgen` → creates TypeScript interfaces
3. **Frontend build**: `pnpm build` → uses generated types

Reference: See [[developer-tooling-and-automation]] for full build pipeline.

## Security Considerations

### Dependency Integrity

- **Hash verification**: `mops.lock` includes SHA-256 hashes for every file in every package
- **Reproducible builds**: Locked versions ensure same input → same output
- **Supply chain security**: Caffeine AI packages are internally maintained

### Cryptographic Library Choices

**Why ECDSA on secp256k1?**
- Ethereum wallet compatibility (MetaMask, WalletConnect)
- Industry-standard curve with extensive testing
- Required for EIP-191 signature verification

**Why Keccak-256 (sha3)?**
- Ethereum's standard hashing algorithm (NOT the final SHA-3 standard)
- Required for Ethereum address derivation and message hashing
- Must match on-chain signature verification

See [[security-audit-findings]] for audit recommendations on signature verification.

## Common Gotchas

### 1. **Binding Generation Timing**

**Problem**: Frontend type errors after backend changes

**Solution**: Always run `pnpm bindgen` after `mops build`

### 2. **pnpm vs npm**

**Problem**: Project enforces pnpm, but npm is used by mistake

```json
"npm": "please use pnpm"  // This shows up as an error in npm
```

**Solution**: Install pnpm globally: `npm install -g pnpm`

### 3. **Stable Memory Compatibility**

**Problem**: Canister upgrade fails due to type changes

**Check**: Mops automatically verifies against `.old/src/backend/dist/backend.most`

**Solution**: See [[canister-upgrade-mechanisms]] for migration strategies

### 4. **Motoko Compiler Version**

**Problem**: Different team members have different `moc` versions

**Solution**: Mops enforces toolchain version from `mops.toml`:
```toml
[toolchain]
moc = "1.3.0"  # Everyone uses this exact version
```

## Related Documentation

- [[developer-tooling-and-automation]] - Build and deployment scripts
- [[caffeine-platform-integration]] - How Caffeine AI packages are used
- [[security-audit-findings]] - Security requirements driving crypto dependencies
- [[canister-upgrade-mechanisms]] - Stable memory and upgrade safety
- [[environment-and-workspace-configuration]] - Workspace structure and setup
