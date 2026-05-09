---
tags: [project-study, minegold-brave, overview, architecture, icp]
---
# Project Overview and Architecture: Minegold.brave

Minegold.brave is a decentralized application (dApp) built for the Internet Computer Protocol (ICP). It leverages the `dfx` command-line tool for local development, building, and deployment.

## Core Components (Canisters)

The application is structured around several ICP canisters, as defined in `dfx.json`:

*   **`backend`**: This is a custom canister responsible for the application's core logic. Its `wasm` and `candid` files are expected to be found in `src/backend/dist`. The build process for this canister involves `mops install` and `mops build`, suggesting it's likely written in Motoko or Rust.

    ```json
    "backend": {
      "type": "custom",
      "wasm": "src/backend/dist/backend.wasm",
      "candid": "src/backend/dist/backend.did",
      "build": "bash -c 'test -f src/backend/dist/backend.wasm && test -f src/backend/dist/backend.did || { echo \"[dfx.json] Pre-built backend artifacts missing.\"; echo \"         Run:  cd src/backend && mops install && mops build\"; exit 1; }'"
    }
    ```

*   **`frontend`**: This canister serves the user interface assets. It depends on the `backend` canister, meaning the frontend interacts with the backend for its functionality. The build process uses `pnpm install` and `pnpm build`, indicating a JavaScript/TypeScript-based frontend framework (e.g., React, Vue, Svelte).

    ```json
    "frontend": {
      "type": "assets",
      "source": ["src/frontend/dist"],
      "dependencies": ["backend"],
      "build": "bash -c 'test -d src/frontend/dist && test -f src/frontend/dist/index.html || { echo \"[dfx.json] Pre-built frontend missing.\"; echo \"         Run:  cd src/frontend && pnpm install && pnpm build\"; exit 1; }'"
    }
    ```

*   **`internet_identity`**: This is a pre-configured custom canister for user authentication. It points to official DFINITY releases for its `candid` and `wasm` files, and has a remote ID for the mainnet ICP network. This indicates that user authentication will be handled securely through the Internet Identity service.

    ```json
    "internet_identity": {
      "type": "custom",
      "candid": "https://github.com/dfinity/internet-identity/releases/latest/download/internet_identity.did",
      "wasm": "https://github.com/dfinity/internet-identity/releases/latest/download/internet_identity_dev.wasm.gz",
      "remote": {
        "id": {
          "ic": "rdmx6-jaaaa-aaaaa-aaadq-cai"
        }
      },
      "frontend": {}
    }
    ```

## Development and Deployment Networks

The `dfx.json` also defines two networks:

*   **`local`**: An ephemeral local replica for development and testing, binding to `127.0.0.1:4943`.
*   **`ic`**: The mainnet ICP network, using `https://icp-api.io` as a provider for persistent deployments.

This setup allows developers to build and test their dApp locally before deploying it to the decentralized Internet Computer mainnet.