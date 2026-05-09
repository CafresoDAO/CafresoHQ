---
tags: [research, neural-networks, search, embeddings]
---
# Vector Databases & Semantic Search

Vector databases power **meaning-based search** by storing and querying neural network embeddings rather than keyword indexes.

## How It Works

1. **Embed content** — A neural network (e.g., text-embedding-ada-002, BERT, CLIP) converts text/images into high-dimensional vectors
2. **Store vectors** — Vector databases (Pinecone, Chroma, FAISS, Weaviate) index these embeddings for fast retrieval
3. **Query by similarity** — User queries are embedded, then matched against stored vectors using distance metrics

## Core Similarity Metrics

| Metric | Best For | Formula |
|--------|----------|--------|
| **Cosine similarity** | Text, normalized vectors | dot(A,B) / (‖A‖·‖B‖) |
| **Euclidean distance** | Dense, spatial data | √Σ(aᵢ-bᵢ)² |
| **Dot product** | Pre-normalized embeddings | Σ(aᵢ·bᵢ) |

## Why It Beats Keyword Search

- **Semantic matching**: "healthy dinner ideas" finds results about "nutritious evening meals"
- **Cross-lingual**: Embeddings can map different languages to shared semantic space
- **Multimodal**: CLIP-style models enable searching images with text queries

## Connection to Research Tools

Tools like Obsidian could leverage vector search for:
- Finding related notes by meaning, not just backlinks
- Surfacing forgotten notes relevant to current writing
- Automatic clustering in [[graph-view-groups-color-coding|graph view]]

## Key Vector Databases

- **Pinecone** — Managed, scalable, production-ready
- **Chroma** — Lightweight, Python-native, great for prototyping
- **FAISS** (Facebook) — Blazing fast, billion-scale, requires more setup
- **Weaviate** — Open source, GraphQL API, hybrid search
- **Milvus** — Open source, distributed, cloud-native

## Typical Pipeline

```
Document → Embedding Model → Vector [768 dims] → Vector DB
                                                    ↓
Query → Embedding Model → Query Vector → k-NN Search → Top Results
```

## Related Concepts

- [[embeddings-representation-learning]] — How embeddings encode meaning
- [[retrieval-augmented-generation-rag]] — Using vector search to ground LLM responses
- [[attention-mechanisms-transformers]] — Architecture behind modern embedding models