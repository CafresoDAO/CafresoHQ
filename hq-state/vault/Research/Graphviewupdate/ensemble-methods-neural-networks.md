---
tags: [research, neural-networks, ensemble-learning]
---

# Ensemble Methods for Neural Networks

Ensemble methods combine predictions from multiple models to achieve better performance and robustness than any single model. While originally developed for traditional ML algorithms, these techniques are increasingly powerful when applied to neural networks.

## Core Ensemble Strategies

### Bagging (Bootstrap Aggregating)
- Train multiple neural networks in **parallel** on random subsets of training data (with replacement)
- Each model sees a slightly different view of the data, learning different patterns
- Final prediction: average outputs (regression) or majority vote (classification)
- **Benefits**: Reduces variance and overfitting, particularly effective for high-capacity models like deep networks
- **Neural network application**: Train 5-10 networks with different random initializations and data samples

### Boosting
- Train models **sequentially**, where each new network focuses on correcting predecessors' errors
- Each iteration re-weights training examples based on previous mistakes
- Less common for deep neural networks due to computational cost, but powerful for shallow networks
- **Trade-off**: Can reduce bias but risks overfitting if not carefully regularized

### Stacking (Meta-learning)
- Train multiple heterogeneous models (can mix architectures: CNN, RNN, Transformer)
- Use predictions from base models as input features to a meta-model
- Meta-model learns optimal way to combine base predictions
- **Neural network application**: Combine specialized architectures (e.g., CNN for images + LSTM for sequences) and let a final network weight their contributions

## Practical Implementation for Neural Networks

**Snapshot Ensembles**: Save model checkpoints during training at different epochs (especially at local minima), then ensemble these snapshots instead of training separate models from scratch.

**Dropout as Implicit Ensemble**: During inference, run forward passes with dropout enabled multiple times and average results - approximates ensembling exponentially many sub-networks.

**Knowledge Distillation**: Train a smaller "student" network to mimic the ensemble's predictions, getting ensemble-like performance with single-model inference cost.

## When to Use Ensembles

✅ **Use when**:
- Prediction accuracy is critical (competitions, high-stakes decisions)
- You have computational budget for training multiple models
- Model variance is high ([[regularization-techniques-overfitting]])
- Different architectures capture complementary patterns

⚠️ **Consider cost**:
- Training time multiplies by number of models
- Inference latency increases (relevant for [[model-serving-deployment]])
- Memory footprint grows unless distillation is applied

## Connection to Other Techniques

- Complements [[hyperparameter-tuning-strategies]] - ensemble models with different hyperparameters
- Can be combined with [[transfer-learning-fine-tuning]] - ensemble fine-tuned versions of pre-trained models
- Relates to [[neural-architecture-search-nas]] - NAS can discover diverse architectures to ensemble
- Enhances [[explainability-xai-techniques]] - model agreement/disagreement reveals uncertainty

## Key Insight

Ensemble methods trade computational resources for prediction quality. The "wisdom of crowds" principle applies: diverse models that disagree on some examples but agree on the final prediction typically outperform any individual expert. For production systems, the cost-benefit analysis depends on whether the accuracy gain justifies the inference overhead.