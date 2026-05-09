---
tags: [project-study, minegold-brave]
---
# Codebase Structure and Key Directories

The Minegold project follows a standard monorepo structure with a clear separation between frontend and backend code. This organization is immediately apparent from the top-level `src` directory.

```
src/
├── backend/
└── frontend/
```

This design separates the user-facing components from the core business logic running on the Internet Computer.

### `src/frontend/`

This directory contains all client-side code responsible for the application's user interface and user experience. Based on the project's tooling, this is a JavaScript/TypeScript project managed with `pnpm`.

Key workflows and build processes for the frontend are detailed in [[frontend-and-backend-workflows]] and [[verified-build-commands-and-dev-workflow]].

### `src/backend/`

This directory houses the backend logic, which is compiled into a canister and deployed on the Internet Computer. It handles core business logic, state management, and data persistence.

This is a Motoko project managed by the `mops` package manager. Further details on its implementation can be found in [[backend-core-implementation]].

The clear separation simplifies development, as frontend and backend concerns are isolated, and allows for independent build and test processes as seen in [[developer-tooling-and-build-process]].