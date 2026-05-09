---
tags: [research, neural-networks, AI, knowledge-tools]
---

# Retrieval Augmented Generation (RAG)

RAG is a technique that enhances Large Language Models by grounding their responses in external, up-to-date knowledge — making AI outputs more accurate and reducing hallucinations.

## How RAG Works

1. **Indexing** — Your knowledge base (documents, notes, databases) is converted into [[embeddings-semantic-search|embeddings]] and stored in a vector database
2. **Retrieval** — When a user asks a question, the query is also embedded and used to find the most semantically similar chunks from the knowledge base
3. **Augmentation** — Retrieved context is injected into the LLM prompt alongside the user's question
4. **Generation** — The LLM generates a response grounded in the retrieved facts rather than relying solely on training data

## Why RAG Matters for Knowledge Tools

- **Currency** — LLMs have knowledge cutoffs; RAG lets them access real-time or frequently updated information
- **Accuracy** — Grounding responses in actual documents reduces confident-but-wrong answers
- **Traceability** — You can cite which documents informed the answer (important for [[great-research-tool-principles|research tools]])
- **Customization** — Your private knowledge base becomes queryable without fine-tuning the model

## RAG vs Fine-Tuning

| Aspect | RAG | Fine-Tuning |
|--------|-----|-------------|
| Update speed | Instant (re-index) | Requires retraining |
| Cost | Lower (inference only) | Higher (training compute) |
| Best for | Facts, documents | Style, behavior |
| Hallucination control | Strong (citable) | Weaker |

## Connection to Obsidian

A RAG-powered Obsidian plugin could:
- Answer questions by searching your vault semantically (beyond keyword search)
- Summarize connections between notes the [[obsidian-graph-view-basics|graph view]] shows visually
- Surface relevant notes as you write, similar to [[ai-powered-ux-patterns|smart autocomplete]]

## Key Components

- **Vector database** — Pinecone, Weaviate, Chroma, pgvector
- **Embedding model** — See [[embeddings-semantic-search]]
- **Chunking strategy** — How to split documents (sentences, paragraphs, semantic units)
- **Reranking** — Optional second pass to refine relevance before prompting the LLM

---

*See also: [[neural-network-inference-deployment]] for serving considerations*