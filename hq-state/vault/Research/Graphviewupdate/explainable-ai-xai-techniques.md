---
tags: [research, neural-networks, ai-ux, interpretability]
---

# Explainable AI (XAI) Techniques

As neural networks grow more complex, **explainability** becomes essential for user trust, debugging, and regulatory compliance. XAI bridges the gap between black-box models and human understanding.

## Why Explainability Matters

- **User trust**: Users adopt AI features more readily when they understand *why* a recommendation was made
- **Debugging**: Developers can identify when models rely on spurious correlations
- **Compliance**: GDPR and other regulations require "right to explanation" for automated decisions
- **Bias detection**: Reveals if protected attributes inappropriately influence predictions

## Core XAI Techniques

### LIME (Local Interpretable Model-agnostic Explanations)

- Explains individual predictions by approximating the complex model locally with an interpretable one
- Model-agnostic: works with any classifier or regressor
- Creates perturbations around the instance, observes how predictions change
- Output: feature importance weights for that specific prediction

**Use case**: "Why did the model flag *this* transaction as fraud?"

### SHAP (SHapley Additive exPlanations)

- Based on game theory (Shapley values from cooperative game theory)
- Provides consistent, theoretically grounded feature attributions
- Variants:
  - **KernelSHAP**: model-agnostic but slower
  - **TreeSHAP**: optimized for tree-based models
  - **DeepSHAP**: combines DeepLIFT with Shapley values for neural networks

**Advantage over LIME**: guarantees consistency and local accuracy properties

### Counterfactual Explanations

- Answers: "What minimal change would flip the prediction?"
- Example: "If your income were $5K higher, the loan would be approved"
- Actionable and intuitive for end users

### Interpretable Neural Networks

- **Attention visualization**: Highlights which input tokens/regions the model focuses on (see [[attention-mechanism-transformers]])
- **Concept bottleneck models**: Force network to predict human-defined concepts as intermediate steps
- **Prototype networks**: Classify by similarity to learned prototypical examples

## Glassbox vs Blackbox Approaches

| Approach | Description | Trade-off |
|----------|-------------|----------|
| Glassbox | Inherently interpretable (EBMs, decision trees) | May sacrifice some accuracy |
| Blackbox + XAI | Complex model + post-hoc explanation | Full accuracy, explanation is approximate |

## Integration with UX

XAI enables the [[ai-powered-ux-patterns]] that build user confidence:

- **Confidence indicators**: Show prediction certainty
- **Feature highlighting**: Visually emphasize what drove the decision
- **"Why?" buttons**: On-demand explanations without cluttering the default view
- **Comparative explanations**: "Similar to X, but differs because..."

## Practical Considerations

- **Performance**: SHAP/LIME add latency; consider pre-computing for common cases
- **Fidelity**: Post-hoc explanations approximate the model — they can mislead if the local approximation is poor
- **User studies**: Technical accuracy ≠ user comprehension; test explanations with real users

## Tools & Libraries

- `shap` (Python): Unified interface for SHAP explanations
- `lime` (Python): Original LIME implementation
- `InterpretML` (Microsoft): Glassbox models + blackbox explainers
- `Captum` (PyTorch): Attribution methods for deep learning

---

Related: [[neural-network-architecture-basics]] · [[neural-network-inference-deployment]] · [[ai-powered-ux-patterns]] · [[attention-mechanism-transformers]]