# RustDesk + ICP DApp Architecture

**Date:** 2026-04-25  
**Status:** Initial research

---

## Overview

Exploring how RustDesk (open-source remote desktop) could integrate with Internet Computer Protocol (ICP) for a decentralized remote access solution.

---

## Key Synergies

- **Shared Language:** RustDesk is Rust-native; ICP canisters compile from Rust → unified codebase potential
- **Self-Hosting → On-Chain Hosting:** RustDesk already decentralizes away from TeamViewer/AnyDesk; ICP could replace self-hosted relay servers with canisters
- **Identity & Auth:** ICP's Internet Identity could replace RustDesk's ID/password system with cryptographic auth
- **Canister as Signaling Server:** ICP canisters could handle device registration, connection brokering, and NAT hole-punch coordination

---

## Architecture Concept

```
┌─────────────────┐       ┌──────────────────────┐
│  RustDesk Client │◄────►│   ICP Canister       │
│  (Desktop/Mobile)│       │  - Device registry   │
└────────┬────────┘       │  - Session broker    │
         │                 │  - Auth (II)         │
         │                 └──────────┬───────────┘
         │                            │
         └────────P2P Stream──────────┘
              (after ICP handshake)
```

---

## Challenges

| Challenge | Notes |
|-----------|-------|
| **Latency** | ICP consensus adds ~200-400ms; fine for signaling, not for video relay |
| **UDP/P2P** | ICP only supports HTTP outcalls; P2P streams must stay off-chain |
| **Relay fallback** | When P2P fails, RustDesk uses relay servers—canisters can't relay raw streams |
| **Storage costs** | Session metadata is cheap; storing connection logs at scale needs cycle budgeting |

---

## Viable Hybrid Model

1. **On-chain (ICP canister):**
   - Device identity registry
   - Connection request queue
   - Access control / permissions
   - Audit logs (hashed)

2. **Off-chain (traditional infra or edge):**
   - Actual video/input stream relay
   - Low-latency STUN/TURN

---

## Next Steps

- [ ] Prototype canister for device registration (Rust + Candid)
- [ ] Test Internet Identity integration with RustDesk auth flow
- [ ] Benchmark ICP signaling latency vs current RustDesk relay
- [ ] Explore Threshold ECDSA for end-to-end encryption keys

---

**Related:** ICP Rust Agent docs, RustDesk self-host guide