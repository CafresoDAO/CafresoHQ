---
tags: [project-study, minegold-brave, docker, devops]
---

# Containerized Development Environment

Minegold.defi provides a **Docker-based development environment** that encapsulates all build tools, dependencies, and deployment infrastructure. This enables consistent builds across different machines and CI/CD pipelines without requiring developers to manually install the ICP toolchain.

## Overview

The `Dockerfile` creates a self-contained environment with:
- **Ubuntu 24.04** base image
- **Motoko** compiler toolchain (v1.2.0)
- **ICP CLI** for canister management
- **Node.js 20.x** + **pnpm** for frontend builds
- **mops** for Motoko package management

**Entry point**: `deploy.sh` runs automatically when the container starts, launching a local ICP replica and deploying both frontend and backend canisters.

## Build Architecture

### Base Layer

The Dockerfile uses a single-stage build starting from `ubuntu:24.04`:

```dockerfile
FROM ubuntu:24.04 AS base
ENV TZ=UTC
ARG NODE_VERSION=20.x
```

**System dependencies installed**:
- `curl`, `wget` — for downloading toolchains
- `build-essential`, `clang`, `llvm` — C/C++ compilation (needed for some Rust/Node native modules)
- `pkg-config`, `libssl-dev` — SSL/TLS support
- `ca-certificates`, `gnupg` — secure package verification

### Toolchain Installation

#### 1. Node.js + pnpm

```dockerfile
RUN curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | \
    gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
RUN apt-get install -y nodejs
RUN npm install -g pnpm@latest-10
```

- Installs Node.js 20.x from the official NodeSource repository
- Pins pnpm to the latest version in the 10.x series
- Used for frontend builds in `src/frontend/`

#### 2. Mops (Motoko Package Manager)

```dockerfile
RUN npm i -g ic-mops@1.11.1
```

- Installs **ic-mops v1.11.1** globally
- Manages Motoko dependencies defined in `mops.toml`
- Required for backend canister builds

#### 3. ICP CLI

```dockerfile
RUN curl --proto '=https' --tlsv1.2 -LsSf \
    https://github.com/dfinity/icp-cli/releases/download/v0.1.0-beta.3/icp-cli-installer.sh | sh
ENV PATH="/home/ubuntu/.cargo/bin:${PATH}"
```

- Installs **icp-cli v0.1.0-beta.3** (alternative to `dfx`)
- Binary placed in `~/.cargo/bin/`
- Used by `deploy.sh` for network management and canister deployment

#### 4. Motoko Compiler Toolchain

The Dockerfile installs three Motoko components:

**a) Motoko Compiler (`moc`)**
```dockerfile
MOTOKO_VERSION=1.2.0
COMPILER_TARBALL="motoko-Linux-x86_64-${MOTOKO_VERSION}.tar.gz"
COMPILER_INSTALL_DIR="$HOME/.motoko/moc/$MOTOKO_VERSION/bin"
curl -L "$COMPILER_RELEASE_URL" | tar -xz -C "$COMPILER_INSTALL_DIR"
```

- Downloads architecture-specific binaries (x86_64 or aarch64)
- Installs to `~/.motoko/moc/1.2.0/bin/`
- Custom Caffeine Labs fork (not the official DFINITY compiler)

**b) Motoko Core Library**
```dockerfile
CORE_LIB_VERSION=moc-1.2.0
curl -L "$CORE_LIB_URL" | tar -xz --strip-components=2 \
    -C "$CORE_LIB_INSTALL_DIR" "motoko-core-${CORE_LIB_VERSION}/src"
```

- Core runtime libraries for Motoko
- Extracted from `caffeinelabs/motoko-core` repository

**c) Motoko Base Library**
```dockerfile
BASE_LIB_VERSION=SKIP
curl -L "$BASE_LIB_URL" | tar -xz --strip-components=2 \
    -C "$BASE_LIB_INSTALL_DIR" "motoko-base-moc-${BASE_LIB_VERSION}/src"
```

- Standard library (data structures, utilities)
- Version tagged as `SKIP` (likely a specific Caffeine Labs release)

**Environment variables set**:
```dockerfile
ENV MOC_PATH="/home/ubuntu/.motoko/moc/1.2.0/bin/moc"
ENV MOTOKO_CORE="/home/ubuntu/.motoko/core/moc-1.2.0"
ENV MOTOKO_BASE="/home/ubuntu/.motoko/base/SKIP"
```

These tell mops and build scripts where to find the compiler and libraries.

### User Configuration

The container runs as the **ubuntu** user (not root) for security:

```dockerfile
USER ubuntu
WORKDIR /home/ubuntu
ENV HOME=/home/ubuntu
RUN mkdir -p /home/ubuntu/bin
```

**PATH configuration**:
```dockerfile
ENV PATH=/home/ubuntu/.mops/bin:/home/ubuntu/bin:\
/home/ubuntu/.local/share/dfx/bin:/home/ubuntu/.cargo/bin:${PATH}
```

Adds:
- `~/.mops/bin/` — mops-installed binaries
- `~/bin/` — user scripts
- `~/.local/share/dfx/bin/` — dfx (if installed)
- `~/.cargo/bin/` — icp-cli and Rust tools

### PNPM Optimization

The container configures pnpm for faster, offline-capable builds:

```dockerfile
RUN mkdir -p /home/ubuntu/.config/pnpm \
    /home/ubuntu/.local/share/pnpm/store \
    /home/ubuntu/.cache/pnpm

cat > /home/ubuntu/.config/pnpm/rc << 'PNPMRC'
nodeLinker=hoisted
store-dir=/home/ubuntu/.local/share/pnpm/store
cache-dir=/home/ubuntu/.cache/pnpm
prefer-offline=true
PNPMRC
```

**Key settings**:
- `nodeLinker=hoisted` — flattened node_modules structure (faster, better compatibility)
- `prefer-offline=true` — uses cached packages when available
- Custom store/cache dirs for persistent volumes

## Container Entry Point

```dockerfile
COPY --chown=ubuntu:ubuntu . /workdir/
RUN chmod +x /workdir/deploy.sh
ENTRYPOINT ["/workdir/deploy.sh"]
```

- Copies the entire project into `/workdir/`
- Sets `deploy.sh` as the default command
- When you run `docker run <image>`, it automatically starts the local ICP network and deploys canisters

See [[local-deployment-with-dfx]] for details on what `deploy.sh` does.

## Usage Patterns

### Building the Image

```bash
docker build -t minegold-defi:latest .
```

**Build time**: ~5-10 minutes (depends on network speed for downloading toolchains)

### Running Local Deployment

```bash
docker run -p 8000:8000 -p 4943:4943 minegold-defi:latest
```

**Ports**:
- `8000` — Internet Identity canister
- `4943` — Local ICP replica API

The container will:
1. Start the ICP network via `icp network start -d`
2. Create frontend and backend canisters
3. Deploy both canisters
4. Keep running until you press Ctrl+C

### Connecting to the Deployed App

After deployment completes, you can access:
- **Backend API**: `http://localhost:6188` (storage gateway)
- **Internet Identity**: `http://rdmx6-jaaaa-aaaaa-aaadq-cai.localhost:8000`
- **Frontend**: Check `deploy.sh` output for the generated canister URL

## Design Rationale

### Why Docker?

1. **Reproducible builds** — everyone uses the exact same compiler versions
2. **Simplified onboarding** — no need to manually install 5+ tools
3. **CI/CD compatibility** — same image runs locally and in GitHub Actions
4. **Isolation** — Motoko toolchain doesn't pollute the host system

### Why Custom Motoko Builds?

The Dockerfile uses **Caffeine Labs forks** of Motoko:
- `https://github.com/caffeinelabs/motoko`
- `https://github.com/caffeinelabs/motoko-core`
- `https://github.com/caffeinelabs/motoko-base`

This suggests the project was **originally developed in Caffeine.ai** (a web-based ICP IDE) and exported for local development. The custom compiler might include:
- Caffeine-specific optimizations
- Bug fixes not yet in upstream DFINITY releases
- Compatibility patches for the generated `backend.wasm`

**Trade-off**: Using a custom fork means you can't easily upgrade to newer DFINITY compiler releases without testing compatibility.

### Why ICP CLI Instead of DFX?

The container installs **icp-cli** (v0.1.0-beta.3) instead of the standard `dfx` tool. This is likely because:
- Caffeine.ai uses icp-cli internally
- It's lighter-weight than the full dfx SDK
- Simpler API for programmatic canister management

However, the **launch scripts** (`launch.sh`, `launch-mainnet.sh`) use `dfx`, not icp-cli. So the Dockerized `deploy.sh` workflow is distinct from the manual launch scripts. See [[build-and-deploy-process]] for the comparison.

## Gotchas

### 1. Motoko Base Library Version is "SKIP"

```dockerfile
BASE_LIB_VERSION=SKIP
```

This unusual version tag suggests a specific Caffeine Labs snapshot. If you need to debug Motoko base library issues, check:
- `https://github.com/caffeinelabs/motoko-base/releases/tag/moc-SKIP`

### 2. deploy.sh Runs Forever

The `deploy.sh` script contains:
```bash
while true; do
    sleep 2
done
```

This keeps the container alive so the ICP replica stays running. **To stop it**, you must send Ctrl+C (SIGINT) or `docker stop <container>`. The cleanup trap ensures the replica shuts down gracefully:
```bash
trap 'cleanup 1' INT TERM
```

### 3. No Volume Persistence

The Dockerfile doesn't define volumes for:
- `.dfx/` — canister state
- `node_modules/` — dependencies
- `~/.local/share/pnpm/store/` — pnpm cache

Each container run starts with a **fresh state**. To persist data across runs:
```bash
docker run -v $(pwd)/.dfx:/workdir/.dfx \
           -v pnpm-cache:/home/ubuntu/.local/share/pnpm/store \
           minegold-defi:latest
```

### 4. Architecture Detection

```dockerfile
case ${TARGETARCH:-$(uname -m)} in
    amd64|x86_64) COMPILER_TARBALL="motoko-Linux-x86_64-${MOTOKO_VERSION}.tar.gz" ;;
    arm64|aarch64) COMPILER_TARBALL="motoko-Linux-aarch64-${MOTOKO_VERSION}.tar.gz" ;;
esac
```

Supports both **x86_64** (Intel/AMD) and **aarch64** (Apple Silicon, ARM servers). If building on unsupported architecture, the build will fail with "Unsupported architecture" error.

## Related Documentation

- [[build-and-deploy-process]] — Comparison of deploy.sh vs launch.sh workflows
- [[local-deployment-with-dfx]] — Manual dfx-based deployment (non-Docker)
- [[project-dependencies]] — Details on mops packages and frontend dependencies
- [[entry-points-and-local-deployment]] — How deploy.sh orchestrates the deployment

## Further Reading

- [ICP CLI Documentation](https://github.com/dfinity/icp-cli)
- [Mops Package Manager](https://mops.one/)
- [Caffeine.ai Platform](https://caffeine.ai/) — Original development environment
- [Docker Best Practices for Node.js](https://github.com/nodejs/docker-node/blob/main/docs/BestPractices.md)