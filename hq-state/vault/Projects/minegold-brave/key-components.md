---
tags: [project-study, minegold-brave]
---
# Key Components: Canisters Overview

The Minegold.brave project is structured around several canisters, which are fundamental building blocks on the Internet Computer. The `dfx.json` configuration file provides a clear definition of these core components:

## 1. `backend` Canister

*   **Type**: Custom canister
*   **Purpose**: This canister houses the application's core business logic and data. It's where the primary functionality of Minegold.brave is implemented.
*   **Location**: Source code and build artifacts are expected within the `src/backend` directory.
*   **Build Command Snippet**:
    ```bash
    test -f src/backend/dist/backend.wasm && test -f src/backend/dist/backend.did || { echo "[dfx.json] Pre-built backend artifacts missing."; echo "         Run:  cd src/backend && mops install && mops build"; exit 1; }
    ```
    This command ensures that the `backend.wasm` (WebAssembly module) and `backend.did` (Candid interface definition) files are present, indicating a compiled module.

## 2. `frontend` Canister

*   **Type**: Assets canister
*   **Purpose**: This canister serves the user interface (UI) for the Minegold.brave application. It provides the web assets (HTML, CSS, JavaScript) that users interact with in their browsers.
*   **Location**: Frontend assets are served from the `src/frontend/dist` directory.
*   **Dependencies**: It explicitly depends on the `backend` canister, meaning the frontend will likely interact with the backend for data and functionality.
*   **Build Command Snippet**:
    ```bash
    test -d src/frontend/dist && test -f src/frontend/dist/index.html || { echo "[dfx.json] Pre-built frontend missing."; echo "         Run:  cd src/frontend && pnpm install && pnpm build"; exit 1; }
    ```
    This ensures the `dist` directory and `index.html` are present, signifying a built frontend application.

## 3. `internet_identity` Canister

*   **Type**: Custom canister (remote dependency)
*   **Purpose**: This is a crucial external service for secure, anonymous user authentication on the Internet Computer. It allows users to log in to dApps without creating traditional usernames and passwords.
*   **Source**: It's fetched directly from DFINITY's official Internet Identity releases, not built locally.
*   **Remote ID**: `rdmx6-jaaaa-aaaaa-aaadq-cai` (mainnet ID)

This modular canister architecture is typical for dApps on the Internet Computer, promoting clear separation of concerns and leveraging existing infrastructure for common services like authentication.