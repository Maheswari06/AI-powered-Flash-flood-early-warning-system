# HYDRA / ARGUS — Complete Project Documentation

## Flash Flood Early Warning System for South Asian River Basins

**Version**: 3.0.0
**Basins Covered**: Beas (Himachal Pradesh), Brahmaputra (Assam)
**Villages Monitored**: 12 (7 HP + 5 Assam)
**Services**: 29 microservices + React dashboard + PWA mobile app

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Tech Stack](#3-tech-stack)
4. [Directory Structure](#4-directory-structure)
5. [Microservices (Backend)](#5-microservices-backend)
6. [Dashboard (Frontend)](#6-dashboard-frontend)
7. [Data Flow & Control Flow](#7-data-flow--control-flow)
8. [ML Models & AI Pipeline](#8-ml-models--ai-pipeline)
9. [External APIs & Data Sources](#9-external-apis--data-sources)
10. [Infrastructure](#10-infrastructure)
11. [Security Layer](#11-security-layer)
12. [Shared Modules](#12-shared-modules)
13. [Integrations](#13-integrations)
14. [Mobile PWA](#14-mobile-pwa)
15. [Platform SDK](#15-platform-sdk)
16. [Demo Mode](#16-demo-mode)
17. [Deployment & Running](#17-deployment--running)
18. [Environment Variables](#18-environment-variables)

---

## 1. Project Overview

**HYDRA (Hydrological Decision-support for Risk Assessment)** is a full-stack flash flood early warning system. The core intelligence engine is called **ARGUS (Adaptive Risk Gauging & Unified Surveillance)**.

### What It Does

ARGUS ingests real-time data from multiple sources — river gauges (CWC), weather stations (IMD/Open-Meteo), CCTV cameras, IoT sensors, and satellite imagery (NASA Earthdata/Sentinel-2) — and runs a multi-track AI prediction pipeline to generate flood risk scores for each monitored village. When risk thresholds are breached, it dispatches alerts via WhatsApp, SMS, cell broadcast, and push notifications to field officers, district administrators, and affected communities.

### Key Capabilities

- **Real-time multi-source ingestion** — CWC river gauges, IMD weather, CCTV, IoT, satellite
- **Explainable AI** — SHAP per-feature explanation + causal DAG visualization
- **Physics-aware prediction** — PINN virtual sensors enforce conservation laws
- **Triple-track prediction** — XGBoost (fast), TFT Temporal Fusion Transformer (deep), Oracle v2
- **Citizen participation** — CHORUS WhatsApp-based community intelligence with consensus
- **RL evacuation routing** — PPO multi-agent shelter assignment and vehicle routing
- **Counterfactual replay** — MIRROR: "what if we opened the dam gates 2 hours earlier?"
- **Blockchain insurance** — FloodLedger parametric claim auto-triggers
- **Federated learning** — Privacy-preserving cross-district model training
- **Multilingual NLP** — IndicBERT for Hindi/Bengali/Assamese flood reports
- **Cell broadcast** — CAP v1.2 XML for India's CBEAS (reaches all phones in an area)
- **Offline-first PWA** — Field officers can work without connectivity
- **Satellite monitoring** — ScarNet terrain change detection (deforestation, slope failure)
- **NDMA compliance** — GREEN/YELLOW/ORANGE/RED framework with SOP 4.2 lead times
- **Developer SDK** — Deploy to any river basin in ~10 lines of code

---

## 2. System Architecture

```
                    ┌────────────────────────────────────────────┐
                    │              DATA SOURCES                  │
                    ├────────────────────────────────────────────┤
                    │  CWC WRIS    IMD/Open-Meteo   CCTV Feeds  │
                    │  IoT Sensors  NASA Earthdata  Sentinel-2   │
                    │  CHORUS (WhatsApp citizen reports)          │
                    └──────────────────┬─────────────────────────┘
                                       │
                                       ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                    INGESTION LAYER                           │
    │  ┌──────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐ │
    │  │Ingestion │  │CV Gauging │  │IoT Gateway│  │Data       │ │
    │  │  :8001   │  │  :8002    │  │  :8020    │  │Connectors │ │
    │  │CWC+IMD   │  │YOLO+SAM  │  │MQTT→Kafka │  │  :8022    │ │
    │  └────┬─────┘  └────┬─────┘  └────┬──────┘  └────┬──────┘ │
    └───────┼──────────────┼──────────────┼──────────────┼────────┘
            │              │              │              │
            ▼              ▼              ▼              ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                     APACHE KAFKA                            │
    │  gauge.realtime | weather.api.imd | cctv.frames.*          │
    │  virtual.gauge.* | iot.* | features.vector.*               │
    │  predictions.fast.* | alerts.dispatch | chorus.signal.*     │
    └──────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                  PROCESSING LAYER                            │
    │  ┌──────────────┐   ┌──────────────┐   ┌─────────────────┐ │
    │  │Feature Engine│   │  Prediction  │   │ Causal Engine   │ │
    │  │    :8003     │   │    :8004     │   │    :8006        │ │
    │  │Kalman+PINN   │   │XGBoost+TFT  │   │do-calculus+GNN  │ │
    │  │TimescaleDB   │   │SHAP+Adaptive │   │Interventions    │ │
    │  └──────┬───────┘   └──────┬───────┘   └──────┬──────────┘ │
    └─────────┼──────────────────┼──────────────────┼─────────────┘
              │                  │                  │
              ▼                  ▼                  ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                  ACTION LAYER                                │
    │  ┌─────────────┐ ┌──────────┐ ┌────────┐ ┌──────────────┐  │
    │  │Alert        │ │Evacuation│ │MIRROR  │ │FloodLedger   │  │
    │  │Dispatcher   │ │RL :8010  │ │:8011   │ │:8007         │  │
    │  │:8005        │ │PPO Agent │ │Counter-│ │Blockchain    │  │
    │  │Twilio+Cell  │ │Routing   │ │factual │ │Insurance     │  │
    │  └──────┬──────┘ └────┬─────┘ └───┬────┘ └──────┬───────┘  │
    └─────────┼─────────────┼───────────┼─────────────┼───────────┘
              │             │           │             │
              ▼             ▼           ▼             ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                  DELIVERY LAYER                              │
    │  ┌────────────────┐  ┌─────────────┐  ┌──────────────────┐  │
    │  │Notification Hub│  │API Gateway  │  │ARGUS Copilot     │  │
    │  │:8014           │  │:8000        │  │:8016 (LLM Chat)  │  │
    │  │WebPush + SSE   │  │Routing+Cache│  │Explainability    │  │
    │  └───────┬────────┘  └──────┬──────┘  └──────┬───────────┘  │
    └──────────┼──────────────────┼────────────────┼──────────────┘
               │                  │                │
               ▼                  ▼                ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                  PRESENTATION LAYER                          │
    │  ┌─────────────────────────┐  ┌────────────────────────┐    │
    │  │  React Dashboard :3000  │  │  PWA Mobile App        │    │
    │  │  12 Tabs + Copilot      │  │  Field Officers        │    │
    │  │  Leaflet Map + Charts   │  │  Offline-First         │    │
    │  └─────────────────────────┘  └────────────────────────┘    │
    └──────────────────────────────────────────────────────────────┘
```

---

## 3. Tech Stack

### Backend
| Technology | Purpose |
|---|---|
| **Python 3.11+** | All microservices |
| **FastAPI** | REST API framework for all 29 services |
| **uvicorn** | ASGI server |
| **Apache Kafka** | Event streaming / message broker |
| **TimescaleDB** | Time-series storage (PostgreSQL extension) |
| **Redis** | Prediction cache, trust scores, pub/sub |
| **structlog** | Structured JSON logging |
| **Pydantic** | Data validation and serialization |

### Frontend
| Technology | Purpose |
|---|---|
| **React 18.3** | UI framework |
| **Vite 6.0** | Build tool + dev server with HMR |
| **Tailwind CSS 4.0** | Utility-first styling |
| **Leaflet 1.9.4** | Interactive maps (OSM tiles) |
| **react-leaflet 4.2.1** | React wrapper for Leaflet |
| **Recharts 2.15** | Charts (intervention sliders, curves) |
| **Axios 1.7** | HTTP client |
| **deck.gl 9.x** | GPU-accelerated map visualizations |

### ML / AI
| Technology | Purpose |
|---|---|
| **XGBoost** | Fast-track flood probability prediction |
| **SHAP** | Explainability — per-feature contribution |
| **TFT (Temporal Fusion Transformer)** | Deep-track multi-horizon forecasting |
| **PINN (Physics-Informed Neural Network)** | Virtual sensor mesh, conservation laws |
| **YOLOv11** | Water detection in CCTV frames |
| **SAM-2 (Segment Anything)** | Precise water segmentation for depth |
| **Causal GNN** | Graph neural network for causal inference |
| **PPO (Proximal Policy Optimization)** | RL evacuation routing |
| **IndicBERT** | Multilingual NLP for citizen reports |
| **Whisper** | Voice transcription for CHORUS |
| **Kalman Filter** | Feature quality assurance |

### Infrastructure
| Technology | Purpose |
|---|---|
| **Docker + Docker Compose** | Container orchestration |
| **Zookeeper** | Kafka broker coordination |
| **Prometheus** | Metrics collection |
| **Grafana** | Monitoring dashboards |
| **MLflow** | ML experiment tracking |
| **Hardhat** | Local Ethereum node (FloodLedger) |
| **nginx** | Production reverse proxy |

---

## 4. Directory Structure

```
/workspaces/HYDRA/
├── .env / .env.example            # Environment configuration
├── docker-compose.yml             # Full infrastructure (25+ services)
├── requirements.txt               # Python dependencies
│
├── dashboard/                     # React/Vite frontend (port 3000)
│   ├── src/
│   │   ├── App.jsx                # Root component, tab routing
│   │   ├── components/            # 21 UI components
│   │   ├── hooks/                 # 9 custom data-fetching hooks
│   │   ├── config/                # API endpoints, demo moments
│   │   ├── data/                  # Static village data
│   │   └── utils/                 # Color scale utilities
│   ├── vite.config.js             # Dev proxy (15+ routes)
│   ├── package.json               # Dependencies
│   └── Dockerfile                 # Multi-stage nginx build
│
├── services/                      # 29 Python microservices
│   ├── api_gateway/               # Central routing (port 8000)
│   ├── ingestion/                 # CWC/IMD/CCTV data (port 8001)
│   ├── cv_gauging/                # YOLO+SAM vision (port 8002)
│   ├── feature_engine/            # Temporal features (port 8003)
│   ├── prediction/                # XGBoost+TFT (port 8004)
│   ├── alert_dispatcher/          # Twilio alerts (port 8005)
│   ├── causal_engine/             # do-calculus (port 8006)
│   ├── flood_ledger/              # Blockchain (port 8007)
│   ├── chorus/                    # Community intel (port 8008)
│   ├── federated_server/          # FL training (port 8009)
│   ├── evacuation_rl/             # PPO routing (port 8010)
│   ├── mirror/                    # Counterfactuals (port 8011)
│   ├── scarnet/                   # Satellite (port 8012)
│   ├── model_monitor/             # Drift detection (port 8013)
│   ├── notification_hub/          # Push/SSE (port 8014)
│   ├── multi_basin/               # Cross-basin (port 8015)
│   ├── copilot/                   # LLM chat (port 8016)
│   ├── drone_stream/              # Drone feeds (port 8017)
│   ├── displacement_tracker/      # Displaced pop. (port 8018)
│   ├── ndma_compliance/           # NDMA checks (port 8019)
│   ├── iot_gateway/               # MQTT bridge (port 8020)
│   ├── flash_flood_engine/        # Urban flash (port 8021)
│   ├── data_connectors/           # CWC/IMD API (port 8022)
│   ├── climate_finance/           # World Bank (port 8023)
│   ├── oracle_v2/                 # Enhanced oracle (port 8024)
│   └── acn_node/                  # Mesh network (port 8006)
│
├── shared/                        # Shared Python modules
│   ├── config.py                  # 150+ env vars, Settings class
│   ├── kafka_client.py            # Kafka producer/consumer wrappers
│   ├── models/                    # Pydantic schemas (ingestion, prediction, phase2)
│   └── causal_dag/                # Causal DAG JSON definitions
│
├── integrations/                  # External system integrations
│   └── cell_broadcast/            # CAP v1.2 XML for CBEAS
│
├── security/                      # Auth & audit
│   ├── auth/                      # OAuth2 + JWT + RBAC middleware
│   └── audit/                     # Chained-hash immutable audit log
│
├── platform/                      # SDK & developer tools
│   ├── argus_sdk/                 # pip-installable SDK
│   ├── developer_portal/          # Basin deployment UI
│   └── plugin_registry/           # Custom plugin system
│
├── mobile/pwa/                    # React PWA for field officers
├── models/                        # ML model checkpoints
├── data/                          # Historical data, configs, tiles
├── global/                        # Cross-border basin adapters
├── training/                      # Model training pipelines
├── research/                      # Benchmarks (ARGUS vs FFGS)
├── infra/                         # Prometheus, Grafana, K8s, nginx
├── tests/                         # Integration & load tests
└── notebooks/                     # Jupyter analysis notebooks
```

---

## 5. Microservices (Backend)

### Phase 1 — Core Pipeline

#### Ingestion Service (port 8001)
- **Purpose**: Ingest real-time data from CWC gauges, IMD weather, CCTV frames, IoT sensors
- **Endpoints**: `POST /api/v1/ingest/gauge`, `/api/v1/ingest/weather`, `/api/v1/ingest/cctv-frame`
- **Output**: Publishes to Kafka topics `gauge.realtime`, `weather.api.imd`, `cctv.frames.*`
- **Data Sources**: CWC WRIS API (river levels), Open-Meteo (rainfall/temperature), CCTV video streams

#### CV Gauging Service (port 8002)
- **Purpose**: Computer vision water level estimation from CCTV feeds
- **Models**: YOLOv11 (water detection) + SAM-2 (segmentation)
- **Pipeline**: Frame → YOLO detection → SAM segmentation → Pixel-to-meter conversion → Virtual gauge reading
- **Endpoints**: `POST /api/v1/virtual-gauge/process`, `GET /api/v1/virtual-gauge/latest`
- **Output**: Publishes `virtual.gauge.*` to Kafka

#### Feature Engine (port 8003)
- **Purpose**: Transform raw data into ML-ready feature vectors
- **Processing**:
  - Temporal rolling windows (1h, 3h, 6h, 24h) for level, rainfall, rate of change
  - Kalman filter for quality assurance and outlier detection
  - PINN mesh for virtual sensor interpolation
  - Spatial features: upstream risk, basin connectivity score
- **Storage**: Writes enriched features to TimescaleDB
- **Output**: Publishes `features.vector.*` to Kafka
- **Endpoints**: `GET /api/v1/features/{station_id}/latest`, `GET /api/v1/pinn/virtual-sensors`

#### Prediction Service (port 8004)
- **Purpose**: Generate flood risk scores for each village
- **Triple-track pipeline**:
  1. **Fast track (XGBoost)**: Instant flood probability (0.0–1.0) + SHAP explanation
  2. **Deep track (TFT)**: Multi-horizon quantile forecasting (15, 30, 60, 120, 180 min)
  3. **Adaptive thresholds**: Adjusted by monsoon season, soil moisture, antecedent moisture index
- **Alert Classification**: NORMAL → ADVISORY → WATCH → WARNING → EMERGENCY with confidence bands
- **Endpoints**:
  - `GET /api/v1/predictions/all` — All village predictions (dashboard map)
  - `GET /api/v1/prediction/{village_id}` — Single village prediction
  - `GET /api/v1/prediction/{village_id}/deep` — TFT multi-horizon forecast
  - `GET /api/v1/model/info` — Model metadata
- **Caching**: Redis (TTL 300s) + in-memory cache

#### Alert Dispatcher (port 8005)
- **Purpose**: Send multi-channel alerts when risk thresholds are breached
- **Channels**: Twilio WhatsApp, SMS, IVRS, Cell Broadcast
- **Logic**: 15-minute cooldown per village, escalating severity
- **Endpoints**: `GET /api/v1/alert/log`, `GET /api/v1/alert/stats`, `POST /api/v1/alert/send`
- **Demo Mode**: Seeds 7 progressive alerts (ADVISORY → EMERGENCY)

#### API Gateway (port 8000)
- **Purpose**: Central routing, response caching, rate limiting
- **Endpoints**: `GET /api/v1/dashboard/snapshot` (aggregated system state), `/api/v1/health/*`
- **Caching**: In-memory with configurable TTL

### Phase 2 — Intelligence Layer

#### Causal Engine (port 8006)
- **Purpose**: Judea Pearl's do-calculus for causal flood risk decomposition
- **Models**: Causal GNN trained on DAG structure
- **Capabilities**: "What happens to Majuli flood depth if we open Pandoh dam gates 50%?"
- **Endpoints**: `GET /api/v1/causal/{village_id}`, `POST /api/v1/causal/intervene`
- **DAG**: Defined in `shared/causal_dag/beas_brahmaputra_v1.json`

#### MIRROR Service (port 8011)
- **Purpose**: Counterfactual event replay
- **Standard Counterfactuals**:
  1. 2-hour earlier dam release
  2. Road closure pre-event
  3. Drought preparedness scenario
  4. Earlier harvest instruction
- **Endpoints**: `GET /api/v1/mirror/counterfactual/{event_id}`, `POST /api/v1/mirror/custom`
- **Output**: Lives saved, depth reduction, economic savings per scenario

#### CHORUS Service (port 8008)
- **Purpose**: Community-sourced intelligence aggregation
- **Pipeline**: WhatsApp message → Whisper ASR (voice) → IndicBERT classification → Geohash aggregation → Consensus (3+ reports)
- **Languages**: Hindi, Bengali, Assamese, English
- **Trust scoring**: Signal credibility based on source history
- **Endpoints**: `GET /api/v1/chorus/signals`, `GET /api/v1/chorus/consensus`

#### FloodLedger (port 8007)
- **Purpose**: Blockchain-anchored parametric insurance oracle
- **How it works**: When prediction breaches threshold → smart contract auto-triggers insurance payout
- **Runtime**: Local Hardhat Ethereum node
- **Endpoints**: `GET /api/v1/ledger/summary`, `GET /api/v1/ledger/chain`, `GET /api/v1/ledger/verify`

#### Evacuation RL (port 8010)
- **Purpose**: PPO-based multi-agent evacuation choreography
- **Optimizes**: Vehicle-to-village assignment, route selection, shelter capacity
- **Vehicle types**: Bus, truck, boat, helicopter
- **Endpoints**: `GET /api/v1/evacuation/plan/{scenario_id}`, `POST /api/v1/evacuation/compute`

### Phase 3+ — Advanced Services

#### ScarNet (port 8012)
- **Purpose**: Satellite terrain monitoring using NASA Earthdata / Sentinel-2
- **Detects**: Deforestation, slope failure, riverbed migration, urban encroachment
- **Endpoints**: `GET /api/v1/scarnet/latest`, `POST /api/v1/scarnet/trigger`

#### Model Monitor (port 8013)
- **Purpose**: Drift detection, accuracy tracking, automated retraining triggers
- **Endpoints**: `GET /api/v1/monitor/drift`, `POST /api/v1/monitor/retrain`

#### Federated Server (port 8009)
- **Purpose**: Train models across districts without sharing raw data
- **Algorithm**: DP-SGD (Differential Privacy)
- **Endpoints**: `GET /api/v1/fl/status`

#### ARGUS Copilot (port 8016)
- **Purpose**: LLM-powered natural language interface for the system
- **Capabilities**: Explain why an alert was triggered, suggest interventions, answer queries
- **Endpoints**: `POST /api/v1/copilot/chat`

#### Notification Hub (port 8014)
- **Purpose**: Web Push notifications + SSE for real-time dashboard streaming
- **Endpoints**: `POST /api/v1/notifications/subscribe`, `GET /api/v1/notifications/stream` (SSE)

---

## 6. Dashboard (Frontend)

### Architecture
- **Framework**: React 18.3 with functional components and hooks
- **Build**: Vite 6.0 with HMR and Tailwind CSS 4.0
- **Routing**: Tab-based navigation (12 tabs), no React Router
- **State**: useState hooks (no Redux/Context — intentionally simple)
- **API Layer**: 15+ Vite proxy rules route `/api/v1/*` to respective backend ports

### Component Tree

```
App.jsx
├── MetricsBar              # Top bar: sensors, villages, alerts, max risk, demo toggle
├── Tab Navigation          # 12 tabs with keyboard shortcuts (Alt+1-9, 0)
├── Main Content Area
│   ├── GaugeHeroPanel      # River gauges + soil moisture (default: Gauges tab)
│   ├── ARGUSMap            # Leaflet risk map with village markers (Risk Map tab)
│   │   ├── RiskLegend      # Bottom-left color scale legend
│   │   ├── ACNStatus       # Bottom-right ACN node status
│   │   └── VillagePopup    # Click popup with SHAP bars + risk gauge
│   ├── NDMACompliancePanel # NDMA color-code mapping + lead times
│   ├── DroneMapPanel       # Live drone feed overlay
│   ├── EvacuationMap       # RL route visualization + shelter cards
│   ├── DisplacementMap     # Post-event displacement tracking
│   ├── LiveValidationPanel # Predicted vs observed comparison
│   ├── MirrorPanel         # Counterfactual analysis + intervention slider
│   ├── FloodLedger         # Blockchain audit + insurance payouts
│   ├── ChorusActivity      # Community signal feed + sentiment
│   ├── ScarNetPanel        # Before/after satellite comparison
│   └── DemoController      # Presenter backstage with 8 moments
├── AlertSidebar            # Right sidebar: scrolling alert log
├── ARGUSCopilot            # Floating LLM chat widget
└── PresentationMode        # Fullscreen F11 overlay for judges
```

### Custom Hooks (9)

| Hook | API Endpoint | Polling | Purpose |
|---|---|---|---|
| `usePredictions` | `/api/v1/predictions/all` | 5-30s | Village risk scores |
| `useAlertLog` | `/api/v1/alert/log` | 5-10s | Alert history |
| `useSSEUpdates` | SSE stream | Real-time | Live prediction stream |
| `useCausalRisk` | `/api/v1/causal/{id}` | On-demand | Causal decomposition |
| `useEvacuationPlan` | `/api/v1/evacuation/plan` | On-demand | RL evacuation routes |
| `useMirrorData` | `/api/v1/mirror/counterfactual` | On-demand | Counterfactual analysis |
| `useChorusSignals` | `/api/v1/chorus/signals` | 8-30s | Community reports |
| `useLedger` | `/api/v1/ledger/*` | On-demand | Blockchain data |
| `useFederatedStatus` | `/api/v1/fl/status` | 15-60s | FL training progress |

### Key Frontend Files

| File | Purpose |
|---|---|
| `src/App.jsx` | Root component, tab state, demo mode, presentation mode |
| `src/config/api.js` | All API endpoint definitions (50+ endpoints) |
| `src/config/moments.js` | 8 demo presentation moments |
| `src/data/villages.js` | 12 villages with coordinates and metadata |
| `src/utils/colorScale.js` | Risk score → color mapping (green-yellow-orange-red) |
| `src/components/map/LeafletConfig.js` | Tile URLs, icon config |
| `vite.config.js` | 15+ proxy rules for microservice routing |

### Vite Proxy Rules

| Route | Target | Service |
|---|---|---|
| `/api/v1/ingest` | localhost:8001 | Ingestion |
| `/api/v1/virtual-gauge` | localhost:8002 | CV Gauging |
| `/api/v1/features` | localhost:8003 | Feature Engine |
| `/api/v1/predict` | localhost:8004 | Prediction |
| `/api/v1/alerts` | localhost:8005 | Alert Dispatcher |
| `/api/v1/causal` | localhost:8006 | Causal Engine |
| `/api/v1/ledger` | localhost:8007 | FloodLedger |
| `/api/v1/chorus` | localhost:8008 | CHORUS |
| `/api/v1/fl` | localhost:8009 | Federated Server |
| `/api/v1/evacuation` | localhost:8010 | Evacuation RL |
| `/api/v1/mirror` | localhost:8011 | MIRROR |
| `/api/v1/scarnet` | localhost:8012 | ScarNet |
| `/api/v1/monitor` | localhost:8013 | Model Monitor |
| `/api/v1/copilot` | localhost:8016 | ARGUS Copilot |
| `/api` | localhost:8000 | API Gateway (fallback) |

---

## 7. Data Flow & Control Flow

### End-to-End Pipeline

```
[1] DATA INGESTION
    CWC WRIS API ──→ Ingestion Service ──→ Kafka: gauge.realtime
    Open-Meteo API ──→ Ingestion Service ──→ Kafka: weather.api.imd
    CCTV Stream ──→ CV Gauging Service ──→ Kafka: virtual.gauge.*
    IoT (MQTT) ──→ IoT Gateway ──→ Kafka: iot.*
                         │
                         ▼
[2] FEATURE ENGINEERING
    Feature Engine consumes all Kafka topics
    ├── Temporal rolling windows: 1h, 3h, 6h, 24h
    │   (mean, max, min, rate of change, std dev)
    ├── Kalman filter for quality assurance
    ├── PINN mesh interpolation for ungauged locations
    ├── Spatial features: upstream risk, basin connectivity
    └── Writes enriched features → TimescaleDB
    └── Publishes → Kafka: features.vector.*
                         │
                         ▼
[3] PREDICTION
    Prediction Service consumes features.vector.*
    ├── Fast Track: XGBoost → flood probability (0.0-1.0)
    │   └── SHAP → top-3 contributing features
    ├── Adaptive Thresholds: Adjust by monsoon/soil/AMI
    │   └── AlertClassifier → NORMAL/ADVISORY/WATCH/WARNING/EMERGENCY
    ├── Deep Track: TFT → quantile forecasts at 15/30/60/120/180 min
    ├── Caches result → Redis + in-memory
    └── Publishes → Kafka: predictions.fast.*
                         │
                         ▼
[4] ALERT DISPATCH
    Alert Dispatcher consumes predictions.fast.*
    ├── Check: risk_score > threshold AND cooldown expired?
    ├── Determine channels: WhatsApp, SMS, Cell Broadcast
    ├── Send via Twilio (WhatsApp/SMS)
    ├── Generate CAP XML for Cell Broadcast Entity
    ├── Log alert to internal store
    └── Publish → Kafka: alerts.dispatch
                         │
                         ▼
[5] DASHBOARD DELIVERY
    API Gateway aggregates all service responses
    Vite proxy routes browser requests to services
    React hooks poll APIs at 5-60s intervals
    ├── usePredictions → updates map markers (color/size)
    ├── useAlertLog → populates alert sidebar
    ├── useSSEUpdates → real-time streaming (when alerts active)
    └── Individual tab hooks → on-demand data
                         │
                         ▼
[6] FIELD DELIVERY
    Notification Hub → Web Push to PWA
    PWA stores data in IndexedDB for offline access
    Field officers see: risk map, evacuation routes, report floods
```

### Causal Analysis Flow

```
Prediction (risk score)
    → Causal Engine loads DAG (beas_brahmaputra_v1.json)
    → Decomposes risk into causal factors:
        rainfall_upstream: +0.35
        soil_saturation: +0.22
        dam_current_level: +0.18
        embankment_condition: -0.05
    → Identifies available interventions:
        dam_pandoh_gate: open 0-100%
        embankment_height: 0-2m increase
        road_closure: yes/no
    → User/system selects intervention
    → do(X=x) calculus computes counterfactual
    → Returns: new risk score, lives saved, cost
```

### CHORUS Community Intelligence Flow

```
Citizen sends WhatsApp message (text or voice)
    → CHORUS receives via Twilio webhook
    → If voice: Whisper ASR → text transcription
    → IndicBERT classification:
        - Flood status: YES/NO/UNCERTAIN
        - Severity: LOW/MEDIUM/HIGH/EXTREME
        - Sentiment: CALM/CONCERNED/ANXIOUS/PANIC
    → Geohash aggregation (precision 5)
    → Trust scoring based on source history
    → Consensus: 3+ reports from same area
    → If consensus + panic > 30%: inject alert
    → Dashboard shows signal feed + sentiment cards
```

---

## 8. ML Models & AI Pipeline

### Model Inventory

| Model | Type | File | Input | Output | Params | Fallback |
|---|---|---|---|---|---|---|
| **XGBoost Flood** | Gradient Boosting | `xgboost_flood.joblib` | 16 features | Probability 0.0-1.0 | 500 trees, depth 6 | Heuristic rules |
| **SHAP Explainer** | XAI | Derived from XGBoost | Feature vector | Top-3 factors | TreeExplainer | Weighted importance |
| **TFT** | Deep Learning | `tft_flood.ckpt` | Time series | 6 horizons x 3 quantiles | PyTorch Lightning | Rising-limb physics |
| **PINN** | Physics-NN | `pinn_beas_river.pt` | (x, t) spatial-temporal | Water level mesh | 64 hidden, 3 layers | NumPy IDW |
| **YOLOv11** | Object Detection | `yolo11n.pt` | CCTV frame RGB | Water bounding boxes | YOLO nano | Demo simulation |
| **SAM-2** | Segmentation | `sam2_tiny.pt` | Frame + bbox | Pixel-precise mask | SAM tiny | Skip segmentation |
| **Causal GNN** | Graph NN | `causal_gnn_brahmaputra.pt` | DAG + evidence | Intervention effects | 64 hidden, 3 GCN | SEM topological |
| **PPO Agent** | Reinforcement Learning | `evac_ppo.zip` | State vector | Vehicle assignments | Stable-Baselines3 | Priority heuristic |
| **IndicBERT** | NLP Classification | `indic_bert_flood_classifier/` | Text (4 languages) | 12-class label | ai4bharat/indic-bert | Keyword zero-shot |
| **Whisper** | ASR | OpenAI base | Audio bytes | Transcribed text | 77M params | Empty fallback |
| **Oracle v2** | Micro-Transformer | `oracle_v2_stub.pt` | 24x6 sensor window | Risk + 4-class alert | ~94K params | N/A |
| **Kalman Filter** | State Estimation | In-memory | Raw observation | Filtered + anomaly flag | Q=0.01, R=0.5 | Raw passthrough |

---

### 8.1 XGBoost Flood Probability Predictor

**File:** `services/prediction/fast_track/xgboost_predictor.py`

XGBoost is the primary "fast track" predictor. It produces a single flood probability score (0.0 to 1.0) for each village every 60 seconds.

**Hyperparameters:**
```
n_estimators:      500        # Number of boosted trees
max_depth:         6          # Maximum tree depth
learning_rate:     0.05       # Step size shrinkage
subsample:         0.8        # Row sampling per tree
colsample_bytree:  0.8        # Column sampling per tree
eval_metric:       logloss    # Binary cross-entropy
```

**16-Feature Input Vector (order is critical):**

| # | Feature | Unit | Description |
|---|---|---|---|
| 1 | `level_1hr_mean` | meters | Mean water level over last 1 hour |
| 2 | `level_3hr_mean` | meters | Mean water level over last 3 hours |
| 3 | `level_6hr_mean` | meters | Mean water level over last 6 hours |
| 4 | `level_24hr_mean` | meters | Mean water level over last 24 hours |
| 5 | `level_1hr_max` | meters | Maximum level spike in 1 hour |
| 6 | `rate_of_change_1hr` | m/hr | How fast water is rising (critical signal) |
| 7 | `rate_of_change_3hr` | m/hr | 3-hour rate of change (trend) |
| 8 | `cumulative_rainfall_6hr` | mm | Total rainfall in 6 hours |
| 9 | `cumulative_rainfall_24hr` | mm | Total rainfall in 24 hours |
| 10 | `soil_moisture_index` | 0-1 | Current soil saturation |
| 11 | `antecedent_moisture_index` | mm | Pre-existing ground moisture |
| 12 | `upstream_risk_score` | 0-1 | Risk at upstream stations (cascading) |
| 13 | `basin_connectivity_score` | 0-1 | Hydrological connectivity factor |
| 14 | `hour_of_day` | 0-23 | Diurnal cycle (flash floods peak in afternoon) |
| 15 | `day_of_year` | 1-366 | Seasonal context |
| 16 | `is_monsoon_season` | 0/1 | Binary: June-September (critical) |

**Training:**
- Temporal split: 80% train / 20% test (no random shuffle — respects time ordering)
- Synthetic data generation with realistic monsoon dynamics when historical data unavailable
- Trained on startup (`TRAIN_ON_STARTUP=true`) using CWC historical 2019-2023 CSV
- Retraining triggered by model monitor when drift detected

**Fallback:** When model file is unavailable, uses a heuristic rule-based predictor with weighted feature importance.

---

### 8.2 SHAP Explainer (Explainable AI)

**File:** `services/prediction/fast_track/shap_explainer.py`

Every prediction comes with a human-readable explanation of WHY the model made that decision. SHAP (SHapley Additive exPlanations) decomposes the prediction into per-feature contributions.

**How it works:**
1. `shap.TreeExplainer` is pre-computed at startup (not per-request — fast inference)
2. For each prediction, compute SHAP values for all 16 features
3. Select top-N features by absolute SHAP magnitude (default N=3)
4. For each feature, output:
   - Feature name with human-readable label
   - SHAP value (magnitude of contribution)
   - Direction: `INCREASES_RISK` or `DECREASES_RISK`
   - Contribution percentage relative to total

**Example output:**
```json
{
  "explanation": [
    {
      "feature": "cumulative_rainfall_6hr",
      "label": "6-hour rainfall: 85mm",
      "shap_value": 0.23,
      "direction": "INCREASES_RISK",
      "contribution_pct": 41.2
    },
    {
      "feature": "soil_moisture_index",
      "label": "Soil saturation: 89%",
      "shap_value": 0.15,
      "direction": "INCREASES_RISK",
      "contribution_pct": 26.8
    },
    {
      "feature": "rate_of_change_1hr",
      "label": "Water rising at 0.3m/hr",
      "shap_value": 0.12,
      "direction": "INCREASES_RISK",
      "contribution_pct": 21.4
    }
  ]
}
```

**Fallback heuristic weights** (when SHAP unavailable):
```
cumulative_rainfall_6hr:  0.18
upstream_risk_score:      0.16
rate_of_change_1hr:       0.14
soil_moisture_index:      0.12
level_1hr_max:            0.10
(remaining features with lower weights)
```

---

### 8.3 TFT — Temporal Fusion Transformer (Deep Track)

**File:** `services/prediction/deep_track/tft_predictor.py`

While XGBoost gives an instant "right now" risk score, TFT provides multi-horizon probabilistic forecasts — predicting flood risk at 15, 30, 45, 60, 90, and 120 minutes into the future.

**Architecture:**
- PyTorch Lightning checkpoint
- Produces quantile forecasts: p10 (optimistic), p50 (median), p90 (pessimistic)
- Same 16-feature input as XGBoost

**Forecast Horizons:**
```
Horizon 1:  15 minutes ahead
Horizon 2:  30 minutes ahead
Horizon 3:  45 minutes ahead
Horizon 4:  60 minutes ahead
Horizon 5:  90 minutes ahead
Horizon 6: 120 minutes ahead
```

**Synthetic Rising-Limb Physics Model (fallback when checkpoint unavailable):**

The TFT fallback uses actual hydrological physics — a rising limb model based on how flood waves propagate:

```
risk(t) = base + amplitude × (1 - e^(-t/τ))
```

Where:
- `base` = Current XGBoost risk score (anchoring to real-time data)
- `amplitude` = f(rainfall, soil_moisture, upstream_risk) capped at 0.6
- `τ (time constant)` = 20-60 minutes (faster when soil is saturated)
- Uncertainty bands: heteroscedastic σ = 0.03 + 0.001 × horizon_minutes
- Quantiles via Gaussian approximation: z_10 = -1.2816, z_90 = 1.2816

**Output example:**
```json
{
  "horizons": [
    {"minutes": 15,  "p10": 0.52, "p50": 0.58, "p90": 0.64},
    {"minutes": 30,  "p10": 0.55, "p50": 0.63, "p90": 0.71},
    {"minutes": 60,  "p10": 0.59, "p50": 0.70, "p90": 0.81},
    {"minutes": 120, "p10": 0.61, "p50": 0.74, "p90": 0.87}
  ],
  "peak_risk_horizon_min": 120,
  "peak_risk_value": 0.87,
  "trend": "RISING"
}
```

**Trend Detection:**
- `RISING`: last horizon p50 > first horizon p50 + 0.05
- `FALLING`: last horizon p50 < first horizon p50 - 0.05
- `STABLE`: otherwise

---

### 8.4 PINN — Physics-Informed Neural Network

**Files:** `services/prediction/pinn.py`, `services/feature_engine/pinn_mesh.py`

India has ~5,000 CWC gauges for rivers spanning 300,000+ km. PINN fills the gaps — generating "virtual sensors" at ungauged locations by combining sparse real readings with fluid dynamics equations.

**Architecture:**
```
Input:  (x_normalized, t_normalized)  →  spatial position + time
Layer 1: Linear(2, 64) + Tanh
Layer 2: Linear(64, 64) + Tanh
Layer 3: Linear(64, 1)            →  predicted water level h(x,t)
```

**Physics Constraint — Saint-Venant Continuity Equation:**
```
∂A/∂t + ∂Q/∂x = 0
```
Where A = cross-sectional area, Q = flow discharge. This ensures the model obeys conservation of mass — water can't appear or disappear.

**Loss Function:**
```
L = L_data + λ × L_physics

L_data    = MSE(h_predicted, h_observed)     # Fit to gauge readings
L_physics = MSE(∂A/∂t + ∂Q/∂x, 0)          # Physics residual
λ = 0.1                                      # Physics loss weight
```

Gradients ∂h/∂x and ∂h/∂t are computed via PyTorch autograd — the same automatic differentiation used in backpropagation.

**Virtual Sensor Mesh (Beas River):**
```
VIRT-BEAS-001:  x = 5 km   (near Manali)
VIRT-BEAS-002:  x = 10 km  (between Manali and Kullu)
VIRT-BEAS-003:  x = 20 km  (Kullu)
VIRT-BEAS-004:  x = 35 km  (Larji)
VIRT-BEAS-005:  x = 55 km  (Pandoh)
Reach length: 70 km
```

**Fallback:** NumPy Inverse-Distance Weighted (IDW) interpolation with physics residual approximation:
```
h(x) = Σ(w_i × h_i) / Σ(w_i)
w_i = 1 / distance(x, x_i)^2
```

**Retraining:**
- Optimizer: Adam (lr=1e-3)
- Epochs: 500
- Characteristic wave speed: c = sqrt(g × |h|) where g = 9.81 m/s^2

---

### 8.5 YOLOv11 + SAM-2 — Computer Vision Gauging

**File:** `services/cv_gauging/main.py`

Transforms standard CCTV footage into water level measurements — turning every surveillance camera near a river into a virtual gauge station.

**Pipeline:**
```
CCTV Frame (RGB)
    → YOLOv11 inference: Detect water surface bounding boxes
    → SAM-2 segmentation: Pixel-precise water mask within bbox
    → Pixel-to-Meter conversion:
        CCTV mode: Pre-calibrated homography matrix (station-specific)
        Drone mode: GSD = (altitude_m × FOV_rad) / (image_width_px × 0.3048)
    → Output: depth_m, velocity_m_s, confidence [0-1], alert_flag
```

**Models:**
- **YOLOv11 Nano** (`yolo11n.pt`): ~6M params, optimized for edge devices, detects water regions in frame
- **SAM-2 Tiny** (`sam2_tiny.pt`): Segment Anything Model for precise water boundary segmentation

**Alert Thresholds (from water depth):**
```
depth > 4.0m  →  alert_flag = True (EMERGENCY)
depth > 3.0m  →  WATCH
depth > 2.0m  →  ADVISORY
depth < 2.0m  →  NORMAL
```

**Demo Cameras:**
```
CAM-BEAS-01: Beas River – Manali Bridge (32.24°N, 77.19°E)
CAM-BEAS-02: Beas River – Kullu Dam (31.95°N, 77.10°E)
```

---

### 8.6 Causal GNN — Graph Neural Network for Causal Inference

**File:** `services/causal_engine/gnn.py`

Instead of just correlating features with flood risk ("rainfall went up, so risk is high"), the Causal GNN models actual cause-and-effect relationships using Judea Pearl's do-calculus framework.

**Architecture (PyTorch):**
```
Input:  Node features (1 per node) → d_model=64 projection
Layer 1: GCN(64, 64) + ReLU + residual connection
Layer 2: GCN(64, 64) + ReLU + residual connection
Layer 3: GCN(64, 64) + ReLU + residual connection
Output:  Linear(64, 1) + Sigmoid → risk [0,1] per node
```

**Message Passing (GCN):**
```
H^(l+1) = σ(D^{-1} × A × H^(l) × W^(l))
```
Where A = adjacency matrix, D = degree matrix, W = learnable weights.

**Causal DAG Structure (`beas_brahmaputra_v1.json`):**

Node types:
- **OBSERVABLE**: Measured — rainfall, soil saturation, tributary levels, gauge readings
- **LATENT**: Hidden/unmeasured — surface runoff, infiltration rate
- **INTERVENTION**: Actionable — dam gate position (0-100%), embankment height, road closures
- **OUTCOME**: Target — downstream flood depth, displacement count, economic loss

**do-Calculus Intervention:**
```
do(dam_pandoh_gate = 0.8):   # "What if we open the dam 80%?"
  1. Cut all incoming edges to dam_pandoh_gate node
  2. Fix dam_pandoh_gate = 0.8 in evidence
  3. Propagate forward through remaining DAG
  4. Compare: original flood_depth vs counterfactual flood_depth
  → Returns: {risk_reduction: 0.15, lives_saved: 340, cost_reduction: $2.1M}
```

**Fallback:** NumPy Structural Equation Model (SEM) with Kahn's topological sort for forward propagation when PyTorch is unavailable.

---

### 8.7 PPO — Proximal Policy Optimization (Evacuation RL)

**File:** `services/evacuation_rl/agent/ppo_agent.py`, `services/evacuation_rl/environment/flood_env.py`

When a flood is imminent, the system must decide: which vehicles go to which villages, via which routes, to which shelters — all in real-time with changing road conditions and shelter capacities.

**Environment (PettingZoo Multi-Agent):**
```
Agents:     coordinator_majuli, coordinator_jorhat (one per district)
State:      Villages at risk, vehicle fleet, shelter capacities, road closures, time to flood
Action:     Discrete: (vehicle_idx × village_idx × route_idx)
Observation: n_villages×3 + n_vehicles×3 + n_shelters + 2
```

**State Vector per Village:**
```
[risk_score (0-1), population_remaining/max, population_evacuated/max]
```

**Reward Function (what the agent optimizes):**
```
+10  per person evacuated (normalized by population)
 -1  vehicle currently busy
 -3  attempt to use closed road
 -2  empty trip (< 20% vehicle capacity)
 -5  route conflict (2+ vehicles on same road segment)
 -8  shelter overflow
 +3  time buffer > 30 minutes before flood arrival
```

**Vehicle Routing:**
- Distance: Haversine formula between GPS coordinates
- Travel time: `distance_km / avg_speed_kmh × 60` (minutes)
- Round-trip tracking: vehicle unavailable until return
- Types: bus (50 passengers), truck (30), boat (20), helicopter (10, fast)

**Fallback:** Priority-based heuristic planner when RL agent unavailable:
```
Priority = risk_score × population
Vehicle  = nearest available with capacity
Shelter  = nearest with remaining capacity
Route    = shortest safe road
```

---

### 8.8 IndicBERT + Whisper — Multilingual NLP (CHORUS)

**Files:** `services/chorus/nlp/analyzer.py`, `services/chorus/nlp/indic_classifier.py`, `services/chorus/nlp/whisper_transcriber.py`

CHORUS aggregates citizen reports from WhatsApp (text and voice) in multiple Indian languages, classifies them, and builds consensus-based flood alerts.

#### Whisper (Speech-to-Text)

**Model:** OpenAI Whisper `base` (77M params, fast for hackathon; production: `medium` or `large-v3`)

```
Input:   Audio bytes (WAV/OGG/MP3) from WhatsApp voice note
Output:  { text, detected_language, confidence }
Languages: Hindi, Assamese, Bengali, English (native multilingual)
```

#### IndicBERT (Text Classification)

**Model:** `ai4bharat/indic-bert` fine-tuned for flood classification

**12 Output Classes:**
```
FLOOD_PRECURSOR        — Early warning signs ("water rising fast")
ACTIVE_FLOOD           — Ongoing inundation ("my house is flooded")
INFRASTRUCTURE_FAILURE — Bridges/roads damaged
PEOPLE_STRANDED        — Rescue needed
FALSE_ALARM            — No actual threat
ROAD_BLOCKED           — Route inaccessible
DAMAGE_REPORT          — Property/crop loss
RESOURCE_REQUEST       — Need food, medicine, boats
OFFICIAL_UPDATE        — Government / NDRF announcement
WEATHER_OBSERVATION    — Rain, cloudburst report
ANIMAL_MOVEMENT        — Unusual animal behavior (traditional signal)
UNRELATED              — Not flood-related
```

**Flood-relevant subset** (triggers alert escalation):
`FLOOD_PRECURSOR`, `ACTIVE_FLOOD`, `INFRASTRUCTURE_FAILURE`, `PEOPLE_STRANDED`, `ROAD_BLOCKED`

#### Full Analysis Pipeline

```
WhatsApp message arrives
    │
    ├─ [If voice] → Whisper → transcribed text
    │
    ├─ IndicBERT classification → 12-class label
    │
    ├─ Keyword extraction (165+ keywords across 4 languages)
    │   Hindi:    "baadh", "paani", "doob", "bachao"
    │   Assamese: "baan", "paani", "dubise"
    │   Bengali:  "bonna", "jol", "dubechhe"
    │
    ├─ Sentiment scoring:
    │   PANIC:     ≥2 panic keywords OR (1 panic + 3 flood keywords)
    │   ANXIOUS:   3+ flood keywords OR 1 panic keyword
    │   CONCERNED: 1+ flood keyword
    │   CALM:      Default
    │
    ├─ Credibility scoring:
    │   Base: 0.3
    │   + 0.10 if text length > 50 chars
    │   + 0.10 if text length > 150 chars
    │   + 0.05 per keyword (max +0.20)
    │   + 0.20 if source = field_worker or government
    │   + 0.10 if GPS location provided
    │   + classification_confidence × 0.10
    │
    ├─ Geohash aggregation (precision 5 ~ 5km cells)
    │
    └─ Consensus: 3+ reports from same cell → inject into alert system
```

---

### 8.9 Kalman Filter — Quality Assurance

**File:** `services/feature_engine/kalman_filter.py`

Raw sensor data is noisy — gauges can spike due to debris, sensors can malfunction, CCTV estimates can jitter. The Extended Kalman Filter (EKF) smooths the data and detects anomalies.

**State Vector:**
```
x = [water_level (m), rate_of_change (m/hr)]
```

**System Model (constant velocity):**
```
F = [[1.0, dt],    # Level = previous level + rate × time
     [0.0, 1.0]]   # Rate persists (constant velocity assumption)
```

**Parameters:**
```
Q (process noise):      0.01   # Water levels change slowly
R (observation noise):  0.5    # Sensor measurement error
Anomaly threshold:      3.0σ   # 3-sigma outlier detection
Timestep default:       5 min
```

**Per-observation update cycle:**
```
1. PREDICT:
   x_pred = F × x_previous
   P_pred = F × P × F^T + Q

2. DETECT ANOMALY:
   innovation = z_observed - H × x_pred
   S = H × P_pred × H^T + R
   innovation_score = |innovation| / √S

3. DECIDE:
   if innovation_score > 3.0:
       REJECT observation → quality_flag = KALMAN_IMPUTED
       Use predicted value (x_pred) instead
   else:
       NORMAL UPDATE:
       K = (P_pred × H^T) / S          # Kalman gain
       x = x_pred + K × innovation      # Update state
       P = (I - K × H) × P_pred        # Update covariance
       quality_flag = GOOD
```

**Usage:** Independent EKF instance maintained per station_id. Outputs: `filtered_value`, `rate_of_change`, `innovation_score`, `quality_flag`.

---

### 8.10 Adaptive Threshold Engine

**File:** `services/prediction/fast_track/threshold_engine.py`

The system doesn't use fixed alert thresholds. Instead, it dynamically adjusts based on ground conditions — during monsoon with saturated soil, lower thresholds trigger alerts earlier (more lead time for evacuation).

**Base Thresholds (NDMA Standard):**
```
ADVISORY:  0.35
WATCH:     0.55
WARNING:   0.72
EMERGENCY: 0.88
Floor:     0.20  (never lower than this)
```

**Adaptive Adjustment Rules (multiplicative):**
```python
multiplier = 1.0

if soil_moisture_index > 0.8:        # Saturated ground
    multiplier *= 0.85               # → 15% lower thresholds

if is_monsoon_season:                # June-September
    multiplier *= 0.90               # → 10% lower thresholds

if antecedent_moisture_index > 0.6:  # Recent heavy rain
    multiplier *= 0.92               # → 8% lower thresholds

adjusted_threshold = max(base × multiplier, 0.20)  # Floor at 0.20
```

**Example — Monsoon + Wet Soil + Recent Rain:**
```
Multiplier: 1.0 × 0.85 × 0.90 × 0.92 = 0.703

ADVISORY:  0.35 × 0.703 = 0.25  (triggers 29% sooner)
WATCH:     0.55 × 0.703 = 0.39  (triggers 29% sooner)
WARNING:   0.72 × 0.703 = 0.51  (triggers 29% sooner)
EMERGENCY: 0.88 × 0.703 = 0.62  (triggers 29% sooner)
```

This means during peak monsoon with saturated soil, the system effectively provides ~29% more lead time for evacuations.

---

### 8.11 Alert Classifier

**File:** `services/prediction/fast_track/alert_classifier.py`

Converts the XGBoost probability + adaptive thresholds into a discrete alert level with a confidence band.

**Classification:**
```
if probability >= emergency_threshold:  → EMERGENCY
elif probability >= warning_threshold:  → WARNING
elif probability >= watch_threshold:    → WATCH
elif probability >= advisory_threshold: → ADVISORY
else:                                   → NORMAL
```

**Confidence Bands:**
```
min_margin = minimum distance from probability to any threshold boundary

HIGH:   margin >= 0.10  (firmly in this category)
MEDIUM: margin >= 0.04  (likely correct but near boundary)
LOW:    margin <  0.04  (borderline — could shift with next reading)
```

LOW confidence triggers more frequent polling (5s instead of 30s) in the dashboard.

---

### 8.12 Oracle v2 — MobileFloodFormer (Edge Deployment)

**File:** `services/oracle_v2/mobile_flood_former.py`

A micro-transformer designed to run on Raspberry Pi and Android phones — enabling flood prediction at the edge, without internet connectivity.

**Architecture:**
```
Input:  (batch, 24, 6)  — 24-hour window × 6 features
        Features: water_level_m, rainfall_mm, soil_moisture_pct,
                  rate_of_change, hour_of_day, is_monsoon

Embedding:     Linear(6, 32)
Pos Encoding:  Learned positional embeddings (24 positions)
Transformer:   2 layers × 4 attention heads × d_model=32 × d_ff=64
Head:          Linear(32, 4) → softmax for alert classes
               Linear(32, 1) → sigmoid for risk score

Total Parameters: ~94,000 (vs BERT's 110M — 1,170× smaller)
Model Size:       ~376 KB (fp32), <500 KB (int8 quantized)
```

**Quantization for Edge:**
```
Original (fp32):  376 KB
Quantized (int8): <500 KB
Backend:          QNNPACK (ARM Cortex-A76 optimized)
Target Latency:   < 80ms on Raspberry Pi 5
Export Formats:   TorchScript (.pt), ONNX, TFLite
```

**Input Normalization:**
```
MEANS = [3.2, 15.0, 55.0, 0.05, 12.0, 0.5]
STDS  = [2.1, 25.0, 20.0, 0.15, 6.9,  0.5]
```

**Attention-based Explainability:** The attention weights reveal which of the 24 hours were most influential — if the model focuses on hours 18-21 (late afternoon), it learned that the rapid afternoon rise mattered most.

---

### 8.13 Federated Learning (Privacy-Preserving Training)

**File:** `services/federated_server/aggregator.py`

Districts may not want to share raw flood data (political sensitivity, privacy concerns). Federated learning trains a shared model WITHOUT districts sharing their data.

**Algorithm: FedAvg + Differential Privacy (DP-SGD)**

```
Round N:
  1. Server sends global model weights to participating districts
  2. Each district trains locally on their data (never leaves their server)
  3. Each district sends ONLY weight deltas (not data) back

  DP-SGD Privacy Steps:
  4. Clip gradient norms:
     if ||gradient|| > clip_norm:
         gradient *= clip_norm / ||gradient||

  5. Add calibrated noise:
     σ = √(2 × ln(1.25/δ)) / ε × clip_norm
     noise ~ N(0, σ²)
     dp_gradient = gradient + noise

  6. FedAvg aggregation:
     new_weights[layer] = global[layer] + Σ(clipped_delta × n_samples/total_samples) + noise
```

**DP Configuration:**
```
ε (epsilon) = 1.0    # Privacy budget (lower = more private)
δ (delta)   = 1e-5   # Failure probability
clip_norm   = 1.0    # Gradient clipping threshold
```

**Interpretation:** ε = 1.0 means an adversary with access to the model can increase their confidence about any individual data point by at most a factor of e^1 ≈ 2.7. This is considered strong privacy protection.

**Demo Nodes:**
```
Node 1: Mandi District    (HP)     — 2,400 samples — ACTIVE
Node 2: Kullu District    (HP)     — 1,800 samples — ACTIVE
Node 3: Majuli District   (Assam)  — 3,100 samples — ACTIVE
Node 4: Jorhat District   (Assam)  — 2,600 samples — ACTIVE
Node 5: Dibrugarh District(Assam)  — 1,200 samples — OFFLINE
Node 6: Tezpur District   (Assam)  — 2,100 samples — SYNCING
```

---

### Design Philosophy: Graceful Degradation

Every ML component has a fallback, ensuring the system NEVER fails silently:

| Component | Primary | Fallback |
|---|---|---|
| XGBoost | Trained model | Heuristic weighted rules |
| SHAP | TreeExplainer | Pre-defined feature importance |
| TFT | PyTorch checkpoint | Rising-limb physics equation |
| PINN | Neural network | NumPy IDW interpolation |
| Causal GNN | PyTorch GCN | NumPy SEM + topological sort |
| PPO Agent | Trained RL policy | Priority-based greedy heuristic |
| IndicBERT | Fine-tuned transformer | Keyword matching (165+ words) |
| Whisper | OpenAI model | Empty transcription |
| Kalman Filter | Full EKF | Raw passthrough |
| Thresholds | Adaptive engine | Static NDMA base values |

---

## 9. External APIs & Data Sources

### Active APIs

| API | Type | Auth | Purpose | Cost |
|---|---|---|---|---|
| **Open-Meteo** | Weather | None | Rainfall, temperature, humidity | Free, no key |
| **NASA Earthdata (CMR)** | Satellite | Bearer token | HLSL30 Sentinel/Landsat imagery | Free (register) |
| **Sentinel-2 L2A (AWS)** | Satellite | None | Public open data bucket | Free, no key |
| **Twilio** | Messaging | SID + Token | WhatsApp/SMS alerts | Trial: $15 credit |
| **CartoDB / OSM** | Map tiles | None | Dark map tiles for dashboard | Free, no key |

### Government APIs (Optional)

| API | Type | Auth | Purpose |
|---|---|---|---|
| **CWC / WRIS** | River data | Token | Real-time gauge readings from Central Water Commission |
| **IMD** | Weather | API Key | Official India Meteorological Department data |
| **NDMA CBEAS** | Cell broadcast | Token | National cell broadcast emergency alerts |

### Kafka Topics

```
# Ingestion
gauge.realtime                    # CWC gauge readings
weather.api.imd                   # Weather data (IMD/Open-Meteo)
cctv.frames.{camera_id}          # CCTV frame metadata
iot.gauge / iot.rainfall / iot.soil_moisture  # IoT sensor data

# Processing
virtual.gauge.{camera_id}        # CV-derived gauge readings
features.vector.{station_id}     # Enriched feature vectors
pinn.mesh.{grid_cell_id}         # PINN virtual sensor outputs

# Predictions
predictions.fast.{village_id}    # Fast-track XGBoost results
prediction.flood.{station_id}    # Legacy predictions

# Actions
alerts.dispatch                   # Alert dispatcher input
chorus.signal.{geohash}          # CHORUS citizen reports
causal.risk.{basin_id}           # Causal risk scores
```

---

## 10. Infrastructure

### Docker Compose Services

| Service | Port | Image | Purpose |
|---|---|---|---|
| **Zookeeper** | 2181 | confluentinc/cp-zookeeper:7.6.0 | Kafka coordination |
| **Kafka** | 9092 | confluentinc/cp-kafka:7.6.0 | Message broker |
| **TimescaleDB** | 5432 | timescale/timescaledb:latest-pg16 | Time-series DB |
| **Redis** | 6379 | redis:7-alpine | Cache + pub/sub |
| **Prometheus** | 9090 | prom/prometheus | Metrics ingestion |
| **Grafana** | 3001 | grafana/grafana | Monitoring dashboards |
| **MLflow** | 5000 | ghcr.io/mlflow/mlflow | Experiment tracking |
| **Hardhat** | 8545 | (from npm) | Local Ethereum node |

### Redis Database Layout

| DB | Purpose |
|---|---|
| db 0 | Prediction cache (TTL 300s) |
| db 1 | CHORUS trust engine scores |
| db 3 | Notification Hub subscriptions |
| db 4 | Multi-Basin comparison data |

---

## 11. Security Layer

### Authentication (`security/auth/auth_middleware.py`)

- **Method**: OAuth2 + JWT via Keycloak (production) or symmetric JWT (development)
- **Validation**: RS256 with JWKS URI (production), HS256 symmetric (dev)
- **Discovery**: `{KEYCLOAK_URL}/realms/{REALM}/.well-known/openid-configuration`
- **Dev mode**: `AUTH_ENABLED=false` disables all auth checks

### Role-Based Access Control (RBAC)

| Role | Level | Permissions |
|---|---|---|
| `VIEWER` | 0 | Read-only dashboard access |
| `OPERATOR` | 1 | Acknowledge alerts, view detailed predictions |
| `DISTRICT_ADMIN` | 2 | Trigger evacuations for their district |
| `SYSTEM_ADMIN` | 3 | Full system access, configuration changes |
| `SERVICE` | 3 | Inter-service mTLS communication |

### Immutable Audit Logger (`security/audit/audit_logger.py`)

- **Storage**: TimescaleDB table `argus_audit_log` + optional CloudWatch
- **Tamper detection**: SHA-256 chained hashes — modifying any past entry breaks the chain
- **Per entry**: timestamp, actor (JWT sub), action, resource, details, IP, user-agent
- **Audited actions**: Evacuation triggers, alert overrides, config changes, model retraining

---

## 12. Shared Modules

### `shared/config.py`
Centralized `Settings` class with 150+ environment variables covering all services, model paths, Kafka config, Redis, Twilio, feature windows, alert cooldowns, etc.

### `shared/kafka_client.py`
- `KafkaProducerClient`: JSON-serialized message publishing
- `KafkaConsumerClient`: Auto-deserializing consumer with group management

### `shared/models/` (Pydantic Schemas)

| Module | Key Models |
|---|---|
| `ingestion.py` | GaugeReading, WeatherData, CCTVFrame |
| `feature_engine.py` | FeatureVector, TemporalFeatures, SpatialFeatures |
| `cv_gauging.py` | VirtualGaugeReading |
| `prediction.py` | FloodPrediction, SHAPExplanation, AlertPayload, PINNSensorReading |
| `phase2.py` | CausalDAG, InterventionRequest, CounterfactualQuery |

### `shared/causal_dag/beas_brahmaputra_v1.json`

Defines the causal graph with 4 node types:
- **OBSERVABLE**: Measured (rainfall, soil, gauge levels)
- **LATENT**: Hidden (runoff, infiltration)
- **INTERVENTION**: Actionable (dam gates, embankments, road closures)
- **OUTCOME**: Target (flood depth, displacement, economic loss)

---

## 13. Integrations

### Cell Broadcast (port 8025)
- **Standard**: OASIS CAP v1.2 / ITU-T X.1303bis
- **Purpose**: Generate XML alert payloads for India's planned CBEAS
- **Advantage**: Reaches ALL phones in a geographic area without phone numbers — critical for rural areas with unregistered SIMs
- **Endpoints**: `POST /api/v1/cell-broadcast/send`, `GET /api/v1/cell-broadcast/history`

### NDMA Compliance (port 8019)
- **Purpose**: Map ARGUS alerts to NDMA GREEN/YELLOW/ORANGE/RED framework
- **SOP 4.2**: Minimum lead time validation (RED requires 2+ hours lead time)
- **Endpoints**: `POST /api/v1/ndma/translate`, `GET /api/v1/ndma/mapping-table`

### Climate Finance (port 8023)
- **Purpose**: World Bank climate finance API integration
- **Use case**: Insurance parametric triggers via FloodLedger

---

## 14. Mobile PWA

**Location**: `/workspaces/HYDRA/mobile/pwa/`

### Features
- **Offline-first**: IndexedDB caching for predictions, alerts, village data
- **Installable**: Add to home screen (PWA manifest)
- **Real-time**: Web Push notifications from Notification Hub
- **Geolocation**: Auto-detect nearest village

### Screens
| Route | Component | Purpose |
|---|---|---|
| `/` | FieldDashboard | Main risk display for selected village |
| `/select` | VillageSelector | Choose monitoring village |
| `/report` | ReportFlood | Submit flood observation (CHORUS input) |
| `/evacuation` | EvacuationCard | View RL routes and shelter info |

### Target Users
- Village sarpanchs (elected heads)
- NDRF field coordinators
- SDMA district officers
- Community first responders

---

## 15. Platform SDK

**Package**: `argus-flood-sdk` (v3.0.0, Apache 2.0)
**Location**: `/workspaces/HYDRA/platform/argus_sdk/`

### Quick Start

```python
from argus import Basin, ARGUSDeployment

# Define basin from YAML configuration
basin = Basin.from_config("my_basin.yaml")

# Create deployment
deployment = ARGUSDeployment(basin)

# Connect data sources
deployment.connect_data_sources()

# Train models
deployment.train_models()

# Start ARGUS
deployment.start()  # System is now running
```

### SDK Modules
- `basin.py` — Basin configuration from YAML
- `deployment.py` — ARGUSDeployment orchestrator
- `prediction.py` — PredictionClient API
- `alert.py` — AlertClient for custom alerting
- `causal.py` — CausalClient for do-calculus queries
- `trainers.py` — Training factories (XGBoost, PINN, Causal DAG)

---

## 16. Demo Mode

### Purpose
The system runs fully with synthetic/demo data when real APIs are unavailable. Designed for hackathon presentations and judge demonstrations.

### How It Works

| Component | Demo Behavior |
|---|---|
| **App.jsx** | `demoMode=true` by default, `activeTab='risk_map'` |
| **usePredictions** | Generates sigmoid-ramped risk scores over 3 minutes (rising crisis) |
| **useAlertLog** | Accumulates alerts as risk increases |
| **GaugeHeroPanel** | Falls back to 6 demo gauges + 4 soil stations |
| **NDMACompliancePanel** | Falls back to ORANGE alert for Majuli + 5-row mapping table |
| **DisplacementMap** | Falls back to 4,250 displaced, 5 shelters, 5 flows |
| **ScarNetPanel** | Has built-in silent fallback |
| **Prediction Service** | Seeds 12 villages with varied risk scores on startup |
| **Alert Dispatcher** | Seeds 7 progressive alerts (ADVISORY → EMERGENCY) |

### Presentation Mode
- Press **F11** for fullscreen judge-facing UI
- 8 demo moments showcasing different capabilities
- Keyboard: Arrow keys to navigate, Alt+1-9 for tabs

---

## 17. Deployment & Running

### Option 1: Full Docker Compose
```bash
docker compose up --build
```
Starts all 25+ services. Requires ~10GB disk, 8GB RAM.

### Option 2: Hybrid (Recommended for Development)
```bash
# Start infrastructure in Docker
docker compose up -d zookeeper kafka timescaledb redis

# Start backend services natively
DEMO_MODE=true python -m uvicorn services.ingestion.main:app --port 8001 &
DEMO_MODE=true python -m uvicorn services.cv_gauging.main:app --port 8002 &
DEMO_MODE=true python -m uvicorn services.feature_engine.main:app --port 8003 &
DEMO_MODE=true python -m uvicorn services.prediction.main:app --port 8004 &
DEMO_MODE=true python -m uvicorn services.alert_dispatcher.main:app --port 8005 &
# ... (repeat for all services)

# Start frontend
cd dashboard && npm install && npx vite --host 0.0.0.0 --port 3000
```

### Port Map

| Port | Service |
|---|---|
| 3000 | Dashboard (Vite) |
| 8000 | API Gateway |
| 8001 | Ingestion |
| 8002 | CV Gauging |
| 8003 | Feature Engine |
| 8004 | Prediction |
| 8005 | Alert Dispatcher |
| 8006 | Causal Engine |
| 8007 | FloodLedger |
| 8008 | CHORUS |
| 8009 | Federated Server |
| 8010 | Evacuation RL |
| 8011 | MIRROR |
| 8012 | ScarNet |
| 8013 | Model Monitor |
| 8014 | Notification Hub |
| 8015 | Multi-Basin |
| 8016 | ARGUS Copilot |
| 8017-8025 | Additional services |
| 2181 | Zookeeper |
| 9092 | Kafka |
| 5432 | TimescaleDB |
| 6379 | Redis |
| 9090 | Prometheus |
| 3001 | Grafana |
| 5000 | MLflow |

---

## 18. Environment Variables

### Required (Infrastructure)
```env
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
TIMESCALE_URL=postgresql://argus:argus@localhost:5432/argus_db
REDIS_URL=redis://localhost:6379
```

### API Keys (Optional — Demo Mode Works Without)
```env
# Twilio (for real SMS/WhatsApp alerts)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# NASA Earthdata (for real satellite imagery)
NASA_EARTHDATA_TOKEN=your_jwt_token

# Government APIs (optional — demo fallback available)
WRIS_TOKEN=your_cwc_token
IMD_API_KEY=your_imd_key
```

### Map Tiles (Free, No Key)
```env
VITE_MAP_TILE_URL=https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png
VITE_MAP_TILE_URL_SATELLITE=https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}
```

### ML Configuration
```env
DEMO_MODE=true
TRAIN_ON_STARTUP=true
TFT_ENABLED=false
XGBOOST_MODEL_PATH=./models/xgboost_flood.joblib
PINN_MODEL_PATH=./models/pinn_beas_river.pt
```

### Security (Dev Mode)
```env
AUTH_ENABLED=false
JWT_SECRET_KEY=argus_dev_secret_change_in_production
```

---

*Built for the intersection of climate resilience and AI — protecting communities where the monsoon meets the mountain.*
