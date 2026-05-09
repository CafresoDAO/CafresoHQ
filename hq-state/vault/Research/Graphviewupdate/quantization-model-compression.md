---
tags: [research, neural-networks, deployment, optimization]
---

# Quantization & Model Compression

Quantization transforms trained neural networks from high-precision floating-point (FP32) to lower-precision formats (INT8, FP8, even 1-bit), enabling faster inference and smaller memory footprints. This is essential for deploying models on edge devices, mobile, or cost-sensitive cloud infrastructure.

## Core Techniques

### Post-Training Quantization (PTQ)
- **No retraining required** — uses a small calibration dataset to determine optimal quantization parameters
- Converts FP32 → INT8 by analyzing activation distributions
- Tools like OpenVINO's NNCF and Intel Neural Compressor automate this process
- Typical result: ~4× memory reduction with minimal accuracy loss

### Quantization-Aware Training (QAT)
- Simulates quantization during training ("fake quantization")
- Forward/backward passes use rounded values mimicking INT8, but compute in float
- Higher accuracy than PTQ but requires retraining cycles
- Better for models sensitive to precision loss

### Emerging Formats
| Format | Compression | Use Case |
|--------|-------------|----------|
| INT8 | 4× | Standard inference |
| FP8 (E4M3) | 4× | **92.64% pass rate** vs 65.87% for INT8 on complex workloads |
| INT4/AWQ | 8× | Large language models |
| 1-bit | 32× | Extreme edge deployment |

## Activation-Aware Quantization (AWQ)
- Key insight: not all weights matter equally for accuracy
- Uses calibration data to identify **top 1% most important parameters** (based on activation magnitude)
- Important weights stay full-precision; rest quantized to 4-bit
- Achieves ~8× compression with minimal performance degradation
- Particularly effective for LLMs where naive quantization causes quality collapse

## Practical Workflow
1. Train model at FP32 precision (standard)
2. Export to intermediate representation (ONNX, OpenVINO IR)
3. Run calibration dataset through model to profile activations
4. Apply quantization (PTQ for speed, QAT if accuracy-sensitive)
5. Validate on held-out test set
6. Deploy via optimized runtime (TensorRT, OpenVINO, ONNX Runtime)

## When to Use What
- **PTQ + INT8**: Production deployment, ~2-4% accuracy budget acceptable
- **QAT + INT8**: Accuracy-critical applications, have training infrastructure
- **AWQ + INT4**: Large language models, memory-constrained serving
- **FP8**: Modern GPUs (H100+), balance of range and precision

## Connection to Other Topics
- Complements [[knowledge-distillation-teacher-student]] — distill first, then quantize for maximum compression
- Works alongside [[model-serving-inference-apis]] — quantized models serve faster
- Consider [[regularization-techniques-overfitting]] during QAT to maintain generalization
- [[hyperparameter-tuning-strategies]] applies to calibration dataset selection

## Key Insight
FP8 format (E4M3 specifically) shows 92.64% workload pass rate compared to 65.87% for INT8, suggesting FP8 may become the default quantization target as hardware support expands.