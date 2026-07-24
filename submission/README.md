# ARGUS — Hackathon Submission
## Adaptive Real-time Guardian & Unified Sentinel

> *"Every sensor can break. Every tower can fall. ARGUS cannot be blinded."*

---

## Quick Links

| Resource | Link |
|----------|------|
| **Live Demo** | `http://localhost:5173` (PresentationMode: press F11) |
| **API Gateway** | `http://localhost:8000` |
| **Health Check** | `http://localhost:8000/health` |
| **Pitch Deck** | [`pitch/slides/index.html`](../pitch/slides/index.html) |
| **Demo Video Script** | [`submission/DEMO_VIDEO_SCRIPT.md`](DEMO_VIDEO_SCRIPT.md) |
| **Impact Statement** | [`submission/IMPACT_STATEMENT.md`](IMPACT_STATEMENT.md) |
| **Technical Appendix** | [`submission/TECHNICAL_APPENDIX.md`](TECHNICAL_APPENDIX.md) |
| **API Reference** | [`docs/API_REFERENCE.md`](../docs/API_REFERENCE.md) |
| **Deployment Guide** | [`docs/DEPLOYMENT_GUIDE.md`](../docs/DEPLOYMENT_GUIDE.md) |

---

## The Problem

**71 people died** in Himachal Pradesh on August 14, 2023. The first official warning arrived **8 minutes** before the flood. Evacuation requires **90 minutes**.

India's flood warning infrastructure relies on ₹3 lakh physical sensors that fail during the very disasters they're meant to detect. When 5,000 sensors broke under the mud, communities had no warning.

## The Solution

ARGUS is an **AI-powered flash flood early warning system** that requires **zero new hardware**. It turns existing traffic cameras into calibrated river gauges, runs offline on ₹5,000 edge computers, and provides **78 minutes of warning** — enough to evacuate.

### Key Metrics

| Metric | Official (2023) | ARGUS (Simulated) |
|--------|:---------------:|:-----------------:|
| First detection | T-8 min | **T-180 min** |
| First alert sent | T-8 min | **T-78 min** |
| Evacuation plan | None | **T-60 min** |
| Causal intervention | N/A | **T-120 min** |
| Lives saveable | 0 / 71 | **40–47 / 71** |

---

## Architecture

**14 microservices · 5 AI models · 0 new hardware**

| Layer | Services | Ports |
|-------|----------|-------|
| **Data** | Ingestion, CV Gauging, CHORUS, ScarNet | 8001, 8002, 8008, 8012 |
| **AI** | Feature Engine, Prediction, Causal Engine, Model Monitor, Federated | 8003, 8004, 8006, 8013, 8009 |
| **Decision** | Evacuation RL, MIRROR, FloodLedger | 8010, 8011, 8007 |
| **Alert** | Alert Dispatcher, ACN Edge Mesh, API Gateway | 8005, 8006, 8000 |

### Five Core Innovations

1. **CV Virtual Gauging** — YOLO v11 + SAM2 turns any traffic camera into a calibrated river gauge (±8cm accuracy)
2. **Temporal Causal AI** — GNN do-calculus engine provides mathematically provable intervention recommendations
3. **Offline Edge Mesh** — ACN crisis nodes run autonomously when 4G fails, alerting in < 4 seconds
4. **CHORUS** — Community reports in 12 Indian languages with credibility scoring
5. **FloodLedger** — Parametric insurance via smart contract — satellite confirms, payout executes

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker (optional, for full infrastructure)

### 1. Clone & Install
```bash
git clone https://github.com/Dhanalakshmi246/HYDRA.git
cd HYDRA
pip install -r requirements.txt
cd dashboard && npm install && cd ..
```

### 2. Start All Services
```bash
bash scripts/start_all.sh
```

This starts all 14 services + the dashboard. Services run in demo mode by default.

### 3. Run Health Check
```bash
python scripts/health_checker.py
```

All services should show 🟢 UP.

### 4. Open Dashboard
Navigate to `http://localhost:5173` and press **F11** for PresentationMode.

### Alternative: Docker Compose
```bash
docker compose up -d
```

---

## Demo Scenarios

### Full Demo (7 minutes)
```bash
python -m demo.orchestrator run --scenario brahmaputra_monsoon
```

### Individual Service Tests
```bash
# CV Gauging
curl http://localhost:8002/api/v1/virtual-gauge/demo

# Flood Prediction
curl http://localhost:8004/api/v1/predict/brahmaputra_upper

# Causal Intervention
curl -X POST http://localhost:8006/api/v1/causal/intervene \
  -H "Content-Type: application/json" \
  -d '{"basin_id":"brahmaputra_upper","intervention":{"variable":"dam_pandoh_gate","value":0.25}}'

# Evacuation Plan
curl http://localhost:8010/api/v1/evacuation/plan/majuli_2024

# FloodLedger
curl http://localhost:8007/api/v1/ledger/chain/summary

# MIRROR Counterfactual
curl http://localhost:8011/api/v1/mirror/event/himachal_2023/counterfactuals

# ScarNet Terrain
curl http://localhost:8012/api/v1/scarnet/latest

# Model Monitor
curl http://localhost:8013/api/v1/monitor/drift-report
```

---

## Tech Stack

| Category | Technologies |
|----------|-------------|
| **AI/ML** | PyTorch, XGBoost, scikit-learn, SHAP, Stable Baselines3 |
| **Computer Vision** | YOLO v11, SAM2, OpenCV |
| **NLP** | Whisper, IndicBERT, spaCy |
| **Backend** | FastAPI, uvicorn, Pydantic v2, structlog |
| **Messaging** | Apache Kafka |
| **Storage** | TimescaleDB, Redis, SQLite |
| **Blockchain** | Solidity, Hardhat, hashlib |
| **Frontend** | React 18, Vite, Tailwind CSS v4, Recharts |
| **Infrastructure** | Docker Compose |

---

## Business Model

| Revenue Stream | Description |
|---------------|-------------|
| **B2G SaaS** | State disaster management subscription (₹2Cr/year/state) |
| **FloodLedger API** | Insurance oracle for parametric flood policies |
| **Risk Data** | Licensing terrain change + flood risk data to reinsurers |

**Market size:** India spends ₹40,000 crore annually on flood recovery. ARGUS addresses the cause, not just the consequence.

---

## Team

| Member | Role | Contributions |
|--------|------|---------------|
| **Rogesh** | Systems architect | ScarNet, API Gateway, integration tests, startup scripts |
| **Sabarish** | ML engineer | Model Monitor, demo orchestrator, GAN generator, pitch script |
| **Dhanalakshmi** | Full-stack + UX | Dashboard, PresentationMode, visual design, submission docs |

---

## Repository Structure

```
HYDRA/
├── services/           # 14 FastAPI microservices
│   ├── ingestion/      # Phase 1: Data pipeline
│   ├── cv_gauging/     # Phase 1: Computer vision
│   ├── feature_engine/ # Phase 1: Temporal features
│   ├── prediction/     # Phase 1: XGBoost + TFT
│   ├── alert_dispatcher/ # Phase 1: Multi-channel alerts
│   ├── acn_node/       # Phase 2: Offline edge mesh
│   ├── causal_engine/  # Phase 2: GNN do-calculus
│   ├── chorus/         # Phase 2: Community NLP
│   ├── federated_server/ # Phase 2: FL + DP
│   ├── flood_ledger/   # Phase 2: Blockchain insurance
│   ├── evacuation_rl/  # Phase 2: PPO routing
│   ├── mirror/         # Phase 2: Counterfactual
│   ├── scarnet/        # Phase 3: Satellite terrain
│   ├── model_monitor/  # Phase 3: Drift detection
│   └── api_gateway/    # Phase 3: Unified API
├── dashboard/          # React + Vite + Tailwind
├── demo/               # Orchestrator + scenarios
├── tests/              # Integration + load tests
├── scripts/            # Startup + health checks
├── pitch/              # Slide deck + scripts
├── submission/         # This document + appendices
├── docs/               # API reference + deployment
└── shared/             # Config + models + Kafka client
```

---

## License

MIT License. See individual service files for details.

---

*Built with conviction that early warning saves lives. ARGUS cannot be blinded.*
