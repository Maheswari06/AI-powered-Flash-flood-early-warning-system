# HYDRA/ARGUS — ML & AI Models Deep Dive

## Every AI/ML Model Used in the System: What It Is, How It Works, and Its Role

---

## Table of Contents

1. [XGBoost — Fast-Track Flood Predictor](#1-xgboost--fast-track-flood-predictor)
2. [SHAP — Explainability Engine](#2-shap--explainability-engine)
3. [TFT (Temporal Fusion Transformer) — Deep-Track Forecaster](#3-tft-temporal-fusion-transformer--deep-track-forecaster)
4. [PINN (Physics-Informed Neural Network) — Virtual Sensor Mesh](#4-pinn-physics-informed-neural-network--virtual-sensor-mesh)
5. [YOLOv11 — Water Detection from CCTV](#5-yolov11--water-detection-from-cctv)
6. [SAM-2 (Segment Anything Model 2) — Water Segmentation](#6-sam-2-segment-anything-model-2--water-segmentation)
7. [Causal GNN — Causal Inference Engine](#7-causal-gnn--causal-inference-engine)
8. [PPO (Proximal Policy Optimization) — Evacuation Router](#8-ppo-proximal-policy-optimization--evacuation-router)
9. [IndicBERT — Multilingual Flood Report Classifier](#9-indicbert--multilingual-flood-report-classifier)
10. [Whisper — Voice Transcription for CHORUS](#10-whisper--voice-transcription-for-chorus)
11. [Kalman Filter — Sensor Quality Assurance](#11-kalman-filter--sensor-quality-assurance)
12. [Adaptive Threshold Engine — Dynamic Alert Boundaries](#12-adaptive-threshold-engine--dynamic-alert-boundaries)
13. [Alert Classifier — Risk-to-Alert Mapping](#13-alert-classifier--risk-to-alert-mapping)
14. [Oracle v2 (MobileFloodFormer) — Edge Micro-Transformer](#14-oracle-v2-mobilefloodformer--edge-micro-transformer)
15. [Federated Learning — Privacy-Preserving Training](#15-federated-learning--privacy-preserving-training)
16. [Model Summary Table](#16-model-summary-table)
17. [How All Models Work Together](#17-how-all-models-work-together)

---

## 1. XGBoost — Fast-Track Flood Predictor

**File:** `services/prediction/fast_track/xgboost_predictor.py`
**Model File:** `models/xgboost_flood.joblib`

### What Is XGBoost?

XGBoost (Extreme Gradient Boosting) is an ensemble machine learning algorithm that builds many small decision trees sequentially, where each new tree corrects the errors of the previous ones. It is known for being fast, accurate, and the winning algorithm in most tabular data competitions.

### Role in HYDRA

XGBoost is the **primary flood prediction engine** — the "fast track." Every 60 seconds, for each of the 12 monitored villages, it takes a vector of 16 real-time features (water levels, rainfall, soil moisture, etc.) and outputs a single flood probability between 0.0 and 1.0. This is the number that drives the entire alert system.

### How It Works in This Project

```
Raw sensor data → Feature Engine → 16-feature vector → XGBoost → flood probability (0.0-1.0)
```

**Hyperparameters:**
| Parameter | Value | Why |
|---|---|---|
| `n_estimators` | 500 | Enough trees for complex flood patterns |
| `max_depth` | 6 | Prevents overfitting while capturing interactions |
| `learning_rate` | 0.05 | Slow learning for better generalization |
| `subsample` | 0.8 | Row sampling to reduce variance |
| `colsample_bytree` | 0.8 | Feature sampling per tree |
| `eval_metric` | logloss | Binary classification (flood/no-flood) |

**The 16 Input Features (order matters):**

| # | Feature | Unit | What It Measures |
|---|---|---|---|
| 1 | `level_1hr_mean` | meters | Average water level over last 1 hour |
| 2 | `level_3hr_mean` | meters | Average water level over last 3 hours |
| 3 | `level_6hr_mean` | meters | Average water level over last 6 hours |
| 4 | `level_24hr_mean` | meters | Average water level over last 24 hours |
| 5 | `level_1hr_max` | meters | Maximum water level spike in last hour |
| 6 | `rate_of_change_1hr` | m/hr | How fast water is rising right now |
| 7 | `rate_of_change_3hr` | m/hr | 3-hour trend in water level change |
| 8 | `cumulative_rainfall_6hr` | mm | Total rainfall in last 6 hours |
| 9 | `cumulative_rainfall_24hr` | mm | Total rainfall in last 24 hours |
| 10 | `soil_moisture_index` | 0-1 | How saturated the ground is (1 = fully saturated) |
| 11 | `antecedent_moisture_index` | mm | Pre-existing ground moisture from prior rainfall |
| 12 | `upstream_risk_score` | 0-1 | Flood risk at upstream stations (cascade effect) |
| 13 | `basin_connectivity_score` | 0-1 | How hydraulically connected this point is |
| 14 | `hour_of_day` | 0-23 | Time factor (flash floods peak at certain hours) |
| 15 | `day_of_year` | 1-366 | Seasonal factor |
| 16 | `is_monsoon_season` | 0 or 1 | June-September = 1 (monsoon amplifies risk) |

**Training:**
- Uses historical CWC data from 2019-2023 (`data/cwc_historical_2019_2023.csv`)
- Temporal 80/20 split (no data leakage — test set is always after train set)
- If historical data is unavailable, generates synthetic training data using realistic monsoon flood dynamics with logistic regression coefficients
- Trains on startup when `TRAIN_ON_STARTUP=true`

**Fallback:** When XGBoost model fails to load, a rule-based heuristic predictor takes over using weighted feature sums:
```
risk = 0.25 × (rainfall/100) + 0.20 × soil_moisture + 0.20 × (rate_of_change/0.5) + ...
```

### Why XGBoost and Not Deep Learning?

1. **Speed**: Inference in <1ms (deep learning takes 10-100ms)
2. **Tabular data**: XGBoost consistently outperforms neural networks on tabular features
3. **Explainability**: Tree-based models work natively with SHAP
4. **Small data**: Works well with limited historical flood records
5. **No GPU required**: Runs on any CPU

---

## 2. SHAP — Explainability Engine

**File:** `services/prediction/fast_track/shap_explainer.py`

### What Is SHAP?

SHAP (SHapley Additive exPlanations) is a game-theoretic approach to explain machine learning predictions. It assigns each feature an importance value for a particular prediction. Named after Lloyd Shapley's Nobel Prize-winning work in cooperative game theory.

### Role in HYDRA

SHAP answers the critical question: **"Why does the model think Majuli has 81% flood risk?"** It decomposes every prediction into per-feature contributions, enabling district officials to understand and trust the AI's recommendations.

### How It Works

```
XGBoost prediction (0.81) → SHAP TreeExplainer → "rainfall contributed +0.25, soil moisture +0.18, upstream risk +0.12"
```

**Implementation Details:**
- Uses `shap.TreeExplainer` — optimized specifically for tree-based models
- Pre-computes the explainer at service startup (not per-request) for speed
- Selects **top-N** most impactful features (default N=3, configurable via `SHAP_TOP_N`)
- Each factor includes:
  - Feature name with human-readable label
  - SHAP value (contribution magnitude)
  - Direction: `INCREASES_RISK` or `DECREASES_RISK`
  - Percentage of total prediction explained

**Human-Readable Labels:**
```
level_1hr_mean          → "Water level (1hr avg): 4.15m"
cumulative_rainfall_6hr → "Rainfall (6hr): 85mm"
soil_moisture_index     → "Soil saturation: 72%"
rate_of_change_1hr      → "Rise rate: 0.35m/hr"
upstream_risk_score     → "Upstream risk: 65%"
```

**Example Output (for Majuli at 81% risk):**
```json
{
  "explanation": [
    {
      "feature": "cumulative_rainfall_6hr",
      "label": "Rainfall (6hr): 85mm",
      "shap_value": 0.247,
      "direction": "INCREASES_RISK",
      "contribution_pct": 31
    },
    {
      "feature": "soil_moisture_index",
      "label": "Soil saturation: 72%",
      "shap_value": 0.183,
      "direction": "INCREASES_RISK",
      "contribution_pct": 23
    },
    {
      "feature": "upstream_risk_score",
      "label": "Upstream risk: 65%",
      "shap_value": 0.124,
      "direction": "INCREASES_RISK",
      "contribution_pct": 15
    }
  ]
}
```

**Fallback Heuristic (when SHAP unavailable):**
Uses pre-defined feature importance weights:
```
cumulative_rainfall_6hr:  0.18
upstream_risk_score:      0.16
rate_of_change_1hr:       0.14
soil_moisture_index:      0.12
level_1hr_max:            0.10
```

### Why SHAP Matters for Flood Warning

In emergency management, officials cannot blindly trust a number. If the system says "81% flood risk," they need to know *why*. SHAP enables:
- **Actionable insights**: "Rainfall is the main driver" → prioritize drainage
- **Trust building**: Officials can verify against their local knowledge
- **Accountability**: Every alert can be traced to specific data points
- **NDMA compliance**: Indian disaster management requires explainable decision-making

---

## 3. TFT (Temporal Fusion Transformer) — Deep-Track Forecaster

**File:** `services/prediction/deep_track/tft_predictor.py`
**Model File:** `models/tft_flood.ckpt`

### What Is TFT?

The Temporal Fusion Transformer is a deep learning architecture designed by Google specifically for multi-horizon time series forecasting. Unlike XGBoost which gives a single "right now" probability, TFT predicts **multiple future time points** with **uncertainty quantification**.

### Role in HYDRA

TFT is the **"deep track"** — it answers: "What will the flood risk be in 15 minutes? 30 minutes? 1 hour? 2 hours?" This gives emergency responders lead time to act before a flood hits.

### How It Works

```
Last 24 hours of features → TFT → risk at [15, 30, 45, 60, 90, 120] minutes
                                    with uncertainty bands [p10, p50, p90]
```

**Forecast Configuration:**
| Parameter | Value |
|---|---|
| Horizons | 15, 30, 45, 60, 90, 120 minutes |
| Quantiles | p10 (optimistic), p50 (median), p90 (pessimistic) |
| Lookback window | 24 hours |
| Features | Same 16 as XGBoost |

**Output Structure:**
```json
{
  "deep_track": {
    "horizons": [
      {"minutes": 15, "p10": 0.72, "p50": 0.78, "p90": 0.85},
      {"minutes": 30, "p10": 0.75, "p50": 0.82, "p90": 0.91},
      {"minutes": 60, "p10": 0.68, "p50": 0.76, "p90": 0.88},
      {"minutes": 120, "p10": 0.55, "p50": 0.65, "p90": 0.80}
    ],
    "peak_risk_horizon_min": 30,
    "peak_risk_value": 0.91,
    "trend": "RISING"
  }
}
```

**Physics-Based Synthetic Model (when checkpoint unavailable):**

When the trained TFT model isn't loaded, the system uses a physics-based rising-limb hydrograph:

```
risk(t) = base + amplitude × (1 − e^(−t/τ))
```

Where:
- `base` = Current XGBoost risk score (anchoring fast-track to deep-track)
- `amplitude` = f(rainfall, soil_moisture, upstream_risk) → maximum 0.6
- `τ` (time constant) = 20-60 minutes, inversely proportional to soil saturation
  - Wet soil → fast rising → short τ
  - Dry soil → slow rising → long τ
- Uncertainty: Heteroscedastic σ = 0.03 + 0.001 × horizon_minutes
- Quantiles: Gaussian approximation with z-scores (z₁₀ = -1.2816, z₉₀ = +1.2816)

**Trend Detection:**
```
slope = (last_horizon_risk - first_horizon_risk) / time_span
if slope > 0.01/min:  RISING
if slope < -0.01/min: FALLING
else:                  STABLE
```

### Why Both XGBoost AND TFT?

| Aspect | XGBoost (Fast Track) | TFT (Deep Track) |
|---|---|---|
| **Latency** | <1ms | ~50ms |
| **Output** | Single probability | 6 horizons × 3 quantiles |
| **Uncertainty** | No | Yes (p10/p50/p90) |
| **Lead time** | "Right now" | "Next 2 hours" |
| **GPU needed** | No | Preferred |
| **Fallback** | Rule-based heuristic | Physics-based rising limb |

The fast track triggers immediate alerts. The deep track tells responders how much time they have.

---

## 4. PINN (Physics-Informed Neural Network) — Virtual Sensor Mesh

**File:** `services/prediction/pinn.py` + `services/feature_engine/pinn_mesh.py`
**Model File:** `models/pinn_beas_river.pt`

### What Is a PINN?

A Physics-Informed Neural Network is a neural network that is trained not just on data, but also on the laws of physics. The loss function includes both a data-fitting term and a physics residual term, so the model cannot violate known physical equations even where data is sparse.

### Role in HYDRA

India has only ~50 physical river gauges for the entire Beas basin. PINN creates **thousands of virtual sensors** by interpolating between real gauges while obeying the Saint-Venant equations of shallow water flow. This converts sparse point measurements into a continuous water level mesh.

### The Physics: Saint-Venant Continuity Equation

```
∂A/∂t + ∂Q/∂x = 0
```

Where:
- `A` = cross-sectional area of water (related to depth h)
- `Q` = volumetric flow rate
- `x` = distance along the river
- `t` = time

In plain English: **water is conserved** — what flows in must flow out (or accumulate). The neural network learns to predict water levels while respecting this fundamental law.

### Architecture

```
Input: (x_normalized, t_normalized) → position along river + time
  ↓
Linear(2, 64) → Tanh
Linear(64, 64) → Tanh
Linear(64, 64) → Tanh
Linear(64, 1) → h_predicted (water level)
```

**Loss Function:**
```
Loss = data_loss + λ × physics_residual_loss

data_loss    = MSE(h_predicted, h_observed)     at gauge locations
physics_loss = MSE(∂h/∂t + c × ∂h/∂x, 0)      everywhere in mesh

λ = 0.1  (physics regularization weight)
c = √(g × |h|)  (characteristic wave speed, g = 9.81 m/s²)
```

The gradients ∂h/∂t and ∂h/∂x are computed via PyTorch autograd — the same backpropagation machinery used for training.

**Virtual Sensor Mesh (Beas River):**
```
VIRT-BEAS-001  @ 5 km   (near Manali)
VIRT-BEAS-002  @ 10 km
VIRT-BEAS-003  @ 20 km  (between Kullu and Bhuntar)
VIRT-BEAS-004  @ 35 km
VIRT-BEAS-005  @ 55 km  (near Pandoh)

Total reach: 70 km
Real gauges: ~5 along this stretch
Virtual sensors: 10+ filling the gaps
```

**Fallback (when PyTorch unavailable):**
Inverse-Distance Weighting (IDW) with physics residual approximation using NumPy:
```
h_virtual(x) = Σ(w_i × h_gauge_i) / Σ(w_i)
w_i = 1 / distance(x, gauge_i)²
```

### Why PINN and Not Just Interpolation?

Simple interpolation can produce water levels that violate physics — for example, predicting water appearing where there is no inflow. PINN guarantees that virtual sensors are physically plausible, which prevents false alarms from unphysical predictions.

---

## 5. YOLOv11 — Water Detection from CCTV

**File:** `services/cv_gauging/main.py`
**Model File:** `models/yolo11n.pt`

### What Is YOLO?

YOLO (You Only Look Once) is a real-time object detection algorithm. Version 11 (YOLOv11) is the latest iteration, capable of detecting objects in images at 30+ FPS. The "n" suffix means "nano" — the smallest, fastest variant.

### Role in HYDRA

India lacks sufficient physical river gauges. CCTV cameras already exist at bridges, dams, and roads. YOLOv11 turns every CCTV camera into a **virtual water level gauge** by detecting and measuring the water surface in each video frame.

### How It Works

```
CCTV Frame (RGB image)
  ↓
YOLOv11 Detection
  ↓
Bounding boxes around water regions
  ↓
Pixel-to-Meter Conversion
  ↓
Water depth (meters), velocity estimate, confidence score
```

**Pipeline Steps:**

1. **Frame Capture**: CCTV streams send frames to the CV Gauging service
2. **YOLO Detection**: Identifies water regions with bounding boxes and confidence scores
3. **Pixel-to-Meter Conversion**:
   - **CCTV mode**: Pre-calibrated homography matrix for each camera (maps pixels to real-world meters)
   - **Drone mode**: Uses altitude + field-of-view to calculate Ground Sample Distance:
     ```
     GSD = (altitude_m × FOV_rad) / (image_width_px × 0.3048)
     ```
4. **Depth Estimation**: Bounding box height × pixel-to-meter ratio = depth in meters
5. **Alert Thresholds**:
   ```
   depth > 4.0m → alert_flag = True (EMERGENCY)
   depth > 3.0m → WATCH
   depth > 2.0m → ADVISORY
   ```

**Confidence Threshold:** `CV_CONFIDENCE_THRESHOLD=0.4` — detections below 40% confidence are discarded.

**Demo Cameras:**
```
CAM-BEAS-01: Beas River — Manali Bridge (32.24°N, 77.19°E)
CAM-BEAS-02: Beas River — Kullu Dam (31.95°N, 77.10°E)
```

### Why Not Just Use River Gauges?

Physical gauges are expensive ($5,000-$20,000 each), require maintenance, and India has only ~5,000 across the entire country. There are millions of CCTV cameras. Converting existing cameras into gauges using AI costs almost nothing and creates a much denser sensor network.

---

## 6. SAM-2 (Segment Anything Model 2) — Water Segmentation

**File:** `services/cv_gauging/main.py`
**Model File:** `models/sam2_tiny.pt`

### What Is SAM-2?

SAM-2 (Segment Anything Model 2) is Meta's foundation model for image and video segmentation. Given a prompt (like a bounding box from YOLO), it produces a pixel-precise mask of the object.

### Role in HYDRA

After YOLO detects a rectangular region containing water, SAM-2 refines it to the **exact pixel boundary** of the water surface. This is critical because:
- Water edges are irregular (not rectangular)
- Bridges, vegetation, and debris create complex boundaries
- Accurate area measurement requires precise segmentation

### How It Works (YOLO → SAM Pipeline)

```
CCTV Frame
  ↓
YOLO: "Water detected in box [x1=120, y1=200, x2=640, y2=480]"
  ↓
SAM-2: Takes box as prompt → generates pixel mask of exact water boundary
  ↓
Mask area (pixels²) × GSD² = water surface area (m²)
Mask height × pixel-to-meter = precise water depth
```

**Why "Tiny"?**
SAM-2 comes in multiple sizes. The "tiny" variant is used for real-time inference on CPU — achievable at 5-10 FPS, sufficient for gauge reading (no need for 30 FPS).

---

## 7. Causal GNN — Causal Inference Engine

**File:** `services/causal_engine/gnn.py`
**Model File:** `models/causal_gnn_brahmaputra.pt`
**DAG File:** `shared/causal_dag/beas_brahmaputra_v1.json`

### What Is a Causal GNN?

A Causal Graph Neural Network combines two ideas:
1. **Causal inference** (Judea Pearl's do-calculus): Understanding cause-and-effect, not just correlation
2. **Graph Neural Networks**: Neural networks that operate on graph-structured data

### Role in HYDRA

The Causal GNN answers questions like:
- "How much of Majuli's flood risk is **caused by** upstream rainfall vs. dam levels?"
- "If we **open the dam gates** 50%, what happens to downstream flood depth?"
- "What is the **optimal intervention** to minimize casualties?"

This goes beyond prediction (what will happen?) to intervention (what should we do?).

### The Causal DAG

The system encodes domain knowledge as a Directed Acyclic Graph (DAG):

```
rainfall_upstream ──→ surface_runoff ──→ downstream_flood_depth
       │                                        ↑
       └──→ soil_saturation ────────────────────┘
                                                 ↑
dam_pandoh_gate (INTERVENTION) ─────────────────┘
                                                 ↑
embankment_height (INTERVENTION) ───────────────┘
```

**Node Types:**
| Type | Meaning | Examples |
|---|---|---|
| OBSERVABLE | Measurable from sensors | rainfall, gauge levels, soil moisture |
| LATENT | Hidden variables (inferred) | surface runoff, infiltration rate |
| INTERVENTION | Actions we can take | dam gate position, road closure |
| OUTCOME | What we want to predict/control | flood depth, displacement, economic loss |

### GNN Architecture

```
Input: Node features (current observations or interventions)
  ↓
Input Projection: Linear(1, 64)
  ↓
GCN Layer 1: h = D⁻¹AXW₁ + h (residual)  → ReLU
GCN Layer 2: h = D⁻¹AXW₂ + h (residual)  → ReLU
GCN Layer 3: h = D⁻¹AXW₃ + h (residual)  → ReLU
  ↓
Output: Sigmoid → risk per node [0,1]
```

Where `D⁻¹AXW` is degree-normalized message passing — each node aggregates information from its causal parents.

### Pearl's do-Calculus Implementation

The `do(X=x)` operator simulates an intervention:

```python
def do_intervention(node, value):
    1. Cut all incoming edges to the intervention node
    2. Fix the node's value to the intervention value
    3. Propagate forward through the DAG (topological order)
    4. Compare: original_outcomes vs. counterfactual_outcomes
    5. Return: delta per outcome node
```

**Example:**
```
do(dam_pandoh_gate = 0.8)  # Open dam 80%
→ downstream_flood_depth: -0.35m (reduces flood by 35cm)
→ displacement_count: -1,200 people saved
→ economic_loss: -₹2.3 crore saved
```

**NumPy Fallback (when PyTorch unavailable):**
Uses Structural Equation Model (SEM) with Kahn's topological sort for forward propagation through the DAG.

---

## 8. PPO (Proximal Policy Optimization) — Evacuation Router

**File:** `services/evacuation_rl/agent/ppo_agent.py` + `services/evacuation_rl/environment/flood_env.py`
**Model File:** `models/evac_ppo.zip`

### What Is PPO?

PPO is a reinforcement learning algorithm developed by OpenAI. It trains an agent to make optimal decisions by trial-and-error in a simulated environment, using a clipped objective function that prevents destructively large policy updates.

### Role in HYDRA

When a flood alert is issued, someone must decide:
- Which villages to evacuate first?
- Which vehicles go where?
- Which shelters to use?
- Which roads are safe?

This is a multi-constraint optimization problem. PPO trains an agent to solve it optimally.

### Environment Design (PettingZoo Multi-Agent)

**Agents:** District coordinators (e.g., coordinator_majuli, coordinator_jorhat)

**State Space (what the agent observes):**
```
Per village (×12):
  - risk_score [0-1]
  - population_remaining / max_population
  - population_evacuated / max_population

Per vehicle (×N):
  - type: bus(50), truck(30), boat(20), helicopter(15)
  - location (lat, lon)
  - available: yes/no

Per shelter (×5):
  - current_occupancy / capacity
  - open: yes/no

Global:
  - time_remaining before flood
  - number of road closures
```

**Action Space:** Discrete — each action is a (vehicle, village, route) assignment.

**Reward Function:**
| Event | Reward | Why |
|---|---|---|
| Person evacuated | +10 | Primary objective |
| Vehicle sent to empty village | -2 | Waste of resources |
| Road closed encountered | -3 | Re-routing penalty |
| Shelter overflow | -8 | Dangerous overcrowding |
| Empty trip (<20% capacity) | -2 | Inefficient use |
| Road conflict (2+ vehicles) | -5 | Traffic jam |
| Time buffer > 30 min | +3 | Safety margin |

**Vehicle Routing:**
```
Travel time = haversine_distance(village, shelter) / avg_speed × 60 minutes
Departure cutoff = flood_arrival_time - travel_time
Round-trip = 2 × travel_time + loading_time
```

**Fallback (rule-based heuristic):**
```
Priority = risk_score × population
→ Sort villages by priority (descending)
→ For each village:
    Find nearest available vehicle
    Find nearest shelter with capacity
    Assign route via nearest safe road
```

---

## 9. IndicBERT — Multilingual Flood Report Classifier

**File:** `services/chorus/nlp/analyzer.py` + `services/chorus/nlp/indic_classifier.py`
**Model:** `ai4bharat/indic-bert` (fine-tuned)
**Checkpoint:** `models/indic_bert_flood_classifier/`

### What Is IndicBERT?

IndicBERT is a multilingual BERT model trained by AI4Bharat on 12 major Indian languages. BERT (Bidirectional Encoder Representations from Transformers) understands the meaning of text by reading it in both directions simultaneously.

### Role in HYDRA

When citizens in flood-affected areas send WhatsApp messages like:
- Hindi: "पानी बहुत तेज़ी से बढ़ रहा है, रास्ता बंद है"
- Assamese: "পানী বাঢ়িছে, সহায় লাগে"
- English: "Water rising fast, road blocked, need rescue"

IndicBERT understands the intent regardless of language and classifies it into one of 12 categories.

### 12-Class Classification

| Class | Description | Action Triggered |
|---|---|---|
| `FLOOD_PRECURSOR` | Early warning signals | Heighten monitoring |
| `ACTIVE_FLOOD` | Ongoing inundation | Immediate alert |
| `INFRASTRUCTURE_FAILURE` | Bridges, roads damaged | Reroute evacuations |
| `PEOPLE_STRANDED` | Rescue needed | Deploy NDRF |
| `ROAD_BLOCKED` | Route inaccessible | Update evacuation routes |
| `DAMAGE_REPORT` | Property loss | Insurance trigger |
| `RESOURCE_REQUEST` | Food, medical, boats needed | Logistics dispatch |
| `OFFICIAL_UPDATE` | Government/NDRF information | Broadcast to citizens |
| `WEATHER_OBSERVATION` | Rain/cloudburst report | Update weather model |
| `ANIMAL_MOVEMENT` | Unusual animal behavior (flood indicator) | Corroborate with sensors |
| `FALSE_ALARM` | Not an actual threat | Suppress alert |
| `UNRELATED` | Not flood-related | Ignore |

**Flood-Relevant Classes** (trigger further analysis):
`FLOOD_PRECURSOR`, `ACTIVE_FLOOD`, `INFRASTRUCTURE_FAILURE`, `PEOPLE_STRANDED`, `ROAD_BLOCKED`

### Sentiment Analysis

Each message is also scored for sentiment:
```
PANIC:     ≥2 panic keywords OR (1 panic + 3+ flood keywords)
ANXIOUS:   3+ flood keywords OR 1+ panic keyword
CONCERNED: 1+ flood keyword
CALM:      Default
```

**Panic keywords (multilingual, 165+ total):**
- English: "drowning", "trapped", "emergency", "dying"
- Hindi: "डूब", "फंसे", "बचाओ", "मौत"
- Assamese: "ডুবি", "আবদ্ধ", "সহায়"

### Credibility Scoring

Not all reports are equally reliable. Each signal gets a credibility score:
```
Base:                      0.30
+ Message length > 50:     +0.10
+ Message length > 150:    +0.10
+ Per keyword matched:     +0.05 (max 0.20)
+ Source = field worker:   +0.20
+ Source = government:     +0.20
+ Location provided:       +0.10
+ Classification confidence: +confidence × 0.10

Range: 0.30 — 1.00
```

### Consensus Mechanism

Individual reports may be unreliable. CHORUS requires **3+ independent reports** from the same geohash area before triggering an alert:
```
If (report_count >= 3) AND (average_panic > 30%):
    → Inject consensus alert into system
    → Increase village risk score
```

**Keyword Fallback (when IndicBERT unavailable):**
Pattern matching against 165+ multilingual keywords for zero-shot classification without the neural network.

---

## 10. Whisper — Voice Transcription for CHORUS

**File:** `services/chorus/nlp/whisper_transcriber.py`
**Model:** OpenAI Whisper `base` (77M parameters)

### What Is Whisper?

Whisper is OpenAI's automatic speech recognition (ASR) model, trained on 680,000 hours of multilingual audio. It can transcribe speech in 97 languages and translate to English.

### Role in HYDRA

Many citizens in rural India have limited literacy. They send **voice notes** on WhatsApp instead of text. Whisper converts these voice messages to text, which IndicBERT then classifies.

### Pipeline

```
WhatsApp voice note (OGG/WAV/MP3)
  ↓
Whisper ASR
  ↓
Transcribed text + detected_language + confidence
  ↓
IndicBERT classification
```

**Configuration:**
| Parameter | Value | Notes |
|---|---|---|
| Model size | `base` (77M params) | Fast enough for hackathon |
| Production size | `medium` or `large-v3` | Better accuracy |
| Supported languages | Hindi, Assamese, Bengali, English (and 93 more) | Automatic language detection |
| Input formats | WAV, OGG, MP3 | Audio bytes |

**Output:**
```json
{
  "text": "पानी बहुत तेज़ी से बढ़ रहा है",
  "language": "hi",
  "confidence": 0.87
}
```

### Why Whisper?

1. **Multilingual by default** — no separate model per language
2. **Handles accents and dialects** — trained on diverse audio
3. **Works offline** — model runs locally, no API calls
4. **Auto language detection** — no need to specify the language

---

## 11. Kalman Filter — Sensor Quality Assurance

**File:** `services/feature_engine/kalman_filter.py`

### What Is a Kalman Filter?

The Kalman Filter is a mathematical algorithm that estimates the true state of a system from noisy measurements. Invented in 1960 by Rudolf Kalman, it is used in everything from spacecraft navigation to smartphone GPS.

### Role in HYDRA

Real-world sensors are noisy. A river gauge might report 3.5m, then 3.8m, then 2.1m (a sensor glitch), then 3.6m. The Kalman Filter:
1. Smooths out normal noise
2. Detects anomalous readings (the 2.1m spike)
3. Imputes reasonable values when sensors malfunction
4. Estimates rate of change (how fast water is rising)

### How It Works

**State Vector:**
```
x = [water_level, rate_of_change]   (meters, meters/hour)
```

**Prediction Step (what we expect):**
```
F = [[1, dt],    # water_level = previous_level + rate × time
     [0,  1]]    # rate_of_change stays roughly the same

x_predicted = F × x_previous
P_predicted = F × P_previous × F^T + Q    (Q = process noise = 0.01)
```

**Update Step (when new measurement arrives):**
```
innovation = z_measured - H × x_predicted   (H = [1, 0] — we measure level, not rate)
S = H × P_predicted × H^T + R              (R = measurement noise = 0.5)
K = P_predicted × H^T / S                  (Kalman gain)

x_updated = x_predicted + K × innovation
P_updated = (I - K × H) × P_predicted
```

**Anomaly Detection (3-sigma rule):**
```
innovation_score = |innovation| / √S

if innovation_score > 3.0:
    REJECT measurement → use predicted value instead
    quality_flag = "KALMAN_IMPUTED"
else:
    ACCEPT measurement → normal Kalman update
    quality_flag = "GOOD"
```

**Per-Sensor Independence:**
Each sensor station maintains its own independent Kalman state. A faulty sensor in Mandi doesn't affect the filter for Majuli.

### Example

```
Time 10:00  Gauge reads 3.50m  → Kalman: 3.50m (GOOD)
Time 10:05  Gauge reads 3.55m  → Kalman: 3.54m (GOOD, smoothed)
Time 10:10  Gauge reads 2.10m  → Kalman: 3.58m (KALMAN_IMPUTED, rejected outlier)
Time 10:15  Gauge reads 3.62m  → Kalman: 3.61m (GOOD)
```

The 2.10m reading was a sensor glitch. Without the Kalman Filter, that reading would propagate through the pipeline, potentially causing a false "all clear" signal during actual flooding.

---

## 12. Adaptive Threshold Engine — Dynamic Alert Boundaries

**File:** `services/prediction/fast_track/threshold_engine.py`

### What Is It?

A dynamic threshold engine that adjusts alert levels based on real-time environmental conditions. Instead of fixed "alert at 0.72," the boundaries shift with the monsoon, soil moisture, and recent rainfall history.

### Why Not Fixed Thresholds?

A 60% flood probability during dry season is alarming. The same 60% during peak monsoon with dry soil is routine. Fixed thresholds either:
- Generate too many false alarms during monsoon (causing alert fatigue)
- Miss real threats during non-monsoon (when any flooding is unusual)

### How It Works

**Base Thresholds (NDMA standard):**
```
ADVISORY:   0.35
WATCH:      0.55
WARNING:    0.72
EMERGENCY:  0.88
Floor:      0.20  (never lower than this)
```

**Multiplicative Adjustments:**
```python
multiplier = 1.0

if soil_moisture_index > 0.8:       # Ground nearly saturated
    multiplier *= 0.85              # 15% lower thresholds
    reason += "saturated_soil"

if is_monsoon_season:               # June-September
    multiplier *= 0.90              # 10% lower thresholds
    reason += "monsoon_active"

if antecedent_moisture_index > 0.6: # Recent heavy rain
    multiplier *= 0.92              # 8% lower thresholds
    reason += "elevated_AMI"

adjusted = max(base × multiplier, 0.20)
```

**Example Scenarios:**

| Condition | ADVISORY | WATCH | WARNING | EMERGENCY |
|---|---|---|---|---|
| Dry season, dry soil | 0.35 | 0.55 | 0.72 | 0.88 |
| Monsoon, normal soil | 0.32 | 0.50 | 0.65 | 0.79 |
| Monsoon, wet soil | 0.27 | 0.42 | 0.55 | 0.67 |
| Monsoon, wet soil, high AMI | 0.25 | 0.39 | 0.51 | 0.62 |

This means during the worst monsoon conditions, an EMERGENCY alert can trigger at 62% probability instead of 88% — reflecting that conditions are already primed for catastrophic flooding.

---

## 13. Alert Classifier — Risk-to-Alert Mapping

**File:** `services/prediction/fast_track/alert_classifier.py`

### What Is It?

The Alert Classifier takes the XGBoost probability and the adaptive thresholds, and outputs an alert level plus a confidence band.

### Classification Logic

```
Given: probability = 0.68, thresholds = {advisory: 0.27, watch: 0.42, warning: 0.55, emergency: 0.67}

0.68 >= emergency (0.67) → AlertLevel.EMERGENCY
```

```
EMERGENCY:  probability >= threshold_emergency
WARNING:    probability >= threshold_warning
WATCH:      probability >= threshold_watch
ADVISORY:   probability >= threshold_advisory
NORMAL:     probability < threshold_advisory
```

### Confidence Bands

How confident are we that the alert level is correct? If the probability is close to a boundary, confidence is low.

```
margins = [|probability - boundary| for each boundary]
min_margin = min(margins)

HIGH:    min_margin >= 0.10  (clearly in one zone)
MEDIUM:  min_margin >= 0.04  (probably correct)
LOW:     min_margin < 0.04   (borderline — could flip any moment)
```

**Example:**
```
probability = 0.68, emergency_threshold = 0.67
margin = |0.68 - 0.67| = 0.01
→ Confidence: LOW (barely crossed into EMERGENCY)

probability = 0.85, emergency_threshold = 0.67
margin = |0.85 - 0.67| = 0.18
→ Confidence: HIGH (solidly EMERGENCY)
```

This prevents trigger-happy alerting when the model oscillates near a boundary.

---

## 14. Oracle v2 (MobileFloodFormer) — Edge Micro-Transformer

**File:** `services/oracle_v2/mobile_flood_former.py`
**Model File:** `models/oracle_v2_stub.pt`

### What Is It?

MobileFloodFormer is a tiny transformer model designed to run on a **Raspberry Pi** or smartphone. It brings flood prediction to the edge — no internet required.

### Why a Separate Model?

The main XGBoost + TFT pipeline requires a server with Python, libraries, and database access. In remote villages with no connectivity, a Raspberry Pi with the Oracle v2 can make local predictions from sensor data alone.

### Micro-Transformer Architecture

```
Input: 24-hour window × 6 features = (24, 6) tensor

Features:
  0: water_level_m
  1: rainfall_mm
  2: soil_moisture_pct
  3: rate_of_change (m/hr)
  4: hour_of_day (0-23)
  5: is_monsoon (0 or 1)

Architecture:
  ┌─ Input Projection: Linear(6, 32) ─┐
  │                                     │
  │  Positional Embedding (learned)    │
  │                                     │
  │  TransformerEncoder Layer 1 (4 heads, d=32, ff=64)
  │  TransformerEncoder Layer 2 (4 heads, d=32, ff=64)
  │                                     │
  │  Mean pooling over 24 timesteps    │
  │                                     │
  │  Risk head:  Linear(32, 1) → Sigmoid → risk_score [0,1]
  │  Alert head: Linear(32, 4) → Softmax → [NORMAL, ADVISORY, WARNING, EMERGENCY]
  └─────────────────────────────────────┘

Total Parameters: ~94,000 (compare: BERT = 110,000,000)
```

**Size Comparison:**
| Model | Parameters | Size |
|---|---|---|
| MobileFloodFormer | 94K | ~376 KB (fp32) |
| XGBoost (500 trees) | ~500K | ~2 MB |
| BERT-base | 110M | ~440 MB |
| TFT | ~5M | ~20 MB |

**Quantization for Raspberry Pi:**
```
fp32 (376 KB) → int8 quantization → <500 KB
Backend: QNNPACK (ARM Cortex-A76 optimized)
Latency target: <80ms on RPi5 CPU
Export: TorchScript (.pt), ONNX, TFLite
```

**Attention-Based Explainability:**
The transformer's attention weights reveal which of the 24 hours contributed most to the prediction. Top-5 contributing hours are returned alongside the risk score.

**Z-Score Normalization:**
```
MEANS = [3.2, 15.0, 55.0, 0.05, 12.0, 0.5]
STDS  = [2.1, 25.0, 20.0, 0.15,  6.9, 0.5]

normalized = (raw - MEANS) / STDS
```

---

## 15. Federated Learning — Privacy-Preserving Training

**File:** `services/federated_server/aggregator.py`

### What Is Federated Learning?

Federated Learning trains a shared ML model across multiple data holders (districts) without ever sharing raw data. Each district trains locally and only sends model weight updates (gradients) to the central server.

### Role in HYDRA

Different districts have different flood data. Traditionally, they'd need to share this sensitive data centrally. With federated learning:
- Majuli district trains on its local flood history
- Mandi district trains on its local flood history
- Neither shares raw data with the other
- Both benefit from a model trained on combined knowledge

### Algorithm: FedAvg with Differential Privacy

**Training Round:**
```
1. Central server sends global model weights to all districts
2. Each district trains locally on its own data for a few epochs
3. Each district sends weight updates (deltas) back to server
4. Server aggregates: new_weights = weighted_average(all deltas)
5. Repeat
```

**Differential Privacy (DP-SGD):**

To prevent even the gradients from leaking private data:

```python
# Step 1: Clip gradients (bound sensitivity)
if ||gradient|| > clip_norm:
    gradient = gradient × (clip_norm / ||gradient||)

# Step 2: Add calibrated noise
σ = √(2 × ln(1.25/δ)) / ε × clip_norm
noise = Normal(0, σ²)
dp_gradient = gradient + noise
```

**Privacy Parameters:**
| Parameter | Value | Meaning |
|---|---|---|
| `ε` (epsilon) | 1.0 | Privacy budget — lower = more private |
| `δ` (delta) | 1e-5 | Probability of privacy breach |
| `clip_norm` | 1.0 | Maximum gradient magnitude |

**FedAvg Aggregation:**
```
global_weights[layer] += Σ(client_delta[layer] × n_samples/total_samples) + dp_noise
```

**Demo Configuration:**
- 6 federated nodes (4 active, 1 offline, 1 syncing)
- Simulated client updates with noise_scale=0.01
- Privacy budget tracking across rounds

---

## 16. Model Summary Table

| Model | Type | Latency | Size | GPU? | Fallback | File |
|---|---|---|---|---|---|---|
| XGBoost | Gradient Boosting | <1ms | ~2MB | No | Rule-based heuristic | `xgboost_flood.joblib` |
| SHAP | Explainability | ~5ms | — | No | Weighted importance | Derived from XGBoost |
| TFT | Transformer | ~50ms | ~20MB | Preferred | Rising-limb physics | `tft_flood.ckpt` |
| PINN | Physics-NN | ~10ms | ~1MB | No | NumPy IDW | `pinn_beas_river.pt` |
| YOLOv11 | Object Detection | ~30ms | ~6MB | Preferred | Demo simulation | `yolo11n.pt` |
| SAM-2 | Segmentation | ~50ms | ~40MB | Preferred | YOLO bbox only | `sam2_tiny.pt` |
| Causal GNN | Graph NN | ~20ms | ~5MB | No | SEM topological | `causal_gnn_brahmaputra.pt` |
| PPO | Reinforcement Learning | ~100ms | ~3MB | No | Priority heuristic | `evac_ppo.zip` |
| IndicBERT | NLP | ~50ms | ~440MB | Preferred | Keyword matching | `indic_bert_flood_classifier/` |
| Whisper | ASR | ~2s/clip | ~290MB | Preferred | Empty fallback | OpenAI whisper-base |
| Kalman Filter | State Estimation | <0.1ms | — | No | None (always runs) | In-memory per sensor |
| Threshold Engine | Rule-based | <0.1ms | — | No | Static NDMA levels | Config-driven |
| Alert Classifier | Rule-based | <0.1ms | — | No | None | Config-driven |
| Oracle v2 | Micro-Transformer | <80ms | ~376KB | No (RPi) | None | `oracle_v2_stub.pt` |
| Fed Aggregator | FL Server | N/A | — | No | Weighted average | Server-side |

---

## 17. How All Models Work Together

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA ACQUISITION                            │
│                                                                     │
│  CWC Gauges ──→ Raw water level readings                           │
│  Open-Meteo ──→ Rainfall, temperature, humidity                    │
│  CCTV ──→ Video frames                                             │
│  IoT ──→ Soil moisture, rainfall, water level                     │
│  WhatsApp ──→ Voice notes + text messages                          │
│  Satellite ──→ Sentinel-2 / NASA Earthdata imagery                │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    QUALITY ASSURANCE                                │
│                                                                     │
│  [KALMAN FILTER] ── Smooths noise, detects anomalies, imputes     │
│                     bad readings, estimates rate of change          │
│                                                                     │
│  [YOLOv11 + SAM-2] ── Converts CCTV frames to virtual gauge       │
│                        readings (depth in meters)                   │
│                                                                     │
│  [Whisper] ── Converts voice notes to text for NLP analysis        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FEATURE ENGINEERING                              │
│                                                                     │
│  [PINN] ── Fills gaps between real gauges with physics-aware       │
│            virtual sensors (Saint-Venant equations)                 │
│                                                                     │
│  Feature Engine ── Rolling windows (1h/3h/6h/24h), spatial         │
│                    features, monsoon detection → 16 features       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PREDICTION (Triple Track)                       │
│                                                                     │
│  [XGBoost] ── Fast track: probability NOW (0.0-1.0) in <1ms       │
│       │                                                             │
│       ├──→ [SHAP] ── WHY this probability? Top 3 factors          │
│       │                                                             │
│       ├──→ [Threshold Engine] ── Adjust alert boundaries          │
│       │         │                 by monsoon/soil/AMI              │
│       │         └──→ [Alert Classifier] ── NORMAL/ADVISORY/       │
│       │                                    WATCH/WARNING/EMERGENCY │
│       │                                                             │
│  [TFT] ── Deep track: probability at +15/30/45/60/90/120 min     │
│            with uncertainty bands (p10/p50/p90)                    │
│                                                                     │
│  [Oracle v2] ── Edge track: same prediction on Raspberry Pi       │
│                 (94K params, <80ms, offline)                       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    CAUSAL UNDERSTANDING                            │
│                                                                     │
│  [Causal GNN] ── Decomposes risk into causal factors              │
│                  Answers "what if we open the dam?"                │
│                  Pearl's do-calculus for interventions              │
│                                                                     │
│  [IndicBERT] ── Classifies citizen flood reports (12 classes)     │
│                 Detects sentiment (CALM → PANIC)                   │
│                 Credibility scoring per report                     │
│                 Consensus: 3+ reports → inject alert               │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    DECISION SUPPORT                                │
│                                                                     │
│  [PPO] ── Optimal evacuation routing                              │
│           Vehicle → village → shelter assignment                   │
│           Handles road closures, capacity limits                   │
│                                                                     │
│  [Federated Learning] ── Improves all models over time            │
│                          without sharing private district data     │
└─────────────────────────────────────────────────────────────────────┘
```

### The 5-Second Prediction Path

When a new gauge reading arrives, here's what happens:

```
0ms    Kalman filter validates the reading
1ms    Feature engine updates rolling windows
2ms    XGBoost produces flood probability
3ms    SHAP explains the prediction
4ms    Threshold engine adjusts alert boundaries
5ms    Alert classifier determines: WATCH/WARNING/EMERGENCY
```

Total latency: **under 5 milliseconds** from data arrival to alert classification. The TFT deep track runs in parallel and updates the multi-horizon forecast within ~50ms.

---

*Every model is designed with graceful degradation — if SHAP fails, use heuristic weights. If TFT is unavailable, use physics-based hydrograph. If IndicBERT isn't loaded, use keyword matching. The system never stops working.*
