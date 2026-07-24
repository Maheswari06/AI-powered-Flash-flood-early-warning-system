# ARGUS — Production Runbook

> **System**: ARGUS Flood Early Warning System  
> **Region**: AP-South-1 (Mumbai AWS — closest to Assam)  
> **Criticality**: Life-safety system — treat all alerts as P0 during monsoon  
> **On-Call Rotation**: #argus-oncall in Slack  

---

## Table of Contents

1. [System Architecture Overview](#system-architecture-overview)
2. [Service Map & Ports](#service-map--ports)
3. [SLA Targets](#sla-targets)
4. [Incident Response Playbooks](#incident-response-playbooks)
5. [Storm Mode Operations](#storm-mode-operations)
6. [Deployment Procedures](#deployment-procedures)
7. [Scaling Guide](#scaling-guide)
8. [Database Operations](#database-operations)
9. [Monitoring & Alerting](#monitoring--alerting)
10. [Disaster Recovery](#disaster-recovery)
11. [Cost Control](#cost-control)
12. [Contact & Escalation](#contact--escalation)

---

## System Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                      ARGUS Architecture                          │
│                                                                  │
│  External Data          Kafka Bus          AI/ML Pipeline        │
│  ┌─────────┐           ┌───────┐          ┌──────────────┐      │
│  │ CWC API │──┐        │       │          │ Feature      │      │
│  │ IMD API │──┤  ┌─────│ MSK   │──────────│ Engine       │      │
│  │ CCTV    │──┤  │     │ Kafka │          │ (8003)       │      │
│  └─────────┘  │  │     │       │          └──────┬───────┘      │
│               ▼  │     └───────┘                 │              │
│          ┌────────┤                              ▼              │
│          │Ingest  │                    ┌──────────────────┐      │
│          │(8001)  │                    │ Prediction(8004) │      │
│          └────────┘                    │ Causal   (8006)  │      │
│               │                        │ MIRROR   (8011)  │      │
│               ▼                        └────────┬─────────┘      │
│          ┌─────────┐                            │               │
│          │CV Gauge │                            ▼               │
│          │(8002)   │                   ┌────────────────┐       │
│          └─────────┘                   │Alert Dispatcher│       │
│                                        │(8005)          │       │
│               ┌────────────────────────┤                │       │
│               │                        └────────────────┘       │
│               ▼                                                  │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ Supporting Services                                     │      │
│  │ CHORUS(8008) │ Federated(8009) │ Evacuation(8010)     │      │
│  │ ScarNet(8012)│ ModelMonitor(8013)│ FloodLedger(8007)  │      │
│  └───────────────────────────────────────────────────────┘      │
│                         │                                        │
│                         ▼                                        │
│  ┌──────────────────────────────────┐                           │
│  │ API Gateway (8000) + Nginx       │                           │
│  │ → Dashboard (CloudFront CDN)     │                           │
│  └──────────────────────────────────┘                           │
└──────────────────────────────────────────────────────────────────┘
```

---

## Service Map & Ports

| Service | Port | Replicas (Prod) | HPA Max | GPU | Critical |
|---------|------|-----------------|---------|-----|----------|
| API Gateway | 8000 | 3 | 20 | No | ✓ |
| Ingestion | 8001 | 2 | 10 | No | ✓ |
| CV Gauging | 8002 | 2 | 8 | No | |
| Feature Engine | 8003 | 2 | 12 | No | ✓ |
| Prediction | 8004 | 2 | 20 | No | ✓ |
| Alert Dispatcher | 8005 | 2 | 15 | No | ✓ |
| Causal Engine | 8006 | 1 | 4 | ✓ | |
| FloodLedger | 8007 | 2 | 6 | No | |
| CHORUS | 8008 | 2 | 8 | No | |
| Federated Server | 8009 | 1 | 3 | No | |
| Evacuation RL | 8010 | 2 | 10 | No | ✓ |
| MIRROR | 8011 | 1 | 4 | No | |
| ScarNet | 8012 | 1 | 6 | No | |
| Model Monitor | 8013 | 1 | 3 | No | |

---

## SLA Targets

| Metric | Target | Alert Threshold | Severity |
|--------|--------|-----------------|----------|
| Prediction latency p95 | < 50ms | > 50ms for 5min | Critical |
| Alert dispatch latency p95 | < 30s | > 30s for 3min | Critical |
| Village prediction gap | < 5min | > 5min for 2min | Critical |
| CHORUS trust score | > 0.3 | < 0.3 for 10min | Warning |
| Village coverage | > 95% | < 95% for 5min | Warning |
| Alert delivery rate | > 90% | < 90% for 5min | Critical |
| AWS monthly cost | < $500 | > $500 | Warning |
| System uptime | 99.9% | - | - |

---

## Incident Response Playbooks

### <a name="prediction-latency"></a>Playbook: High Prediction Latency

**Alert**: `PredictionLatencyP95High`  
**Severity**: Critical  
**Impact**: Villages may not receive timely flood warnings

**Steps**:

1. **Check Kafka consumer lag**
   ```bash
   kubectl -n argus-prod exec -it deploy/argus-prediction -- \
     python -c "from shared.kafka_client import get_consumer_lag; print(get_consumer_lag())"
   ```

2. **Check pod resource usage**
   ```bash
   kubectl -n argus-prod top pods -l app=argus-prediction
   ```

3. **If CPU > 80%**: Scale prediction pods
   ```bash
   kubectl -n argus-prod scale deploy argus-prediction --replicas=5
   ```

4. **If Kafka lag > 1000**: Check upstream pipeline
   ```bash
   # Check feature engine health
   kubectl -n argus-prod logs -l app=argus-feature-engine --tail=100
   # Check ingestion health
   kubectl -n argus-prod logs -l app=argus-ingestion --tail=100
   ```

5. **If model loading is slow**: Verify EFS mount
   ```bash
   kubectl -n argus-prod exec -it deploy/argus-prediction -- ls -la /models/
   ```

6. **Escalate if not resolved in 15 minutes**: Page on-call SRE

---

### <a name="alert-dispatch"></a>Playbook: Alert Dispatch Failure

**Alert**: `AlertDispatchLatencyHigh` or `AlertDeliveryFailureRate`  
**Severity**: Critical  
**Impact**: Flood alerts not reaching communities

**Steps**:

1. **Check Twilio API status**: https://status.twilio.com
   
2. **Check alert dispatcher logs**
   ```bash
   kubectl -n argus-prod logs -l app=argus-alert-dispatcher --tail=200 | grep -i error
   ```

3. **If Twilio rate-limited**: Enable SMS fallback
   ```bash
   kubectl -n argus-prod set env deploy/argus-alert-dispatcher SMS_FALLBACK=true
   ```

4. **If Kafka lag**: Scale dispatcher
   ```bash
   kubectl -n argus-prod scale deploy argus-alert-dispatcher --replicas=5
   ```

5. **EMERGENCY FALLBACK**: Activate NDRF direct communication channel
   - Contact: NDRF Guwahati +91-XXX-XXX-XXXX
   - Contact: CWC Regional Center +91-XXX-XXX-XXXX

---

### <a name="village-gap"></a>Playbook: Village Prediction Gap

**Alert**: `VillagePredictionGapHigh`  
**Severity**: Critical  
**Impact**: Village not monitored — risk of undetected flooding

**Steps**:

1. **Identify affected villages**
   ```bash
   curl -s http://argus-api-gateway:8000/api/v1/predictions/coverage | jq '.gaps'
   ```

2. **Check data source for the village**
   - CWC station online? Check ingestion logs
   - CCTV feed active? Check CV gauging logs

3. **If data source offline**: 
   ```bash
   # Switch to satellite-only prediction for affected village
   kubectl -n argus-prod exec -it deploy/argus-prediction -- \
     python -c "from predictor import enable_satellite_fallback; enable_satellite_fallback('VILLAGE_ID')"
   ```

4. **If pipeline stalled**: Restart affected service
   ```bash
   kubectl -n argus-prod rollout restart deploy/argus-prediction
   ```

---

### <a name="chorus-trust"></a>Playbook: Low CHORUS Trust Score

**Alert**: `CHORUSTrustBelowThreshold`  
**Severity**: Warning  
**Impact**: Data quality degradation — predictions may be unreliable

**Steps**:

1. **Identify degraded source**
   ```bash
   curl -s http://argus-api-gateway:8000/api/v1/chorus/trust | jq '.sources[] | select(.score < 0.3)'
   ```

2. **If CWC station**: Check for sensor malfunction
   - Compare with neighboring stations
   - Contact CWC regional office if persistent

3. **If CCTV source**: Check camera feed
   ```bash
   kubectl -n argus-prod logs -l app=argus-cv-gauging --tail=50 | grep "SOURCE_ID"
   ```

4. **If IMD data**: Check API connectivity
   ```bash
   kubectl -n argus-prod exec -it deploy/argus-ingestion -- curl -s https://api.imd.gov.in/health
   ```

5. **Automatic**: CHORUS will down-weight untrusted sources in predictions

---

## Storm Mode Operations

Storm Mode activates when **≥ 3 villages are at EMERGENCY level**.

### Automatic Actions
- Prediction & Alert pods scale to **minimum 10 replicas**
- Kafka partitions rebalanced for throughput
- Alert dispatch switches to **multi-channel** (SMS + WhatsApp + Voice)
- Dashboard enters **crisis view** (map-only, real-time updates)

### Manual Activation
```bash
# Activate Storm Mode manually
kubectl -n argus-prod apply -f infra/kubernetes/base/namespace-and-config.yaml
kubectl -n argus-prod scale deploy argus-prediction --replicas=10
kubectl -n argus-prod scale deploy argus-alert-dispatcher --replicas=10
kubectl -n argus-prod scale deploy argus-api-gateway --replicas=10

# Verify Storm Mode
kubectl -n argus-prod get configmap argus-storm-mode -o yaml
```

### Deactivation
```bash
# Only deactivate when all villages are below WARNING
kubectl -n argus-prod scale deploy argus-prediction --replicas=2
kubectl -n argus-prod scale deploy argus-alert-dispatcher --replicas=2
kubectl -n argus-prod scale deploy argus-api-gateway --replicas=3
```

### Storm Mode Checklist
- [ ] All prediction pods running and healthy
- [ ] Alert dispatcher confirmed sending to all channels
- [ ] NDRF notified via hotline
- [ ] District administration dashboard active
- [ ] CWC real-time data feeds confirmed
- [ ] Evacuation routes computed for affected villages
- [ ] FloodLedger recording all predictions on-chain

---

## Deployment Procedures

### Standard Deployment (Blue-Green)

```bash
# 1. Build and push new image
docker build -t argus/prediction:3.1 -f services/prediction/Dockerfile .
docker push argus/prediction:3.1

# 2. Update deployment (rolling update)
kubectl -n argus-prod set image deploy/argus-prediction prediction=argus/prediction:3.1

# 3. Monitor rollout
kubectl -n argus-prod rollout status deploy/argus-prediction --timeout=300s

# 4. Verify health
kubectl -n argus-prod get pods -l app=argus-prediction
curl -s http://argus-api-gateway:8000/api/v1/predictions/health

# 5. If issues, rollback immediately
kubectl -n argus-prod rollout undo deploy/argus-prediction
```

### Model Update Deployment

```bash
# 1. Upload new model to S3
aws s3 cp models/xgboost_flood_v2.joblib s3://argus-models-production/xgboost_flood.joblib

# 2. Sync EFS from S3
kubectl -n argus-prod create job model-sync --from=cronjob/model-sync

# 3. Rolling restart to pick up new model
kubectl -n argus-prod rollout restart deploy/argus-prediction

# 4. Monitor model metrics for 30 minutes
# Dashboard: Grafana → ARGUS SLA → Model Monitor panel
```

### Kustomize Deployment

```bash
# Development
kubectl apply -k infra/kubernetes/overlays/development

# Staging
kubectl apply -k infra/kubernetes/overlays/staging

# Production
kubectl apply -k infra/kubernetes/overlays/production
```

---

## Scaling Guide

### Horizontal Scaling

| Trigger | Action |
|---------|--------|
| CPU > 70% on prediction pods | HPA auto-scales (max 20) |
| Kafka lag > 100 on feature.engineered | HPA auto-scales prediction |
| Kafka lag > 200 on gauge.realtime | HPA auto-scales feature engine |
| CPU > 60% on API gateway | HPA auto-scales (max 20) |
| Storm Mode activated | Manual scale to 10 replicas |

### Vertical Scaling (requires restart)

```bash
# Increase prediction pod resources
kubectl -n argus-prod patch deploy argus-prediction -p \
  '{"spec":{"template":{"spec":{"containers":[{"name":"prediction","resources":{"limits":{"memory":"4Gi","cpu":"2000m"}}}]}}}}'
```

### Node Group Scaling (Terraform)

```bash
cd infra/terraform
terraform plan -var="general_node_max=15" -var="gpu_node_max=6"
terraform apply
```

---

## Database Operations

### TimescaleDB

```bash
# Connect to database
kubectl -n argus-prod exec -it deploy/argus-prediction -- \
  psql "postgresql://argus:$TIMESCALE_PASSWORD@$TIMESCALE_HOST:5432/argus_db"

# Check hypertable sizes
SELECT hypertable_name, pg_size_pretty(hypertable_size(format('%I.%I', hypertable_schema, hypertable_name)::regclass))
FROM timescaledb_information.hypertables;

# Compression policy (auto-compress data older than 7 days)
SELECT add_compression_policy('gauge_readings', INTERVAL '7 days');

# Retention policy (drop data older than 2 years)
SELECT add_retention_policy('gauge_readings', INTERVAL '2 years');
```

### Redis

```bash
# Check memory usage
kubectl -n argus-prod exec -it deploy/argus-chorus -- redis-cli -u $REDIS_URL INFO memory

# Flush prediction cache (if stale)
kubectl -n argus-prod exec -it deploy/argus-prediction -- redis-cli -u $REDIS_URL FLUSHDB
```

---

## Monitoring & Alerting

### Dashboards

| Dashboard | URL | Purpose |
|-----------|-----|---------|
| SLA Overview | `grafana.argus.internal/d/argus-sla-prod` | Primary operations view |
| Kafka Lag | `grafana.argus.internal/d/argus-kafka` | Pipeline throughput |
| Node Resources | `grafana.argus.internal/d/argus-nodes` | Infrastructure health |

### Key Metrics to Watch

```promql
# Prediction throughput
sum(rate(argus_prediction_requests_total[5m]))

# End-to-end pipeline latency (ingest → alert)
histogram_quantile(0.95, sum(rate(argus_e2e_latency_seconds_bucket[5m])) by (le))

# Active villages being monitored
count(argus_village_last_prediction_timestamp > (time() - 300))

# Model drift score
argus_model_drift_score{model="xgboost"}
```

### Alert Routing

| Severity | Channel | Response Time |
|----------|---------|---------------|
| Critical | PagerDuty + Slack #argus-alerts + SMS | 5 minutes |
| Warning | Slack #argus-alerts | 30 minutes |
| Info | Slack #argus-monitoring | Next business day |

---

## Disaster Recovery

### RDS Failover

```bash
# RDS Multi-AZ automatic failover (< 60s)
# Manual failover if needed:
aws rds reboot-db-instance --db-instance-identifier argus-timescale-production --force-failover
```

### Full Cluster Recovery

```bash
# 1. Create new EKS cluster
cd infra/terraform && terraform apply

# 2. Deploy all services
kubectl apply -k infra/kubernetes/overlays/production

# 3. Restore database from latest snapshot
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier argus-timescale-recovery \
  --db-snapshot-identifier argus-latest-snapshot

# 4. Restore models from S3
aws s3 sync s3://argus-models-production /tmp/models
kubectl cp /tmp/models argus-prod/argus-prediction-abc123:/models

# 5. Verify all services healthy
kubectl -n argus-prod get pods
curl https://api.argus.flood.gov.in/health
```

### RPO / RTO Targets

| Component | RPO | RTO |
|-----------|-----|-----|
| TimescaleDB | 5 minutes (continuous backup) | 30 minutes |
| Redis | 1 hour (snapshot) | 10 minutes |
| Models (S3) | 0 (versioned) | 5 minutes |
| Kafka topics | N/A (replayable) | 15 minutes |

---

## Cost Control

### Monthly Budget Breakdown (Target: < $500)

| Resource | Estimated Cost | Notes |
|----------|---------------|-------|
| EKS Control Plane | $73 | Fixed |
| EC2 (4× m5.xlarge) | $220 | General nodes |
| EC2 (1× g4dn.xlarge) | $55 | GPU node |
| MSK (3× kafka.m5.large) | $60 | 3 brokers |
| RDS (db.r6g.xlarge) | $50 | Multi-AZ |
| ElastiCache | $25 | 2-node Redis |
| S3 + CloudFront | $10 | Models + Dashboard |
| Data Transfer | $7 | Regional |
| **Total** | **~$500** | |

### Cost Optimization Actions

1. **Use Spot Instances** for non-critical services (MIRROR, ScarNet)
2. **Scale down GPU nodes** outside monsoon season (Oct-Mar)
3. **Reserved Instances** for general nodes (1-year = 30% savings)
4. **TimescaleDB compression** reduces storage by ~90%
5. **S3 Glacier** for models older than 90 days

---

## Contact & Escalation

### Team Contacts

| Role | Name | Contact |
|------|------|---------|
| Tech Lead | Rogesh | Slack: @rogesh |
| ML Lead | Dhanalakshmi | Slack: @dhana |
| SRE On-Call | Rotation | PagerDuty: #argus-oncall |
| CWC Liaison | Regional Office | +91-XXX-XXX-XXXX |
| NDRF Contact | Guwahati Base | +91-XXX-XXX-XXXX |

### Escalation Path

```
L1: On-Call Engineer (5 min response)
  ↓ 15 min unresolved
L2: Tech Lead + ML Lead
  ↓ 30 min unresolved  
L3: CWC Regional Office + District Administration
  ↓ Storm Mode only
L4: NDRF + State Disaster Management Authority
```

---

*Last updated: Phase 5 — Rogesh*  
*Document hash: Auto-generated on commit*
