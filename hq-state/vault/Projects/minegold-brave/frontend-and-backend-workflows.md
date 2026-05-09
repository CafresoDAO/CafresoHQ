---
tags: [project-study, minegold-brave]
---
# Frontend and Backend Development Workflows

The `AGENTS.md` file provides a concise guide to the project's development and build process, revealing a clear separation between the frontend and backend workflows. Each has its own dedicated tooling and commands.

This separation allows developers to work on the UI and the core canister logic independently before integrating them.

## Frontend Workflow (`src/frontend/`)

The frontend is managed using `pnpm`, a common package manager in the Node.js ecosystem. All commands should be run from the `src/frontend/` directory.

```bash
# Install dependencies (preferring offline cache)
pnpm install --prefer-offline

# Run the TypeScript type checker
pnpm typecheck

# Automatically fix linting issues
pnpm fix

# Build the production assets
pnpm build
```

## Backend Workflow (`src/backend/`)

The backend canister code is managed with `mops`, the package manager for the Motoko programming language. Commands should be run from the `src/backend/` directory.

```bash
# Install Motoko dependencies
mops install

# Check types and apply fixes
mops check --fix

# Build the backend canister
mops build
```

## Integration Step (Root Directory)

To enable communication between the frontend and the backend, type bindings must be generated. This crucial step, run from the project root, creates the necessary interface files for the frontend to call backend methods.

```bash
# Generate frontend bindings for backend methods
pnpm bindgen
```

This workflow is a key part of the project's [[developer-tooling-and-build-process]].