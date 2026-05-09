---
tags: [research, neural-networks, machine-learning]
---

# Neural Network Training: Backpropagation & Gradient Descent

Understanding how neural networks *learn* is essential for leveraging AI effectively. Training involves two core algorithms working together: **backpropagation** and **gradient descent**.

## The Learning Loop

1. **Forward pass** — Input flows through the network, producing a prediction
2. **Loss calculation** — Compare prediction to ground truth using a cost function
3. **Backward pass (backpropagation)** — Compute how each weight contributed to the error
4. **Weight update (gradient descent)** — Adjust weights to reduce error
5. Repeat until convergence

## Backpropagation: The Chain Rule in Action

Backpropagation computes gradients by propagating errors *backward* through the network:

- Uses the **chain rule of calculus** to decompose complex derivatives
- Each layer's gradient depends on the layer above it
- Efficiently computes partial derivatives for thousands/millions of parameters
- Also called "reverse-mode automatic differentiation"

## Gradient Descent: The Optimizer

Gradient descent adjusts parameters to minimize the loss function:

- **Learning rate** controls step size — too high causes overshooting, too low is slow
- **Stochastic gradient descent (SGD)** uses mini-batches for efficiency
- Modern variants: Adam, RMSprop, AdaGrad add momentum and adaptive rates

## Practical Implications for AI Users

| Concept | User Benefit |
|---------|-------------|
| Learning rate tuning | Faster training, better convergence |
| Batch size selection | Memory/speed tradeoffs |
| Early stopping | Prevent overfitting |
| Transfer learning | Leverage pre-trained weights |

## Key Insight

Most ML frameworks (PyTorch, TensorFlow) handle backpropagation automatically — you define the architecture, and **autograd** computes gradients. This abstraction lets users focus on architecture design and hyperparameter tuning rather than manual calculus.

---

See also: [[neural-network-architecture-basics]] · [[great-research-tool-principles]]