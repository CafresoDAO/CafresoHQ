---
tags: [research, neural-networks, training]
---

# Regularization Techniques: Preventing Overfitting

Regularization constrains neural networks during training to prevent overfitting—when a model memorizes training data instead of learning generalizable patterns.

## Core Techniques

### L2 Regularization (Ridge)
Adds penalty term to loss function proportional to the **square** of weights:
```
Loss = Original_Loss + λ * Σ(w²)
```
- Shrinks weights toward zero but rarely makes them exactly zero
- Smooth penalty encourages small, distributed weights
- Default choice in most production systems
- Works with [[gradient-descent-optimizers]] by adding gradient component

### L1 Regularization (Lasso)
Penalizes the **absolute value** of weights:
```
Loss = Original_Loss + λ * Σ|w|
```
- Drives many weights to exactly zero → sparse models
- Implicit feature selection (zero weights = ignored features)
- Less common than L2 for neural networks
- Useful when interpretability matters

### Elastic Net
Combines L1 and L2 with mixing parameter ρ:
```
Elastic Net = ρ · L1 + (1-ρ) · L2
```
- Balance between sparsity and smooth penalties
- Most production systems use this hybrid approach

### Dropout
Randomly **deactivates neurons** during training:
- During training: set p% of neurons to 0 each batch
- During inference: use all neurons, scale outputs by (1-p)
- Prevents co-adaptation—forces network to learn redundant representations
- Neural network equivalent of ensemble/bagging methods
- Typical dropout rates: 0.2-0.5
- Works best with larger networks

Implementation connects to [[batch-layer-normalization]] and [[hyperparameter-tuning-strategies]].

### Early Stopping
Monitors validation loss and halts training when improvement plateaus:
- Implicit regularization through optimal training duration
- Prevents overfitting without modifying loss function
- Requires held-out validation set
- Patience parameter: how many epochs to wait before stopping

## When to Use What

| Technique | Best For | Tuning Parameter |
|-----------|----------|------------------|
| L2 | Default choice, most architectures | λ (penalty strength) |
| L1 | Sparse models, feature selection | λ |
| Elastic Net | Production systems needing balance | λ, ρ |
| Dropout | Large networks (CNNs, Transformers) | dropout rate p |
| Early Stopping | All training runs | patience epochs |

## Combining Techniques

Regularization methods stack:
- L2 + Dropout is common for [[convolutional-neural-networks-cnn]]
- L2 + Early Stopping is nearly universal
- [[attention-mechanisms-transformers]] often use Dropout in attention layers + weight decay (L2)

Overregularization creates underfitting—model too simple to capture patterns. Tune regularization strength during [[hyperparameter-tuning-strategies]].

## Production Considerations

**Monitoring**: Track train vs. validation loss gap. Widening gap = underfitting signals need for stronger regularization.

**Inference**: Dropout must be disabled at inference time. Most frameworks handle this automatically (train vs. eval mode).

**Computational cost**: Dropout adds negligible overhead. L1/L2 only affect gradient computation, minimal impact on [[model-serving-inference-apis]].

Regularization is cheaper than collecting more data and often equally effective at improving generalization.