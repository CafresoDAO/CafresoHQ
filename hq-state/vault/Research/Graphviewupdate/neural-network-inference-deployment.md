---
tags: [research, neural-networks, deployment, inference]
---
# Neural Network Inference & Deployment

Once a neural network is trained (see [[neural-network-training-backpropagation]]), you need to **deploy** it so applications can use it. This is called **inference** — feeding new data through the trained model to get predictions.

## Key Concepts

- **Training vs Inference**: Training adjusts weights; inference uses frozen weights to make predictions
- **Model artifacts**: The saved weights, architecture definition, and preprocessing config
- **Latency**: How fast the model responds (critical for real-time apps)
- **Throughput**: How many predictions per second

## Common Deployment Patterns

### 1. REST API Serving
Wrap your model in a web service:
- **Flask/FastAPI** (Python): Simple, flexible, good for prototypes
- **TensorFlow Serving**: Production-grade, handles model versioning
- **TorchServe**: PyTorch equivalent

```python
# Simplified FastAPI example
@app.post("/predict")
def predict(data: InputData):
    tensor = preprocess(data)
    result = model(tensor)
    return {"prediction": result.tolist()}
```

### 2. Embedded/Edge Deployment
Run models directly on devices:
- **ONNX Runtime**: Cross-platform model format
- **TensorRT**: NVIDIA GPU optimization (up to 16x efficiency gains)
- **TensorFlow Lite**: Mobile/embedded devices

### 3. Serverless / Cloud Functions
- AWS Lambda, Google Cloud Functions, Azure Functions
- Pay-per-invocation, auto-scaling
- Cold start latency can be a concern

### 4. Batch Inference
Process large datasets offline:
- Spark ML pipelines
- Scheduled jobs processing queued data

## Optimization for Production

| Technique | Benefit | Trade-off |
|-----------|---------|----------|
| Quantization | Smaller model, faster inference | Slight accuracy loss |
| Pruning | Removes unnecessary weights | Requires fine-tuning |
| Distillation | Smaller "student" model | Training overhead |
| Caching | Reuse common predictions | Memory usage |

## Integration Checklist

- [ ] Export model to portable format (ONNX, SavedModel, TorchScript)
- [ ] Add preprocessing/postprocessing to service
- [ ] Set up monitoring (latency, error rates, drift detection)
- [ ] Version your models alongside code
- [ ] Plan rollback strategy

## Related
- [[neural-network-architecture-basics]] — what you're deploying
- [[great-research-tool-principles]] — UX considerations for AI-powered features