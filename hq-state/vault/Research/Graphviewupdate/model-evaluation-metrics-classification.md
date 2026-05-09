---
tags: [research, neural-networks, evaluation, metrics]
---

# Model Evaluation Metrics for Classification

Once you've [[neural-network-training-backpropagation|trained a neural network]], how do you know it's actually working? Evaluation metrics translate model outputs into actionable insights.

## The Confusion Matrix: Foundation of All Metrics

A 2x2 grid for binary classification:

|                | Predicted Positive | Predicted Negative |
|----------------|-------------------|-------------------|
| Actual Positive | True Positive (TP) | False Negative (FN) |
| Actual Negative | False Positive (FP) | True Negative (TN) |

Every metric below derives from these four values.

## Core Metrics

### Accuracy
$$\text{Accuracy} = \frac{TP + TN}{TP + TN + FP + FN}$$

- **Good for**: Balanced datasets with similar class sizes
- **Misleading when**: Classes are imbalanced (99% accuracy on fraud detection might mean you caught 0 frauds)

### Precision
$$\text{Precision} = \frac{TP}{TP + FP}$$

"Of everything I predicted positive, how many were actually positive?"

- **Prioritize when**: False positives are costly (spam filters — don't want good emails marked spam)

### Recall (Sensitivity)
$$\text{Recall} = \frac{TP}{TP + FN}$$

"Of all actual positives, how many did I catch?"

- **Prioritize when**: False negatives are costly (disease detection — don't miss cancer)

### F1 Score
$$F1 = 2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}$$

Harmonic mean balances precision and recall. Use when both matter and you need a single number.

### Matthews Correlation Coefficient (MCC)
$$MCC = \frac{TP \times TN - FP \times FN}{\sqrt{(TP+FP)(TP+FN)(TN+FP)(TN+FN)}}$$

- Range: -1 to +1 (0 = random, 1 = perfect)
- **Best for**: Imbalanced datasets — considered more robust than F1

## Choosing the Right Metric

| Scenario | Primary Metric | Why |
|----------|---------------|-----|
| Balanced classes, general use | Accuracy | Simple, interpretable |
| Medical diagnosis | Recall | Missing disease is dangerous |
| Email spam filter | Precision | Don't lose important emails |
| Fraud detection | F1 or MCC | Both errors costly, imbalanced data |
| Credit scoring | Business cost function | Dollar impact of each error type |

## Validation Strategies

- **Hold-out split**: Simple train/test split (70/30 or 80/20)
- **K-fold cross-validation**: Split data into k folds, train k times, average results
- **Stratified sampling**: Maintain class ratios in each fold — critical for imbalanced data

## Multi-Class Extensions

- **Macro-average**: Calculate metric per class, then average (treats all classes equally)
- **Micro-average**: Aggregate TP/FP/FN across classes, then calculate (weights by class frequency)
- **Weighted-average**: Like macro, but weighted by class support

## Practical Tips

1. **Start with the confusion matrix** — see the actual error distribution before computing any single metric
2. **Understand error costs** — a 95% accurate model might be worthless if that 5% error causes $1M losses
3. **Report multiple metrics** — single numbers hide important trade-offs
4. **Match metric to business goal** — what does success actually mean for your application?

These metrics feed directly into [[hyperparameter-tuning-strategies|hyperparameter tuning]] — you optimize for the metric that matters most to your use case.

## See Also
- [[neural-network-inference-deployment]] — deploying once you've evaluated
- [[explainable-ai-xai-techniques]] — understanding *why* the model made errors