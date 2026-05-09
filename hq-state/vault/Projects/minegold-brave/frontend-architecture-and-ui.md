---
tags: [project-study, minegold-brave, frontend, react, web3]
---

# Frontend Architecture and UI

## Overview

The Minegold.Brave frontend is a **React + TypeScript** single-page application built with **Vite** that provides a cross-chain DeFi interface for bridging Ethereum UNI tokens to ICP's sGLDT tokens through the ckERC-20 protocol.

**Tech Stack:**
- React 18 with TypeScript
- Vite (build tool + dev server)
- TanStack React Query (state/cache management)
- Viem (Ethereum interaction library)
- Internet Identity + WalletConnect (authentication)
- Tailwind CSS (styling)
- Lucide React (icons)

## Application Entry Point

**`src/frontend/src/main.tsx`** is the root entry point:

```tsx
// Polyfills MUST load first for WalletConnect compatibility
import "./polyfills";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ReactDOM from "react-dom/client";
import App from "./App";
import { InternetIdentityProvider } from "./auth";
import "./hooks/useTheme"; // Auto-applies stored theme on load

// Enable BigInt JSON serialization
BigInt.prototype.toJSON = function () {
  return this.toString();
};

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={queryClient}>
    <InternetIdentityProvider>
      <App />
    </InternetIdentityProvider>
  </QueryClientProvider>,
);
```

**Key initialization steps:**
1. **Polyfills first** — WalletConnect v2 requires `Buffer` and `process` globals
2. **Theme application** — stored theme class applied immediately to prevent flash
3. **BigInt serialization** — enables JSON.stringify on blockchain values
4. **Provider nesting** — QueryClient (data) → InternetIdentity (auth) → App

## Page Structure

The application has **four main pages** (though `App.tsx` is massive at >62k tokens, indicating it contains routing logic):

### 1. **BankingBraveHome.tsx** — Landing/Marketing Page

Public homepage shown to unauthenticated users:

```tsx
interface BankingBraveHomeProps {
  onLogin: () => void;
  isLoggingIn: boolean;
  onOpenMinegoldBrave: () => void;
  ethPrice?: number | null;
  uniPrice?: number | null;
  sgldtPrice?: number | null;
  treasury: TreasuryData; // Live treasury balances
}
```

**Features:**
- Hero section with Banking.Brave branding
- Live price ticker (ETH, UNI, sGLDT)
- Treasury balance display (sGLDT, ckUNI, ETH UNI)
- Theme toggle
- Sign in CTA

### 2. **MinegoldBraveSoon.tsx** — Coming Soon/Teaser

Likely shown before features are live or for specific protocols.

### 3. **TransactionHistoryPage.tsx** — User Deposit History

Shows user's past UNI deposit transactions and their status.

### 4. **AdminPage.tsx** — Admin Dashboard

Restricted interface for treasury management and system operations (see [[canister-upgrade-mechanisms]] and [[security-audit-findings]] for access controls).

## Component Architecture

### Core UI Components

#### **CrossChainFlow** — Bridge Visualization

Animated two-chain bridge UI showing ETH → ICP flow:

```tsx
type Props = {
  phase: "eth" | "bridge" | "icp" | "done";
  amount?: string;
};

export function CrossChainFlow({ phase, amount }: Props) {
  // Renders:
  // [Ethereum card] ←→ [ckERC-20 bridge] ←→ [ICP card]
  // with animated particles flowing between chains
}
```

**Phase states:**
- `"eth"` — User signing / tx mining on Ethereum
- `"bridge"` — ckERC-20 minter processing
- `"icp"` — ckUNI minted, sGLDT releasing on ICP
- `"done"` — Complete

**Visual design:**
- CSS-only animations (no motion library dependency)
- Gradient particle flow using keyframe animations (`xchain-flow`)
- Color-coded states: yellow (active), emerald (complete), zinc (pending)
- Chain glyphs rendered as inline SVG

#### **Other Key Components**

- **`ProtocolCards`** — Display available DeFi protocols
- **`BridgeProgressCard`** — Real-time deposit progress tracking
- **`TransactionTimeline`** — Step-by-step tx lifecycle visualization
- **`WorkflowStepper`** — Multi-step form progression UI
- **`ConnectWalletModal`** — Internet Identity login dialog
- **`WalletConnectModal`** — WalletConnect v2 pairing UI
- **`PixelAxeAnimation`** — Decorative mining animation
- **`BlockConfirmationMeter`** — Ethereum block confirmation counter
- **`ThemeToggle`** — Light/dark mode switcher
- **`GoldCTA`** — Branded call-to-action button

### Phase Components (Transaction Flow UI)

Located in `src/frontend/src/components/phases/`:

- **`PhaseWalletConfirming.tsx`** — "Waiting for wallet signature" state
- **`PhaseSuccess.tsx`** — Transaction completion screen

## State Management

### React Query Architecture

The frontend uses **TanStack React Query** for all server state, NOT Redux/Zustand. This provides:

- **Automatic caching** with configurable staleness
- **Background refetching** on window focus
- **Request deduplication**
- **Optimistic updates**
- **Query invalidation** on identity change

**`useBackendActor`** is the foundation hook:

```tsx
export function useBackendActor() {
  const { identity, isInitializing } = useInternetIdentity();
  const queryClient = useQueryClient();
  const principalText = identity?.getPrincipal().toString() ?? "anon";

  const actorQuery = useQuery({
    queryKey: [ACTOR_QUERY_KEY, principalText],
    queryFn: async () => {
      const agent = await HttpAgent.create({
        identity: identity as never,
        host: "https://icp-api.io",
      });
      return createActor("c626g-iyaaa-aaaau-agpoa-cai", ...);
    },
    enabled: !isInitializing,
    staleTime: Infinity, // Actor never goes stale
  });

  // Invalidate all queries when identity changes (login/logout)
  useEffect(() => {
    if (actorQuery.data) {
      queryClient.invalidateQueries({
        predicate: (q) => !q.queryKey.includes(ACTOR_QUERY_KEY),
      });
    }
  }, [actorQuery.data, queryClient]);

  return { actor: actorQuery.data || null, isFetching: actorQuery.isFetching };
}
```

**Key pattern:** When the user logs in/out, the actor changes, triggering **cascading invalidation** of all dependent queries (balances, deposits, treasury data). This ensures the UI always reflects the correct identity's data.

### Custom Hooks (from `useQueries.ts`)

All backend interaction happens through custom hooks:

**User queries:**
- `useUserSGLDTBalance()` — Current user's sGLDT token balance
- `useMyUNIDeposits()` — User's deposit history
- `isCallerBoundToEth()` — Check if principal is bound to ETH address

**Treasury queries:**
- `usePublicTreasuryBalance()` — Public sGLDT treasury balance
- `usePublicCkUNITreasuryBalance()` — Public ckUNI treasury balance
- `useDirectSGLDTTreasuryBalance()` — Direct treasury query (admin)
- `useDirectCkUNITreasuryBalance()` — Direct ckUNI query (admin)
- `useGetTreasuryWalletInfo()` — Treasury wallet addresses

**Mutations:**
- `directSubmitUNIDeposit()` — Submit UNI deposit transaction
- `autoFinalizeUNIDeposit()` — Complete deposit after confirmations
- `directBindEthAddressViaTx()` — Bind ETH address to principal
- `icrc1TransferFromCaller()` — ICRC-1 token transfer
- `useRetryUNIDepositPayout()` — Retry failed payout

**Admin queries:**
- `useIsAdmin()` — Check if caller has admin privileges

See [[api-and-endpoints]] for backend method signatures.

## Wallet Integration

### Dual Authentication System

The app supports **two parallel wallet systems**:

1. **Internet Identity** (ICP authentication)
   - Managed by `InternetIdentityProvider` context
   - Binds user to ICP Principal
   - Used for canister calls

2. **Ethereum Wallets** (EVM transaction signing)
   - **WalletConnect v2** (mobile wallets, MetaMask mobile)
   - **Browser extensions** (MetaMask, Coinbase Wallet via injected provider)
   - Used ONLY for signing Ethereum transactions

**Key files:**
- `src/frontend/src/lib/walletconnect.ts` — WalletConnect v2 session management
- `src/frontend/src/lib/eth.ts` — Viem-based Ethereum interaction
- `src/frontend/src/hooks/useEthereumWallet.ts` — Unified wallet hook

### Ethereum Address Binding

From `App.tsx` comments:

```tsx
// Wallet-binding crypto helpers removed — the bind now happens automatically
// inside the backend's submitUNIDeposit via _bindOrCheckEthAddress on the
// user's first refinery deposit. No client-side hashing/signing needed.
```

**Binding flow:**
1. User signs Ethereum tx with their wallet
2. Backend extracts ETH address from tx signature
3. Backend binds ETH address → ICP Principal automatically
4. Subsequent deposits verify the binding matches

See [[backend-core-implementation]] for `_bindOrCheckEthAddress` logic.

## Build Configuration

**`vite.config.js`** handles environment-specific builds:

```js
const ii_url =
  process.env.DFX_NETWORK === "local"
    ? `http://rdmx6-jaaaa-aaaaa-aaadq-cai.localhost:8081/`
    : `https://identity.ic0.app`;

process.env.II_URL = process.env.II_URL || ii_url;
process.env.STORAGE_GATEWAY_URL =
  process.env.STORAGE_GATEWAY_URL || "https://blob.caffeine.ai";
```

**Key configuration:**

- **Environment variable injection:**
  - `CANISTER_*` — Canister IDs (via `vite-plugin-environment`)
  - `DFX_*` — DFX network info
  - `II_URL` — Internet Identity URL (local replica vs mainnet)
  - `STORAGE_GATEWAY_URL` — Caffeine platform blob storage

- **Node.js polyfills for WalletConnect:**
  ```js
  define: {
    global: "globalThis",
    "process.env.NODE_ENV": JSON.stringify(process.env.NODE_ENV || "production"),
  }
  ```

- **Local development proxy:**
  ```js
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:4943", // Local dfx replica
        changeOrigin: true,
      },
    },
  }
  ```

- **Path aliases:**
  - `declarations` → `../declarations` (generated canister types)
  - `@` → `./src` (absolute imports)

**Build settings:**
- `sourcemap: false` — No source maps in production
- `minify: false` — Keep readable (likely for debugging)
- PostCSS with Tailwind CSS

See [[build-and-deploy-process]] for full build pipeline and [[containerized-development-environment]] for Docker setup.

## Frontend-Backend Boundary

**Critical connection point:** `src/frontend/src/backend.ts`

This file exports:
- `createActor()` — Factory for typed canister actor
- TypeScript declarations for all backend methods

**Type generation flow:**
1. Backend Motoko code compiled → `backend.did` (Candid interface)
2. DFX generates `backend.did.js` and `backend.did.d.ts` from Candid
3. Frontend imports types from `declarations/backend.did.d.ts`

See [[project-dependencies]] for Candid toolchain details.

## Styling and Theming

**Custom CSS properties** for theming (from `BankingBraveHome.tsx`):

```css
var(--bb-bg)          /* Background color */
var(--bb-text)        /* Primary text */
var(--bb-text-dim)    /* Dimmed text */
var(--bb-text-muted)  /* Muted text */
var(--bb-brand)       /* Brand accent color */
var(--bb-border)      /* Border color */
```

**Theme management:**
- `src/frontend/src/hooks/useTheme.ts` — Theme state hook
- Theme class applied to `<body>` on mount
- Persisted to localStorage
- Auto-loaded on page load (before first paint)

**Animation conventions:**
- Prefer CSS keyframes over JS libraries
- Example: `@keyframes xchain-flow` for cross-chain particle flow
- Tailwind's built-in animations (`animate-pulse`, etc.)

## Developer Experience

**Hot Module Replacement (HMR):**
Vite provides instant feedback during development — edit a component, see changes without full page reload.

**Type safety:**
Full TypeScript coverage with strict mode enabled (`tsconfig.json`).

**Post-build script:**
`src/frontend/scripts/post-build.mjs` — Runs after Vite build to process artifacts for canister deployment.

See [[developer-tooling-and-automation]] for additional dev utilities.

## Edge Cases and Gotchas

### 1. Polyfill Order Matters

From `main.tsx`:

```tsx
// IMPORTANT: polyfills MUST be imported before anything else so Buffer/process
// are on window before WalletConnect's init code runs.
import "./polyfills";
```

If polyfills load after WalletConnect, you get:
```
ReferenceError: Buffer is not defined
```

### 2. Identity Change Invalidation

When a user logs out while queries are in-flight, stale data can appear. The `useBackendActor` hook solves this by **invalidating ALL queries** when the actor changes:

```tsx
useEffect(() => {
  if (actorQuery.data) {
    queryClient.invalidateQueries({
      predicate: (q) => !q.queryKey.includes(ACTOR_QUERY_KEY),
    });
    queryClient.refetchQueries({
      predicate: (q) => !q.queryKey.includes(ACTOR_QUERY_KEY),
    });
  }
}, [actorQuery.data, queryClient]);
```

### 3. BigInt JSON Serialization

Blockchain values are `bigint`, which JSON.stringify doesn't support. The fix in `main.tsx`:

```tsx
BigInt.prototype.toJSON = function () {
  return this.toString();
};
```

Without this, you get:
```
TypeError: Do not know how to serialize a BigInt
```

### 4. Safe Balance Display

From `App.tsx`:

```tsx
function safeBalance(val: string | number | null | undefined): string {
  if (val === null || val === undefined || val === "" || val === "NaN")
    return "0.0000";
  const n = typeof val === "number" ? val : Number.parseFloat(String(val));
  return Number.isNaN(n) || !Number.isFinite(n) ? "0.0000" : String(val);
}
```

Prevents displaying "NaN", "undefined", or "Infinity" in the UI when balance queries fail.

### 5. Actor Creation Timing

From `useBackendActor`:

```tsx
enabled: !isInitializing,  // Don't build an actor before II has finished initializing
```

If you create an actor before Internet Identity finishes loading, you cache an **anonymous actor** that persists after login, causing authorization failures.

## Related Documentation

- [[backend-core-implementation]] — Canister methods called by frontend
- [[api-and-endpoints]] — Full API reference
- [[data-flow-and-transaction-lifecycle]] — How UNI deposits flow through the system
- [[wallet-integration]] — Deep dive on WalletConnect and ETH wallet handling (if it exists)
- [[build-and-deploy-process]] — Frontend build pipeline
- [[testing-and-quality-assurance]] — Frontend test strategy
- [[patterns-and-conventions]] — Code style and naming conventions

---

**Implementation notes:**
- The frontend is a **thick client** — most business logic lives in hooks and components, not the backend
- **No server-side rendering** — pure SPA deployed to ICP asset canister
- **Real-time updates** via React Query refetch intervals (not WebSockets)
- **Optimistic UI** for better UX (submit tx, show pending state immediately)