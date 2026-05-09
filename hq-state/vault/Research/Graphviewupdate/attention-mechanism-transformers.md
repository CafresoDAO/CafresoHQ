---
tags: [research, neural-networks, transformers, attention]
---

# Attention Mechanisms in Transformers

The **attention mechanism** is the breakthrough innovation that powers modern AI — from semantic search to large language models. It replaced recurrent architectures (RNNs/LSTMs) by allowing models to process all tokens in parallel while dynamically weighting relationships.

## How Self-Attention Works

Self-attention computes contextual embeddings through three steps:

1. **Query, Key, Value projections** — Each token is transformed into three vectors (Q, K, V)
2. **Attention scores** — Dot product of Query with all Keys, scaled by √d
3. **Weighted sum** — Softmax-normalized scores weight the Value vectors

```
Attention(Q, K, V) = softmax(QK^T / √d_k) × V
```

This lets each token "attend" to every other token, learning which relationships matter for the task.

## Multi-Head Attention

Transformers run multiple attention operations in parallel at each layer. Each "head" learns different relationship patterns:
- One head might focus on syntax
- Another on semantic similarity  
- Another on positional relationships

Outputs are concatenated and projected back to the model dimension.

## Why It Matters for Knowledge Tools

Attention is what enables:
- **[[embeddings-semantic-search]]** — Contextual embeddings that understand meaning
- **[[retrieval-augmented-generation]]** — Models attending to retrieved context
- **Long-range dependencies** — Capturing relationships across entire documents

Unlike RNNs that process sequentially, attention sees the whole sequence at once — making it parallelizable (fast training) and capable of modeling complex dependencies.

## Connection to Graph Views

Attention weights form a kind of implicit graph: tokens as nodes, attention scores as weighted edges. This mirrors how Obsidian's [[obsidian-graph-view-basics|graph view]] visualizes note relationships, and suggests why graph-based interfaces feel natural for exploring AI-generated connections.

## Key Insight

> The Transformer is the first transduction model relying *entirely* on self-attention to compute representations without sequence-aligned RNNs or convolution.

This architectural simplicity is why transformers scaled to billions of parameters — each component (attention, feedforward, normalization) is straightforward; the magic is in stacking them deep.

---

See also: [[neural-network-architecture-basics]], [[neural-network-inference-deployment]]