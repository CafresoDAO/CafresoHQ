---
tags: [research, obsidian, graph-view, visualization]
---

# Graph View Groups: Color-Coding Nodes in Obsidian

The **Groups** feature in Obsidian's graph view allows you to assign colors to nodes based on query filters, making visual patterns and clusters immediately recognizable.

## How Groups Work

1. Open the graph view (Global or Local)
2. Expand the **Groups** section in the settings panel
3. Click **New group** to add a color-coded filter
4. Define a query using [[graph-filter-search-syntax|graph filter syntax]]
5. Choose a color for matching nodes

## Query Examples for Groups

| Query | Effect |
|-------|--------|
| `path:Projects` | Colors all notes in the Projects folder |
| `tag:#active` | Highlights notes tagged #active |
| `file:MOC` | Colors Map of Content notes |
| `-path:Archive` | Everything except archived notes |
| `line:(status:: done)` | Notes with specific inline field values |

## Rendering Order Matters

Groups are applied **top-to-bottom** in the list. If a node matches multiple groups, the **last matching group's color wins**. This lets you create layered highlighting:

1. Base color for all notes in a folder
2. Override color for high-priority items within that folder

## Scope: Global vs Local Graph

Importantly, group settings are **shared** between global and local graph views within a vault. This is by design but can be limiting — you can't have different color schemes for different contexts without manually toggling groups on/off.

## Common Pitfalls

- **Performance**: Too many complex groups can slow rendering on large vaults (1000+ nodes)
- **Attachment nodes**: Standard groups only target `.md` files — attachments (images, PDFs) require workarounds
- **White nodes**: If colors aren't showing, check for CSS snippet conflicts or ensure groups are enabled

## UX Pattern: Visual Clustering

Combine groups with the [[local-graph-view-ego-network|local graph]] depth setting to create a "radar view" of how a note connects across different domains:

- Red = technical notes
- Blue = project notes  
- Green = people/contacts
- Yellow = ideas/seeds

This supports the research tool principle of **glanceable context** — seeing relationships without reading every title.

## Related

- [[graph-filter-search-syntax]] — the query language groups use
- [[local-graph-view-ego-network]] — focused views that benefit most from color coding
- [[knowledge-graphs-ai-integration]] — broader context on graph-based knowledge systems