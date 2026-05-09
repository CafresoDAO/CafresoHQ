---
tags: [research, obsidian, graph-view]
---
# Graph Groups: Visual Clustering in Obsidian

While [[graph-filter-syntax]] controls *which* nodes appear, **Groups** control *how* they look. This is Obsidian's approach to visual clustering.

## How Groups Work

1. Open Graph View → Settings (gear icon)
2. Scroll to **Groups** section
3. Click "New group" to add a rule

Each group has:
- **Query**: Uses the same search syntax as filters
- **Color**: A color picker for matching nodes

## Evaluation Order

Groups are evaluated **top to bottom**. The first matching group wins — a node only gets one color. Drag groups to reorder priority.

## Practical Examples

| Query | Purpose |
|-------|--------|
| `path:Projects` | Color all notes in Projects folder |
| `tag:#y1900_1909` | Group by decade (per Reddit user) |
| `path:Archive` | Dim archived notes (use gray) |
| `tag:#active` | Highlight active items |

## Community Pain Points (from forums)

1. **Local vs Global sync**: Color group settings don't automatically apply to local graphs — you must reconfigure each time ([forum thread](https://forum.obsidian.md/t/colour-group-settings-apply-to-both-global-and-local-graphs/12709))
2. **No automatic clustering**: Graph physics creates visual clusters, but you can't auto-color disconnected clusters differently ([feature request](https://forum.obsidian.md/t/graph-view-colored-clusters/1038))
3. **Dense vaults struggle**: Users with many folders want multiple simultaneous filter+color profiles ([thread](https://forum.obsidian.md/t/multiple-graph-view-filters-and-color-grouping-for-each/39076))

## Visual Hierarchy Strategy

A well-designed group setup creates **visual layers**:

1. **Hot nodes** (red/orange): Active work, urgent items
2. **Warm nodes** (yellow/green): In-progress, reference
3. **Cool nodes** (blue/gray): Archive, background

## Connection to Research Tools

Visual clustering reduces cognitive load by encoding meaning in color rather than requiring label reading. This connects to principles in [[great-research-tools]].