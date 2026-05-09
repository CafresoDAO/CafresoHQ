---
tags: [project-study, minegold-brave]
---

# Project Overview: minegold.defi

`minegold.defi` is a cross-chain DeFi (Decentralized Finance) refinery dApp built to run on the **Internet Computer Protocol (ICP)**. Its primary function is to allow users to exchange Uniswap's ERC-20 token (**UNI**) for a synthetic, gold-backed token (**sGLDT**).

## Core User Flow

The process creates a bridge between the Ethereum and ICP ecosystems:

1.  A user connects an Ethereum wallet and deposits `UNI` to a specific address.
2.  An ICP service, the **ERC-20 minter canister**, observes the deposit and mints a corresponding amount of `ckUNI` (chain-key UNI) on the Internet Computer.
3.  The `minegold.defi` backend canister receives the `ckUNI` and releases `sGLDT` to the user's ICP wallet at the current exchange rate.

## Architecture & Tech Stack

The application is composed of two primary canisters:

| Canister | Type | Source | Description |
|---|---|---|---|
| `backend` | Motoko | `src/backend/main.mo` | Handles the core logic, including token swaps, user roles, and HTTP outcalls to services like CoinGecko. |
| `frontend`| Assets | `src/frontend/dist/` | The user-facing web interface, including wallet connection, transaction history, and price feeds. |

It also integrates with the standard **Internet Identity** canister for user authentication.

### Key Technologies

- **Blockchain**: Internet Computer Protocol (ICP)
- **Backend Language**: Motoko
- **Frontend Framework**: (Not specified, but uses Node.js tooling)
- **ICP SDK**: `dfx`
- **Package Management**: `pnpm` (for frontend) and `mops` (for Motoko)

This project was originally created with [Caffeine](https://caffeine.ai/) but is designed to be deployed and managed using the standard `dfx` tooling, as detailed in [[verified-build-commands-and-dev-workflow]].