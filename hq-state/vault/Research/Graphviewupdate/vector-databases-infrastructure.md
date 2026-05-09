---
tags: [research, ai-infrastructure, databases]
---

# Vector Databases: Infrastructure for AI Applications

Vector databases are specialized storage systems designed to index and query high-dimensional [[embeddings-semantic-search|embeddings]] efficiently. They're the infrastructure backbone that makes [[retrieval-augmented-generation|RAG]], recommendation systems, and semantic search practical at scale.

## Why Traditional Databases Fall Short

- **Exact match vs. similarity**: SQL databases excel at `WHERE name = 'X'`; vector DBs excel at "find the 10 most similar items"
- **Dimensionality**: Embeddings often have 384–1536 dimensions; B-tree indexes aren't designed for this
- **Distance metrics**: Cosine similarity, Euclidean distance, dot product — specialized algorithms required

## Key Players (2025–2026)

| Database | Best For | Deployment | Scale |
|----------|----------|------------|-------|
| **Pinecone** | Enterprise, fully managed | Cloud-only | Billions of vectors |
| **Weaviate** | Knowledge graphs + vectors | Cloud or self-hosted | Large-scale |
| **Chroma** | Prototyping, small-medium apps | Embedded/local | ~5-10M vectors |
| **Qdrant** | Open-source, high performance | Self-hosted or cloud | Large-scale |
| **pgvector** | Existing Postgres users | Self-hosted | Moderate |
| **FAISS** | Research, in-memory | Library (not DB) | Very large |

## How They Work

1. **Indexing**: Use algorithms like **HNSW (Hierarchical Navigable Small World)** graphs to create navigable structures
2. **Approximate Nearest Neighbor (ANN)**: Trade perfect accuracy for massive speed gains
3. **Hybrid search**: Combine vector similarity with traditional filters (metadata, keywords)

## Choosing the Right One

- **Proof of concept / local dev**: Chroma (embedded, zero config)
- **Production + managed**: Pinecone (simplest ops, strong SLAs)
- **Need graph relationships**: Weaviate (GraphQL, knowledge graph features)
- **Already using Postgres**: pgvector (familiar tooling)
- **Open-source priority**: Qdrant or Milvus

## Integration with AI Workflows

Vector databases slot into the [[retrieval-augmented-generation|RAG]] pipeline:

```
User query → Embed query → Vector DB search → Top-k results → LLM context
```

They also power:
- Semantic deduplication
- Anomaly detection (find outliers in embedding space)
- Recommendation engines
- Image/audio similarity search

## Operational Considerations

- **Index rebuild time**: Adding new vectors may require periodic re-indexing
- **Memory vs. disk**: In-memory indexes are faster but costlier
- **Recall vs. latency tradeoff**: Tune ANN parameters based on your accuracy needs
- **Compliance**: Pinecone offers SOC 2, HIPAA; self-hosted options give full data control

---

*Next steps*: Explore specific HNSW algorithm details, benchmark comparisons, or production monitoring patterns.