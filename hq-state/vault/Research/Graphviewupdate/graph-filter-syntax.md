---
tags: [research, obsidian, graph-view]
date: 2026-05-02
---

# Obsidian Graph View Filter Syntax

Building on [[obsidian-graph-view-basics]], this note dives into the **filter and query syntax** that controls what appears in your graph.

## Core Filter Operators

| Operator | Example | What it does |
|----------|---------|-------------|
| `path:` | `path:Projects` | Shows only notes in that folder |
| `tag:` | `tag:#research` | Filters to notes with that tag |
| `file:` | `file:daily` | Matches filenames containing the term |
| `-` (minus) | `-path:Archive` | Excludes matching notes |
| `OR` | `path:home OR path:work` | Combines multiple conditions |

## Boolean Logic

You can combine filters:
- **AND** (implicit): `path:Projects tag:#active` — must match both
- **OR** (explicit): `path:Projects OR path:Ideas` — matches either
- **Exclusion**: `-tag:#daily -path:Templates` — hides matching notes

## Property Filtering (v1.4+)

Recent Obsidian versions allow filtering by **frontmatter properties**:
- `[status:active]` — notes where status property equals "active"
- `[author:self]` — custom property matching

This is powerful for filtering by metadata beyond just tags and paths.

## Color Groups

Groups let you assign colors to node clusters:
1. Open Graph Settings → Groups
2. Add a query (e.g., `path:Projects`)
3. Pick a color

**Limitation**: Each group uses the same filter syntax, but you can't currently save multiple named filter *presets* for the global graph — a frequently requested feature.

## Local vs Global Graph

- **Local graph** (per-note): Automatically centered on current file; filters apply on top
- **Global graph**: Shows entire vault; filters essential for large vaults

## Common Use Cases

- Hide daily notes: `-path:Daily`
- Focus on active projects: `path:Projects -tag:#archived`
- View two subtrees: `path:Work OR path:Personal`
- Highlight by status: Group with `tag:#in-progress` → yellow

## Current Limitations

- No saved filter presets (must re-enter each session)
- Can't filter by link count or orphan status directly
- Groups share one global color scheme (can't have different schemes per filter)

---

**See also**: [[obsidian-graph-view-basics]]