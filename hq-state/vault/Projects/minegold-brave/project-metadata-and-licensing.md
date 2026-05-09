---
tags: [project-study, minegold-brave, metadata, licensing]
---

# Project Metadata and Licensing

Minegold.brave maintains structured project metadata in `project.json` and uses MIT licensing. This note documents the project's self-description, categorization, and legal framework.

## Project Metadata (project.json)

The `project.json` file serves as the **canonical project descriptor** — a machine-readable manifest used by documentation generators, package managers, and search/discovery tools.

### Overview Statement

```json
"overview": "minegold.defi is a cross-chain DeFi refinery where users bridge Uniswap (UNI) tokens from Ethereum to the Internet Computer and refine them into gold-backed sGLDT tokens. Features automated ckUNI minting via ICP's official ERC-20 minter, a full user transaction history, and an admin treasury management panel."
```

This single-sentence summary captures:
- **Core metaphor**: "DeFi refinery" (transforming raw UNI into refined sGLDT)
- **Bridge flow**: Ethereum → ICP (one-way by design)
- **Official infrastructure**: Uses ICP's native ERC-20 minter (not a custom bridge)
- **User features**: Transaction history, balance tracking
- **Admin features**: Treasury management panel

### Feature Catalog

The `features` array documents **shipped capabilities** (not roadmap items):

```json
"features": [
  "UNI → ckUNI automated bridge via ICP ERC-20 minter",
  "Full user transaction history with status indicators",
  "sGLDT refinery — ckUNI → sGLDT swap with live exchange rates",
  "Brave wallet integration with live ETH/UNI/sGLDT balances",
  "Internet Identity authentication",
  "Admin treasury management panel",
  "ICRC-1 compliant token transfers",
  "Live CoinGecko price feeds"
]
```

#### Feature Breakdown

| Feature | Technical Implementation | See Also |
|---------|-------------------------|----------|
| UNI → ckUNI bridge | ICP ERC-20 minter canister via HTTP outcalls | [[http-outcalls-and-ethereum-verification]] |
| Transaction history | Backend stores user operations with status | [[backend-core-implementation]] |
| ckUNI → sGLDT swap | Exchange rate calculation with treasury management | [[token-economics-and-exchange-rates]] |
| Brave wallet integration | Frontend reads balances via ICRC-1 ledger calls | [[frontend-architecture-and-ui]] |
| Internet Identity | ICP native authentication, no passwords | [[identity-and-access-control]] |
| Admin treasury panel | Role-based access to treasury operations | [[identity-and-access-control]] |
| ICRC-1 compliance | Standard token interface for interoperability | [[canister-architecture-and-api-surface]] |
| CoinGecko feeds | HTTP outcalls for live ETH/UNI/GLDT prices | [[http-outcalls-and-ethereum-verification]] |

### Categorization and Discovery

```json
"category": "defi-finance",
"tags": [
  "defi", "bridge", "cross-chain", "icp", "ethereum",
  "uniswap", "icrc1", "gold", "wallet"
]
```

**Category**: `defi-finance` positions the project in DeFi tooling (not just a token or simple swap)

**Tags** support:
- **Search optimization**: Users searching "ethereum bridge icp" will find this project
- **Ecosystem mapping**: ICP ecosystem explorers can categorize by tags
- **Dependency tracking**: `icrc1` tag signals standards compliance

### Versioning

```json
"last_updated": "2026-04-09T16:52:31.726Z"
```

- ISO 8601 timestamp tracks metadata freshness
- Updated when features are added/removed or overview changes
- **Not** the code version — see [[deployment-scripts-and-automation]] for versioning strategy

## Licensing (MIT License)

Minegold.brave uses the **MIT License**, one of the most permissive open-source licenses.

### License Text (LICENSE)

```text
MIT License Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions...
```

### What MIT License Permits

✅ **Commercial use**: Deploy your own instance, charge fees, monetize
✅ **Modification**: Fork and customize for your use case
✅ **Distribution**: Share modified or unmodified versions
✅ **Private use**: Run internally without disclosing changes
✅ **Sublicensing**: Incorporate into proprietary software

### MIT License Requirements

📋 **Include license**: Must reproduce copyright notice and license text in distributions
📋 **No warranty**: Software provided "as is" with no liability

### Why MIT for DeFi?

1. **Ecosystem growth**: Permissive licensing encourages forks and integrations
2. **Audit transparency**: Anyone can review security without NDA
3. **Composability**: Other DeFi projects can integrate freely
4. **Deployment flexibility**: Users can self-host with modifications

**Notable**: No copyleft requirement (unlike GPL) — derivatives can be closed-source.

## Design Documentation (DESIGN.md)

The `DESIGN.md` file is a **placeholder** for design system documentation:

```markdown
# Design Brief

> The design brief is a summary of the design direction, tone, differentiation,
> color palette, typography, elevation & depth, structural zones, spacing & rhythm,
> component patterns, motion, constraints, and signature detail.
```

### Current State

- **Header only**: No actual design specifications documented yet
- **Intended scope**: Complete design system (color, typography, components)
- **Status**: Pending (UI design is functional but not formally documented)

### What Should Go Here

Based on the header, a complete design brief would include:

| Section | Purpose | Example |
|---------|---------|--------|
| Direction | Overall aesthetic goal | "Minimalist financial interface" |
| Tone | Emotional character | "Trustworthy, precise, calm" |
| Differentiation | Unique visual elements | "Gold accent color for sGLDT" |
| Color palette | Brand and UI colors | Primary, secondary, semantic colors |
| Typography | Font families and scale | Headings, body, code |
| Elevation & depth | Shadow and layering system | Card elevation, modal overlays |
| Structural zones | Layout regions | Header, sidebar, main content |
| Spacing & rhythm | Spacing scale | 4px base grid, 8px rhythm |
| Component patterns | Reusable UI components | Buttons, inputs, cards |
| Motion | Animation guidelines | Transition duration, easing |
| Constraints | Design limitations | Mobile breakpoints, accessibility |
| Signature detail | Defining visual element | "Refinery" iconography |

See [[frontend-architecture-and-ui]] for the actual implemented UI components (React + Shadcn).

## Integration Points

### Discovery Flow

```mermaid
flowchart LR
    A[User searches<br/>"ICP Ethereum bridge"] --> B[Finds via tags]
    B --> C[Reads project.json<br/>overview]
    C --> D[Reviews MIT license]
    D --> E[Clones repo]
    E --> F[Deploys own instance]
```

### Metadata Consumers

1. **Package managers**: Read `category` and `tags` for classification
2. **Documentation generators**: Use `overview` for auto-generated docs
3. **Search engines**: Index tags for discoverability
4. **Analytics tools**: Track feature adoption via feature list

### License Compliance Checklist

When using or distributing Minegold.brave:

- [ ] Include `LICENSE` file in distributions
- [ ] Preserve copyright notice in source code
- [ ] Document any modifications (not required, but recommended)
- [ ] Accept "as is" warranty disclaimer
- [ ] Attribute original authors (not required, but courteous)

## Key Takeaways

**project.json**:
- Single source of truth for project description
- Machine-readable feature catalog
- Supports ecosystem discovery and categorization
- Timestamp tracks metadata freshness (not code version)

**MIT License**:
- Maximum permissiveness for DeFi composability
- Allows commercial use and closed-source derivatives
- Only requires license reproduction
- No warranty or liability for deployers

**DESIGN.md**:
- Placeholder for future design system documentation
- UI exists and works (see [[frontend-architecture-and-ui]])
- Formal design specs not yet documented

## Cross-References

- [[project-overview]] — High-level project introduction
- [[frontend-architecture-and-ui]] — Actual UI implementation
- [[deployment-scripts-and-automation]] — Code versioning and releases
- [[package-management-and-dependencies]] — Open-source dependency tree