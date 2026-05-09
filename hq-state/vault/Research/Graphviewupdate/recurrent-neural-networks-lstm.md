---
tags: [research, neural-networks, sequential-data, architecture]
---

# Recurrent Neural Networks (RNNs) and LSTMs

Recurrent Neural Networks are architectures designed for **sequential data** — text, time-series, audio, or any input where order matters. Unlike feedforward networks, RNNs have **recurrent connections** that create an internal memory state.

## Core RNN Architecture

```
Input (x_t) → Hidden State (h_t) → Output (y_t)
                  ↑____↓
            Previous state (h_{t-1})
```

At each timestep, the hidden state combines:
- Current input `x_t`
- Previous hidden state `h_{t-1}`

This creates a "memory" that theoretically captures context from earlier in the sequence.

## The Vanishing Gradient Problem

Vanilla RNNs suffer from **vanishing gradients** during backpropagation through time (BPTT):

- Gradients are multiplied repeatedly as they flow backward through timesteps
- Values < 1 shrink exponentially; values > 1 explode
- Result: network "forgets" long-range dependencies (50+ steps back)

This made early RNNs impractical for tasks requiring long-term context.

## LSTM: The Solution

**Long Short-Term Memory (LSTM)** networks, introduced by Hochreiter & Schmidhuber (1997), solve vanishing gradients through a **gated cell architecture**:

| Gate | Purpose |
|------|--------|
| **Forget Gate** | Decides what information to discard from cell state |
| **Input Gate** | Controls what new information enters cell state |
| **Output Gate** | Determines what to output based on cell state |

The key innovation: the **cell state** acts as a "conveyor belt" where gradients can flow unchanged across many timesteps, protected by the gates.

## When to Use RNNs/LSTMs Today

- **Time-series forecasting** (stock prices, sensor data)
- **Streaming applications** where you process one token at a time
- **Resource-constrained environments** (smaller than transformers)
- **Variable-length sequences** with clear temporal dependencies

## Comparison with [[attention-mechanisms-transformers|Transformers]]

| Aspect | LSTM | Transformer |
|--------|------|-------------|
| Parallelization | Sequential (slow) | Fully parallel |
| Long-range dependencies | Hundreds of steps | Thousands+ |
| Memory footprint | O(1) per step | O(n²) attention |
| Streaming | Natural fit | Requires windowing |

For most NLP tasks, [[attention-mechanisms-transformers|transformers]] have largely replaced LSTMs. But for real-time streaming or when memory is constrained, LSTMs remain relevant.

## Variants

- **GRU (Gated Recurrent Unit)**: Simplified LSTM with 2 gates instead of 3
- **Bidirectional LSTM**: Processes sequences forward and backward
- **Stacked LSTM**: Multiple LSTM layers for hierarchical features

## Connection to [[transfer-learning-fine-tuning|Transfer Learning]]

Pre-trained language models like ELMo used bidirectional LSTMs before BERT popularized transformer-based transfer learning. The concept of learning contextual representations applies to both architectures.

## Practical Considerations

- Use [[gradient-descent-optimizers|gradient clipping]] to prevent exploding gradients
- Apply [[regularization-techniques-overfitting|dropout]] between LSTM layers
- Consider [[batch-layer-normalization|layer normalization]] for stability
- Monitor hidden state norms during training