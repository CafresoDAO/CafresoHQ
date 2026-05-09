---
tags: [research, frontend, agent-js]
---

# Frontend Integration with agent-js

Connecting a web-based frontend, like our Cafreso Design System, to a backend canister running on the Internet Computer is primarily handled by the official `agent-js` library. This library acts as the communication layer, analogous to `web3.js` or `ethers.js` in the Ethereum ecosystem.

### Core Concepts

1.  **Agent**: The `Agent` is the low-level interface for communicating with the Internet Computer. You configure it to talk to a specific network (like the local replica or the mainnet).

2.  **Actor**: An `Actor` is a higher-level JavaScript object that represents a specific canister. It's created using an `Agent` and the canister's Candid interface definition (IDL).

3.  **Candid Interface**: The Candid interface of a canister defines all its public methods and data types. The `dfx` toolchain can automatically generate JavaScript or TypeScript files from this interface using the `dfx generate` command. This is a massive boon for development, as it provides type-safe methods to call your canister's functions directly from the frontend.

### Typical Workflow

-   **Installation**: Add `@dfinity/agent` and other related packages to your frontend project.
-   **Code Generation**: Run `dfx generate <canister_name>` to create the actor interface files. This command inspects your `dfx.json` configuration and the canister's Candid file.
-   **Instantiation**: In your frontend code, you import the generated actor, create an `HttpAgent`, and then instantiate the actor. This gives you a ready-to-use object for making calls.
-   **Method Calls**: You can then call the canister's public methods as if they were local asynchronous functions on the actor object (e.g., `await myCanisterActor.someQueryFunction();`). The agent handles all the underlying complexity of serialization, signing, and communication with the IC.

This approach provides a clean separation between our [[03-core-canDB-api-modules|canDB backend logic]] and the frontend presentation layer, while still offering a strongly-typed and efficient connection.