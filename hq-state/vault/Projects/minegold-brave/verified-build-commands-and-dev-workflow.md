---
tags: [project-study, minegold-brave]
---
# Verified Build Commands and Dev Workflow

This note provides the canonical, verified commands for building the Minegold project, sourced from `AGENTS.md`. Following this sequence is essential for a consistent and successful development workflow.

This process is a core part of the [[developer-tooling-and-build-process]].

## Standard Workflow

The typical workflow involves setting up the backend, then the frontend, and finally generating the integration bindings.

### 1. Backend Setup (`src/backend/`)

First, navigate to the `src/backend/` directory and run the following commands in order:

- **Install Dependencies**: Uses `mops`, the Motoko package manager.
  ```bash
  mops install
  ```
- **Typecheck & Fix**: Checks Motoko code for errors and applies automatic fixes.
  ```bash
  mops check --fix
  ```
- **Build Canister**: Compiles the backend canister.
  ```bash
  mops build
  ```

### 2. Frontend Setup (`src/frontend/`)

Next, navigate to the `src/frontend/` directory and run these commands:

- **Install Dependencies**: Uses `pnpm`, preferring an offline cache for speed.
  ```bash
  pnpm install --prefer-offline
  ```
- **Typecheck**: Runs the TypeScript compiler to check for type errors.
  ```bash
  pnpm typecheck
  ```
- **Lint & Fix**: Automatically fixes linting issues.
  ```bash
  pnpm fix
  ```
- **Build Application**: Compiles the frontend for deployment.
  ```bash
  pnpm build
  ```

### 3. Integration Step (Project Root)

Finally, return to the project's root directory to connect the frontend and backend. This is a critical step for [[frontend-backend-configuration-syncing|syncing the two parts]].

- **Generate Bindings**: This command creates the necessary TypeScript bindings so the frontend can make type-safe calls to the backend canister's methods.
  ```bash
  pnpm bindgen
  ```
