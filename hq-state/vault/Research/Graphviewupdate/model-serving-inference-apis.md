---
tags: [research, deployment, neural-networks, production]
---

# Model Serving & Inference APIs

Once a neural network is trained, **model serving** is how you expose it for real-world use. This bridges the gap between a .pt or .onnx file and an API your applications can call.

## Major Serving Frameworks

| Framework | Native Format | Key Strength |
|-----------|--------------|---------------|
| **TensorFlow Serving** | SavedModel | Google Cloud integration, gRPC |
| **TorchServe** | .mar archives | PyTorch-native, simple handlers |
| **ONNX Runtime** | .onnx | Framework-agnostic, broad hardware support |
| **Triton Inference Server** | Multiple | Multi-framework, GPU optimization |

## Common Deployment Pattern

1. **Export** — Convert trained model to servable format (TorchScript, SavedModel, ONNX)
2. **Package** — Bundle model + handler scripts + dependencies
3. **Deploy** — Load into serving framework with REST/gRPC endpoints
4. **Scale** — Add batching, versioning, and load balancing

## TorchServe Workflow

TorchServe uses **Model Archive (.mar)** files:
- Serialized model (often TorchScripted for portability)
- Handler script defining `preprocess()`, `inference()`, `postprocess()`
- Config for batching and workers

Exposes two REST APIs:
- **Inference API** — `/predictions/<model_name>` for predictions
- **Management API** — Register/unregister models, scaling

## ONNX Runtime Advantage

ONNX acts as an **interchange format** — train in PyTorch, serve via ONNX Runtime. Benefits:
- Hardware acceleration (TensorRT, DirectML, CoreML backends)
- Consistent inference across cloud providers
- Azure ML has native ONNX deployment support

## Key Optimizations for Inference

- **Batching** — Group requests to maximize GPU utilization (see [[model-quantization-compression]])
- **Model Versioning** — A/B test new models, rollback if needed
- **Caching** — Store frequent predictions
- **Async Processing** — Queue requests for throughput over latency

## Integration with AI-Powered Apps

Once served, your model becomes an API endpoint:
```
POST /predictions/resnet50
Content-Type: application/json

{"image": "base64_encoded_data"}
```

This enables:
- [[retrieval-augmented-generation|RAG pipelines]] calling embedding models
- [[ai-powered-ux-patterns|UX features]] with real-time inference
- Chaining multiple models (ensemble serving)

## Choosing a Framework

- **TensorFlow ecosystem** → TensorFlow Serving
- **PyTorch + simplicity** → TorchServe
- **Multi-framework or hardware flexibility** → Triton or ONNX Runtime
- **Serverless/managed** → Cloud-native options (SageMaker, Vertex AI, Azure ML)