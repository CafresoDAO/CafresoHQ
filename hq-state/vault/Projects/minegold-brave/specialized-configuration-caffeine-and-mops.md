---
tags: [project-study, minegold-brave]
---
# Specialized Configuration: Caffeine and Mops

Beyond the standard [[dfx-configuration-and-project-structure]], this project uses two specialized TOML files, `caffeine.toml` and `mops.toml`, to manage its build process and dependencies, particularly for the Motoko backend.

### `caffeine.toml`: Project Manifest

This file acts as a high-level project manifest. Its primary roles are to define the project's identity, specify which files are part of the workspace, and declare dependencies between canisters.

```toml
manifest_version = "0.1.0"

[project]
id = "my-app"
name = "my-app"

[workspace]
include = ["src/**"]

[canisters.frontend]
depends_on = ["backend"]
```

The key takeaway is the `[canisters.frontend]` section, which explicitly states that the frontend canister depends on the backend. This informs the build and deployment order.

### `mops.toml`: Motoko Package & Build Configuration

This file is the configuration hub for `mops`, the Motoko package manager, and the `moc` Motoko compiler. It's much more granular than `caffeine.toml`.

Its responsibilities include:
- **Package Metadata**: Defines the backend canister's name and version.
- **Build Instructions**: Specifies the output directory and compiler arguments.
- **Canister Entry Point**: Points to the main Motoko source file (`src/backend/main.mo`).
- **Toolchain Pinning**: Locks the specific versions of `moc` and the linter `lintoko`.
- **Compiler Flags**: Provides a detailed list of arguments for the `moc` compiler to control features and suppress warnings.
- **Dependencies**: Lists the Motoko libraries required for the project, with insightful comments explaining their purpose.

```toml
[package]
name = "backend"
version = "0.1.0"

[canisters.backend]
main = "src/backend/main.mo"

[toolchain]
moc = "1.3.0"
lintoko = "0.7.0"

[dependencies]
core = "2.2.0"
caffeineai-authorization = "0.1.0"
caffeineai-http-outcalls = "0.1.0"
# Crypto primitives for EIP-191 signature verification (front-running fix).
# - ecdsa: ECDSA signature verify on secp256k1 curve, used to verify the
#   wallet-signed bind message. Active library, last updated 2025-09.
# - sha3: low-level Keccak-f[1600] round function. We build keccak256 on
#   top of it (see _keccak256 helper in main.mo).
ecdsa = "7.1.0"
sha3 = "0.1.1"
```

The comments in the `[dependencies]` section are particularly valuable, explaining that `ecdsa` and `sha3` are used for Ethereum's EIP-191 signature verification, which is a critical security detail.