# ARGUS — Deployment Guide
## From Development to Production
### Prepared by Sabarish | Team ARGUS

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development Setup](#local-development-setup)
3. [Docker Compose Deployment](#docker-compose-deployment)
4. [Service Health Verification](#service-health-verification)
5. [Demo Scenario Execution](#demo-scenario-execution)
6. [Production Deployment (AWS)](#production-deployment-aws)
7. [ACN Node Setup (Raspberry Pi)](#acn-node-setup)
8. [Monitoring and Alerting](#monitoring-and-alerting)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Software Requirements

| Component | Version | Purpose |
|-----------|---------|---------|
| Docker | 24.0+ | Container runtime |
| Docker Compose | 2.20+ | Multi-container orchestration |
| Python | 3.10+ | Services and scripts |
| Node.js | 18+ | Dashboard frontend |
| Git | 2.40+ | Version control |

### Hardware Requirements (Development)

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 4 cores | 8 cores |
| RAM | 8 GB | 16 GB |
| Disk | 20 GB | 40 GB |
| GPU | Not required | NVIDIA GPU (for TFT training) |

---

## Local Development Setup

### 1. Clone Repository

```bash
git clone <repo-url>
cd argus
```

### 2. Environment Configuration

```bash
cp .env.example .env
# Edit .env with your configuration:
# - DISABLE_AUTH=true (for demo)
# - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
# - TIMESCALEDB_URL=postgresql://argus:argus@timescaledb:5432/argus
```

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Dashboard Dependencies

```bash
cd dashboard
npm install
cd ..
```

---

## Docker Compose Deployment

### Start All Services

```bash
# Start everything
docker-compose up -d

# Watch logs
docker-compose logs -f

# Check status
docker-compose ps
```

### Service Startup Order

Docker Compose handles dependencies, but the expected startup order is:

1. **Zookeeper** → **Kafka** (messaging infrastructure)
2. **TimescaleDB** (database)
3. **Feature Engine** (data processing)
4. **Prediction Service** (ML inference)
5. **Causal Engine** (causal inference)
6. **CV Gauging** (computer vision)
7. **CHORUS** (community intelligence)
8. **Evacuation RL** (route planning)
9. **FloodLedger** (parametric insurance)
10. **ACN Node** (offline crisis node)
11. **MIRROR** (counterfactual)
12. **Federated Server** (FL coordination)
13. **API Gateway** (aggregation layer)
14. **Dashboard** (frontend)

### Stop All Services

```bash
docker-compose down

# With volume cleanup
docker-compose down -v
```

---

## Service Health Verification

### Automated Health Check

```bash
python demo/health_checker.py
```

Expected output:
```
✅ Zookeeper .............. UP
✅ Kafka .................. UP
✅ TimescaleDB ............ UP
✅ Feature Engine ......... UP (port 8001)
✅ Prediction Service ..... UP (port 8002)
✅ Causal Engine .......... UP (port 8003)
✅ CV Gauging ............. UP (port 8004)
✅ CHORUS ................. UP (port 8005)
✅ Evacuation RL .......... UP (port 8006)
✅ FloodLedger ............ UP (port 8007)
✅ ACN Node ............... UP (port 8008)
✅ MIRROR ................. UP (port 8009)
✅ Federated Server ....... UP (port 8010)
✅ Model Monitor .......... UP (port 8011)
✅ API Gateway ............ UP (port 8000)
✅ Dashboard .............. UP (port 5173)

All 16 services healthy. ✅
```

### Manual Health Check

```bash
# API Gateway
curl http://localhost:8000/api/v1/health

# Individual services
curl http://localhost:8001/health  # Feature Engine
curl http://localhost:8002/health  # Prediction
curl http://localhost:8003/health  # Causal Engine
# ... etc
```

---

## Demo Scenario Execution

### Load Demo Scenario

```bash
python demo/orchestrator.py
```

This will:
1. Load the Majuli Ward 7 flood scenario
2. Start synthetic data generators
3. Ramp risk scores from CALM → ADVISORY → WATCH → WARNING → EMERGENCY
4. Trigger evacuation planning
5. Fire FloodLedger parametric trigger
6. Run MIRROR counterfactual analysis

### Dashboard Access

Open `http://localhost:5173` in Chrome (dark mode recommended).

### Tabs to Verify

1. **Map View** — Village polygons colored by risk level
2. **Prediction** — Risk score + SHAP explanation for selected village
3. **Causal** — Intervention query panel
4. **Evacuation** — Route map + vehicle assignments
5. **FloodLedger** — Insurance trigger + blockchain transaction
6. **MIRROR** — Backtest timeline
7. **ACN** — Offline node status

---

## Production Deployment (AWS)

### Recommended Architecture

```
┌─────────────────────────────────┐
│  AWS Region: ap-south-1 (Mumbai)│
│                                 │
│  ECS Fargate (12 services)      │
│  Amazon MSK (Kafka)             │
│  Amazon RDS (TimescaleDB)       │
│  S3 (satellite imagery cache)   │
│  CloudFront (dashboard CDN)     │
│  Lambda (alert dispatch)        │
│  API Gateway (REST + WS)        │
└─────────────────────────────────┘
```

### Cost Estimate

| Mode | Instances | Daily Cost |
|------|-----------|-----------|
| CALM | 2× t3.medium | ~$15 |
| ADVISORY | 4× t3.large | ~$60 |
| EMERGENCY | 8× c5.xlarge + 1× g4dn.xlarge | ~$180 |

### Auto-Scaling Policy

```yaml
# Scale up when risk_score_max > 0.6 across any monitored village
scaling_trigger:
  metric: argus.risk_score.max
  threshold: 0.6
  action: scale_to_advisory
  
# Scale to emergency compute when risk > 0.85
emergency_trigger:
  metric: argus.risk_score.max
  threshold: 0.85
  action: scale_to_emergency
```

---

## ACN Node Setup (Raspberry Pi)

### Hardware Bill of Materials

| Component | Specification | Cost (₹) |
|-----------|--------------|----------|
| Raspberry Pi 4 | 4GB RAM | 3,500 |
| SD Card | 32GB Class 10 | 500 |
| LoRa Module | SX1276 868/915MHz | 800 |
| Solar Panel | 10W | 600 |
| Battery | 10000mAh LiPo | 400 |
| Case | Weatherproof IP65 | 200 |
| **Total** | | **₹6,000** |

### Software Setup

```bash
# Flash Raspberry Pi OS Lite (64-bit)
# SSH into the Pi

# Install ONNX Runtime
pip install onnxruntime

# Copy ORACLE model
scp oracle_model_majuli_v2.3.onnx pi@acn-node:/opt/argus/models/

# Install ACN service
scp -r services/acn_node/ pi@acn-node:/opt/argus/

# Configure
cat > /opt/argus/config.yaml << EOF
node_id: acn_majuli_01
village_id: majuli_ward_7
oracle_model: /opt/argus/models/oracle_model_majuli_v2.3.onnx
lora_frequency: 868.0
lora_spreading_factor: 12
cloud_endpoint: https://api.argus.dev/v1
fallback_mode: true
EOF

# Start service
systemctl enable argus-acn
systemctl start argus-acn
```

---

## Monitoring and Alerting

### Key Metrics to Monitor

| Metric | Alert Threshold | Action |
|--------|----------------|--------|
| Service health | Any service DOWN > 30s | Page on-call |
| Kafka consumer lag | > 1000 messages | Scale consumers |
| Prediction latency (p99) | > 100ms | Check model server |
| TFT inference latency | > 1s | Check GPU allocation |
| PINN physics residual | > threshold | Flag LOW_CONFIDENCE |
| ACN last heartbeat | > 5 minutes | Check node connectivity |
| Dashboard WebSocket | Disconnected > 10s | Reconnect |

### Log Aggregation

All services log to stdout in JSON format. In production:
- **CloudWatch Logs** for aggregation
- **CloudWatch Metrics** for dashboards
- **SNS** for alerting

---

## Troubleshooting

### Common Issues

| Problem | Cause | Solution |
|---------|-------|---------|
| Service won't start | Port conflict | `docker-compose down` then `up` |
| Kafka connection refused | Zookeeper not ready | Wait 30s, retry |
| Dashboard blank | API Gateway not ready | Check `localhost:8000/api/v1/health` |
| Prediction returns null | Feature Engine backlog | Check Kafka consumer lag |
| Causal query returns UNIDENTIFIABLE | DAG structure issue | Check DAG for d-separation |
| ACN offline | Expected during demo | Toggle "Simulate Offline" |
| FloodLedger tx pending | Blockchain sync | Wait for block confirmation |

### Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api_gateway
docker-compose logs -f causal_engine
docker-compose logs -f prediction

# Last 100 lines
docker-compose logs --tail=100 feature_engine
```

### Reset Everything

```bash
docker-compose down -v
docker system prune -f
docker-compose up -d
sleep 30
python demo/health_checker.py
```

## Monitoring and Alerting

### Key Metrics to Monitor

| Metric | Alert Threshold | Action |
|--------|----------------|--------|
| Service health | Any service DOWN > 30s | Page on-call |
| Kafka consumer lag | > 1000 messages | Scale consumers |
| Prediction latency (p99) | > 100ms | Check model server |
| TFT inference latency | > 1s | Check GPU allocation |
| PINN physics residual | > threshold | Flag LOW_CONFIDENCE |
| ACN last heartbeat | > 5 minutes | Check node connectivity |
| Dashboard WebSocket | Disconnected > 10s | Reconnect |

### Log Aggregation

All services log to stdout in JSON format. In production:
- **CloudWatch Logs** for aggregation
- **CloudWatch Metrics** for dashboards
- **SNS** for alerting

---

## Troubleshooting

### Common Issues

| Problem | Cause | Solution |
|---------|-------|---------|
| Service won't start | Port conflict | `docker-compose down` then `up` |
| Kafka connection refused | Zookeeper not ready | Wait 30s, retry |
| Dashboard blank | API Gateway not ready | Check `localhost:8000/api/v1/health` |
| Prediction returns null | Feature Engine backlog | Check Kafka consumer lag |
| Causal query returns UNIDENTIFIABLE | DAG structure issue | Check DAG for d-separation |
| ACN offline | Expected during demo | Toggle "Simulate Offline" |
| FloodLedger tx pending | Blockchain sync | Wait for block confirmation |

### Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api_gateway
docker-compose logs -f causal_engine
docker-compose logs -f prediction

# Last 100 lines
docker-compose logs --tail=100 feature_engine
```

### Reset Everything

```bash
docker-compose down -v
docker system prune -f
docker-compose up -d
sleep 30
python demo/health_checker.py
```
