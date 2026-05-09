---
tags: [research, neural-networks, human-in-loop, ux]
---

# Active Learning: Query Strategies for Efficient Annotation

Active learning is a machine learning paradigm where the model **actively selects which data points to label**, rather than passively receiving randomly sampled labeled data. This dramatically reduces annotation costs while improving model performance — a direct UX win for teams building AI systems.

## The Core Loop

1. Train initial model on small labeled seed set
2. Model scores unlabeled pool for "informativeness"
3. Most informative samples sent to human annotator
4. Labels incorporated, model retrained
5. Repeat until budget exhausted or performance plateau

## Query Strategies

### Uncertainty Sampling
The most common approach — select samples where the model is *least confident*:

- **Least Confidence**: Pick samples with lowest max-class probability
- **Margin Sampling**: Pick samples where top-2 predictions are closest
- **Prediction Entropy**: Pick samples with highest entropy across all classes

```python
# Entropy-based uncertainty
import numpy as np
def entropy_score(probs):
    return -np.sum(probs * np.log(probs + 1e-10), axis=1)
```

### Query by Committee (QBC)
Train multiple models (or use dropout to simulate an ensemble). Select samples where committee members **disagree most**. Works well with [[attention-mechanisms-transformers|transformers]] using MC Dropout.

### Diversity Sampling
Avoid selecting redundant samples — ensure selected batch covers different regions of feature space. Often combined with uncertainty for best results.

### Contrastive Active Learning
Recent approach comparing sample representations in embedding space. Selects samples that would **shift the decision boundary** most if labeled. Connects to [[embeddings-representation-learning|representation learning]].

## UX Benefits for AI Applications

| Benefit | Impact |
|---------|--------|
| Reduced labeling cost | 10-100x fewer labels needed for same accuracy |
| Faster iteration | Ship MVPs with smaller labeled datasets |
| Human-in-the-loop trust | Annotators see model "asking for help" |
| Edge case discovery | Model surfaces hard examples automatically |

## Integration with Modern Architectures

Active learning pairs well with:
- [[transfer-learning-fine-tuning|Transfer learning]] — pretrained features improve uncertainty estimates
- [[knowledge-distillation-teacher-student|Knowledge distillation]] — teacher model can guide query selection
- [[explainability-xai-techniques|XAI]] — explain *why* a sample was selected for labeling

## Practical Considerations

- **Cold start problem**: Initial model with few labels has poor uncertainty estimates
- **Batch selection**: Selecting top-K uncertain samples can be redundant; combine with diversity
- **Annotation latency**: Real-time active learning requires fast model inference
- **Label noise**: Human annotators fatigue on hard samples; QA checks essential

## Research Frontiers

- **Deep Bayesian active learning**: Using proper uncertainty quantification rather than softmax confidence
- **Multi-task active learning**: Selecting samples informative across multiple related tasks
- **Active learning for LLMs**: Selecting which prompts/examples to include in fine-tuning

---

*Active learning transforms the training data pipeline from passive data collection into an intelligent, interactive process — one of the clearest ways NN design directly improves the end-to-end user and developer experience.*