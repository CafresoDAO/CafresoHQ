---
tags: [research, neural-networks, alignment, rlhf]
---

# Reinforcement Learning from Human Feedback (RLHF)

RLHF is the key technique that transforms a pre-trained language model into an aligned, helpful AI assistant. It addresses a fundamental challenge: how do you optimize a model for "helpfulness" when there's no mathematical formula for what humans actually want?

## The Three-Stage Pipeline

### Stage 1: Supervised Fine-Tuning (SFT)
- Start with a pre-trained base model (like GPT or LLaMA)
- Fine-tune on high-quality demonstration data
- Human experts write ideal responses to prompts
- Model learns the *format* and *style* of good responses

### Stage 2: Reward Model Training
- Generate multiple responses to the same prompt
- Human raters **rank** responses (not score them absolutely)
- Train a separate neural network to predict human preferences
- This reward model learns to approximate human judgment

### Stage 3: RL Optimization (PPO)
- Use Proximal Policy Optimization to fine-tune the SFT model
- Reward signal comes from the trained reward model
- KL divergence penalty prevents drifting too far from original model
- Model learns to generate responses the reward model scores highly

## Why Ranking > Rating

Human raters are inconsistent at absolute scoring ("rate this 1-10"), but reliable at comparative judgments ("which response is better?"). RLHF exploits this by:
- Showing raters pairs/sets of responses
- Asking only which is preferred
- Using Bradley-Terry or Elo-style models to convert comparisons to scores

## Connection to Research Tools

RLHF is what makes AI assistants actually *useful* for research:
- Models learn to cite sources, hedge uncertainty, ask clarifying questions
- Without RLHF: model might be technically accurate but unhelpful
- With RLHF: model learns what researchers actually find valuable

This connects to [[transfer-learning-fine-tuning]] (SFT stage) and [[loss-functions-neural-networks]] (reward modeling uses cross-entropy on preference pairs).

## Limitations & Alternatives

| Challenge | Description |
|-----------|-------------|
| Reward hacking | Model finds exploits that score high but aren't actually helpful |
| Human bias | Reward model inherits biases from human raters |
| Expensive | Requires thousands of human comparisons |

Emerging alternatives:
- **DPO (Direct Preference Optimization)**: Skips reward model, optimizes preferences directly
- **RLAIF**: Uses AI feedback instead of human feedback
- **Constitutional AI**: Model self-critiques against written principles

## Practical Application

Once you've trained a neural network (see [[attention-mechanisms-transformers]], [[embeddings-representation-learning]]), RLHF is how you make it *usable*:

1. Deploy base model with instruction-following SFT
2. Collect user feedback (thumbs up/down, regenerations)
3. Train reward model on aggregated preferences
4. Run PPO optimization cycles
5. Iterate as user needs evolve

This is the bridge between "I have a trained model" and "I have a useful AI product."