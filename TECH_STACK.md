# HYDRA/ARGUS — Technology Stack Deep Dive

## Every Technology Used: What It Is, Why It Was Chosen, and How It's Used

---

## Table of Contents

1. [Backend Technologies](#1-backend-technologies)
   - [Python 3.11+](#11-python-311)
   - [FastAPI](#12-fastapi)
   - [uvicorn](#13-uvicorn)
   - [Apache Kafka](#14-apache-kafka)
   - [TimescaleDB](#15-timescaledb)
   - [Redis](#16-redis)
   - [structlog](#17-structlog)
   - [Pydantic](#18-pydantic)
2. [Frontend Technologies](#2-frontend-technologies)
   - [React 18.3](#21-react-183)
   - [Vite 6.0](#22-vite-60)
   - [Tailwind CSS 4.0](#23-tailwind-css-40)
   - [Leaflet 1.9.4](#24-leaflet-194)
   - [react-leaflet 4.2.1](#25-react-leaflet-421)
   - [Recharts 2.15](#26-recharts-215)
   - [Axios 1.7](#27-axios-17)
   - [deck.gl 9.x](#28-deckgl-9x)
3. [ML / AI Libraries](#3-ml--ai-libraries)
   - [XGBoost](#31-xgboost)
   - [SHAP](#32-shap)
   - [PyTorch](#33-pytorch)
   - [PyTorch Lightning](#34-pytorch-lightning)
   - [Ultralytics (YOLOv11)](#35-ultralytics-yolov11)
   - [OpenAI Whisper](#36-openai-whisper)
   - [Transformers (IndicBERT)](#37-transformers-indicbert)
   - [Stable-Baselines3](#38-stable-baselines3)
   - [PettingZoo](#39-pettingzoo)
   - [NumPy / SciPy](#310-numpy--scipy)
4. [Infrastructure Technologies](#4-infrastructure-technologies)
   - [Docker + Docker Compose](#41-docker--docker-compose)
   - [Zookeeper](#42-zookeeper)
   - [Prometheus](#43-prometheus)
   - [Grafana](#44-grafana)
   - [MLflow](#45-mlflow)
   - [Hardhat](#46-hardhat)
   - [nginx](#47-nginx)
5. [External Services & APIs](#5-external-services--apis)
   - [Open-Meteo](#51-open-meteo)
   - [NASA Earthdata (CMR)](#52-nasa-earthdata-cmr)
   - [Sentinel-2 L2A (AWS)](#53-sentinel-2-l2a-aws)
   - [Twilio](#54-twilio)
   - [CartoDB / OpenStreetMap](#55-cartodb--openstreetmap)
6. [Technology Summary Table](#6-technology-summary-table)
7. [How Technologies Connect](#7-how-technologies-connect)

---

## 1. Backend Technologies

### 1.1 Python 3.11+

**What It Is:** A high-level, general-purpose programming language known for readability and a vast ecosystem of scientific computing and ML libraries.

**Role in HYDRA:** Python is the language for all 29 backend microservices. Every service — from data ingestion to ML prediction to blockchain anchoring — is written in Python.

**Why Python:**
- **ML ecosystem**: XGBoost, PyTorch, SHAP, scikit-learn, Whisper — all have first-class Python APIs
- **FastAPI/async**: Python 3.11's improved async performance makes it viable for real-time services
- **Rapid development**: Critical for hackathon timelines
- **Single language**: One language across all services reduces context switching

**Where It's Used:**
```
services/prediction/main.py          — Prediction service
services/alert_dispatcher/main.py    — Alert delivery
services/feature_engine/main.py      — Feature engineering
services/causal_engine/gnn.py        — Causal inference
services/chorus/nlp/analyzer.py      — NLP analysis
services/evacuation_rl/agent/        — Reinforcement learning
shared/config.py                     — Centralized configuration
shared/kafka_client.py               — Kafka wrapper
```

---

### 1.2 FastAPI

**What It Is:** A modern, high-performance Python web framework for building APIs. Built on Starlette (ASGI) and Pydantic, it provides automatic OpenAPI documentation, type validation, and native async support.

**Role in HYDRA:** FastAPI is the REST API framework for every microservice. Each service exposes endpoints that the dashboard, other services, and external systems consume.

**Why FastAPI (not Flask or Django):**
- **Performance**: ASGI-native, 3-10x faster than Flask for async workloads
- **Automatic docs**: Swagger UI at `/docs` for every service — invaluable during development
- **Type safety**: Pydantic integration validates request/response data at runtime
- **Async first**: Native `async/await` for non-blocking I/O (Kafka consumers, DB queries, HTTP calls)
- **Lifespan management**: Built-in startup/shutdown hooks for initializing ML models and consumers

**How It's Used:**

Service creation with lifespan context manager:
```python
# services/prediction/main.py
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start all consumers and background tasks on startup."""
    logger.info("prediction_service_starting", version="2.1.0")

    # Start Kafka consumer
    kafka_task = asyncio.create_task(start_prediction_consumer(...))

    # Start TimescaleDB feature consumer
    feature_task = asyncio.create_task(feature_consumer.start())

    # Seed demo predictions
    if DEMO_MODE and not _predictions_cache:
        _seed_demo_predictions()

    yield  # Service is running

    # Shutdown
    kafka_task.cancel()
    await feature_consumer.stop()

app = FastAPI(
    title="ARGUS Prediction Service",
    version="2.1.0",
    lifespan=lifespan,
)
```

Endpoint definition with path parameters:
```python
@app.get("/api/v1/prediction/{village_id}")
async def get_prediction(village_id: str):
    cached = _predictions_cache.get(village_id)
    if cached is not None:
        return cached
    raise HTTPException(status_code=404, detail=f"No prediction for {village_id}")
```

CORS middleware for dashboard access:
```python
# services/alert_dispatcher/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Services using FastAPI (all 29):**

| Service | Port | Key Endpoints |
|---|---|---|
| API Gateway | 8000 | `/api/v1/dashboard/snapshot`, `/api/v1/health/*` |
| Ingestion | 8001 | `POST /api/v1/ingest/gauge`, `/api/v1/ingest/weather` |
| CV Gauging | 8002 | `POST /api/v1/virtual-gauge/process` |
| Feature Engine | 8003 | `GET /api/v1/features/{station_id}/latest` |
| Prediction | 8004 | `GET /api/v1/predictions/all`, `/api/v1/prediction/{village_id}` |
| Alert Dispatcher | 8005 | `POST /api/v1/alert/send`, `GET /api/v1/alert/log` |
| Causal Engine | 8006 | `POST /api/v1/causal/intervene` |
| FloodLedger | 8007 | `GET /api/v1/ledger/summary` |
| CHORUS | 8008 | `GET /api/v1/chorus/signals` |
| Evacuation RL | 8010 | `POST /api/v1/evacuation/compute` |
| MIRROR | 8011 | `GET /api/v1/mirror/counterfactual/{event_id}` |
| ARGUS Copilot | 8016 | `POST /api/v1/copilot/chat` |

---

### 1.3 uvicorn

**What It Is:** A lightning-fast ASGI (Asynchronous Server Gateway Interface) server for Python. It serves FastAPI applications and handles HTTP connections with high concurrency.

**Role in HYDRA:** uvicorn is the production server that runs every FastAPI microservice. It handles incoming HTTP requests and routes them to FastAPI's async handlers.

**Why uvicorn (not gunicorn or waitress):**
- **ASGI native**: Supports async/await natively (gunicorn is WSGI-based)
- **HTTP/2 support**: Better performance for dashboard polling
- **Hot reload**: `--reload` flag for development
- **Lightweight**: Minimal overhead per connection

**How It's Used:**

Development (with hot reload):
```bash
uvicorn services.prediction.main:app --reload --port 8004
```

Production (in Docker):
```dockerfile
# services/prediction/Dockerfile
CMD ["uvicorn", "services.prediction.main:app", "--host", "0.0.0.0", "--port", "8004"]
```

Programmatic startup:
```python
# services/alert_dispatcher/main.py
if __name__ == "__main__":
    uvicorn.run(
        "services.alert_dispatcher.main:app",
        host="0.0.0.0",
        port=ALERT_PORT,
        reload=True,
    )
```

---

### 1.4 Apache Kafka

**What It Is:** A distributed event streaming platform. Originally developed at LinkedIn, Kafka handles high-throughput, low-latency data pipelines. Messages are organized into topics, and consumers can read from any point in the stream.

**Role in HYDRA:** Kafka is the central nervous system — the message bus that connects all microservices. When a gauge reading arrives, it flows through Kafka topics from ingestion to feature engineering to prediction to alert dispatch.

**Why Kafka (not RabbitMQ or Redis Pub/Sub):**
- **Durability**: Messages persist on disk — if prediction service restarts, it can replay missed messages
- **Ordering**: Messages within a partition maintain strict order (critical for time-series data)
- **Scalability**: Handles millions of messages/second (future-proofing for nationwide deployment)
- **Consumer groups**: Multiple services can independently consume the same topic
- **Replay**: Can re-process historical data for model retraining or debugging

**How It's Used:**

Kafka producer wrapper:
```python
# shared/kafka_client.py
class KafkaProducerClient:
    def __init__(self, client_id: str = "argus-producer") -> None:
        from confluent_kafka import Producer
        settings = get_settings()
        self._producer = Producer({
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "client.id": client_id,
            "acks": "all",          # Wait for all replicas to acknowledge
            "retries": 5,           # Retry on transient failures
            "linger.ms": 10,        # Batch messages for 10ms for throughput
        })

    def produce(self, topic: str, value: Dict[str, Any], key: Optional[str] = None) -> None:
        self._producer.produce(
            topic=topic,
            key=key.encode("utf-8") if key else None,
            value=json.dumps(value, default=str).encode("utf-8"),
            callback=self._delivery_report,
        )
```

Publishing predictions:
```python
# services/prediction/publishers/prediction_publisher.py
def _publish_kafka(self, village_id: str, prediction: Dict[str, Any]) -> None:
    topic = f"predictions.fast.{village_id}"
    self._kafka_producer.produce(topic=topic, key=village_id, value=prediction)
```

**Kafka Topics in HYDRA:**

| Topic Pattern | Producer | Consumer(s) | Data |
|---|---|---|---|
| `gauge.realtime` | Ingestion | Feature Engine | CWC gauge readings |
| `weather.api.imd` | Ingestion | Feature Engine | Rainfall, temperature |
| `cctv.frames.{camera_id}` | Ingestion | CV Gauging | CCTV frame metadata |
| `virtual.gauge.{camera_id}` | CV Gauging | Feature Engine | CV-derived water levels |
| `iot.*` | IoT Gateway | Feature Engine | Soil moisture, rainfall sensors |
| `features.vector.{station_id}` | Feature Engine | Prediction | 16-feature ML vectors |
| `predictions.fast.{village_id}` | Prediction | Alert Dispatcher, Dashboard | Flood risk scores |
| `alerts.dispatch` | Alert Dispatcher | Notification Hub | Alert payloads |
| `chorus.signal.{geohash}` | CHORUS | Prediction | Citizen flood reports |

**Infrastructure:**
```yaml
# docker-compose.yml
kafka:
  image: confluentinc/cp-kafka:7.6.0
  ports:
    - "9092:9092"
  environment:
    KAFKA_BROKER_ID: 1
    KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
    KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
    KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
```

---

### 1.5 TimescaleDB

**What It Is:** A PostgreSQL extension that turns PostgreSQL into a purpose-built time-series database. It adds hypertables (auto-partitioned by time), continuous aggregates, and compression — while keeping full SQL compatibility.

**Role in HYDRA:** TimescaleDB stores all time-series data: gauge readings, weather observations, feature vectors, predictions, and audit logs. The feature engine writes enriched features here, and the prediction service polls them.

**Why TimescaleDB (not InfluxDB or plain PostgreSQL):**
- **Full SQL**: Complex joins between time-series and relational data (villages, sensors)
- **Hypertables**: Automatic time-based partitioning for fast range queries
- **Compression**: 90%+ compression on historical data
- **PostgreSQL ecosystem**: All PostgreSQL tools, ORMs, and extensions work
- **Continuous aggregates**: Materialized views that auto-update (rolling averages)

**How It's Used:**

Connection DSN:
```python
# services/prediction/main.py
_TIMESCALE_DSN = os.getenv(
    "TIMESCALE_URL",
    "postgresql://argus:argus@localhost:5432/argus_db",
)
```

Feature consumer polling TimescaleDB:
```python
# services/prediction/consumers/feature_consumer.py
class FeatureConsumer:
    def __init__(self, dsn: str, on_features: Callable):
        self._dsn = dsn
        self._on_features = on_features

    async def start(self):
        """Poll TimescaleDB for new feature vectors every 60 seconds."""
        # Connects via asyncpg, queries latest features per station
        # Calls self._on_features(village_id, features, quality) for each
```

Audit log storage:
```python
# security/audit/audit_logger.py
# Table: argus_audit_log (TimescaleDB hypertable)
# Columns: timestamp, actor, action, resource, details, ip, user_agent, chain_hash
```

**Infrastructure:**
```yaml
# docker-compose.yml
timescaledb:
  image: timescale/timescaledb:latest-pg16
  ports:
    - "5432:5432"
  environment:
    POSTGRES_USER: argus
    POSTGRES_PASSWORD: argus
    POSTGRES_DB: argus_db
  volumes:
    - timescale_data:/var/lib/postgresql/data
```

---

### 1.6 Redis

**What It Is:** An in-memory data structure store used as a database, cache, message broker, and streaming engine. Redis stores data in RAM, making reads/writes sub-millisecond.

**Role in HYDRA:** Redis serves multiple purposes:
1. **Prediction cache**: Latest flood risk scores with 300-second TTL (fast dashboard reads)
2. **CHORUS trust scores**: Citizen credibility ratings
3. **Notification subscriptions**: Web Push subscription storage
4. **Multi-basin data**: Cross-basin comparison cache

**Why Redis (not Memcached or in-memory dict):**
- **Persistence**: Optional snapshotting means cache survives restarts
- **Data structures**: Sorted sets for leaderboards, hashes for structured data
- **Pub/Sub**: Real-time notification channels
- **Multiple databases**: Logical separation (db 0 for predictions, db 1 for trust scores)
- **Shared state**: Multiple service instances can share the same cache

**How It's Used:**

Prediction caching:
```python
# services/prediction/publishers/prediction_publisher.py
def _ensure_redis(self) -> None:
    import redis
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    self._redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
    self._redis_client.ping()  # Verify connection

def _publish_redis(self, village_id: str, prediction: Dict[str, Any]) -> None:
    """Cache prediction in Redis with TTL."""
    key = f"prediction:{village_id}"
    self._redis_client.setex(key, 300, json.dumps(prediction))  # 5-minute TTL
```

**Redis Database Layout:**

| DB | Purpose | TTL |
|---|---|---|
| db 0 | Prediction cache | 300 seconds |
| db 1 | CHORUS trust engine scores | Persistent |
| db 3 | Notification Hub subscriptions | Persistent |
| db 4 | Multi-Basin comparison data | 600 seconds |

**Infrastructure:**
```yaml
# docker-compose.yml
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
```

---

### 1.7 structlog

**What It Is:** A structured logging library for Python that outputs logs as key-value pairs (typically JSON). Instead of unstructured text like `"Processing village Majuli"`, structlog produces `{"event": "processing_village", "village": "Majuli", "risk_score": 0.81}`.

**Role in HYDRA:** structlog is the standard logging library across all 29 services. Every log line is a structured JSON object that can be queried, filtered, and aggregated by monitoring tools.

**Why structlog (not standard logging or loguru):**
- **Machine-readable**: JSON logs are parseable by Prometheus, Grafana Loki, and ELK
- **Context binding**: Attach request-scoped fields (village_id, risk_score) once, they appear in all subsequent logs
- **Performance**: Lazy evaluation — log fields are only serialized if the log level is active
- **Consistency**: Enforces a structured format across all services

**How It's Used:**

```python
# services/prediction/main.py
import structlog

logger = structlog.get_logger(__name__)

# Info with structured context
logger.info("demo_predictions_seeded", count=len(villages))

# Rich prediction logging
logger.info(
    "prediction_complete",
    village=village_id,
    risk_score=risk_score,
    alert_level=alert_level.value,
    confidence=confidence.value,
)

# Error with exception context
logger.exception("prediction_pipeline_error", village=village_id, error=str(exc))

# Warning for degraded state
logger.warning("twilio_unavailable", error=str(e))
```

**Output example (JSON):**
```json
{
  "event": "prediction_complete",
  "village": "VIL-AS-MAJULI",
  "risk_score": 0.81,
  "alert_level": "WARNING",
  "confidence": "HIGH",
  "timestamp": "2025-07-15T14:22:01Z",
  "logger": "services.prediction.main"
}
```

---

### 1.8 Pydantic

**What It Is:** A data validation library that uses Python type annotations to define data schemas. It validates, serializes, and documents data structures at runtime.

**Role in HYDRA:** Pydantic defines the data contracts between services. Every API request, response, Kafka message, and database record has a Pydantic model that ensures data integrity.

**Why Pydantic (not dataclasses or marshmallow):**
- **FastAPI integration**: FastAPI natively uses Pydantic for request/response validation
- **Auto-documentation**: Pydantic models generate OpenAPI schemas automatically
- **Validation**: Type coercion, range checks, regex patterns — all declarative
- **Serialization**: `.model_dump()` for JSON, `.model_dump(mode="json")` for API responses

**How It's Used:**

Prediction response model:
```python
# shared/models/prediction.py
from pydantic import BaseModel, Field
from enum import Enum

class RiskLevel(str, Enum):
    NORMAL = "NORMAL"
    WATCH = "WATCH"
    WARNING = "WARNING"
    DANGER = "DANGER"
    EXTREME = "EXTREME"

class SHAPExplanation(BaseModel):
    feature_name: str
    shap_value: float = Field(..., description="SHAP contribution (log-odds scale)")
    feature_value: float = Field(..., description="Actual feature value used")
    rank: int = Field(..., ge=1, description="Importance rank (1 = most important)")

class FloodPrediction(BaseModel):
    station_id: str = Field(..., description="Target station identifier")
    timestamp: datetime = Field(..., description="Prediction UTC timestamp")
    flood_probability: float = Field(..., ge=0.0, le=1.0)
    risk_level: RiskLevel
    lead_time_hours: float = Field(..., ge=0)
    explanation: List[SHAPExplanation] = Field(default_factory=list)
```

Alert request validation:
```python
# services/alert_dispatcher/main.py
class AlertRequest(BaseModel):
    village_id: str
    village_name: str = ""
    alert_level: str = Field(..., description="NORMAL|ADVISORY|WATCH|WARNING|EMERGENCY")
    risk_score: float = Field(0.0, ge=0, le=1)
    message: str = ""
    channels: List[str] = Field(default=["whatsapp", "sms"])
    phone_numbers: List[str] = Field(default=[])
    force: bool = Field(default=False, description="Bypass cooldown")
```

**Pydantic Model Modules:**

| Module | Key Models |
|---|---|
| `shared/models/ingestion.py` | GaugeReading, WeatherData, CCTVFrame |
| `shared/models/prediction.py` | FloodPrediction, SHAPExplanation, AlertPayload, PINNSensorReading |
| `shared/models/phase2.py` | CausalDAG, InterventionRequest, CounterfactualQuery |
| `shared/models/cv_gauging.py` | VirtualGaugeReading |
| `shared/models/feature_engine.py` | FeatureVector, TemporalFeatures, SpatialFeatures |

---

## 2. Frontend Technologies

### 2.1 React 18.3

**What It Is:** A JavaScript library for building user interfaces, developed by Meta. React uses a component-based architecture where the UI is composed of reusable, self-contained components that manage their own state.

**Role in HYDRA:** React powers the entire dashboard — the 12-tab interface that district officials use to monitor flood risk, view predictions, analyze causal factors, and manage evacuations.

**Why React (not Vue, Angular, or Svelte):**
- **Ecosystem**: Massive library ecosystem (react-leaflet, recharts, deck.gl)
- **Hooks**: `useState`, `useEffect`, `useCallback` for clean state management
- **Lazy loading**: `React.lazy()` + `Suspense` for code splitting heavy components
- **Community**: Largest developer community — easy to find solutions and contributors

**How It's Used:**

Root component with tab navigation:
```jsx
// dashboard/src/App.jsx
import { useState, useEffect, lazy, Suspense } from 'react'

// Phase 1 components (always loaded)
import ARGUSMap from './components/ARGUSMap'
import MetricsBar from './components/MetricsBar'
import AlertSidebar from './components/AlertSidebar'

// Phase 2 components (lazy-loaded — heavier panels)
const EvacuationMap = lazy(() => import('./components/EvacuationMap'))
const MirrorPanel = lazy(() => import('./components/MirrorPanel'))
const FloodLedger = lazy(() => import('./components/FloodLedger'))

export default function App() {
  const [demoMode, setDemoMode] = useState(true)
  const [activeTab, setActiveTab] = useState('risk_map')
  const [presenting, setPresenting] = useState(false)

  // Tab rendering
  return (
    <div className="min-h-screen bg-navy-dark text-white">
      <MetricsBar predictions={predictions} alerts={alerts} demoMode={demoMode} />
      <TabNavigation activeTab={activeTab} setActiveTab={setActiveTab} />
      <Suspense fallback={<LoadingPanel />}>
        {activeTab === 'risk_map' && <ARGUSMap predictions={predictions} />}
        {activeTab === 'evacuation' && <EvacuationMap />}
        {activeTab === 'mirror' && <MirrorPanel />}
      </Suspense>
      <AlertSidebar alerts={alerts} />
    </div>
  )
}
```

Custom hooks for data fetching:
```jsx
// dashboard/src/hooks/usePredictions.js
function usePredictions(demoMode) {
  const [predictions, setPredictions] = useState([])

  useEffect(() => {
    const interval = setInterval(async () => {
      const res = await axios.get('/api/v1/predictions/all')
      setPredictions(res.data)
    }, demoMode ? 5000 : 30000)  // 5s in demo, 30s in production
    return () => clearInterval(interval)
  }, [demoMode])

  return predictions
}
```

**Component Architecture:**

| Layer | Components | Purpose |
|---|---|---|
| Layout | App, MetricsBar, TabNavigation | Overall structure, navigation |
| Map | ARGUSMap, RiskLegend, ACNStatus, VillagePopup | Geospatial visualization |
| Panels | GaugeHeroPanel, NDMACompliancePanel, DisplacementMap | Tab-specific data views |
| Intelligence | MirrorPanel, EvacuationMap, FloodLedger, ChorusActivity | Phase 2 interactive panels |
| Overlay | ARGUSCopilot, PresentationMode, DemoController | LLM chat, demo controls |
| Sidebar | AlertSidebar | Real-time alert feed |

---

### 2.2 Vite 6.0

**What It Is:** A next-generation frontend build tool that provides instant dev server startup (using ES modules) and optimized production builds (using Rollup). Vite replaces webpack with dramatically faster build times.

**Role in HYDRA:** Vite serves the React dashboard in development with hot module replacement (HMR) and proxies API requests to backend services. In production, it builds optimized static assets.

**Why Vite (not webpack or Create React App):**
- **Speed**: Dev server starts in <1 second (webpack: 10-30 seconds)
- **HMR**: Component changes reflect in <100ms without full page reload
- **ES modules**: Uses native browser ES module support — no bundling during development
- **Proxy**: Built-in dev proxy for routing API calls to backend services
- **Plugin system**: First-class Tailwind CSS and React plugins

**How It's Used:**

Build configuration with 15+ proxy rules:
```javascript
// dashboard/vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  optimizeDeps: {
    include: ['leaflet', 'react-leaflet'],  // Pre-bundle map libraries
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      // Phase 1 — Core pipeline
      '/api/v1/ingest':       { target: 'http://localhost:8001', changeOrigin: true },
      '/api/v1/virtual-gauge':{ target: 'http://localhost:8002', changeOrigin: true },
      '/api/v1/features':     { target: 'http://localhost:8003', changeOrigin: true },
      '/api/v1/predict':      { target: 'http://localhost:8004', changeOrigin: true },
      '/api/v1/alerts':       { target: 'http://localhost:8005', changeOrigin: true },

      // Phase 2 — Intelligence layer
      '/api/v1/causal':       { target: 'http://localhost:8006', changeOrigin: true },
      '/api/v1/ledger':       { target: 'http://localhost:8007', changeOrigin: true },
      '/api/v1/chorus':       { target: 'http://localhost:8008', changeOrigin: true },
      '/api/v1/fl':           { target: 'http://localhost:8009', changeOrigin: true },
      '/api/v1/evacuation':   { target: 'http://localhost:8010', changeOrigin: true },
      '/api/v1/mirror':       { target: 'http://localhost:8011', changeOrigin: true },
      '/api/v1/scarnet':      { target: 'http://localhost:8012', changeOrigin: true },
      '/api/v1/monitor':      { target: 'http://localhost:8013', changeOrigin: true },
      '/api/v1/copilot':      { target: 'http://localhost:8016', changeOrigin: true },

      // Fallback — API Gateway
      '/api':                 { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
```

**Why the proxy matters:** The browser makes requests to `localhost:3000/api/v1/predictions/all`. Vite intercepts this and forwards it to `localhost:8004` (the prediction service). This avoids CORS issues and mimics a production reverse proxy setup.

---

### 2.3 Tailwind CSS 4.0

**What It Is:** A utility-first CSS framework that provides low-level utility classes (like `bg-blue-500`, `text-xl`, `flex`, `p-4`) instead of pre-built components. You compose designs directly in HTML/JSX instead of writing custom CSS.

**Role in HYDRA:** Tailwind styles the entire dashboard and PWA mobile app. The dark theme, responsive layout, status colors, and glassmorphism effects are all built with Tailwind utilities.

**Why Tailwind (not Bootstrap, Material UI, or plain CSS):**
- **No context switching**: Styles are inline with JSX — no separate CSS files
- **Dark theme**: Easy to build dark-themed dashboards with `bg-slate-900` utilities
- **Responsive**: Mobile-first breakpoints (`sm:`, `md:`, `lg:`) for PWA
- **Customizable**: Extended with ARGUS brand colors and fonts
- **Small bundle**: Purges unused classes — final CSS is typically <10KB

**How It's Used:**

Custom theme configuration:
```javascript
// mobile/pwa/tailwind.config.js
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        argus: {
          bg:      '#050d1a',     // Deep navy background
          surface: '#0a1628',     // Card surface
          card:    '#111d32',     // Elevated card
          border:  '#1a2d4a',     // Subtle borders
          accent:  '#00c9ff',     // Primary cyan accent
          cyan:    '#00e5ff',     // Bright cyan
          green:   '#00e676',     // Safe/normal
          yellow:  '#ffd600',     // Advisory/watch
          orange:  '#ff9100',     // Warning
          red:     '#ff1744',     // Emergency/danger
          text:    '#e0e7ef',     // Primary text
          muted:   '#8899aa',     // Secondary text
        },
      },
      fontFamily: {
        exo2:     ['"Exo 2"', 'sans-serif'],
        rajdhani: ['Rajdhani', 'sans-serif'],
      },
    },
  },
}
```

Component styling example:
```jsx
// Glassmorphism header bar
<div className="bg-navy-light/90 backdrop-blur-md border-b border-white/10 flex items-center justify-between px-4 z-40">
  <h1 className="font-heading text-xl font-bold tracking-wider">
    <span className="text-accent">ARGUS</span>
    <span className="text-muted ml-2 text-sm">v3.0.0</span>
  </h1>
</div>

// Alert level badge with dynamic color
<span className={`px-2 py-1 rounded text-xs font-bold ${
  level === 'EMERGENCY' ? 'bg-red-600 text-white' :
  level === 'WARNING'   ? 'bg-orange-500 text-black' :
  level === 'WATCH'     ? 'bg-yellow-500 text-black' :
                          'bg-green-600 text-white'
}`}>
  {level}
</span>
```

---

### 2.4 Leaflet 1.9.4

**What It Is:** An open-source JavaScript library for interactive maps. It's lightweight (~42KB gzipped), mobile-friendly, and works with multiple tile providers (OpenStreetMap, CartoDB, Mapbox).

**Role in HYDRA:** Leaflet renders the Risk Map — the primary dashboard view showing all 12 villages as color-coded circle markers on a dark-themed map. Officials click villages to see risk details, SHAP explanations, and evacuation routes.

**Why Leaflet (not Mapbox GL JS or Google Maps):**
- **Free**: No API key required (uses CartoDB/OSM tiles)
- **Lightweight**: 42KB vs Mapbox GL's 200KB+
- **Open source**: No vendor lock-in or usage limits
- **Plugin ecosystem**: Heatmaps, clustering, drawing tools
- **react-leaflet**: First-class React integration

**How It's Used:**

Map tile configuration:
```javascript
// dashboard/src/components/map/LeafletConfig.js
const TILE_LAYERS = {
  dark: {
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attribution: '&copy; OSM contributors &copy; CARTO',
    maxZoom: 19,
  },
  satellite: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: '&copy; Esri',
    maxZoom: 18,
  },
}
```

Risk map with village markers:
```jsx
// dashboard/src/components/ARGUSMap.jsx
<MapContainer center={[30.5, 80.5]} zoom={7} zoomControl={false}>
  <TileLayer url={TILE_LAYERS.dark.url} attribution={TILE_LAYERS.dark.attribution} />
  <ZoomControl position="bottomright" />

  {predictions.map((village) => (
    <CircleMarker
      key={village.id}
      center={[village.lat, village.lon]}
      radius={riskRadius(village.risk_score)}        // 8-20px based on risk
      pathOptions={{
        fillColor: riskColor(village.risk_score),      // green→yellow→orange→red
        fillOpacity: 0.9,
        color: borderColor(village.alert_level),
        weight: 1.5,
      }}
    >
      <Tooltip permanent={level === 'EMERGENCY'}>
        {level} — {village.name}
      </Tooltip>
      <Popup><VillagePopup village={village} /></Popup>
    </CircleMarker>
  ))}
</MapContainer>
```

---

### 2.5 react-leaflet 4.2.1

**What It Is:** A React wrapper for Leaflet that provides React components (`<MapContainer>`, `<TileLayer>`, `<CircleMarker>`, etc.) instead of imperative Leaflet API calls. It manages Leaflet instances through React's lifecycle.

**Role in HYDRA:** react-leaflet bridges React's declarative component model with Leaflet's imperative API. When predictions update (risk scores change), React re-renders the circle markers with new colors and sizes — without manually calling Leaflet methods.

**Why react-leaflet (not raw Leaflet or react-map-gl):**
- **Declarative**: Map elements are JSX components, not imperative API calls
- **React lifecycle**: Map state syncs with React state automatically
- **Composable**: Nest `<CircleMarker>`, `<Popup>`, `<Tooltip>` as children
- **Type-safe**: Full TypeScript support

**Key Components Used:**

| Component | Purpose in HYDRA |
|---|---|
| `MapContainer` | Root map container with center, zoom, style |
| `TileLayer` | CartoDB dark tiles or satellite imagery |
| `CircleMarker` | Village risk indicator (color + size = risk level) |
| `Popup` | Click-triggered village details with SHAP bars |
| `Tooltip` | Hover label showing village name and alert level |
| `ZoomControl` | Positioned at bottom-right |
| `useMap` | Hook for programmatic zoom/pan |

---

### 2.6 Recharts 2.15

**What It Is:** A composable charting library built on React components and D3. It provides `<LineChart>`, `<BarChart>`, `<AreaChart>`, and more as React components with responsive containers.

**Role in HYDRA:** Recharts renders the data visualizations across multiple dashboard tabs:
- **MirrorPanel**: Time series of predicted vs actual water levels with intervention slider
- **VillagePopup**: SHAP contribution bar charts
- **LiveValidationPanel**: Predicted vs observed scatter plots
- **GaugeHeroPanel**: Water level trend lines

**Why Recharts (not Chart.js, Nivo, or D3 directly):**
- **React-native**: Components instead of canvas manipulation
- **Composable**: Mix `<Line>`, `<Bar>`, `<ReferenceLine>` in the same chart
- **Responsive**: `<ResponsiveContainer>` auto-sizes to parent
- **Tooltips**: Built-in interactive tooltips
- **Lightweight**: Smaller than Nivo, more React-friendly than Chart.js

**How It's Used:**

Counterfactual time series (MirrorPanel):
```jsx
// dashboard/src/components/MirrorPanel.jsx
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, ReferenceLine
} from 'recharts'

<ResponsiveContainer width="100%" height={250}>
  <LineChart data={sliderData}>
    <CartesianGrid strokeDasharray="3 3" stroke="#1a2d4a" />
    <XAxis dataKey="time_before_peak_min" stroke="#8899aa" />
    <YAxis stroke="#8899aa" />
    <Tooltip />
    <Legend />
    <ReferenceLine x={sliderValue} stroke="#ffd600" strokeWidth={2} />
    <Line type="monotone" dataKey="predicted_water_level_m"
          stroke="#00c9ff" strokeWidth={2} name="Predicted" />
    <Line type="monotone" dataKey="actual_water_level_m"
          stroke="#ef4444" strokeWidth={2} name="Actual" />
  </LineChart>
</ResponsiveContainer>
```

SHAP explanation bar chart (VillagePopup):
```jsx
// dashboard/src/components/VillagePopup.jsx
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

<ResponsiveContainer width="100%" height={120}>
  <BarChart data={shapData} layout="vertical">
    <XAxis type="number" />
    <YAxis dataKey="feature" type="category" width={120} />
    <Bar dataKey="shap_value" fill="#00c9ff" />
  </BarChart>
</ResponsiveContainer>
```

---

### 2.7 Axios 1.7

**What It Is:** A promise-based HTTP client for the browser and Node.js. It provides a clean API for making HTTP requests with automatic JSON parsing, request/response interceptors, and timeout handling.

**Role in HYDRA:** Axios is the HTTP client used by all React components and custom hooks to fetch data from the 15+ backend API endpoints.

**Why Axios (not fetch API):**
- **Interceptors**: Global error handling, auth token injection
- **Timeout**: Built-in request timeout (fetch requires AbortController)
- **JSON auto-parsing**: Responses are automatically parsed from JSON
- **Error handling**: Non-2xx responses throw errors (fetch doesn't)
- **Browser compatibility**: Consistent behavior across browsers

**How It's Used:**

API configuration:
```javascript
// dashboard/src/config/api.js
const API = {
  predictionsAll:    '/api/v1/predictions/all',
  prediction:        (id) => `/api/v1/prediction/${id}`,
  predictionDeep:    (id) => `/api/v1/prediction/${id}/deep`,
  alertLog:          '/api/v1/alert/log',
  alertStats:        '/api/v1/alert/stats',
  causalRisk:        (id) => `/api/v1/causal/${id}`,
  causalIntervene:   '/api/v1/causal/intervene',
  evacuationPlan:    (id) => `/api/v1/evacuation/plan/${id}`,
  mirrorCounterfactual: (id) => `/api/v1/mirror/counterfactual/${id}`,
  chorusSignals:     '/api/v1/chorus/signals',
  ledgerSummary:     '/api/v1/ledger/summary',
  copilotChat:       '/api/v1/copilot/chat',
  gatewayHealth:     '/api/v1/health',
  // ... 50+ endpoints total
}
```

Data fetching in components:
```jsx
// dashboard/src/components/SystemHealth.jsx
import axios from 'axios'

const fetchHealth = useCallback(async () => {
  try {
    const res = await axios.get(API.gatewayHealth)
    setHealth(res.data)
  } catch {
    setHealth({ overall: 'OPERATIONAL', services: mockServices })
  }
}, [])
```

---

### 2.8 deck.gl 9.x

**What It Is:** A GPU-powered visualization framework by Uber for large-scale geospatial data. It renders millions of data points using WebGL with minimal CPU overhead.

**Role in HYDRA:** deck.gl was originally used for high-density flood visualization (heatmaps, flow maps). It has been replaced by Leaflet for the primary map, but remains available for specialized GPU-accelerated visualizations like the displacement flow map.

**Current Status:** Listed in `package.json` dependencies. The primary map migrated from MapBox + deck.gl to Leaflet + OpenStreetMap for simplicity and zero-cost operation.

**Packages included:** `@deck.gl/core`, `@deck.gl/layers`, `@deck.gl/react`, `@deck.gl/aggregation-layers`

---

## 3. ML / AI Libraries

### 3.1 XGBoost

**What It Is:** Extreme Gradient Boosting — an optimized gradient boosting library that builds ensembles of decision trees. The fastest and most accurate algorithm for tabular data.

**Role in HYDRA:** Primary flood prediction engine. Takes 16 real-time features and outputs a flood probability (0.0-1.0) in under 1 millisecond.

**File:** `services/prediction/fast_track/xgboost_predictor.py`

---

### 3.2 SHAP

**What It Is:** SHapley Additive exPlanations — a game-theoretic approach to explain ML predictions by computing per-feature contribution values.

**Role in HYDRA:** Explains every prediction. "Why does Majuli have 81% risk?" → "Rainfall contributed +25%, soil moisture +18%, upstream risk +12%."

**File:** `services/prediction/fast_track/shap_explainer.py`

---

### 3.3 PyTorch

**What It Is:** An open-source deep learning framework by Meta. Provides tensors with GPU acceleration and automatic differentiation for building neural networks.

**Role in HYDRA:** Powers the PINN (virtual sensors), Causal GNN (causal inference), Oracle v2 (edge transformer), and serves as the backend for TFT training. Uses `torch.autograd` for physics-informed training.

**Files:** `services/prediction/pinn.py`, `services/causal_engine/gnn.py`, `services/oracle_v2/mobile_flood_former.py`

---

### 3.4 PyTorch Lightning

**What It Is:** A lightweight PyTorch wrapper that eliminates boilerplate code for training loops, distributed training, mixed precision, and logging.

**Role in HYDRA:** Used for training the TFT (Temporal Fusion Transformer) model with proper checkpointing, early stopping, and MLflow integration.

**File:** `training/tft_trainer/train.py`

---

### 3.5 Ultralytics (YOLOv11)

**What It Is:** The Ultralytics library provides YOLOv11, the latest real-time object detection model. The "nano" variant runs at 30+ FPS on CPU.

**Role in HYDRA:** Detects water surfaces in CCTV frames, turning every surveillance camera near a river into a virtual water level gauge.

**File:** `services/cv_gauging/main.py`, **Model:** `models/yolo11n.pt`

---

### 3.6 OpenAI Whisper

**What It Is:** An automatic speech recognition model trained on 680,000 hours of multilingual audio. Supports 97 languages with automatic language detection.

**Role in HYDRA:** Transcribes citizen voice notes from WhatsApp into text for NLP classification. Supports Hindi, Assamese, Bengali, and English.

**File:** `services/chorus/nlp/whisper_transcriber.py`, **Model:** `whisper-base` (77M params)

---

### 3.7 Transformers (IndicBERT)

**What It Is:** Hugging Face Transformers library with the `ai4bharat/indic-bert` model — a multilingual BERT trained on 12 Indian languages.

**Role in HYDRA:** Classifies citizen flood reports into 12 categories (ACTIVE_FLOOD, PEOPLE_STRANDED, ROAD_BLOCKED, etc.) regardless of language.

**File:** `services/chorus/nlp/indic_classifier.py`, **Model:** `models/indic_bert_flood_classifier/`

---

### 3.8 Stable-Baselines3

**What It Is:** A set of reliable reinforcement learning implementations in PyTorch. Provides PPO, A2C, DQN, and other algorithms.

**Role in HYDRA:** Trains and runs the PPO evacuation routing agent that optimally assigns vehicles to villages and routes them to shelters.

**File:** `services/evacuation_rl/agent/ppo_agent.py`, **Model:** `models/evac_ppo.zip`

---

### 3.9 PettingZoo

**What It Is:** A multi-agent reinforcement learning environment library (like Gymnasium but for multiple agents).

**Role in HYDRA:** Defines the multi-agent evacuation environment where district coordinators (agents) coordinate vehicle dispatch, route selection, and shelter assignment.

**File:** `services/evacuation_rl/environment/flood_env.py`

---

### 3.10 NumPy / SciPy

**What It Is:** NumPy provides N-dimensional arrays and mathematical operations. SciPy builds on NumPy with scientific computing algorithms (optimization, interpolation, statistics).

**Role in HYDRA:** Used throughout as the foundation for:
- Kalman filter state estimation (`services/feature_engine/kalman_filter.py`)
- PINN fallback (Inverse-Distance Weighting interpolation)
- Causal GNN fallback (Structural Equation Model propagation)
- Feature engineering (rolling windows, normalization)
- Synthetic data generation

---

## 4. Infrastructure Technologies

### 4.1 Docker + Docker Compose

**What It Is:** Docker packages applications into containers — isolated, portable environments that include everything needed to run. Docker Compose orchestrates multi-container applications with a single YAML file.

**Role in HYDRA:** Docker containerizes all 29 services + infrastructure (Kafka, TimescaleDB, Redis, Prometheus, Grafana, MLflow). `docker compose up` starts the entire system.

**Why Docker (not bare metal or Kubernetes for dev):**
- **Reproducibility**: Same environment on every machine
- **Isolation**: Each service has its own dependencies
- **One-command startup**: `docker compose up --build` starts everything
- **Infrastructure as code**: `docker-compose.yml` documents the entire architecture

**How It's Used:**

Multi-stage dashboard build:
```dockerfile
# dashboard/Dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY dashboard/ .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
```

Python service build:
```dockerfile
# services/prediction/Dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ shared/
COPY services/prediction/ services/prediction/
COPY data/ data/
COPY models/ models/
EXPOSE 8004
CMD ["uvicorn", "services.prediction.main:app", "--host", "0.0.0.0", "--port", "8004"]
```

**Docker Compose services (25+):**

| Category | Services |
|---|---|
| Infrastructure | Zookeeper, Kafka, TimescaleDB, Redis |
| Monitoring | Prometheus, Grafana |
| ML | MLflow |
| Blockchain | Hardhat |
| Backend | 29 Python microservices (ports 8000-8025) |
| Frontend | Dashboard (nginx, port 3000) |

---

### 4.2 Zookeeper

**What It Is:** Apache ZooKeeper is a centralized coordination service for distributed systems. It manages configuration, naming, synchronization, and group services.

**Role in HYDRA:** Zookeeper coordinates the Kafka broker — managing broker registration, partition leadership, and consumer group membership.

**Why Zookeeper (not KRaft):**
- **Kafka 7.6 default**: The Confluent Kafka image uses Zookeeper by default
- **Proven stability**: Zookeeper has been battle-tested in Kafka deployments for years
- **Simple setup**: Single-node Zookeeper is sufficient for development/hackathon

**Infrastructure:**
```yaml
# docker-compose.yml
zookeeper:
  image: confluentinc/cp-zookeeper:7.6.0
  ports:
    - "2181:2181"
  environment:
    ZOOKEEPER_CLIENT_PORT: 2181
    ZOOKEEPER_TICK_TIME: 2000
```

---

### 4.3 Prometheus

**What It Is:** An open-source monitoring and alerting toolkit. Prometheus scrapes metrics from services at regular intervals, stores them in a time-series database, and provides a query language (PromQL) for analysis.

**Role in HYDRA:** Prometheus collects performance and operational metrics from all services — prediction latency, alert dispatch rates, Kafka consumer lag, model inference times, and error rates.

**How It's Used:**

Scraping configuration:
```yaml
# infra/monitoring/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: "argus-gateway"
    static_configs:
      - targets: ["api_gateway:8000"]
    metrics_path: /metrics

  - job_name: "argus-prediction"
    static_configs:
      - targets: ["prediction:8004"]
    metrics_path: /metrics

  - job_name: "argus-alert-dispatcher"
    static_configs:
      - targets: ["alert_dispatcher:8005"]
    metrics_path: /metrics
```

Alert rules:
```yaml
# infra/monitoring/prometheus_rules.yml
groups:
  - name: argus_alerts
    rules:
      - alert: PredictionLatencyHigh
        expr: histogram_quantile(0.95, rate(argus_prediction_latency_seconds_bucket[5m])) > 0.05
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Prediction p95 latency exceeds 50ms"
```

**Infrastructure:**
```yaml
# docker-compose.yml
prometheus:
  image: prom/prometheus:v2.51.0
  ports:
    - "9090:9090"
  volumes:
    - ./infra/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
    - ./infra/monitoring/prometheus_rules.yml:/etc/prometheus/rules.yml
  command:
    - "--config.file=/etc/prometheus/prometheus.yml"
    - "--storage.tsdb.retention.time=30d"
```

---

### 4.4 Grafana

**What It Is:** An open-source analytics and visualization platform. Grafana connects to data sources like Prometheus and renders real-time dashboards with gauges, graphs, tables, and heatmaps.

**Role in HYDRA:** Grafana provides the operations dashboard — SLA monitoring, prediction latency gauges, alert throughput graphs, and service health panels. Separate from the user-facing React dashboard.

**How It's Used:**

Pre-configured dashboard:
```json
// infra/monitoring/grafana_dashboard.json
{
  "description": "ARGUS Flood Early Warning System — Production SLA Dashboard",
  "panels": [
    {
      "title": "Prediction Latency p95",
      "description": "SLA Target: < 50ms",
      "type": "gauge",
      "datasource": { "type": "prometheus" },
      "fieldConfig": {
        "defaults": {
          "unit": "ms",
          "thresholds": {
            "steps": [
              { "color": "green", "value": null },
              { "color": "yellow", "value": 30 },
              { "color": "orange", "value": 50 },
              { "color": "red", "value": 100 }
            ]
          }
        }
      },
      "targets": [{
        "expr": "histogram_quantile(0.95, sum(rate(argus_prediction_latency_seconds_bucket[5m])) by (le)) * 1000"
      }]
    }
  ]
}
```

**Infrastructure:**
```yaml
# docker-compose.yml
grafana:
  image: grafana/grafana:10.4.0
  ports:
    - "3001:3000"
  environment:
    GF_SECURITY_ADMIN_PASSWORD: argus
    GF_USERS_ALLOW_SIGN_UP: "false"
  volumes:
    - ./infra/monitoring/grafana_dashboard.json:/var/lib/grafana/dashboards/argus.json
  depends_on:
    - prometheus
```

---

### 4.5 MLflow

**What It Is:** An open-source platform for managing the ML lifecycle — experiment tracking, model registry, and deployment. It logs metrics, parameters, and artifacts for every training run.

**Role in HYDRA:** MLflow tracks model training experiments for XGBoost, TFT, and PINN models. Each training run logs hyperparameters, loss curves, validation metrics, and model checkpoints.

**How It's Used:**

TFT training with MLflow logging:
```python
# training/tft_trainer/train.py
import mlflow
import pytorch_lightning as pl
from pytorch_forecasting import TemporalFusionTransformer

def train_tft_for_basin(basin_id, data, max_epochs=50, learning_rate=0.001):
    with mlflow.start_run(run_name=f"tft_{basin_id}"):
        mlflow.log_params({
            "basin": basin_id,
            "max_epochs": max_epochs,
            "learning_rate": learning_rate,
        })

        trainer = pl.Trainer(max_epochs=max_epochs, callbacks=[...])
        trainer.fit(model, train_dataloader, val_dataloader)

        mlflow.log_metrics({
            "val_loss": trainer.callback_metrics["val_loss"],
            "val_mae": trainer.callback_metrics["val_mae"],
        })
        mlflow.pytorch.log_model(model, "tft_model")
```

**Infrastructure:**
```yaml
# docker-compose.yml
mlflow:
  image: ghcr.io/mlflow/mlflow:v2.12.1
  ports:
    - "5000:5000"
  command: >
    mlflow server
    --host 0.0.0.0 --port 5000
    --backend-store-uri postgresql://argus:argus@timescaledb:5432/mlflow
    --default-artifact-root /mlflow/artifacts
```

**Access:** `http://localhost:5000` — MLflow UI for browsing experiments, comparing runs, and downloading model artifacts.

---

### 4.6 Hardhat

**What It Is:** An Ethereum development environment for compiling, deploying, testing, and debugging Solidity smart contracts. Includes a local Ethereum node for testing.

**Role in HYDRA:** Hardhat runs a local Ethereum blockchain for FloodLedger — the parametric insurance oracle. When flood risk exceeds a threshold, the smart contract automatically records the event and triggers insurance payouts.

**How It's Used:**

Hardhat configuration:
```javascript
// services/flood_ledger/hardhat.config.js
require("@nomicfoundation/hardhat-toolbox");

module.exports = {
  solidity: "0.8.19",
  networks: {
    localhost: {
      url: "http://localhost:8545",
    },
  },
  paths: {
    sources: "./contracts",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts",
  },
};
```

FloodLedger smart contract:
```solidity
// services/flood_ledger/contracts/FloodLedger.sol
pragma solidity ^0.8.19;

contract FloodLedger {
    struct FloodEvent {
        uint256 id;
        string basinId;
        uint256 timestamp;
        uint256 riskScore;          // basis points (0-10000)
        string alertLevel;
        bool payoutTriggered;
        uint256 payoutAmountWei;
    }

    uint256 public payoutThreshold;
    mapping(uint256 => FloodEvent) public events;

    function recordFloodEvent(
        string memory basinId,
        uint256 riskScore,
        string memory alertLevel
    ) external onlyOwner returns (uint256) {
        eventCount++;
        events[eventCount] = FloodEvent({
            id: eventCount,
            basinId: basinId,
            timestamp: block.timestamp,
            riskScore: riskScore,
            alertLevel: alertLevel,
            payoutTriggered: riskScore >= payoutThreshold,
            payoutAmountWei: 0
        });
        emit FloodRecorded(eventCount, basinId, riskScore);
    }
}
```

**Local node:** `http://localhost:8545` — Hardhat Network provides instant block mining and configurable accounts for testing.

---

### 4.7 nginx

**What It Is:** A high-performance HTTP server and reverse proxy. In production, nginx sits in front of all services, handling TLS termination, load balancing, rate limiting, and static file serving.

**Role in HYDRA:**
1. **Production reverse proxy**: Routes all API traffic to backend services with rate limiting
2. **TLS termination**: Handles HTTPS certificates
3. **Dashboard serving**: Serves the React build as static files
4. **WebSocket proxy**: Forwards real-time update connections
5. **Security headers**: HSTS, X-Content-Type-Options, X-Frame-Options

**How It's Used:**

Production configuration:
```nginx
# infra/nginx/argus.conf

# Rate limiting zones
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=30r/s;
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=5r/s;

# Upstream definitions
upstream api_gateway {
    least_conn;
    server argus-api-gateway:8000;
    keepalive 32;
}

# API Server — HTTPS
server {
    listen 443 ssl http2;
    server_name api.argus.flood.gov.in;

    ssl_certificate     /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    # API proxying with rate limiting
    location /api/ {
        limit_req zone=api_limit burst=50 nodelay;
        proxy_pass http://api_gateway;
        proxy_http_version 1.1;
    }

    # WebSocket endpoint
    location /ws/ {
        proxy_pass http://api_gateway;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    # Auth endpoints (stricter rate limiting)
    location /api/v1/auth/ {
        limit_req zone=auth_limit burst=10 nodelay;
        proxy_pass http://api_gateway;
    }
}

# Dashboard — SPA with cache
server {
    listen 443 ssl http2;
    server_name dashboard.argus.flood.gov.in;
    root /var/www/dashboard;

    location / {
        try_files $uri $uri/ /index.html;  # SPA fallback
    }

    location ~* \.(js|css|png|jpg|svg)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

---

## 5. External Services & APIs

### 5.1 Open-Meteo

**What It Is:** A free, open-source weather API providing global meteorological data without authentication.

**Role in HYDRA:** Provides real-time and forecast rainfall, temperature, humidity, and wind data for the Beas and Brahmaputra basins.

| Attribute | Value |
|---|---|
| **URL** | `https://api.open-meteo.com/v1/forecast` |
| **Auth** | None required |
| **Cost** | Free, no rate limits |
| **Data** | Hourly rainfall, temperature, humidity, wind speed |
| **Used by** | Ingestion Service (port 8001) |

---

### 5.2 NASA Earthdata (CMR)

**What It Is:** NASA's Common Metadata Repository providing access to satellite imagery including HLSL30 (Harmonized Landsat Sentinel-2).

**Role in HYDRA:** Provides satellite imagery for ScarNet terrain monitoring — detecting deforestation, slope failure, and riverbed migration.

| Attribute | Value |
|---|---|
| **URL** | `https://cmr.earthdata.nasa.gov/search/` |
| **Auth** | Bearer JWT token (free registration) |
| **Cost** | Free |
| **Data** | Sentinel-2 / Landsat imagery metadata and download links |
| **Used by** | ScarNet Service (port 8012) |

---

### 5.3 Sentinel-2 L2A (AWS)

**What It Is:** Copernicus Sentinel-2 satellite imagery hosted as an open dataset on AWS S3.

**Role in HYDRA:** Direct access to multi-spectral satellite imagery (10m resolution) for before/after terrain comparison.

| Attribute | Value |
|---|---|
| **Bucket** | `sentinel-s2-l2a` (eu-central-1) |
| **Auth** | None (public open data) |
| **Cost** | Free |
| **Data** | RGB, NIR, SWIR bands at 10-20m resolution |
| **Used by** | ScarNet Service (port 8012) |

---

### 5.4 Twilio

**What It Is:** A cloud communications platform providing SMS, WhatsApp, voice, and video APIs.

**Role in HYDRA:** Delivers flood alerts via WhatsApp and SMS to field officers, district administrators, and affected communities.

| Attribute | Value |
|---|---|
| **Auth** | Account SID + Auth Token |
| **Cost** | Trial: $15 credit (requires card for upgrade) |
| **Channels** | WhatsApp, SMS, IVRS (voice) |
| **Used by** | Alert Dispatcher (port 8005) |

---

### 5.5 CartoDB / OpenStreetMap

**What It Is:** CartoDB provides free dark-themed map tiles. OpenStreetMap provides the underlying geographic data.

**Role in HYDRA:** Provides the map tiles for the Risk Map dashboard — the dark background over which village markers and risk indicators are rendered.

| Attribute | Value |
|---|---|
| **URL** | `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png` |
| **Auth** | None required |
| **Cost** | Free |
| **Used by** | Dashboard ARGUSMap component |

---

## 6. Technology Summary Table

| Technology | Category | Version | Purpose | Cost | Required |
|---|---|---|---|---|---|
| **Python** | Language | 3.11+ | All backend services | Free | Yes |
| **FastAPI** | Framework | Latest | REST API framework | Free | Yes |
| **uvicorn** | Server | Latest | ASGI server | Free | Yes |
| **Apache Kafka** | Messaging | 7.6.0 | Event streaming | Free | Yes |
| **TimescaleDB** | Database | pg16 | Time-series storage | Free | Yes |
| **Redis** | Cache | 7 | Prediction cache | Free | Yes |
| **structlog** | Logging | Latest | Structured logging | Free | Yes |
| **Pydantic** | Validation | v2 | Data schemas | Free | Yes |
| **React** | Frontend | 18.3 | Dashboard UI | Free | Yes |
| **Vite** | Build Tool | 6.0 | Dev server + build | Free | Yes |
| **Tailwind CSS** | Styling | 4.0 | Utility-first CSS | Free | Yes |
| **Leaflet** | Maps | 1.9.4 | Interactive maps | Free | Yes |
| **react-leaflet** | Maps | 4.2.1 | React + Leaflet | Free | Yes |
| **Recharts** | Charts | 2.15 | Data visualization | Free | Yes |
| **Axios** | HTTP | 1.7 | API client | Free | Yes |
| **deck.gl** | Viz | 9.x | GPU visualization | Free | Optional |
| **XGBoost** | ML | Latest | Flood prediction | Free | Yes |
| **SHAP** | XAI | Latest | Explainability | Free | Yes |
| **PyTorch** | ML | Latest | Deep learning | Free | Yes |
| **Docker** | Infra | Latest | Containerization | Free | Yes |
| **Zookeeper** | Infra | 7.6.0 | Kafka coordination | Free | Yes |
| **Prometheus** | Monitoring | 2.51.0 | Metrics collection | Free | Optional |
| **Grafana** | Monitoring | 10.4.0 | Dashboards | Free | Optional |
| **MLflow** | ML Ops | 2.12.1 | Experiment tracking | Free | Optional |
| **Hardhat** | Blockchain | Latest | Smart contracts | Free | Optional |
| **nginx** | Server | Alpine | Reverse proxy | Free | Production only |
| **Open-Meteo** | API | - | Weather data | Free | Yes |
| **NASA Earthdata** | API | - | Satellite imagery | Free | Optional |
| **Twilio** | API | - | SMS/WhatsApp | Trial free | Optional |
| **CartoDB/OSM** | API | - | Map tiles | Free | Yes |

---

## 7. How Technologies Connect

```
┌─ EXTERNAL APIs ──────────────────────────────────────────┐
│  Open-Meteo (weather)  NASA Earthdata (satellite)        │
│  CartoDB/OSM (tiles)   Twilio (SMS/WhatsApp)             │
└───────────────────────────┬──────────────────────────────┘
                            │
                            ▼
┌─ INGESTION (Python + FastAPI + uvicorn) ─────────────────┐
│  Ingestion:8001  →  Kafka Producer  →  gauge.realtime    │
│  CV Gauging:8002 →  Kafka Producer  →  virtual.gauge.*   │
│  IoT Gateway:8020 → Kafka Producer  →  iot.*             │
└───────────────────────────┬──────────────────────────────┘
                            │ Apache Kafka (event bus)
                            ▼
┌─ PROCESSING (Python + FastAPI + XGBoost + PyTorch) ──────┐
│  Feature Engine:8003                                      │
│    Kafka Consumer → Kalman Filter (NumPy)                │
│                   → PINN Mesh (PyTorch)                  │
│                   → TimescaleDB (asyncpg)                │
│                   → Kafka Producer → features.vector.*   │
│                                                           │
│  Prediction:8004                                          │
│    Kafka Consumer → XGBoost → SHAP → Adaptive Thresholds│
│                   → TFT (PyTorch Lightning)              │
│                   → Redis Cache (prediction TTL 300s)    │
│                   → Kafka Producer → predictions.fast.*  │
└───────────────────────────┬──────────────────────────────┘
                            │ Apache Kafka
                            ▼
┌─ ACTION (Python + FastAPI + Twilio) ─────────────────────┐
│  Alert Dispatcher:8005                                    │
│    Kafka Consumer → Twilio WhatsApp/SMS                  │
│                   → Cell Broadcast (CAP XML)             │
│                   → Kafka Producer → alerts.dispatch     │
│                                                           │
│  Evacuation RL:8010  (Stable-Baselines3 + PettingZoo)   │
│  Causal Engine:8006  (PyTorch GNN)                       │
│  FloodLedger:8007    (Hardhat local Ethereum)            │
│  CHORUS:8008         (Whisper + IndicBERT)               │
└───────────────────────────┬──────────────────────────────┘
                            │ HTTP (Axios)
                            ▼
┌─ FRONTEND (React + Vite + Tailwind) ────────────────────┐
│  Dashboard:3000                                          │
│    Vite dev proxy → 15+ backend routes                   │
│    React hooks → Axios → /api/v1/* endpoints             │
│    Leaflet + react-leaflet → CartoDB tiles + markers     │
│    Recharts → time-series charts + SHAP bar charts       │
│    Tailwind CSS → dark theme + responsive layout         │
└──────────────────────────────────────────────────────────┘

┌─ MONITORING (Prometheus + Grafana) ─────────────────────┐
│  Prometheus:9090 → scrapes /metrics from all services    │
│  Grafana:3001    → SLA dashboard, latency gauges         │
│  MLflow:5000     → experiment tracking, model registry   │
└──────────────────────────────────────────────────────────┘

┌─ INFRASTRUCTURE (Docker + Compose) ─────────────────────┐
│  Zookeeper:2181  → Kafka broker coordination             │
│  Kafka:9092      → event streaming backbone              │
│  TimescaleDB:5432→ time-series + relational storage      │
│  Redis:6379      → prediction cache + pub/sub            │
│  nginx           → production TLS + rate limiting        │
└──────────────────────────────────────────────────────────┘
```

---

*Every technology was chosen for a specific reason — performance, cost, ecosystem fit, or regulatory compliance. The stack is designed so that the entire system runs on free, open-source tools with no vendor lock-in.*
