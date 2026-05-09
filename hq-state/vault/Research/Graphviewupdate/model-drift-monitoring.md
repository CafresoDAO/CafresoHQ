---
tags: [research, neural-networks, mlops, monitoring]
---

# Model Drift Detection and Monitoring

Once a neural network is deployed ([[model-serving-deployment]]), its performance can degrade over time as production data diverges from training data. This is **model drift**, and detecting it is critical for maintaining reliable AI systems.

## Types of Drift

**Data Drift (Covariate Shift)**  
Input feature distributions change while relationships stay constant. Example: a fraud detection model trained on pre-pandemic spending sees different transaction patterns post-pandemic.

**Concept Drift**  
The underlying relationship between features and targets changes. Example: user preferences shift, making old recommendation patterns obsolete. This is harder to detect since the "ground truth" changes.

**Prediction Drift**  
Model output distributions shift, even if inputs haven't changed noticeably. Can indicate subtle upstream issues or emergent patterns.

## Detection Strategies

### Direct Quality Monitoring
- Track **accuracy, precision, recall, F1** on labeled production samples
- Compare against baseline metrics from validation sets
- Alert when performance drops below thresholds
- Requires ground truth labels (delayed or sampled)

### Statistical Drift Tests
- **Kolmogorov-Smirnov test**: compares feature distributions between training and production
- **Population Stability Index (PSI)**: measures distribution shifts in categorical/binned features
- **Wasserstein distance**: quantifies difference between probability distributions
- Run periodically on incoming data windows

### Proxy Metrics
When labels are delayed or unavailable:
- Monitor prediction confidence distributions
- Track feature statistics (mean, std, percentiles)
- Log outlier rates and missing value frequencies
- Correlate with business KPIs that may signal model issues

## Production Implementation

**Continuous Monitoring Pipeline**  
1. Log model inputs, outputs, and metadata at inference time
2. Compute drift metrics on rolling windows (hourly, daily)
3. Compare against reference distributions from training/validation
4. Trigger alerts or automatic retraining when thresholds exceeded

**Tools & Frameworks**  
- **Evidently AI**: open-source drift detection and visualization
- **Arize**: ML observability platform with drift analysis
- **AWS SageMaker Model Monitor**: integrated drift detection for SageMaker models
- **Seldon Alibi Detect**: real-time outlier and drift detection

## Mitigation Strategies

When drift is detected:
- **Retrain** with recent data to capture new patterns
- **Fine-tune** on production samples ([[transfer-learning-fine-tuning]])
- **Active learning** to collect labels for high-uncertainty cases ([[active-learning-query-strategies]])
- **Model ensemble** with recent and historical models
- **Feature engineering** to add drift-resistant signals

## Connection to XAI

Drift detection pairs well with [[explainability-xai-techniques]] - when performance drops, explainability tools help diagnose *why*. SHAP values or feature importance can reveal which features are driving anomalous predictions.

## Key Takeaway

Model drift is inevitable in production. The question isn't *if* drift will happen, but *when* and *how quickly you can detect it*. Automated monitoring with clear escalation paths is essential for any deployed neural network.
