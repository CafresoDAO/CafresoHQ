---
tags: [research, neural-networks, graphs]
---

# Graph Neural Networks (GNNs)

Neural networks designed to operate directly on graph-structured data — a "graph-in, graph-out" architecture that preserves connectivity while transforming node, edge, and global embeddings.

## Why Graphs Need Special Architectures

Traditional neural networks expect fixed-size inputs. Graphs are:
- **Variable size** — different numbers of nodes/edges
- **Permutation invariant** — no inherent ordering of nodes
- **Structurally rich** — topology carries meaning

## Core Mechanism: Message Passing

GNNs learn by iteratively aggregating information from neighboring nodes:

1. **Message** — each node sends its current embedding to neighbors
2. **Aggregate** — collect messages from neighborhood N(u)
3. **Update** — combine aggregated info with node's own features
4. **Iterate** — repeat across layers to capture multi-hop relationships

```
h_v^(k+1) = UPDATE(h_v^(k), AGGREGATE({h_u^(k) : u ∈ N(v)}))
```

After K layers, each node's embedding encodes its K-hop neighborhood structure.

## Key Architectures

| Architecture | Aggregation Style | Best For |
|--------------|-------------------|----------|
| **GCN** (Graph Convolutional) | Mean of neighbors | Semi-supervised node classification |
| **GraphSAGE** | Sampling + aggregation | Large-scale, inductive learning |
| **GAT** (Graph Attention) | Attention-weighted | When neighbor importance varies |
| **GIN** (Graph Isomorphism) | Sum aggregation | Graph-level classification |

## Applications

- **Social networks** — friend recommendations, community detection
- **Molecules** — drug discovery, property prediction
- **Knowledge graphs** — link prediction, entity classification
- **Code analysis** — bug detection on AST graphs
- **Recommender systems** — user-item interaction graphs

## Connection to Knowledge Management

Obsidian's graph view represents notes as nodes, links as edges. A GNN could:
- Learn note embeddings that capture *structural* similarity (not just content)
- Predict missing links ("you might want to connect these")
- Cluster related notes by graph topology
- Power smarter [[local-graph-view-ego-network]] recommendations

This bridges [[embeddings-semantic-search]] (content similarity) with structural patterns.

## Known Limitation: Over-smoothing

Too many message-passing layers cause all node embeddings to converge — they become indistinguishable. Deep GNNs (>4-6 layers) often perform worse than shallow ones. Mitigation strategies include skip connections, layer normalization, and dropout.

## Related Concepts

- [[attention-mechanism-transformers]] — GAT applies attention to graphs
- [[knowledge-graphs-ai-integration]] — GNNs power many KG applications
- [[neural-network-architecture-basics]] — GNNs as specialized architecture
- [[obsidian-graph-view-basics]] — the graph structure GNNs could learn from