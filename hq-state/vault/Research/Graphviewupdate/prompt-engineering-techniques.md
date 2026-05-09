---
tags: [research, ai, neural-networks, practical]
---

# Prompt Engineering Techniques

Once you have a trained [[neural-network-architecture-basics|neural network]] (especially an LLM), **prompt engineering** is how you extract useful behavior from it. This is the practical craft of interfacing with AI.

## Core Techniques

### Zero-Shot Prompting
- Give the model a task with no examples
- Works well for general knowledge tasks
- Relies entirely on the model's pre-training

### One-Shot / Few-Shot Prompting
- Provide 1-3+ examples of input → output pairs
- Teaches format, tone, and reasoning patterns
- Best practices:
  - Use consistent formatting across examples
  - Separate examples from the actual task with clear delimiters
  - Mix input variety while keeping output format stable

### Chain-of-Thought (CoT)
- Ask the model to reason step-by-step before answering
- Simple trigger: "Let's think step by step"
- Dramatically improves performance on:
  - Math and logic problems
  - Multi-step reasoning
  - Complex analysis tasks
- **Zero-shot CoT** (Kojima et al. 2022): Adding "Let's think step by step" works even without examples

### Self-Consistency Prompting
- Generate multiple reasoning paths for the same problem
- Take the majority answer or most consistent conclusion
- Improves accuracy on tasks with clear correct answers

### Meta Prompting
- Ask the model to generate or refine its own prompts
- Useful for token efficiency
- Reduces biases from hand-crafted examples

## Practical Principles

1. **Be specific** — vague prompts get vague outputs
2. **Structure matters** — use delimiters, headers, numbered steps
3. **Persona assignment** — "Act as a senior engineer" can shift response quality
4. **Output format** — specify JSON, markdown, bullet points explicitly
5. **Constraints** — state what NOT to do as clearly as what to do

## Connection to Neural Network Design

Prompt engineering is constrained by [[attention-mechanism-transformers|attention]] and context windows. Understanding [[embeddings-semantic-search|embeddings]] helps explain why semantically similar prompts yield similar outputs. [[retrieval-augmented-generation|RAG]] extends prompting by injecting relevant context dynamically.

## When Prompting Isn't Enough

If prompt engineering hits limits, consider:
- [[transfer-learning-fine-tuning|Fine-tuning]] for domain adaptation
- [[retrieval-augmented-generation|RAG]] for knowledge grounding
- Tool use / function calling for actions beyond text