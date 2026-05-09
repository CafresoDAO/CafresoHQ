---
tags: [research, obsidian, graph-view]
---
# Local Graph View: Ego-Centric Network Navigation

The **local graph** is Obsidian's ego-centric network view — it shows only the notes directly connected to your current note, rather than the entire vault.

## Accessing the Local Graph

- **Command palette**: "Open local graph"
- **Hotkey**: Can be bound in Settings → Hotkeys
- **Right-click tab** → "Open local graph"

## Key Differences from Global Graph

| Aspect | Global Graph | Local Graph |
|--------|--------------|-------------|
| Scope | Entire vault | Current note + neighbors |
| Center | No fixed center | Active note is always center |
| Depth | All connections | Configurable depth (1–5) |
| Performance | Can lag on large vaults | Always fast |
| Use case | Big-picture exploration | Contextual navigation |

## Depth Setting

The **Depth** slider controls how many "hops" from the current note are shown:

- **Depth 1**: Only direct links (backlinks + outgoing)
- **Depth 2**: Friends-of-friends
- **Depth 3+**: Broader neighborhood

Higher depth creates a "snowball" effect — each added layer exponentially increases visible nodes.

## Filters in Local Graph

Local graph supports the same [[graph-filter-syntax|filter syntax]] as global:

```
-path:"daily"        # hide daily notes
tag:#project         # only project-tagged notes
file:"meeting"       # notes with "meeting" in filename
```

## Settings Persistence Issue

A common frustration: **local graph settings don't persist** the same way global graph settings do. Each time you open local graph on a different note, settings reset to defaults.

**Workarounds**:
- Community plugins like "Graph Analysis" offer saved presets
- Some users create template workspaces with pre-configured local graph panes

## When to Use Local Graph

- **Writing**: See related notes without leaving your current context
- **Reviewing**: Understand a note's position in your knowledge web
- **Refactoring**: Identify orphan links or over-connected hubs
- **Learning**: Trace concept relationships incrementally

The local graph is particularly powerful for [[great-research-tool-principles|research workflows]] — it provides focused context without overwhelming you with the full vault topology.

## Visual Clustering

Combined with [[graph-groups-visual-clustering|color groups]], local graph becomes a mini-map of concept categories radiating from your current note.