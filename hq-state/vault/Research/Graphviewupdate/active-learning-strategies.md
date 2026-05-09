---
tags: [research, machine-learning, human-in-the-loop]
---

# Active Learning Strategies for AI Systems

Active learning is a machine learning paradigm where the model **strategically selects** which data points to request human labels for, rather than passively accepting a pre-labeled dataset. This dramatically reduces labeling costs while maintaining or improving model accuracy.

## The Core Loop

1. **Train** initial model on small labeled set
2. **Query** — select most informative unlabeled samples
3. **Annotate** — human labels selected samples
4. **Retrain** — incorporate new labels
5. **Repeat** until performance target reached

## Key Sampling Strategies

### Uncertainty Sampling
Select samples where the model is *least confident*:
- **Least confidence**: Pick samples with lowest predicted probability for top class
- **Margin sampling**: Pick samples with smallest gap between top two predictions
- **Entropy-based**: Pick samples with highest prediction entropy

See [[neural-network-training-backpropagation]] for how confidence scores emerge from training.

### Query-by-Committee
Train multiple models (committee) and select samples where they **disagree most**. Disagreement indicates regions of high uncertainty in the hypothesis space.

### Diversity Sampling
Select samples that are **representative of the unlabeled pool** — avoids redundant queries on similar data points. Often combined with uncertainty for exploration-exploitation balance.

### Membership Query Synthesis
The learner generates *synthetic* samples in input space to query — useful when data generation is cheap but labeling expensive.

## Cold Start Problem

Initial models trained on tiny datasets have unreliable uncertainty estimates. Solutions:
- Start with random sampling for first N iterations
- Use pre-trained [[embeddings-semantic-search|embeddings]] to bootstrap diversity
- Hybrid strategies balancing exploration/exploitation

## Integration with Research Tools

Active learning applies directly to knowledge management:
- **Note prioritization**: Surface notes most likely to benefit from human review
- **Tag suggestions**: Query user only for ambiguous classifications
- **Link discovery**: Highlight potential connections with highest uncertainty

This aligns with [[ai-powered-ux-patterns]] — the system learns *when* to interrupt the user vs. act autonomously.

## Practical Considerations

| Factor | Trade-off |
|--------|----------|
| Batch size | Larger batches = fewer retrain cycles but less adaptive |
| Query budget | Hard cap on total labels constrains strategy choice |
| Annotator fatigue | Too many uncertain samples → frustrating UX |
| Model retraining cost | Frequent retraining improves selection but costs compute |

## Connection to Explainability

Active learning benefits from [[explainable-ai-xai-techniques]] — showing *why* a sample was selected helps annotators provide better labels and builds trust in the system's reasoning.

---

**Sources**: Settles (2009) survey; Springer Nature HITL review (2022); Encord Active Learning Guide (2025)