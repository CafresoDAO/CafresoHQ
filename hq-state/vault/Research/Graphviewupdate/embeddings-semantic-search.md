---
tags: [research, neural-networks, knowledge-management]
---

# Embeddings & Semantic Search

Embeddings are how [[neural-network-architecture-basics|neural networks]] translate meaning into geometry — turning words, sentences, images, or any data into fixed-length numeric vectors.

## Core Concept

- **Vector representation**: Each input passes through a neural network that outputs a dense vector (e.g., 768 or 1536 dimensions)
- **Semantic proximity**: Similar meanings cluster together in vector space; dissimilar ones spread apart
- **Distributional hypothesis**: Words appearing in similar contexts share similar meanings — the foundation of embedding models

## How It Works

1. **Training**: A neural network learns to position related concepts nearby (see [[neural-network-training-backpropagation]])
2. **Indexing**: Documents/notes are converted to vectors and stored in a vector database
3. **Querying**: Your search query becomes a vector; the system finds nearest neighbors
4. **Ranking**: Results ranked by cosine similarity or Euclidean distance — not keyword overlap

## Key Embedding Approaches

| Model Type | Description |
|------------|-------------|
| **Word2Vec / CBOW** | Predicts words from surrounding context |
| **Sentence Transformers** | Encodes entire sentences/paragraphs |
| **Graph Embeddings** | Captures entity relationships (like PyTorch BigGraph) |
| **Multimodal** | Embeds text + images in shared space |

## Why This Matters for Knowledge Tools

- **Beyond keywords**: Find notes by *meaning*, not just matching words
- **Concept clustering**: Related ideas naturally group together — like Obsidian's graph but in semantic space
- **Cross-linking discovery**: Embeddings can suggest links you didn't know existed
- **RAG (Retrieval-Augmented Generation)**: Powers modern AI assistants by finding relevant context before generating answers

## Connection to Graph Views

Obsidian's [[obsidian-graph-view-basics|graph view]] shows explicit links. Semantic search could reveal *implicit* connections — notes that discuss similar concepts even without wikilinks. This is a frontier for [[great-research-tool-principles|research tools]].

## Practical Application

Once you have a trained embedding model (see [[neural-network-inference-deployment]]), you can:
- Index your entire vault
- Search by concept, not keywords
- Auto-suggest related notes
- Build smarter [[ai-powered-ux-patterns|AI-powered features]]