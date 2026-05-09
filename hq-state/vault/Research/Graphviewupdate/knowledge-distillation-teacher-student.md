---
tags: [research, neural-networks, model-compression, deployment]
---

# Knowledge Distillation: Teacher-Student Model Compression

Knowledge distillation is a model compression technique where a smaller "student" model learns to mimic a larger, pre-trained "teacher" model. Unlike [[model-quantization-compression]] which reduces precision, distillation transfers learned behavior into a fundamentally smaller architecture.

## Core Mechanism

### Soft Labels vs Hard Labels
- **Hard labels**: Traditional one-hot encoded ground truth (e.g., [0, 0, 1, 0])
- **Soft labels**: Teacher's probability distribution across all classes (e.g., [0.05, 0.10, 0.80, 0.05])
- Soft labels encode "dark knowledge" — relationships between classes the teacher learned
- A cat image might have 80% cat, 10% dog, 5% tiger — this similarity structure helps the student generalize

### Temperature Scaling
```python
# Soften probability distribution
soft_probs = softmax(logits / temperature)
```
- Higher temperature (T > 1) produces softer probability distributions
- Reveals more information about class relationships
- Typical values: T = 2 to 20 during training, T = 1 at inference

### Training Objective
```
L_total = α * L_hard(student, ground_truth) + (1-α) * L_soft(student, teacher)
```
- **L_hard**: Standard cross-entropy with true labels
- **L_soft**: KL divergence between student and teacher soft outputs
- **α**: Balance factor (typically 0.1 to 0.5 for hard loss weight)

## Distillation Variants

### Response-Based Distillation
- Student matches teacher's final output layer
- Simplest form; works well for classification
- Limited transfer of intermediate representations

### Feature-Based Distillation
- Student matches teacher's intermediate layer activations
- Requires architecture alignment or projection layers
- Transfers richer structural knowledge
- Examples: FitNets, Attention Transfer

### Relation-Based Distillation
- Preserves relationships between samples or layers
- Transfers similarity structures, not absolute values
- More robust to architecture differences

## Advanced Techniques

### Multi-Teacher Distillation
- Multiple specialized teachers contribute knowledge
- Student can exceed any single teacher's performance
- Useful for ensemble compression — single model achieves ensemble-like accuracy

### Self-Distillation
- Same network serves as both teacher and student
- Knowledge flows from deeper to shallower layers
- Born-Again Networks: retrain identical architecture on own soft labels
- Surprisingly effective — student often outperforms teacher

### Online Distillation
- Teacher and student train simultaneously
- Mutual learning between peer networks
- No pre-trained teacher required

## Practical Applications

| Domain | Teacher → Student Example | Compression Ratio |
|--------|---------------------------|-------------------|
| NLP | BERT-Large → DistilBERT | 2x smaller, 60% faster |
| Vision | ResNet-152 → ResNet-18 | 8x fewer params |
| Speech | Conformer-XL → Conformer-S | 10x smaller |
| Recommendation | Ensemble → Single model | N models → 1 |

## Comparison with Other Compression Methods

| Technique | What it Reduces | Accuracy Impact | Combinable |
|-----------|-----------------|-----------------|------------|
| [[model-quantization-compression]] | Bit precision | Low | Yes |
| Knowledge Distillation | Architecture size | Medium | Yes |
| Pruning | Connection count | Medium | Yes |
| Neural Architecture Search | Design complexity | Variable | Yes |

**Best practice**: Combine distillation + quantization for maximum compression with minimal accuracy loss.

## Connection to [[transfer-learning-fine-tuning]]

Both transfer knowledge between models, but:
- **Transfer learning**: Same task, different domains
- **Distillation**: Same domain, different model capacities

Distillation is particularly valuable for [[neural-network-inference-deployment]] where latency and memory constraints matter — edge devices, mobile apps, real-time systems.

## Key Takeaway

Knowledge distillation lets you deploy smaller, faster models that retain most of a large model's intelligence by learning *how* it thinks, not just *what* it predicts.