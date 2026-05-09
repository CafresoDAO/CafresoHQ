---
tags: [research, neural-networks, training]
---
# Batch Normalization vs Layer Normalization

Normalization techniques stabilize neural network training by adjusting activations to have consistent distributions. Two dominant approaches serve different use cases.

## Batch Normalization (BatchNorm)

**How it works:** Normalizes across the batch dimension — computes mean and variance for each feature across all samples in a mini-batch.

**Benefits:**
- Reduces internal covariate shift (layer inputs changing distribution during training)
- Enables higher learning rates → faster convergence
- Acts as mild regularization (noise from batch statistics)
- Smooths the loss landscape for easier [[gradient-descent-optimizers|optimization]]

**Limitations:**
- Depends on batch size — small batches produce noisy statistics
- Problematic for variable-length sequences (RNNs)
- Train/inference behavior differs (uses running averages at inference)

## Layer Normalization (LayerNorm)

**How it works:** Normalizes across the feature dimension — computes mean and variance for each sample independently across all its features.

**Benefits:**
- Batch-size independent — works with batch size 1
- Ideal for sequence models and [[attention-mechanism-transformers|transformers]]
- Consistent behavior between training and inference
- Essential for autoregressive models (GPT-style)

**Limitations:**
- Slightly less effective than BatchNorm for CNNs on image tasks
- Doesn't provide same regularization effect

## When to Use Which

| Scenario | Recommended |
|----------|-------------|
| CNNs with large batches | BatchNorm |
| Transformers / attention | LayerNorm |
| Small batch sizes | LayerNorm |
| RNNs / variable sequences | LayerNorm |
| Online learning (batch=1) | LayerNorm |
| Image classification | BatchNorm |

## Other Variants

- **Instance Normalization:** Per-sample, per-channel (style transfer)
- **Group Normalization:** Divides channels into groups, normalizes within (good for small batches)
- **RMSNorm:** Simplified LayerNorm without centering (used in LLaMA)

## Connection to Model Serving

BatchNorm requires handling running statistics during [[model-serving-inference-apis|inference]] — a common source of bugs when exporting models. LayerNorm's consistency simplifies deployment.

## Impact on Training

Both techniques help prevent [[regularization-techniques-overfitting|vanishing/exploding gradients]] by keeping activations in a stable range, enabling deeper networks to train successfully.