---
tags: [research, architecture]
---
# 15. Application Architecture with canDB: A Case Study

The Cafreso project provides an excellent real-world example of how to structure a decentralized application (dapp) on the Internet Computer using `canDB` for scalable data storage. The architecture follows a service-oriented pattern, where different canisters are responsible for specific domains of the application's logic and data.

## High-Level Project Structure

The repository is cleanly divided into three main areas:
-   `src/backend`: Contains all the Motoko source code for the canisters.
-   `src/frontend`: A SvelteKit application for the user interface.
-   `src/e2e`: End-to-end tests that verify the interaction between the frontend and backend.

## Backend Canister Breakdown

The backend is not a single monolithic canister. Instead, it's composed of several specialized canisters that work together:

1.  **`IndexCanister.mo`**: This acts as the central router or registry. It likely holds references to all other canisters, making it the primary entry point for the frontend. This pattern simplifies frontend configuration and allows for easier canister management and upgrades. See [[14-cafreso-project-structure-and-canisters]].

2.  **`UserService`**: This canister is dedicated to managing all user-related data. Looking at the file structure (`User.mo`, `OrderHistory.mo`, `Address.mo`), it handles user profiles, authentication, and personal data like order histories. It would instantiate its own `canDB` instances to store this sharded user data.

3.  **`AppService`**: This canister handles the core business logic of the application, such as managing products (`Product.mo`) and application logs (`Log.mo`). It's distinct from the `UserService` to separate concerns, which is a great practice for scalability and maintenance.

4.  **`generic/CanDB.mo`**: This isn't a running canister itself, but the generic, reusable `canDB` library code that both `UserService` and `AppService` import and use to create their underlying data storage canisters. This highlights the power of `canDB` as a foundational data layer. See [[03-core-canDB-api-modules]].

## Frontend-to-Backend Connection

The frontend Svelte components in `src/frontend/lib/components/entities` mirror the backend canister structure. There are components for `user`, `product`, `order`, etc. This one-to-one mapping suggests that each part of the UI communicates with a specific backend service to fetch and manipulate its data, likely using `agent-js` as the bridge. See [[13-frontend-integration-with-agent-js]].

This architecture is efficient and scalable. By separating data and logic into different canisters, the application avoids hitting canister storage limits and can be updated in a modular fashion.