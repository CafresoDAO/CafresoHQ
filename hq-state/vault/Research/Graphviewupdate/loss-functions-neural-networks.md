---
tags: [research, neural-networks, optimization]
---

# Loss Functions in Neural Networks

Loss functions (also called cost or objective functions) quantify the difference between predicted and actual outputs. They're the signal that drives [[neural-network-training-backpropagation|backpropagation]] — without a well-chosen loss function, gradient descent has no direction.

## Regression Loss Functions

### Mean Squared Error (MSE)
$$L = \frac{1}{n}\sum_{i=1}^{n}(y_i - \hat{y}_i)^2$$

- **Properties**: Convex (guarantees global minimum for linear models), differentiable everywhere
- **Behavior**: Penalizes large errors quadratically — outliers dominate the gradient
- **Use when**: Errors are Gaussian-distributed, outliers are meaningful signals
- **Avoid when**: Data has heavy outliers you want to ignore

### Mean Absolute Error (MAE / L1 Loss)
$$L = \frac{1}{n}\sum_{i=1}^{n}|y_i - \hat{y}_i|$$

- **Properties**: More robust to outliers than MSE
- **Behavior**: Constant gradient magnitude regardless of error size
- **Pitfall**: Non-differentiable at zero — can cause optimization instability
- **Use when**: Outliers should be downweighted

### Huber Loss (Smooth L1)
Combines MSE (for small errors) with MAE (for large errors):
- Quadratic when |error| < δ
- Linear when |error| ≥ δ

**Best of both worlds**: Differentiable everywhere, robust to outliers. Common in object detection (e.g., Faster R-CNN bounding box regression).

## Classification Loss Functions

### Binary Cross-Entropy (Log Loss)
$$L = -\frac{1}{n}\sum_{i=1}^{n}[y_i\log(\hat{y}_i) + (1-y_i)\log(1-\hat{y}_i)]$$

- **Use with**: Sigmoid output activation
- **Behavior**: Heavily penalizes confident wrong predictions
- **Pitfall**: Requires predictions in (0,1) — log(0) = -∞

### Categorical Cross-Entropy
$$L = -\sum_{c=1}^{C}y_c\log(\hat{y}_c)$$

- **Use with**: Softmax output for multi-class problems
- **Variant**: Sparse categorical cross-entropy when labels are integers, not one-hot

### Hinge Loss (SVM Loss)
$$L = \max(0, 1 - y \cdot \hat{y})$$

- **Properties**: Maximum-margin — pushes decision boundary away from all points
- **Use when**: You want SVM-like behavior in a neural network
- **Note**: Works with outputs in (-∞, +∞), not probabilities

## Choosing the Right Loss Function

| Task | Recommended Loss | Output Activation |
|------|-----------------|-------------------|
| Regression (normal errors) | MSE | Linear |
| Regression (outliers) | Huber or MAE | Linear |
| Binary classification | Binary cross-entropy | Sigmoid |
| Multi-class (one label) | Categorical cross-entropy | Softmax |
| Multi-label classification | Binary cross-entropy per label | Sigmoid per output |
| Ranking/margin tasks | Hinge or triplet loss | Linear |

## Common Pitfalls

1. **Mismatched activation + loss**: Using MSE with softmax outputs creates vanishing gradients
2. **Class imbalance**: Cross-entropy treats all classes equally — use weighted loss or focal loss
3. **Numerical instability**: Always use combined log-softmax implementations (e.g., `F.cross_entropy` in PyTorch) rather than separate softmax → log
4. **Wrong scale**: If labels are in [0, 1000] and you use MSE, gradients explode — normalize first

## Connection to Evaluation Metrics

Loss functions ≠ [[model-evaluation-metrics-classification|evaluation metrics]]. You optimize loss during training, but report metrics (accuracy, F1, AUC) for stakeholders. Sometimes they diverge:
- Low cross-entropy doesn't guarantee high accuracy on imbalanced data
- MSE improvement may not improve R² if baseline variance is high

## Advanced: Custom Loss Functions

When standard losses don't fit:
- **Focal loss**: Down-weights easy examples for imbalanced detection
- **Dice loss**: Optimizes IoU directly for segmentation
- **Contrastive/triplet loss**: Learns embeddings for [[embeddings-semantic-search|similarity search]]
- **Perceptual loss**: Compares CNN feature maps for image generation

Custom losses must be differentiable (or use straight-through estimators for discrete operations).