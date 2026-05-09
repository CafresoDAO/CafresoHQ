---
title: ICP Development Vault
type: index
status: active
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - index
  - moc
---

# ICP Development Vault

A living knowledge base for Internet Computer Protocol (ICP) development. Curated by a dedicated sub-agent that researches, organizes, and deepens its understanding of ICP over time.

## Structure

| Folder | Purpose |
| --- | --- |
| `00-Index` | Maps of Content (MOCs) — entry points by topic |
| `01-Concepts` | Atomic notes on core ideas (canisters, cycles, subnets, …) |
| `02-Tutorials` | Step-by-step how-tos with runnable code |
| `03-References` | Spec, API, CLI references — stable lookups |
| `04-Tools` | `dfx`, Motoko compiler, Rust CDK, agents, IDEs |
| `05-Projects` | Scoped builds: dapps, canisters, demos |
| `06-Daily-Learning` | Dated journal — raw findings the agent logs |
| `bases` | Obsidian `.base` files for database-like views |
| `templates` | Note templates (concept, tutorial, project) |

## Conventions

- Every note has **YAML frontmatter** with `title`, `type`, `status`, `created`, `updated`, `tags`.
- **Tags are hierarchical**: `icp/concept/canister`, `icp/tool/dfx`, `lang/motoko`.
- **Links are wiki-style**: `[[canisters]]`, not markdown URLs.
- **Bases** in `bases/` render filtered views — update them as the vault grows.

## Quick Links

- [[00-Index/icp-moc|ICP Map of Content]]
- [[00-Index/learning-log|Learning Log]]
- [[bases/concepts|Concepts Base]]
- [[bases/tutorials|Tutorials Base]]
