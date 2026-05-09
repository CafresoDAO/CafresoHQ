---
tags: [research, neural-networks, optimization, machine-learning]
---

# Hyperparameter Tuning Strategies

Hyperparameters are configuration values set *before* training begins (unlike model parameters learned during training). Choosing them well can mean the difference between a mediocre model and state-of-the-art performance.

## Key Hyperparameters to Tune

- **Learning rate** — most impactful; too high causes divergence, too low means slow convergence
- **Batch size** — affects gradient noise and memory usage
- **Number of layers/neurons** — model capacity
- **Dropout rate** — [[regularization-techniques-overfitting|regularization strength]]
- **Optimizer choice** — SGD, Adam, AdamW (see [[gradient-descent-optimizers]])
- **Weight decay** — L2 regularization coefficient

## Search Strategies

### Grid Search
- Exhaustive search over a predefined discrete grid
- **Pros**: Simple, reproducible, guaranteed to find best in grid
- **Cons**: Exponentially expensive (curse of dimensionality); wastes evaluations on unimportant parameters
- Best for: Small search spaces (≤3 parameters, few values each)

### Random Search
- Samples hyperparameters randomly from distributions
- **Pros**: More efficient than grid search (Bergstra & Bengio 2012 showed it finds good values faster); better coverage of important dimensions
- **Cons**: No learning from previous trials; may miss optimal regions
- Best for: Initial exploration, moderate budgets

### Bayesian Optimization
- Builds a probabilistic surrogate model (often Gaussian Process) of the objective function
- Uses acquisition function (Expected Improvement, UCB) to select next point
- **Pros**: Sample-efficient — finds optimal hyperparameters in ~67 iterations vs 125+ for grid search; reasons about uncertainty
- **Cons**: Computational overhead for surrogate; struggles with high dimensions (>20 params)
- Best for: Expensive evaluations (large models, limited compute)

## Modern Approaches

### Successive Halving / Hyperband
- Early-stops poor configurations to allocate budget to promising ones
- Combines random search with adaptive resource allocation
- Dramatically faster for deep learning where training is expensive

### Population-Based Training (PBT)
- Trains multiple models in parallel, periodically copying weights from top performers
- Allows hyperparameters to *change during training*
- Used by DeepMind for game-playing agents

### Neural Architecture Search (NAS)
- Automates architecture design, not just hyperparameters
- See [[attention-mechanisms-transformers]] for models discovered via NAS

## Practical Tips

1. **Start with learning rate** — use learning rate finder (train briefly at increasing LR, plot loss)
2. **Log scale for LR, linear for others** — search LR in [1e-5, 1e-1] logarithmically
3. **Use validation set, not test set** — avoid overfitting to test data
4. **Track experiments** — tools like Weights & Biases, MLflow, or Optuna
5. **Set a budget upfront** — Bayesian optimization shines when you commit to N trials

## Tools & Libraries

| Tool | Approach | Notes |
|------|----------|-------|
| Optuna | Bayesian + pruning | Python, great visualization |
| Ray Tune | All methods | Distributed, integrates with PyTorch/TF |
| Keras Tuner | Bayesian, Hyperband | TensorFlow/Keras native |
| scikit-optimize | Bayesian | Lightweight, sklearn-style API |
| Weights & Biases Sweeps | Grid, Random, Bayes | Cloud-integrated tracking |

## Connection to UX

For [[model-serving-inference-apis|deployed models]], hyperparameter choices affect:
- **Latency**: Smaller models (fewer layers/neurons) serve faster
- **Memory footprint**: Batch size and architecture impact RAM/VRAM
- **Robustness**: Well-tuned regularization prevents overconfident predictions

AutoML platforms abstract tuning from end users, making neural networks more accessible — a key UX improvement for non-experts.

## References

- Bergstra & Bengio (2012) — Random search is more efficient than grid search
- Snoek et al. (2012) — Practical Bayesian Optimization of ML Algorithms
- Li et al. (2018) — Hyperband: A Novel Bandit-Based Approach