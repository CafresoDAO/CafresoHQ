---
tags: [research, neural-networks, sequence-modeling]
---

# LSTM and RNN: Solving the Vanishing Gradient Problem

## The Core Problem with Vanilla RNNs

Recurrent Neural Networks (RNNs) process sequential data by maintaining hidden states across time steps. However, they suffer from the **vanishing gradient problem** when learning long-term dependencies.

During backpropagation through time (BPTT), gradients are computed by multiplying through many time steps. For a vanilla RNN:
- Gradient decays with $w \cdot \sigma'(\cdot)$ at each time step
- The derivative of typical activation functions (sigmoid, tanh) is < 1
- Over many time steps, gradients shrink exponentially: $(0.1)^{100} \approx 10^{-100}$

This makes it nearly impossible to learn dependencies spanning more than ~10 time steps.

## LSTM Architecture Solution

**Long Short-Term Memory (LSTM)** networks solve this through **gated memory cells** with three key gates:

1. **Forget Gate**: Decides what information to discard from cell state
2. **Input Gate**: Decides what new information to store
3. **Output Gate**: Decides what to output based on cell state

### Why LSTMs Work

The critical difference: LSTM gradients decay with $\sigma(\cdot)$ instead of $w \cdot \sigma'(\cdot)$.

- The network can learn weights where $\sigma(\cdot) \approx 1$
- This creates gradient highways through time
- If $v_{t+k} = wx$ for weight $w$ and input $x$, the network can learn a large $w$ to prevent vanishing
- The cell state provides an additive gradient path (versus multiplicative in vanilla RNNs)

## GRU Alternative

**Gated Recurrent Units (GRUs)** offer a simpler alternative with only two gates:
- Update gate (combines forget and input gates)
- Reset gate

GRUs have fewer parameters and train faster, but LSTMs generally perform better on complex long-sequence tasks.

## Historical Context

The vanishing gradient problem was identified in the early 1990s but persisted because:
- **Exploding gradients** received more attention (visible, dramatic, fixable with clipping)
- **Vanishing gradients** were silent and invisible - models just failed to learn
- Required architectural changes, not just training tricks
- Initial belief was that training issues were due to poor optimization or initialization

The LSTM paper (1997) provided the first clean architectural solution.

## Practical Applications

LSTMs excel at:
- Language modeling and machine translation
- Speech recognition
- Time series forecasting
- Video frame prediction
- Any task requiring memory of events 100+ steps in the past

## Related Concepts

See [[optimization-algorithms-comparison]] for gradient-based training methods, [[attention-mechanisms-transformers]] for the architecture that eventually surpassed LSTMs for many NLP tasks, and [[regularization-techniques-overfitting]] for preventing overfitting in deep recurrent models.