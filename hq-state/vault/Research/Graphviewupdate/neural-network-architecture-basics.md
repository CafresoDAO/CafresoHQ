---
tags: [research, neural-networks, machine-learning]
---
# Neural Network Architecture Basics

Neural networks are computational systems inspired by biological brains, designed to recognize patterns and learn from data.

## Core Components

### Neurons (Nodes)
- **Input neurons**: Receive raw data (pixels, text embeddings, sensor readings)
- **Hidden neurons**: Process intermediate representations
- **Output neurons**: Produce final predictions or classifications

Each neuron computes: `output = activation(weighted_sum + bias)`

### Layers
- **Input layer**: Dimensionality matches your data (e.g., 784 neurons for 28×28 images)
- **Hidden layers**: Where learning happens; depth = number of hidden layers
- **Output layer**: Shape depends on task (1 neuron for regression, N for N-class classification)

## How Information Flows (Forward Propagation)

Forward propagation is how neural networks make predictions:

1. **Input enters** the network at the input layer
2. **Weighted sum**: Each layer computes `z = Wx + b` (linear transformation)
3. **Activation applied**: `a = σ(z)` — acts as a "gatekeeper" deciding what passes forward
4. **Layer-by-layer**: Output of one layer becomes input to the next
5. **Final prediction**: Output layer produces the result

> "Modern hardware (especially GPUs) is optimized for matrix operations, making this approach much faster than calculating each neuron's output individually." — DataCamp

### Common Activation Functions
| Function | Formula | Use Case |
|----------|---------|----------|
| ReLU | max(0, x) | Hidden layers (most common) |
| Sigmoid | 1/(1+e^-x) | Binary classification output |
| Softmax | e^xi / Σe^xj | Multi-class classification |

## Why Depth Matters

Deep networks learn **hierarchical features**:
- Layer 1: Edges, simple patterns
- Layer 2: Shapes, textures  
- Layer 3: Parts (eyes, wheels)
- Layer 4+: Objects, concepts

This connects to [[great-research-tool-principles]] — good research tools reveal patterns at different scales, just as neural networks learn representations at multiple abstraction levels.

## Training: Forward + Backward

> "Once model parameters are initialized, we alternate forward propagation with backpropagation, updating model parameters using gradients." — Dive into Deep Learning

- **Forward pass**: Compute predictions
- **Backward pass**: Calculate weight adjustments
- **Iterate**: Until the network learns

---
*See also: [[graph-filter-syntax]] for how filtering in tools mirrors attention mechanisms*