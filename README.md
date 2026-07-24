# ARGUS – AI-Powered Flash Flood Early Warning System

**ARGUS** (Adaptive Real-time Gauging & Urban Safety) is a Kafka-based microservices platform that fuses CWC river gauge data, IMD weather grids, and CCTV-derived computer-vision readings to deliver real-time flash flood predictions with explainable AI.

---

## Architecture

```
┌────────────┐   ┌──────────────┐   ┌─────────────────┐   ┌──────────────┐
│  Ingestion │──▶│  CV Gauging  │──▶│  Feature Engine  │──▶│  Prediction  │
│  (port 8001)   │  (port 8002) │   │  (port 8003)     │   │  (port 8004) │
└────────────┘   └──────────────┘   └─────────────────┘   └──────┬───────┘
       │                                                          │
       │         ┌──────────────┐   ┌───────────┐                │
       └────────▶│  ACN Node    │   │ Dashboard  │◀───────────────┘
                 │  (port 8006) │   │ (port 3000)│
                 └──────────────┘   └───────────┘
                                          ▲
                 ┌──────────────────┐     │
                 │ Alert Dispatcher │─────┘
                 │   (port 8005)    │
                 └──────────────────┘
```

All services communicate through **Apache Kafka** topics.

---

## Services 

| Service | Owner | Port | Description |
|---------|-------|------|-------------|
| `services/ingestion` | Rogesh | 8001 | CWC, IMD, CCTV data ingestion to Kafka |
| `services/cv_gauging` | Rogesh | 8002 | YOLO v11 + SAM 2 water depth/velocity estimation |
| `services/feature_engine` | Sabarish | 8003 | Temporal + spatial feature engineering |
| `services/prediction` | Sabarish | 8004 | XGBoost flood prediction + SHAP + PINN mesh |
| `services/alert_dispatcher` | Dhana | 8005 | CAP alert generation & multi-channel dispatch |
| `services/acn_node` | Dhana | 8006 | Autonomous Community Network mesh node |
| `dashboard` | Dhana | 3000 | Real-time monitoring dashboard |

---

## Quick Start

### 1. Clone & setup
```bash
git clone https://github.com/Dhanalakshmi246/HYDRA.git
cd HYDRA
cp .env.example .env
pip install -r requirements.txt
```

### 2. Start Kafka (Docker)
```bash
docker-compose up -d zookeeper kafka
```

### 3. Run services individually
```bash
# Feature Engine (Sabarish)
uvicorn services.feature_engine.main:app --reload --port 8003

# Prediction (Sabarish)
uvicorn services.prediction.main:app --reload --port 8004
```

### 4. Or run everything
```bash
docker-compose up --build
```

---

## Kafka Topics

| Topic Pattern | Producer | Consumer |
|---------------|----------|----------|
| `gauge.realtime.{station_id}` | Ingestion | Feature Engine |
| `weather.api.imd` | Ingestion | Feature Engine |
| `cctv.frames.{camera_id}` | Ingestion | CV Gauging |
| `virtual.gauge.{camera_id}` | CV Gauging | Feature Engine |
| `features.vector.{station_id}` | Feature Engine | Prediction |
| `prediction.flood.{station_id}` | Prediction | Dashboard, Alert Dispatcher |
| `pinn.mesh.{grid_cell_id}` | Prediction | Dashboard |
| `alerts.dispatch` | Prediction | Alert Dispatcher |

---

## API Endpoints

### Feature Engine (`:8003`)
- `GET /health`
- `GET /api/v1/features/{station_id}/latest`
- `GET /api/v1/features/{station_id}/temporal`
- `GET /api/v1/features/{station_id}/spatial`
- `GET /api/v1/features/bulk?station_ids=A,B,C`

### Prediction (`:8004`)
- `GET /health`
- `GET /api/v1/prediction/{station_id}/latest`
- `GET /api/v1/prediction/{station_id}/history?limit=50`
- `GET /api/v1/pinn/{grid_cell_id}/latest`
- `GET /api/v1/prediction/bulk?station_ids=A,B,C`
- `GET /api/v1/model/info`

---

## Tech Stack

- **Language:** Python 3.11
- **API:** FastAPI + Uvicorn
- **Messaging:** Apache Kafka (confluent-kafka)
- **ML:** XGBoost, SHAP, PINN (PyTorch Phase 2)
- **CV:** YOLO v11, SAM 2, OpenCV
- **Schemas:** Pydantic v2
- **Config:** python-dotenv
- **Logging:** structlog (JSON)
- **Containers:** Docker + Docker Compose

---

## Team

| Member | Responsibilities |
|--------|-----------------|
| **Rogesh** | Data Ingestion Pipeline, CV Virtual Gauging |
| **Sabarish** | Feature Engineering, XGBoost Prediction, SHAP, PINN Mesh |
| **Dhana** | Alert Dispatcher, ACN Node, Dashboard |

---

## License

MIT
