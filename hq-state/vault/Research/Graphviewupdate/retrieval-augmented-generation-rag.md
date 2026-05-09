---
tags: [research, neural-networks, nlp, rag, practical-ai]
created: 2026-05-02
---

# Retrieval-Augmented Generation (RAG)

RAG is a technique that enhances neural network outputs by dynamically retrieving relevant external knowledge at inference time. It bridges the gap between static model training and real-world information needs.

## Core Architecture

RAG systems have three main components:

1. **Knowledge Base** — External data repository (documents, databases, APIs)
2. **Retriever** — Finds relevant context using [[embeddings-representation-learning|vector similarity search]]
3. **Generator** — LLM that synthesizes answers from retrieved context + user query

## How It Works

```
User Query → Embed Query → Vector Search → Retrieve Top-K Docs → Augment Prompt → LLM Generation → Response
```

### Step-by-Step:
1. Convert query to embedding vector
2. Search vector database for semantically similar documents
3. Inject retrieved passages into the prompt as context
4. LLM generates response grounded in retrieved facts

## Why RAG Matters

| Problem with Pure LLMs | RAG Solution |
|------------------------|---------------|
| Knowledge cutoff date | Pull from live/updated sources |
| Hallucinations | Ground responses in retrieved facts |
| No access to private data | Connect to internal knowledge bases |
| Expensive retraining | Update knowledge base instead |

## Key Components

### Vector Database
Stores embeddings for fast similarity search. Popular options:
- Pinecone, Weaviate, Chroma, Qdrant, Milvus

### Chunking Strategy
Documents must be split into chunks that:
- Fit within context window limits
- Preserve semantic coherence
- Balance granularity vs. context

### Retrieval Methods
- **Dense retrieval**: Neural embeddings (see [[embeddings-representation-learning]])
- **Sparse retrieval**: BM25/keyword matching
- **Hybrid**: Combine both for better recall

## Relation to Other Techniques

- Uses [[attention-mechanisms-transformers|transformer models]] for generation
- Relies heavily on [[embeddings-representation-learning|embedding quality]]
- Can benefit from [[model-serving-inference-apis|inference optimization]] for production
- Often deployed alongside [[knowledge-distillation-teacher-student|distilled models]] for speed

## Practical Considerations

**Evaluation metrics:**
- Retrieval accuracy (Recall@K, MRR)
- Answer faithfulness (groundedness to retrieved docs)
- Answer relevance (does it address the query?)

**Common pitfalls:**
- Poor chunking loses context
- Irrelevant retrieval pollutes prompts
- Over-reliance on retrieval ignores model knowledge

## Connection to Obsidian

Obsidian's graph view and search are conceptually similar — both help surface relevant connected information. RAG is essentially "semantic graph view for AI" — finding related notes/docs to inform responses.

---

**See also:** [[embeddings-representation-learning]], [[attention-mechanisms-transformers]], [[model-serving-inference-apis]]