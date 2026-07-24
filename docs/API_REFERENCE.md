# ARGUS API Reference

> **Base URL (dev):** `http://localhost:8000` (API Gateway)
> **Base URL (direct):** `http://localhost:<port>` per service
> **Auth:** None required (demo mode). Production uses JWT Bearer tokens.
> **Content-Type:** `application/json` unless noted

---

## Table of Contents

- [API Gateway (8000)](#api-gateway-8000)
- [Ingestion Service (8001)](#ingestion-service-8001)
- [CV Gauging (8002)](#cv-gauging-8002)
- [Feature Engine (8003)](#feature-engine-8003)
- [Prediction Service (8004)](#prediction-service-8004)
- [Alert Dispatcher (8005)](#alert-dispatcher-8005)
- [ACN Node (8006)](#acn-node-8006)
- [Causal Engine (8006)](#causal-engine-8006)
- [CHORUS (8008)](#chorus-8008)
- [Federated Learning (8009)](#federated-learning-8009)
- [FloodLedger (8007)](#floodledger-8007)
- [Evacuation RL (8010)](#evacuation-rl-8010)
- [MIRROR (8011)](#mirror-8011)
- [ScarNet (8012)](#scarnet-8012)
- [Model Monitor (8013)](#model-monitor-8013)

---

## API Gateway (8000)

The gateway proxies all `/api/v1/*` routes to backend services and provides aggregated endpoints.

### `GET /health`

Aggregated health status of all 14 services.

**Response:**
```json
{
  "overall": "OPERATIONAL",
  "services": {
    "ingestion": { "status": "UP", "latency_ms": 12 },
    "prediction": { "status": "UP", "latency_ms": 45 }
  },
  "summary": "14/14 services UP",
  "checked_at": "2026-02-23T10:00:00Z"
}
```

### `GET /api/v1/dashboard/snapshot`

Cached aggregation of all dashboard data in a single call. TTL: 30s.

**Response:** Object containing `predictions`, `causal_risk`, `chorus_signals`, `recent_alerts`, `evacuation_plan`, `ledger_events`, `scarnet_latest`, `mirror_events`, `federated_status`, `model_drift`, `snapshot_at`, `services_queried`, `services_up`.

### `ANY /api/v1/{path}`

Reverse proxy — routes to the appropriate backend service based on path prefix.

| Prefix | Service |
|--------|---------|
| `/api/v1/ingest` | Ingestion |
| `/api/v1/virtual-gauge` | CV Gauging |
| `/api/v1/features` | Feature Engine |
| `/api/v1/predict`, `/api/v1/predictions`, `/api/v1/prediction` | Prediction |
| `/api/v1/alert`, `/api/v1/alerts` | Alert Dispatcher |
| `/api/v1/acn` | ACN Node |
| `/api/v1/causal` | Causal Engine |
| `/api/v1/chorus` | CHORUS |
| `/api/v1/fl`, `/api/v1/federated` | Federated Learning |
| `/api/v1/ledger` | FloodLedger |
| `/api/v1/evacuation` | Evacuation RL |
| `/api/v1/mirror` | MIRROR |
| `/api/v1/scarnet` | ScarNet |
| `/api/v1/monitor` | Model Monitor |

---

## Ingestion Service (8001)

Real-time sensor data ingestion from CWC, IMD, and manual sources.

### `GET /health`
Returns `{ "service": "ingestion", "status": "healthy" }`.

### `POST /api/v1/ingest`

Ingest a single sensor reading.

**Request:**
```json
{
  "station_id": "brahmaputra_neamatighat",
  "water_level_m": 8.2,
  "rainfall_mm_h": 45.0,
  "timestamp": "2026-02-23T10:00:00Z",
  "source": "cwc_api"
}
```

**Response:** `{ "status": "accepted", "reading_id": "..." }`

### `POST /api/v1/ingest/batch`

Ingest multiple readings at once.

### `GET /api/v1/ingest/stations`

List all registered monitoring stations.

---

## CV Gauging (8002)

Computer vision-based virtual river gauge using YOLO v11 + SAM2.

### `GET /health`

### `POST /api/v1/virtual-gauge/analyze`

Analyze a camera frame for water level estimation.

**Request:**
```json
{
  "camera_id": "kullu_bridge_01",
  "frame_b64": "<base64-encoded-jpeg>",
  "reference_markers": [
    { "pixel_y": 100, "real_height_m": 0.5 },
    { "pixel_y": 400, "real_height_m": 2.0 }
  ]
}
```

**Response:**
```json
{
  "water_level_m": 2.3,
  "velocity_estimate_ms": 4.2,
  "confidence": 0.942,
  "segmentation_mask_b64": "...",
  "detections": [
    { "class": "water_surface", "bbox": [10, 200, 600, 480], "confidence": 0.96 }
  ]
}
```

### `GET /api/v1/virtual-gauge/cameras`

List all registered CCTV cameras with calibration status.

### `POST /api/v1/virtual-gauge/demo`

Run CV gauging on the built-in demo video. Returns pre-computed results.

---

## Feature Engine (8003)

Temporal and spatial feature computation for prediction models.

### `GET /health`

### `GET /api/v1/features/latest`

Get the latest computed feature vector.

**Response:**
```json
{
  "station_id": "brahmaputra_upper",
  "features": {
    "rainfall_1h_mean": 42.5,
    "rainfall_3h_max": 78.2,
    "water_level_trend_6h": 0.15,
    "soil_moisture_index": 0.82,
    "upstream_flow_rate": 1250.0
  },
  "computed_at": "2026-02-23T10:00:00Z"
}
```

### `GET /api/v1/features/history/{station_id}`

Historical feature vectors for a station.

---

## Prediction Service (8004)

Multi-horizon flood prediction using XGBoost + TFT + PINN.

### `GET /health`

### `GET /api/v1/predict/{basin_id}`

Generate flood predictions for a basin.

**Response:**
```json
{
  "basin_id": "brahmaputra_upper",
  "predictions": [
    { "horizon_h": 1, "flood_probability": 0.23, "water_level_m": 6.8 },
    { "horizon_h": 3, "flood_probability": 0.67, "water_level_m": 8.1 },
    { "horizon_h": 6, "flood_probability": 0.89, "water_level_m": 9.4 }
  ],
  "model": "xgboost_v2",
  "shap_drivers": [
    { "feature": "rainfall_3h_cumulative", "importance": 0.34 },
    { "feature": "upstream_discharge", "importance": 0.28 }
  ],
  "predicted_at": "2026-02-23T10:00:00Z"
}
```

### `GET /api/v1/predictions/all`

All current predictions across all basins.

### `GET /api/v1/prediction/shap/{basin_id}`

SHAP explainability values for the latest prediction.

---

## Alert Dispatcher (8005)

Multi-channel alert distribution (SMS, siren, voice, cell broadcast).

### `GET /health`

### `POST /api/v1/alert/dispatch`

Dispatch an alert to all configured channels.

**Request:**
```json
{
  "basin_id": "brahmaputra_upper",
  "severity": "SEVERE",
  "message": "Flood warning: water level expected to reach 9.4m in 6 hours",
  "channels": ["sms", "siren", "voice", "cell_broadcast"]
}
```

### `GET /api/v1/alert/log`

Recent alert history.

### `GET /api/v1/alerts/active`

Currently active alerts.

---

## ACN Node (8006)

Autonomous Crisis Node — offline-capable edge AI for village-level warning.

### `GET /health`

### `GET /api/v1/acn/status`

Current ACN network status (online/offline nodes).

### `POST /api/v1/acn/oracle/predict`

Run local ORACLE prediction model (works offline).

### `POST /api/v1/acn/siren/trigger`

Trigger village siren. Works without internet connectivity.

### `GET /api/v1/acn/mesh/topology`

Current mesh network topology and node health.

---

## Causal Engine (8006)

GNN-based causal inference engine with do-calculus intervention support.

### `GET /health`

### `GET /api/v1/causal/risk/{basin_id}`

Get current causal risk assessment for a basin.

**Response:**
```json
{
  "basin_id": "brahmaputra_upper",
  "risk_score": 0.78,
  "causal_factors": [
    { "variable": "upstream_rainfall", "effect": 0.42 },
    { "variable": "soil_saturation", "effect": 0.23 },
    { "variable": "dam_release_rate", "effect": 0.13 }
  ],
  "dag_nodes": 12,
  "computed_at": "2026-02-23T10:00:00Z"
}
```

### `POST /api/v1/causal/intervene`

Run a do-calculus intervention query.

**Request:**
```json
{
  "basin_id": "brahmaputra_upper",
  "intervention": {
    "variable": "dam_pandoh_gate",
    "value": 0.25,
    "description": "Open dam gate to 25%"
  }
}
```

**Response:**
```json
{
  "original_prediction": { "depth_m": 4.7, "damage_pct": 52 },
  "intervened_prediction": { "depth_m": 3.1, "damage_pct": 18 },
  "effect": { "depth_reduction_m": 1.6, "damage_reduction_pct": 34 },
  "confidence": 0.87,
  "method": "do-calculus (Pearl)"
}
```

### `GET /api/v1/causal/dag`

Return the causal DAG structure.

---

## CHORUS (8008)

Community Human-Observable Report & Unified Signal — multilingual NLP.

### `GET /health`

### `POST /api/v1/chorus/report`

Submit a community flood report (text or voice).

**Request:**
```json
{
  "reporter_id": "villager_001",
  "text": "Paani bahut badh gaya hai",
  "language": "hi",
  "lat": 26.95,
  "lon": 94.17
}
```

### `GET /api/v1/chorus/stats`

Aggregated signal statistics.

### `GET /api/v1/chorus/signals`

Recent validated community signals.

### `GET /api/v1/chorus/demo/generate`

Generate synthetic demo reports. Query params: `village_id`, `count`.

### `WS ws://localhost:8008/ws/signals`

WebSocket stream of real-time community signals.

---

## Federated Learning (8009)

Privacy-preserving federated model training across states.

### `GET /health`

### `GET /api/v1/fl/status`

Current federated learning round status.

**Response:**
```json
{
  "current_round": 7,
  "total_rounds": 10,
  "active_clients": 3,
  "global_accuracy": 0.924,
  "dp_epsilon": 1.0,
  "aggregation": "fedavg"
}
```

### `POST /api/v1/fl/start`

Start a new federated training round.

### `GET /api/v1/fl/metrics`

Per-round training metrics history.

---

## FloodLedger (8007)

Blockchain-based parametric flood insurance with smart contracts.

### `GET /health`

### `GET /api/v1/ledger/chain/summary`

Blockchain summary (blocks, transactions, hash).

### `GET /api/v1/ledger/chain`

Full chain data.

### `GET /api/v1/ledger/events`

Recent flood events recorded on chain.

### `POST /api/v1/ledger/verify`

Verify chain integrity.

### `GET /api/v1/ledger/demo/flood`

Trigger a demo parametric insurance payout. Query param: `village_id`.

**Response:**
```json
{
  "event_id": "flood_2026_brahmaputra_001",
  "satellite_confirmed": true,
  "smart_contract_triggered": true,
  "payout_amount_inr": 1470000,
  "beneficiaries": 340,
  "tx_hash": "0xabc123...",
  "processing_time_s": 2.3
}
```

---

## Evacuation RL (8010)

Reinforcement learning-based evacuation planning and route optimization.

### `GET /health`

### `GET /api/v1/evacuation/plan/{scenario_id}`

Get pre-computed evacuation plan.

**Response:**
```json
{
  "scenario_id": "majuli_2024",
  "zones": [
    {
      "zone_id": "ward_7",
      "population": 2340,
      "risk_score": 0.92,
      "vehicles": [
        { "id": "AS-01", "type": "bus", "capacity": 45, "route": "NH-715 → SH-23" }
      ],
      "shelter": { "name": "Jorhat Hall", "capacity": 400, "filled": 0 },
      "depart_by": "02:45 UTC",
      "route_closes": "03:12 UTC"
    }
  ],
  "total_evacuees": 2340,
  "eta_minutes": 78
}
```

### `POST /api/v1/evacuation/compute`

Compute a new evacuation plan in real-time.

### `GET /api/v1/evacuation/notifications`

Active evacuation notifications.

### `POST /api/v1/evacuation/demo`

Generate demo evacuation scenario.

---

## MIRROR (8011)

Counterfactual replay engine — "what if we had acted differently?"

### `GET /health`

### `GET /api/v1/mirror/events`

List available historical events for replay.

### `GET /api/v1/mirror/event/{event_id}/counterfactuals`

Get pre-computed counterfactual analyses.

**Response:**
```json
{
  "event_id": "himachal_2023_aug",
  "actual_deaths": 71,
  "counterfactuals": [
    {
      "scenario": "argus_78min_warning",
      "deaths_prevented": 44,
      "survivors": 44,
      "key_intervention": "Early dam gate adjustment + 78min evacuation window"
    }
  ],
  "timeline_steps": 48
}
```

### `POST /api/v1/mirror/event/{event_id}/custom`

Run a custom counterfactual scenario.

**Request:**
```json
{
  "interventions": {
    "warning_lead_time_min": 90,
    "dam_release_pct": 0.25,
    "evacuation_started": true
  }
}
```

### `GET /api/v1/mirror/event/{event_id}/report`

Full counterfactual analysis report.

---

## ScarNet (8012)

Satellite terrain change detection using Sentinel-2 imagery.

### `GET /health`

### `GET /api/v1/scarnet/latest`

Latest terrain change detection results.

**Response:**
```json
{
  "scan_id": "scan_001",
  "region": "beas_valley",
  "changes_detected": [
    {
      "type": "deforestation",
      "area_km2": 2.3,
      "confidence": 0.91,
      "risk_impact": "moderate",
      "coordinates": [32.27, 77.17]
    }
  ],
  "terrain_health_score": 0.72,
  "scanned_at": "2026-02-23T10:00:00Z"
}
```

### `POST /api/v1/scarnet/trigger-demo`

Trigger a demo terrain scan with synthetic data.

### `GET /api/v1/scarnet/history/{scan_id}`

Historical scan results.

### `GET /api/v1/scarnet/tiles/before`
### `GET /api/v1/scarnet/tiles/after`

Sentinel-2 tile images (before/after change).

### `GET /api/v1/scarnet/risk-delta/{region_id}`

Risk score change due to terrain changes.

---

## Model Monitor (8013)

ML model health monitoring — drift detection, accuracy tracking, auto-retrain.

### `GET /health`

### `GET /api/v1/monitor/drift-report`

Current model drift report.

**Response:**
```json
{
  "model_name": "xgboost_flood_v2",
  "drift_detected": false,
  "metrics": {
    "psi_score": 0.08,
    "ks_statistic": 0.12,
    "wasserstein_distance": 0.05
  },
  "threshold": 0.3,
  "recommendation": "No action needed",
  "checked_at": "2026-02-23T10:00:00Z"
}
```

### `GET /api/v1/monitor/accuracy-history`

Historical model accuracy scores.

### `POST /api/v1/monitor/retrain`

Trigger model retraining (manual or automatic when drift > threshold).

**Response:**
```json
{
  "retrain_id": "retrain_001",
  "status": "completed",
  "previous_accuracy": 0.891,
  "new_accuracy": 0.934,
  "improvement_pct": 4.8,
  "duration_s": 12.3
}
```

### `GET /api/v1/monitor/health`

Model monitor service health with drift summary.

---

## Common Response Patterns

### Health Check (all services)
```
GET /<service>/health → { "service": "<name>", "status": "healthy", "uptime_s": 1234 }
```

### Error Responses
```json
{
  "error": "Description of the error",
  "detail": "Additional context",
  "status_code": 400
}
```

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad request |
| 404 | Not found / No service handles path |
| 502 | Backend service unreachable |
| 504 | Backend service timeout |

---

## Rate Limits

In demo mode, no rate limits apply. Production configuration:

| Endpoint Type | Limit |
|---------------|-------|
| Health checks | 60/min |
| Read endpoints | 120/min |
| Write/compute | 30/min |
| WebSocket | 5 concurrent |

---

## Environment Variables

All services respect `DEMO_MODE=true` (default) for pre-computed synthetic responses.
See `.env.example` for the full list of configuration variables.
