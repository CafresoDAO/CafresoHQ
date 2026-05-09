---
tags: [research]
---

# Obsidian Graph View Basics

## Angle
First-pass research into how Obsidian’s built-in Graph View works, focusing on its core controls: filtering, grouping, display, and local graph depth.

## Key findings

Obsidian’s Graph View is a visual map of notes and their relationships. Each note is represented as a node, and links between notes become edges. This turns a Markdown vault into a navigable knowledge graph.

Important features from Obsidian’s official help and related community discussions:

- **Global Graph View**
  - Shows the broader network of notes in a vault.
  - Useful for spotting clusters, isolated notes, and heavily connected “hub” notes.

- **Local Graph View**
  - Starts from the currently active note.
  - Shows nearby connected notes.
  - Includes a **depth slider**:
    - Depth 1 shows directly linked notes.
    - Higher depths expand outward through additional link levels.

- **Filters**
  - Graph View supports search-style filtering.
  - Users can include or exclude notes by things like:
    - path
    - tag
    - search query
    - link relationships
  - Community posts suggest users often want richer Boolean filtering, such as combining multiple paths or tags.

- **Groups**
  - Groups let users color nodes based on filters.
  - This helps distinguish folders, topics, note types, or work areas.
  - A common pain point is managing many groups when the vault becomes large.

- **Display controls**
  - Obsidian lets users adjust visual density and graph behavior.
  - Typical controls include showing/hiding:
    - attachments
    - existing files only
    - orphan notes
    - tags
  - These controls help reduce noise.

## Implications for our app

For `C:\Users\Anthony\Documents\openclawhq`, our Graph View update should treat the graph as more than a visual novelty. The useful parts are:

- **Local-first exploration**
  - Let users start from a file, task, project, or research note and expand outward.
  - Depth control is essential.

- **Strong filtering**
  - Support filters for:
    - folder/path
    - tags
    - file type
    - project
    - status
    - backlinks/outlinks
  - Avoid making users rely on fragile syntax only; provide UI controls too.

- **Color groups**
  - Allow saved group rules.
  - Example:
    - `Research/` = blue
    - `Projects/` = green
    - `Daily/` = gray
    - incomplete tasks = orange

- **Noise reduction**
  - Large knowledge bases quickly become unreadable.
  - We should prioritize:
    - hide orphan nodes
    - hide low-value system files
    - collapse folders/clusters
    - limit graph depth
    - search-within-graph

## Design hypothesis

A better graph view for our app should combine Obsidian-style linking with more guided controls:

- default to a focused local graph
- allow expansion by depth
- provide saved filters and color groups
- surface important hubs and disconnected notes
- make graph filters understandable without requiring users to memorize query syntax

## Sources

- Obsidian Help: Graph View — https://obsidian.md/help/plugins/graph
- Obsidian Help GitHub mirror: Graph view documentation — https://github.com/obsidianmd/obsidian-help/blob/master/en/Plugins/Graph%20view.md
- Obsidian Forum discussions on filters, groups, and folder inclusion/exclusion