---
tags: [research, neural-networks, nlp, embeddings]
---

# Embeddings and Representation Learning

Embeddings are dense vector representations that encode semantic meaning of discrete data (words, images, nodes) into continuous numerical space. This is foundational to modern AI — enabling neural networks to process symbolic data mathematically.

## Core Concept

**The Problem**: Raw data like words are discrete symbols with no inherent numerical relationship. "Cat" and "dog" are just different strings — a computer can't know they're semantically related.

**The Solution**: Map each item to a dense vector (typically 50-1000 dimensions) where similar items cluster together in vector space.

## Word2Vec: The Breakthrough

Word2Vec (2013, Google) popularized neural embeddings with two architectures:

### Continuous Bag of Words (CBOW)
- **Input**: Context words (surrounding words)
- **Output**: Predict the target center word
- **Strength**: Faster training, better for frequent words
- **Example**: Given "the ___ sat on mat" → predict "cat"

### Skip-gram
- **Input**: Single target word
- **Output**: Predict surrounding context words
- **Strength**: Works better for rare words and small datasets
- **Example**: Given "cat" → predict "the", "sat", "on", "mat"

Both are shallow 2-layer neural networks — the magic happens in the hidden layer weights, which become the embedding vectors.

## How Training Works

1. Initialize random vectors for each word in vocabulary
2. Slide a window across text corpus
3. Update vectors so co-occurring words become closer in vector space
4. After training, the hidden layer weights ARE the embeddings

## The Famous Property: Vector Arithmetic

```
vector("king") - vector("man") + vector("woman") ≈ vector("queen")
```

This emerges naturally from the training process — embeddings capture relational semantics, not just similarity.

## Beyond Words: Embedding Everything

The embedding concept generalizes:

| Domain | Technique | What's Embedded |
|--------|-----------|------------------|
| Images | CNN features | Visual patterns |
| Graphs | [[graph-neural-networks-gnn|GNN]] | Node relationships |
| Users | Collaborative filtering | Preferences |
| Sentences | Sentence-BERT | Full text meaning |
| Code | CodeBERT | Programming semantics |

## Why Embeddings Matter for AI Applications

1. **Similarity search** — Power [[vector-databases-infrastructure|vector databases]] for nearest-neighbor lookup
2. **RAG systems** — Enable [[retrieval-augmented-generation|semantic retrieval]] of relevant documents
3. **Transfer learning** — Pretrained embeddings carry learned knowledge to new tasks (see [[transfer-learning-fine-tuning]])
4. **Dimensionality reduction** — Compress sparse one-hot vectors (vocab size) to dense vectors (~300 dims)

## Modern Evolution

Word2Vec's static embeddings (one vector per word) gave way to:

- **ELMo** (2018): Context-dependent embeddings
- **BERT** (2019): Bidirectional context via [[attention-mechanism-transformers|transformers]]
- **Modern LLMs**: Every token gets a contextual embedding that changes based on surrounding text

## Practical Considerations

- **Embedding dimension**: Trade-off between expressiveness (higher) and efficiency (lower)
- **Out-of-vocabulary**: Words not seen during training need handling (subword tokenization, fallbacks)
- **Domain adaptation**: General embeddings may miss domain-specific semantics
- **Evaluation**: Intrinsic (analogy tasks) vs extrinsic (downstream task performance)

## Key Insight

Embeddings are the bridge between human-interpretable symbols and neural network mathematics. Every modern AI system — from search to chatbots to recommendation engines — relies on learned representations to understand meaning.