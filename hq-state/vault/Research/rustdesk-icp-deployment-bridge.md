---
tags: [icp, rustdesk, deployment, architecture, canister]
created: 2026-04-29
status: active-research
---

# Bridging Rustdesk + ICP Dapp: Design to Deployment

## The Gap

Rustdesk is a traditional client-server Rust application. ICP is a canister-based blockchain runtime. Bridging them requires decomposing Rustdesk's architecture into ICP-compatible components.

## Architecture Decomposition

### Rustdesk Components (Traditional)
| Component | Role | Port |
|-----------|------|------|
| `hbbs` | ID/Rendezvous server | 21115-21116 |
| `hbbr` | Relay server | 21117 |
| Client | Desktop app | - |

### ICP Canister Mapping
| Rustdesk Component | ICP Equivalent | Notes |
|--------------------|----------------|-------|
| `hbbs` ID registry | **Backend canister** (Rust) | Store device IDs, connection metadata |
| `hbbr` relay | **Off-chain relay** OR **HTTP outcalls** | P2P relay can't fully live on-chain |
| Web dashboard | **Asset canister** | Frontend UI served via `dfx deploy` |
| Auth/licensing | **Backend canister** | Leverage ICP's identity primitives |

## Deployment Pipeline

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Local Dev      │───▶│  dfx deploy      │───▶│  IC Mainnet     │
│  (dfx start)    │    │  --network ic    │    │  (canisters)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                                              │
         ▼                                              ▼
   Backend canister                              Asset canister
   (Rust → Wasm)                                 (HTML/JS/CSS)
```

### Step-by-Step Deployment

1. **Project scaffold**: `dfx new rustdesk_icp --type rust`
2. **Backend canister**: Compile Rust business logic to Wasm via `ic-cdk`
3. **Frontend canister**: Bundle web UI assets → asset canister
4. **Local testing**: `dfx start --background && dfx deploy`
5. **Mainnet deploy**: `dfx deploy --network ic`
6. **Cycles funding**: Ensure canisters have cycles for compute/storage

## Hybrid Architecture (Recommended)

Pure on-chain relay is impractical due to:
- Latency requirements (real-time desktop streaming)
- Bandwidth costs (cycles per byte)
- WebRTC/UDP not native to HTTP-based canisters

**Hybrid approach**:
- **On-chain**: Device registry, auth, licensing, audit logs, [[sns-treasury-and-initial-token-distribution|DAO governance]]
- **Off-chain**: `hbbr` relay servers (traditional infra or edge nodes)
- **Bridge**: Backend canister stores relay server endpoints; clients fetch via HTTP outcalls

## Critical Integration Points

### ic-agent for Relay ↔ Canister Communication
```rust
use ic_agent::Agent;
// Relay server can query/update canister state
let agent = Agent::builder()
    .with_url("https://ic0.app")
    .build()?;
```

### Candid Interface (Backend Canister)
```candid
service : {
  register_device : (DeviceId, PublicKey) -> (Result);
  get_relay_endpoints : () -> (vec RelayServer) query;
  log_connection : (DeviceId, DeviceId, timestamp) -> ();
}
```

### dfx.json Configuration
```json
{
  "canisters": {
    "rustdesk_backend": {
      "type": "rust",
      "candid": "src/rustdesk_backend/rustdesk_backend.did",
      "package": "rustdesk_backend"
    },
    "rustdesk_frontend": {
      "type": "assets",
      "source": ["dist"]
    }
  }
}
```

## Governance Integration

For decentralized Rustdesk DAO:
- Link to [[neuron-staking-voting-power-mechanics]] for voting on relay policies
- Link to [[dao-failures-tokenomics-mistakes]] to avoid common pitfalls
- Treasury controls relay server funding, feature prioritization

## Open Questions

- [ ] How to handle WebRTC signaling through HTTP-only canisters?
- [ ] Cycles cost model for high-frequency device heartbeats?
- [ ] Encrypted relay traffic via canister-based key management (vetKeys)?

## Next Steps

1. Prototype backend canister with device registry
2. Test HTTP outcalls for relay server health checks
3. Design SNS init file for Rustdesk DAO (see [[sns-treasury-and-initial-token-distribution]])

---

*See also*: [[sns-treasury-and-initial-token-distribution]], [[neuron-staking-voting-power-mechanics]], [[dao-failures-tokenomics-mistakes]]