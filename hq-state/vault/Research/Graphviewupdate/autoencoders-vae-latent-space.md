---
tags: [research, neural-networks, generative-models, unsupervised-learning]
---

# Autoencoders & Variational Autoencoders (VAEs)

Autoencoders are neural network architectures that learn compressed representations of data through unsupervised learning. VAEs extend this concept into the generative domain.

## Standard Autoencoder Architecture

- **Encoder**: Compresses input data into a lower-dimensional latent representation
- **Bottleneck (Latent Space)**: The compressed representation — forces the network to learn essential features
- **Decoder**: Reconstructs the original input from the latent representation
- **Loss**: Reconstruction loss (e.g., MSE, binary cross-entropy) measuring how well the output matches the input

## Variational Autoencoders (VAEs)

VAEs transform autoencoders into generative models by making the latent space probabilistic:

| Aspect | Standard Autoencoder | VAE |
|--------|---------------------|-----|
| Latent space | Deterministic points | Probability distributions |
| Output | Single encoding | Mean (μ) and variance (σ²) parameters |
| Generation | Cannot generate new samples | Can sample from latent space |
| Regularization | None inherent | KL divergence term |

## VAE Loss Function

The VAE loss combines two components:

1. **Reconstruction Loss**: Measures fidelity of reconstructed output vs. input
2. **KL Divergence**: Regularizes the latent distribution toward a prior (typically standard normal N(0,1))

```
Loss = Reconstruction_Loss + β * KL_Divergence(q(z|x) || p(z))
```

The β term (β-VAE) controls the trade-off between reconstruction quality and latent space structure.

## The Reparameterization Trick

To enable backpropagation through the sampling operation:
- Instead of sampling z ~ N(μ, σ²) directly
- Sample ε ~ N(0, 1), then compute z = μ + σ * ε
- This makes the gradient flow through μ and σ while ε provides stochasticity

## Connections to Other Topics

- **[[embeddings-representation-learning]]**: Autoencoders learn dense representations similar to embeddings
- **[[loss-functions-neural-networks]]**: Reconstruction loss + KL divergence is a specialized composite loss
- **[[regularization-techniques-overfitting]]**: KL divergence acts as a regularizer on latent space
- **[[model-quantization-compression]]**: Autoencoders can be used for learned compression

## Applications

- **Dimensionality reduction**: Alternative to PCA that captures nonlinear relationships
- **Anomaly detection**: High reconstruction error indicates unusual inputs
- **Image generation**: Sampling from latent space produces new images (faces, art)
- **Denoising**: Denoising autoencoders learn to remove noise from corrupted inputs
- **Feature learning**: Pre-training representations for downstream tasks

## Variants

- **Conditional VAE (CVAE)**: Conditions generation on class labels or attributes
- **β-VAE**: Adjusts KL weight for more disentangled representations
- **VQ-VAE**: Uses vector quantization for discrete latent codes
- **Adversarial Autoencoder**: Replaces KL with adversarial training