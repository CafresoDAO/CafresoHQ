---
tags: [research, neural-networks, deployment, optimization]
---

# Model Quantization & Compression

Quantization reduces neural network precision from 32-bit floats to lower bit-widths (INT8, INT4, FP8), dramatically cutting memory and compute costs while preserving accuracy.

## Why Quantization Matters

- **Memory reduction**: INT8 uses 4× less memory than FP32
- **Faster inference**: Hardware accelerators (AVX2/AVX512, Tensor Cores) optimize for low-bit ops
- **Edge deployment**: Enables running models on phones, IoT, embedded systems
- **Cost savings**: Smaller models = cheaper cloud inference

## Quantization Approaches

| Type | When Applied | Accuracy | Complexity |
|------|--------------|----------|------------|
| Post-Training (PTQ) | After training | Good | Low |
| Quantization-Aware Training (QAT) | During training | Best | High |
| Dynamic Quantization | At runtime | Moderate | Low |

### Data Format Choices

- **INT8**: Most common; excellent hardware support
- **UINT8 activations + INT8 weights**: Recommended for x86-64 with AVX2/AVX512
- **INT4/MXFP4**: Aggressive compression for LLMs (see [[neural-network-inference-deployment]])
- **FP8/MXFP8**: Balance between INT8 speed and FP16 range

## Tools & Frameworks

### Intel Neural Compressor
- Cross-platform (PyTorch, TensorFlow, ONNX Runtime)
- Auto-tuning for optimal quantization config
- Supports INT8/FP8/INT4 for LLMs
- Upstreamed into ONNX for built-in deployment

### ONNX Runtime Quantization
```python
from onnxruntime.quantization import quantize_dynamic, QuantType

quantize_dynamic(
    model_input="model.onnx",
    model_output="model_int8.onnx",
    weight_type=QuantType.QInt8
)
```

### TensorRT INT8
- NVIDIA's solution for GPU inference
- Calibration-based quantization
- Excellent for transformer models (BERT, GPT)

## Real-World Example: Palo Alto Networks

Palo Alto Networks quantized cybersecurity ML models to INT8 to achieve required response speeds — demonstrating production viability of aggressive quantization.

## Selective Quantization

Not all layers quantize equally well:
- **Sensitive layers**: First/last layers, attention mechanisms — keep higher precision
- **Safe layers**: Dense middle layers — aggressive quantization
- **Mixed precision**: Combine INT8 body with FP16 heads

## Connection to Deployment Pipeline

Quantization fits into the broader [[neural-network-inference-deployment]] workflow:
1. Train model (FP32)
2. Export to ONNX/TensorRT
3. Quantize (PTQ or QAT)
4. Optimize graph (fuse ops, constant folding)
5. Deploy to target hardware

## Accuracy Considerations

- Always benchmark quantized vs original on your actual use case
- Calibration datasets should represent production distribution
- Watch for outlier activations that break INT8 range

See also: [[transfer-learning-fine-tuning]] for starting with pre-quantized models.