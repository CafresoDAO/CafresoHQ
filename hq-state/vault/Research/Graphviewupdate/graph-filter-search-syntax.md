---
tags: [research, obsidian, graph-view]
---
# Graph Filter Search Syntax

Obsidian's graph view filter accepts the **same query syntax as the main Search panel** — a powerful but under-documented feature.

## Core Operators

| Operator | Example | Effect |
|----------|---------|--------|
| `path:` | `path:Projects` | Show only notes in Projects folder |
| `-path:` | `-path:"How to"` | Exclude a folder (quote multi-word names) |
| `tag:` | `tag:#research` | Filter to tagged notes |
| `file:` | `file:index` | Match filename contains |
| `OR` | `path:home OR path:work` | Combine multiple conditions |
| `AND` | `tag:#ai AND path:Research` | Require both conditions |

## Property-Based Filtering

You can filter by frontmatter properties:
- `[publish: yes]` — notes with publish property set to yes
- `-[status: draft]` — exclude drafts

This integrates well with [[graph-groups-visual-clustering]] — use filters to isolate a subgraph, then apply color groups within that subset.

## Practical Patterns

**Focus on active work:**
```
path:Projects -tag:#archived
```

**Research subgraph:**
```
path:Research OR tag:#research
```

**Exclude templates and attachments:**
```
-path:Templates -path:Attachments
```

## Relationship to Local Graph

The [[local-graph-view-ego-network]] respects these filters too — you can open a local graph on a note, then further refine what connections appear using filter syntax.

## AI/Neural Network Connection

This filtering capability mirrors how [[embeddings-semantic-search]] systems work: both reduce a large space to relevant subsets. Understanding query operators in tools like Obsidian builds intuition for designing search interfaces in AI-powered apps (see [[ai-powered-ux-patterns]]).

## Limitations

- No regex support in graph filters (unlike some search plugins)
- Complex boolean logic can be fragile — test in Search panel first
- Performance degrades on very large vaults with complex filters