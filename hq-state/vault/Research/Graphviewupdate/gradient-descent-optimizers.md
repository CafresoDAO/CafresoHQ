---
tags: [research, neural-networks, optimization, training]
---

# Gradient Descent Optimizers

Optimization algorithms determine how a neural network updates its weights during training. The choice of optimizer directly impacts convergence speed, training stability, and final model performance.

## Vanilla SGD (Stochastic Gradient Descent)

**How it works:** Updates weights by moving in the direction opposite to the gradient, scaled by a fixed learning rate.

```
w = w - learning_rate * gradient
```

**Pros:**
- Simple, well-understood
- Often generalizes better (finds flatter minima)
- Low memory overhead

**Cons:**
- Sensitive to learning rate selection
- Can get stuck in saddle points
- Slow convergence on ill-conditioned problems

## SGD with Momentum

**How it works:** Accumulates a velocity vector that dampens oscillations and accelerates movement in consistent gradient directions.

```
velocity = momentum * velocity - learning_rate * gradient
w = w + velocity
```

**Typical momentum value:** 0.9

**Benefit:** Helps escape local minima and speeds up convergence in ravines.

## AdaGrad (Adaptive Gradient)

**Innovation:** Introduced per-parameter learning rates — parameters with frequent large gradients get smaller updates.

**Problem:** Learning rate decays aggressively over time (accumulates all past squared gradients), often causing premature training stoppage in deep networks.

**Best for:** Sparse data (NLP, embeddings) where some features appear rarely.

## RMSprop

**How it works:** Fixes AdaGrad's decay problem by using an *exponentially decaying average* of squared gradients instead of accumulating all history.

```
cache = decay_rate * cache + (1 - decay_rate) * gradient²
w = w - learning_rate * gradient / (√cache + ε)
```

**Typical decay_rate:** 0.9

**Benefit:** Maintains adaptive learning without the aggressive decay — works well for non-stationary objectives (RNNs, online learning).

## Adam (Adaptive Moment Estimation)

**How it works:** Combines the best of Momentum (first moment) and RMSprop (second moment). Maintains exponentially decaying averages of both gradients and squared gradients.

```
m = β1 * m + (1 - β1) * gradient       # first moment
v = β2 * v + (1 - β2) * gradient²      # second moment
m_hat = m / (1 - β1^t)                 # bias correction
v_hat = v / (1 - β2^t)                 # bias correction
w = w - learning_rate * m_hat / (√v_hat + ε)
```

**Typical defaults:** β1=0.9, β2=0.999, ε=1e-8

**Why it's popular:**
- Works well "out of the box" with default hyperparameters
- Handles sparse gradients (from AdaGrad lineage)
- Handles non-stationary objectives (from RMSprop lineage)
- Fast convergence

## Practical Guidelines

| Scenario | Recommended Optimizer |
|----------|----------------------|
| Default starting point | Adam |
| Computer vision (CNNs) | SGD + Momentum (often better generalization) |
| NLP / Transformers | Adam or AdamW |
| Sparse features | AdaGrad or Adam |
| Small datasets | SGD (less prone to overfitting sharp minima) |
| Fine-tuning pretrained models | Adam with low learning rate |

## AdamW Variant

Decouples weight decay from gradient-based updates. Standard in modern transformer training — see [[transfer-learning-fine-tuning]] for fine-tuning strategies.

## Connection to Other Topics

- [[hyperparameter-tuning-strategies]] — learning rate is often the most important hyperparameter
- [[loss-functions-neural-networks]] — optimizers minimize the loss function
- [[regularization-techniques-overfitting]] — weight decay interacts with optimizer choice
- [[knowledge-distillation-teacher-student]] — distillation training often uses different optimizer schedules