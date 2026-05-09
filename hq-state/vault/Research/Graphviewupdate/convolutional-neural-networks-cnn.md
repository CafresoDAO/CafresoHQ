---
tags: [research, neural-networks, computer-vision, deep-learning]
created: 2026-05-02
---
# Convolutional Neural Networks (CNNs)

CNNs are specialized neural networks designed for processing grid-like data (images, audio spectrograms, time series). They achieve **translation equivariance** through shared-weight filters that slide across input features.

## Core Architecture Layers

### 1. Convolutional Layer
The defining layer of CNNs:
- **Filters/Kernels**: Small weight matrices (e.g., 3×3, 5×5) that detect features
- **Feature Maps**: Output activations showing where patterns were detected
- **Stride**: How many pixels the filter moves per step
- **Padding**: Border handling (same vs valid padding)

A filter of size F×F applied to input with C channels creates a F×F×C volume. Element-wise multiplication + summation produces one value in the output feature map.

### 2. Pooling Layer (Downsampling)
Reduces spatial dimensions while retaining important features:
- **Max Pooling**: Takes maximum value in each window (most common)
- **Average Pooling**: Takes mean value
- **Global Pooling**: Reduces entire feature map to single value

Benefits: reduces computation, provides translation invariance, prevents overfitting.

### 3. Fully Connected Layers
Typically at the end of CNN architectures:
- Flatten spatial feature maps to 1D vector
- Perform classification or regression
- Connect to output neurons (class scores)

## Key Properties

| Property | Description |
|----------|-------------|
| Parameter Sharing | Same filter weights applied across entire input |
| Local Connectivity | Each neuron connects only to local region |
| Hierarchical Features | Early layers: edges/textures → Deep layers: complex patterns |
| Translation Invariance | Pooling makes detection robust to small shifts |

## Typical CNN Pipeline

```
Input Image → [Conv → ReLU → Pool] × N → Flatten → FC → Softmax → Output
```

## Hyperparameters to Tune

- Number of filters per layer (depth)
- Filter size (receptive field)
- Stride and padding
- Pooling window size
- Network depth (number of conv blocks)

See [[hyperparameter-tuning-strategies]] for optimization approaches.

## Connection to Other Techniques

- [[batch-layer-normalization]]: Often applied after conv layers for training stability
- [[regularization-techniques-overfitting]]: Dropout, weight decay prevent CNN overfitting
- [[attention-mechanisms-transformers]]: Vision Transformers now compete with CNNs
- [[embeddings-representation-learning]]: CNN feature maps are learned representations
- [[model-quantization-compression]]: CNNs are prime targets for mobile deployment

## Why CNNs Revolutionized Vision

1. **Dramatically fewer parameters** than fully-connected networks (weight sharing)
2. **Exploit spatial structure** inherent in images
3. **Learn hierarchical features** automatically from data
4. **Scale to large images** without memory explosion

## Landmark Architectures

- **LeNet-5** (1998): Pioneered CNN for digit recognition
- **AlexNet** (2012): ImageNet breakthrough, deep + GPU training
- **VGGNet** (2014): Very deep with small 3×3 filters
- **ResNet** (2015): Skip connections enable 100+ layer training
- **EfficientNet** (2019): Compound scaling of depth/width/resolution