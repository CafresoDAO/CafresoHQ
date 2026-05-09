---
tags: [research, neural-networks, computer-vision, deep-learning]
---

# Convolutional Neural Networks (CNNs)

Convolutional Neural Networks are specialized architectures designed to process grid-like data (images, video, spatial data) by preserving spatial relationships between pixels. Unlike fully-connected networks that flatten inputs and lose spatial structure, CNNs use convolution operations to capture local patterns.

## Core Architecture Components

### 1. Convolutional Layers
- **Purpose**: Extract features using learnable filters (kernels)
- **How it works**: Slide small filters (e.g., 3×3, 5×5) across the input, computing dot products at each position
- **Key benefit**: Parameter sharing - same filter detects patterns anywhere in the image (translation invariance)
- **Output**: Feature maps that highlight specific patterns (edges, textures, shapes)
- **Learnable parameters**: Filter weights and biases

### 2. Pooling Layers (Downsampling)
- **Purpose**: Reduce spatial dimensions while preserving dominant features
- **Max pooling**: Takes maximum value in each region (most common)
- **Average pooling**: Takes average value in each region
- **Benefits**:
  - Reduces computation and memory
  - Provides translation invariance
  - Helps prevent overfitting (see [[regularization-techniques-overfitting]])
- **Trade-off**: Loss of precise spatial information

### 3. Fully-Connected Layers
- **Purpose**: Final classification/regression after feature extraction
- **Position**: Typically at the end of the network
- **Function**: Combine all learned features to make predictions

## Why CNNs Work for Spatial Data

**Spatial relationship preservation**: Nearby pixels are processed together, maintaining context that matters for visual understanding.

**Hierarchical feature learning**:
- Early layers: Low-level features (edges, corners, colors)
- Middle layers: Mid-level features (textures, simple shapes)
- Deep layers: High-level features (object parts, semantic patterns)

**Parameter efficiency**: A 3×3 filter has 9 parameters that process millions of pixel locations, vs. fully-connected layers that need parameters for every input-output pair.

## Typical CNN Architecture Pattern

```
INPUT → [CONV → RELU → POOL] × N → [FC → RELU] × M → OUTPUT
```

Example flow:
- Input: 224×224×3 RGB image
- Conv1: 224×224×64 (extract 64 different features)
- Pool1: 112×112×64 (reduce spatial size)
- Conv2: 112×112×128 (extract more complex features)
- Pool2: 56×56×128
- ... continue pattern ...
- Flatten: Convert to 1D vector
- FC layers: Classify into categories

## Connection to Other Techniques

- **[[data-augmentation-techniques]]**: Essential for training CNNs on limited image data (rotation, flipping, cropping)
- **[[regularization-techniques-overfitting]]**: Dropout commonly applied between FC layers; batch normalization after conv layers
- **[[quantization-model-compression]]**: CNNs are often compressed for mobile deployment due to their large size
- **Contrast with [[recurrent-neural-networks-lstm]]**: RNNs handle sequential/temporal data; CNNs handle spatial data
- **[[attention-mechanisms-transformers]]**: Vision Transformers (ViT) are challenging CNNs' dominance in computer vision

## Key Hyperparameters

- **Filter size**: 3×3 most common (balance between receptive field and computation)
- **Stride**: How many pixels to move filter (stride=1 preserves resolution, stride=2 reduces it)
- **Padding**: Adding borders to maintain spatial dimensions
- **Number of filters**: Determines feature map depth (typically increases deeper in network)

## Practical Advantages

1. **Translation invariance**: Detects patterns regardless of position
2. **Local connectivity**: Each neuron only connects to local region, reducing parameters
3. **Shared weights**: Same filter applied everywhere reduces parameters dramatically
4. **Hierarchical learning**: Automatically learns feature hierarchy from data

## Common Applications

- Image classification (ResNet, VGG, Inception)
- Object detection (YOLO, Faster R-CNN)
- Semantic segmentation (U-Net, DeepLab)
- Face recognition
- Medical image analysis
- Video processing

## Modern Considerations

While CNNs remain dominant for computer vision, Vision Transformers are emerging as competitors that replace convolution with self-attention mechanisms, trading inductive bias (local connectivity) for raw learning capacity with sufficient data.
