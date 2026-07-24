# ARGUS Interview Prep — TCS Digital

> **Use this as an honest project narrative.** ARGUS has a strong Phase-1 design and substantial implementation, but this checkout also includes demo fallbacks and some incomplete integration wiring. Do not describe a demo fallback as a production deployment. The **Verify before claiming** notes at the end are deliberate.

## 1. Problem Statement

### The problem

**Flash floods are fast, local, and dangerous.** A river can rise rapidly after intense rainfall, saturated soil, upstream runoff, or a dam-related event. A warning is useful only if it reaches people early enough to make a decision: move to higher ground, close a bridge, deploy rescue teams, or begin evacuation.

ARGUS is designed as an **AI-assisted early-warning platform** that combines:

- physical river-gauge observations;
- weather/rainfall observations;
- optional camera-derived virtual gauge readings; and
- upstream and time-window context.

It converts those inputs into a **flood-risk score, alert level, and human-readable explanation** instead of only showing raw sensor numbers.

### Why existing approaches can be insufficient

- A single physical gauge gives only one local measurement; it may be sparse, noisy, damaged, or downstream of the real risk.
- Weather alone cannot fully capture river response because **soil saturation, existing water level, and upstream conditions** change how rain becomes runoff.
- A dashboard that says “risk is high” without explaining the drivers is difficult for an operator to trust in an emergency.
- Synchronous point-to-point integrations become fragile when many sources and consumers need the same live data.

### Who benefits

- **Residents and local communities:** earlier, more understandable warnings.
- **District disaster-management teams:** a risk view, alert history, and a basis for prioritising response.
- **Field and hydrology teams:** quality-checked sensor data plus a time-series record for analysis.
- **System operators:** independently deployable services, health checks, caching, and an API gateway.

## 2. Project Overview

### 30-second elevator pitch

“ARGUS is a microservices-based flash-flood early-warning system. It ingests river-gauge and weather readings, quality-checks and converts them into rolling features such as recent rainfall, water-level rise rate, soil-moisture proxy, and upstream risk. An XGBoost classifier produces a flood-risk probability, SHAP explains the top factors, and adaptive thresholds map that probability to an actionable alert level. FastAPI exposes the data to a dashboard and alert service, while Kafka, TimescaleDB, Redis, and Docker support decoupled real-time processing.”

### Architecture — intended Phase-1 flow

```text
Gauge readings        Weather readings        CCTV metadata / frames
     |                     |                         |
     +---- Ingestion API ---+-------------------------+
                           |
                  Apache Kafka event topics
                           |
          +----------------+----------------+
          |                                 |
   Feature Engine (FastAPI)          CV Gauging (optional)
   - Kalman quality checks           - depth/velocity estimate
   - temporal/spatial features       - virtual-gauge reading
   - PINN/IDW virtual mesh                    |
          |                                   |
          +------ TimescaleDB feature_store --+
                           |
               Prediction service (FastAPI)
               XGBoost -> SHAP -> thresholds
                    |                  |
       Redis 5-min cache          Kafka prediction event
                    |                  |
             Dashboard/API       Alert Dispatcher/API
```

### Code-confirmed data flow

1. **Ingestion API** accepts `GaugeReading`, `WeatherData`, and `CCTVFrame` payloads.
2. The Feature Engine is designed to consume gauges and weather, retain recent readings in bounded in-memory buffers, use a **Kalman filter** to replace anomalous gauge values, and recompute features every 60 seconds.
3. It produces two representations:
   - a `FeatureVector` for the older Kafka-oriented prediction path; and
   - a JSON feature row in TimescaleDB's `feature_store` table for the newer fast-track path.
4. The newer prediction consumer polls TimescaleDB each 60 seconds, calls **XGBoost**, computes the top three **SHAP** drivers, applies environmental threshold adjustments, then publishes/caches a result.
5. The API returns the latest risk, alert level, explanation, confidence band, and history. The alert service has an HTTP dispatch endpoint with a per-village 15-minute cooldown.

### Important precision for an interview

The architecture above is the **intended flow and mostly implemented service structure**. In this checkout, the primary end-to-end execution is not fully proven: several core pieces default to demo mode, and there are topic/schema mismatches. See [Verify before claiming](#verify-before-claiming-in-an-interview). A strong answer is: “I implemented and understood the core feature/prediction services; we used demo fallbacks while completing the production integration.”

## 3. Detailed Component Explanation

### FastAPI — service boundaries and APIs

FastAPI is the HTTP layer around the pipeline, not the ML model itself. It validates request bodies with Pydantic models and exposes service-specific endpoints.

| Service | Key implemented endpoints | What it does in ARGUS |
|---|---|---|
| **Ingestion** (`:8001`) | `POST /api/v1/ingest/gauge`, `/weather`, `/cctv-frame`; `GET /stats`, `/sources`, `/health` | Accepts external reading payloads and is intended to publish them into the stream. |
| **Feature Engine** (`:8003`) | `GET /api/v1/features/{station}/latest`, `/temporal`, `/spatial`; `GET /api/v1/feature-store/{village}/latest`; `/topology`, `/health` | Lets operators inspect the derived features, quality state, and stored feature records. |
| **Prediction** (`:8004`) | `GET /api/v1/prediction/{village}`, `/history`, `/deep`; `POST /api/v1/prediction/{village}/run`; `GET /predictions/all`, `/model/info`, `/health` | Serves risk scores/explanations, supports a manual test prediction, and exposes model metadata. |
| **Alert Dispatcher** (`:8005`) | `POST /api/v1/alert/send`; `GET /alert/log`, `/alert/stats`; `POST /alert/test` | Formats and records alerts, suppressing repeated alerts during the cooldown. |
| **API Gateway** (`:8000`) | `GET /api/v1/dashboard/snapshot`, `/health`, plus reverse proxy routes | Aggregates dashboard calls and has a small 30-second in-memory snapshot cache. |

### Apache Kafka — event backbone

Kafka is intended to act like a **durable post office**: producers post events without waiting for every downstream service, and different consumer groups can independently read the same stream. That fits flood monitoring because a gauge event can be useful to feature engineering, monitoring, dashboards, and alerting without tightly coupling those services.

The shared Kafka wrapper uses JSON payloads, `acks=all`, five retries, and keyed messages. In a production version, station/village ID should be used as the Kafka key so events for one location retain order within a partition.

The documented topic families are `gauge.realtime`, `weather.api.imd`, `cctv.frames`, `virtual.gauge`, `features.vector`, `prediction.flood`, `pinn.mesh`, and `alerts.dispatch`. The newer fast-track prediction publisher actually writes to `predictions.fast.{village_id}` and to Redis.

**Why Kafka instead of REST-only/direct calls?** Direct calls make the ingestion service wait for downstream services and create a failure chain. Kafka buffers bursts, supports replay after recovery, lets each consumer scale separately, and isolates a slow consumer from the producer. Kafka still does not create exactly-once business outcomes by itself; consumers must make processing idempotent and manage offsets carefully.

### Feature engineering — what reaches the model

The Feature Engine keeps up to 300 readings per source in ring buffers (roughly 25 hours at five-minute intervals) and derives:

- water-level mean, maximum, and rate of change over **1, 3, 6, and 24 hours**;
- cumulative rainfall over the same windows;
- an **antecedent moisture index** using 72-hour exponentially decayed rainfall;
- a soil-moisture/saturation proxy when a real soil-moisture feed is unavailable;
- an upstream-risk score based on upstream levels and station topology; and
- calendar fields such as hour, day of year, and monsoon flag.

Before storage, real gauge readings pass through a two-state Kalman filter: `[water_level, rate_of_change]`. If the innovation is above **3 sigma**, the code flags it as `KALMAN_IMPUTED` and uses the predicted value rather than the raw spike. This reduces the chance that one bad sensor value creates a false alert.

### XGBoost — prediction model

The current fast-track class is an `XGBClassifier` configured with **500 trees**, `max_depth=6`, `learning_rate=0.05`, 0.8 row/column sampling, and a temporal 80/20 split. It returns a binary **flood probability from 0 to 1**.

Its declared 16-feature contract contains recent water-level means and peak, 1/3-hour rise rates, 6/24-hour rain, soil and antecedent moisture, upstream risk, basin connectivity, and calendar/monsoon fields. The repository first tries to load `models/xgboost_flood.joblib`; if absent and startup training is enabled, it tries a CSV and otherwise trains on **synthetic data**.

**Why XGBoost?** It is a practical choice for tabular, heterogeneous sensor features. It handles nonlinear interactions—for example, heavy rain is more concerning when soil is saturated and upstream risk is already high—while providing low-latency inference and compatibility with TreeSHAP. A neural network would require more real labelled sequential data, more tuning, and harder explanation; a Random Forest is a reasonable baseline but often has a larger latency/model-size trade-off for comparable accuracy.

### SHAP — explanation rather than a black box

The fast track creates a `shap.TreeExplainer` once at startup, rather than rebuilding it per request. For each result, it ranks the top three features by absolute SHAP contribution and reports whether each feature **increases** or **decreases** risk, with a readable label and value.

For example, “high 6-hour rainfall,” “rapid level rise,” and “high upstream risk” are more useful to an operator than “risk = 0.78.” SHAP describes the model's local reasoning for that input; it does **not** prove that a feature caused the flood. If SHAP or a trained model is unavailable, the code explicitly falls back to a hand-tuned importance heuristic—do not call that real SHAP.

### Adaptive alert classification

Base thresholds are `ADVISORY 0.35`, `WATCH 0.55`, `WARNING 0.72`, and `EMERGENCY 0.88`. The threshold engine lowers them if soil moisture is above 0.8, during monsoon months, or when antecedent moisture is high. It also records the adjustment reason, which is valuable for auditability.

Confidence in this service means **distance from an alert boundary**, not calibrated statistical uncertainty: within 0.04 of a threshold is `LOW`, 0.04–0.10 is `MEDIUM`, and at least 0.10 away is `HIGH`.

### TimescaleDB — durable time-series feature store

TimescaleDB stores `feature_store` records with `time`, `village_id`, `station_id`, a JSONB feature map, and a quality flag. The service attempts to convert this table into a hypertable using `time`, then supports latest and time-range queries.

It is more appropriate than an unstructured in-memory cache for historical, timestamped data because the project needs rolling windows, trend analysis, range queries, retention/compression policies, and recovery after a service restart. It is still PostgreSQL underneath, so SQL, transactions, and JSONB are available. In the code, prediction currently **polls** TimescaleDB every 60 seconds; it is not event-driven all the way from feature row to model.

### Redis — actual use in the code

Redis is used by the new prediction publisher as a **short-lived latest-prediction cache**, under keys such as `prediction:VIL-HP-MANDI`, with a default TTL of **300 seconds**. This is meant for low-latency dashboard reads and does not replace TimescaleDB as the historical record.

The API Gateway does **not** use Redis; it has its own process-local 30-second `SimpleCache`. Some later services configure their own Redis database numbers, but the Phase-1 resume story should stay focused on the prediction cache unless you personally worked on those later services.

### PINN / virtual sensors — clarify the scope

The Feature Engine contains a small PyTorch 1-D network intended to interpolate water level between real gauges using a simplified Saint-Venant continuity loss. Its fallback is **inverse-distance weighting plus a simple physics correction**, and its uncertainty grows with distance to the nearest gauge. This is a useful resilience idea for uninstrumented river stretches.

However, the checked-in `models/` folder has no PINN checkpoint, so the fallback path is what this checkout would use. Mention it as a prototype/secondary component, not the core resume claim, unless you can demonstrate a trained checkpoint.

### Docker and Docker Compose

Each principal Phase-1 Python service has a Dockerfile based on `python:3.11-slim`; it installs requirements, copies only service/shared/data/model directories needed by that image, exposes its port, and starts Uvicorn. The React dashboard uses a multistage Node build and Nginx runtime image.

`docker-compose.yml` orchestrates Zookeeper, Kafka, TimescaleDB, Redis, Phase-1 services, many later-phase services, Prometheus, Grafana, MLflow, and a local Hardhat node. Compose is excellent for repeatable local integration; it is not by itself the production scaling solution. The repository also contains Kubernetes/Terraform manifests for an intended later deployment path.

## 4. My Role in the Project

### Safe first-person version

“My main contribution was on the **feature-engineering and prediction path**. I worked on deriving rolling water-level and rainfall features, upstream-risk and moisture-related indicators, and integrating those features with the XGBoost prediction workflow. I also worked on FastAPI service integration: exposing feature and prediction endpoints, connecting the prediction output to Redis/Kafka, and making SHAP explanations readable for the dashboard and alert use case. We used AI-assisted development to speed up boilerplate, test scenarios, and documentation, but I reviewed the service boundaries, feature contracts, and failure paths myself.”

### Contributions supported by the repository and resume bullets

- **Feature engineering:** rolling statistics, rainfall accumulation, AMI, soil-moisture proxy, upstream topology features, and calendar features in `services/feature_engine`.
- **Data quality:** Kalman-filter handling of anomalous gauge readings before features are calculated.
- **Prediction workflow:** XGBoost probability scoring, threshold classification, SHAP explanations, model-info endpoint, and manual prediction endpoint in `services/prediction`.
- **Backend integration:** FastAPI APIs, TimescaleDB feature store, Redis cache, Kafka publisher wrappers, Dockerfiles, and Compose configuration for the core services.
- **Operational thinking:** health endpoints, gateway snapshot cache, alert cooldown, feature quality fields, and model-monitor/drift scaffolding.

### Challenges you can discuss — only if they match your experience

1. **Combining sources with different reliability and timing.** “I used rolling windows and a Kalman quality step so one delayed or spiky gauge reading did not dominate the risk score.”
2. **Making model output actionable.** “A probability alone is hard to act on, so I added/adapted SHAP drivers and threshold reasons into the API response.”
3. **Maintaining a stable feature contract.** “The model expects a fixed feature order, so feature names and units must be versioned and validated; this is where I learned that integration contracts matter as much as model code.”
4. **Demo versus production behaviour.** “The project had fallbacks for missing services/models. I would clearly separate simulated paths from trained, live-data paths and add contract tests before production.”

Do not say that you personally built Kafka, YOLO/SAM, Twilio delivery, Kubernetes, federated learning, blockchain, causal GNN, or the frontend unless you genuinely did so.

## 5. Likely TCS Digital Interview Q&A on This Project

### 1. Explain the project in two minutes.

ARGUS is an AI-assisted flash-flood early-warning system built as separate FastAPI services. It ingests river and weather observations, converts them to rolling hydrological features, and uses XGBoost to estimate flood risk. SHAP explains the main drivers, while adaptive thresholds turn the score into an alert level. Kafka decouples services, TimescaleDB stores timestamped features, Redis caches recent prediction results, and Docker gives us a repeatable local environment.

### 2. What problem were you solving?

We wanted to reduce the delay between raw environmental signals and an understandable flood warning. A flash flood depends on more than one reading, so we combine rainfall, water-level trend, moisture, and upstream context. The goal is not just a prediction but a decision-support response: risk, alert level, and reasons.

### 3. Describe the end-to-end data flow.

The intended path starts with a gauge or weather reading at the ingestion API and a Kafka event. The Feature Engine cleans gauge data, maintains rolling history, computes features, and writes a feature row to TimescaleDB. The prediction service polls the latest row, runs XGBoost and SHAP, applies thresholds, then caches/publishes the response. The dashboard or alert API reads that result.

### 4. Which part did you own?

My focus was the feature-to-prediction path: feature engineering, prediction workflow integration, and REST APIs. I can explain the rolling features, the XGBoost feature contract, SHAP output, TimescaleDB feature store, and the result-publishing/cache path. The wider repository has other team/later-phase modules, so I distinguish my work from them.

### 5. Why microservices instead of one monolithic application?

Ingestion, feature calculation, prediction, and alerting have different scaling and failure characteristics. Separating them lets the prediction service be updated without rewriting ingestion, and a slow dashboard does not need to block sensor ingestion. The trade-off is more operational complexity, so common schemas, health checks, logging, and contract tests are essential.

### 6. Why Kafka instead of REST calls between every service?

Kafka makes the data pipeline asynchronous. A producer can write an event even if a consumer is temporarily slow, and several consumers can independently read the stream. This reduces tight coupling and helps with replay/recovery. For request-response operations such as “get the latest prediction,” REST is still appropriate.

### 7. How does Kafka help reliability, and what if a consumer goes down?

Kafka persists events for a configured retention period, and consumer groups maintain offsets. After a consumer restarts, it can continue from its committed offset instead of losing every event while it was down. For stronger reliability, I would use manual commits after successful processing, idempotent writes keyed by event ID, dead-letter topics, replication, and monitoring of consumer lag. The current shared helper uses auto-commit, so that is a production improvement I would make.

### 8. Why did you choose XGBoost over a neural network?

Our primary inputs are structured tabular features rather than images or a very large raw sequence corpus. XGBoost captures nonlinear feature interactions, trains/inferes quickly, and works especially well with TreeSHAP explanations. A neural network or transformer is worth evaluating when we have enough high-quality sequential data and need multi-horizon sequence modelling, but it adds complexity and validation requirements.

### 9. Why not use Random Forest?

Random Forest is a good baseline and I would benchmark it. XGBoost builds trees sequentially to correct earlier errors and gives us learning-rate and regularisation controls, which can yield a stronger compact model on tabular data. We chose it because it balances predictive power, speed, and TreeSHAP compatibility; the final choice should be based on time-based validation metrics, not preference.

### 10. What features does the model use, and why?

The main fast-track contract includes recent water level, peak level, rise rate, 6/24-hour rainfall, soil and antecedent moisture, upstream risk, basin connectivity, and seasonal/calendar fields. Recent rainfall tells us input intensity, water-level rise shows immediate response, and saturation/antecedent rain represent how readily the catchment will produce runoff. Upstream risk helps give downstream locations lead time.

### 11. How did you engineer temporal features?

We retain a bounded recent history and calculate mean, maximum, change, and rate of change over 1, 3, 6, and 24-hour windows. Rainfall is accumulated over comparable windows, and AMI decays older rainfall using a factor of 0.85 across up to 72 hours. I would ensure readings are timestamp-sorted, use actual sampling intervals rather than assuming five minutes when data is irregular, and test for missing periods.

### 12. How did you handle bad sensor readings?

The feature service uses a Kalman filter with water level and level-rate as state. It compares a new observation with the predicted value; a value more than three innovation standard deviations away is treated as anomalous and replaced by the filter prediction with a quality flag. I would preserve the raw event too, because quality decisions need auditing and later review.

### 13. What is SHAP, and what does a SHAP value tell you?

SHAP explains how each feature moved one model prediction relative to the model's baseline. A positive contribution means that input pushed risk up, while a negative contribution pushed it down for that particular prediction. It is a local model explanation, not proof that the factor physically caused the flood. In ARGUS, we return the strongest three drivers in human-readable terms.

### 14. Why is explainability important for flood alerts?

Emergency operators need to know whether an alert is being driven by rainfall, a rapid water-level rise, upstream conditions, or a data-quality issue. That helps them validate the decision with domain knowledge and communicate it clearly to stakeholders. It also makes debugging safer: a surprising risk score can be traced back to inputs instead of being treated as a black box.

### 15. What does TimescaleDB store, and why not a normal SQL database?

It stores timestamped feature rows containing village/station identifiers, JSON features, and a quality flag. TimescaleDB is PostgreSQL with time-series capabilities, so it is suited to time-window queries, hypertables, retention, and compression while retaining SQL and JSONB. Plain PostgreSQL could work initially, but TimescaleDB better matches a continuous sensor history at scale.

### 16. What is Redis used for here?

The prediction publisher stores the latest result at keys like `prediction:{village_id}` with a 300-second TTL. That is a low-latency cache for fresh dashboard-style reads, not the long-term audit store. I would add cache invalidation/versioning and metrics for hit rate and stale data before treating it as production-ready.

### 17. How do alert thresholds work?

The service maps probability to normal, advisory, watch, warning, or emergency levels. Base thresholds are lowered when the soil is saturated, monsoon is active, or antecedent moisture is high, because the same rainfall may be more dangerous in those conditions. The response includes an adjustment reason, which improves auditability. Threshold calibration should be reviewed with hydrology/disaster-management experts.

### 18. Flood events are rare. How would you handle class imbalance?

I would start with a chronological split to avoid leaking future information into training. Then I would compare class weights or `scale_pos_weight`, carefully sampled/augmented training cases, and threshold tuning based on the operational cost of false negatives versus false positives. Accuracy is not enough; I would track precision, recall, F1, PR-AUC, ROC-AUC, false-alarm rate, and lead-time quality. Synthetic data may help prototype software, but it cannot substitute for a representative labelled flood dataset.

### 19. Which evaluation metrics matter most?

For a rare-event warning system, recall is important because a missed dangerous flood can be costly. Precision and false-alarm rate matter too, because too many false alerts create alert fatigue. I would report PR-AUC and ROC-AUC for ranking, F1 at a chosen operating threshold, calibration/Brier score for probability quality, and event-based measures such as warning lead time. I would use time-based and basin-based holdouts, not random mixing of nearby timestamps.

### 20. How do you prevent overfitting and underfitting?

For overfitting, I would use temporal cross-validation, holdout seasons/basins, shallow enough trees, learning-rate control, subsampling, regularisation, and early stopping. I would compare training and validation performance and inspect calibration, not only one score. If both are poor, that suggests underfitting or weak features; I would improve data/features or tune capacity before simply adding more trees.

### 21. How would you scale this to one million sensors?

I would partition Kafka topics by station or basin ID so events from the same location stay ordered, increase partitions and consumer replicas, and autoscale consumers based on lag. I would batch database writes, use TimescaleDB partitioning/compression/retention, cache only hot reads, and separate online inference from batch training. Edge filtering can reduce noisy raw data, while a schema registry, idempotency keys, observability, and multi-region disaster recovery become mandatory.

### 22. What happens if the data feed suddenly stops?

The system should track last-seen timestamps per station and surface a data-freshness/quality state rather than silently treating missing data as zero risk. Predictions should include the input freshness and either use a bounded fallback model or lower confidence, depending on policy. I would alert operations on missing critical sources, retain Kafka events for replay, and never issue a “safe” conclusion from stale data alone.

### 23. What was the hardest bug or integration lesson?

“The most important integration lesson was that feature contracts must be treated like APIs. The model expects exactly named, correctly scaled features in a fixed order; a small naming or units mismatch can make a model silently use defaults and return misleading scores. I learned to add schema validation, feature-version metadata, contract tests, and a model-input audit log.”

### 24. How would you test this system?

I would use unit tests for feature windows, Kalman anomaly behaviour, threshold boundaries, and SHAP response formatting. Integration tests should send known gauge/weather events through Kafka or a test broker and assert that a feature row, prediction, Redis entry, and alert decision are produced. I would also run load tests against the gateway, fault tests for broker/database outages, and backtests using historical labelled events. The repository includes integration-style demo tests and a Locust storm-load script, but they are mostly service/API checks rather than a full data-quality benchmark.

### 25. If you had more time, what would you improve?

I would first finish the live-data contracts: standardise topic names, validate feature schemas, store prediction history durably, and add an alert consumer instead of relying on manually invoked alert HTTP calls. Next, I would train and evaluate with documented real historical data, calibrate thresholds with domain experts, add drift monitoring connected to actual data, and use idempotent Kafka consumers with DLQs. Finally, I would add security—authentication, secrets management, least-privilege access, and restricted CORS—before any public deployment.

## 6. Common TCS Digital Project-Section Questions

### “Walk me through your resume project.”

“ARGUS is a real-time flood-risk platform. I worked on the backend ML path: converting sensor/weather history into features, running XGBoost risk prediction, and exposing SHAP-based explanations through FastAPI APIs. The engineering lesson was that a model is only useful when its data contracts, storage, caching, and operational behaviour are reliable.”

### “What was your individual contribution versus the team’s?”

“My contribution was feature engineering, prediction workflow integration, FastAPI endpoints, and explainability-oriented API responses. The repository also has modules for ingestion/CV, alerts/dashboard, and later services; I would not claim those as individual work. I can independently explain how my component consumes data and hands off a prediction.”

### “What was the toughest technical challenge?”

“Turning time-series measurements into a stable real-time feature vector was the toughest part. I had to consider different windows, missing data, noisy sensors, upstream context, and a fixed model feature contract. I handled this with bounded history, quality flags/Kalman filtering, and explicit feature definitions; I would add automated contract tests as the next hardening step.”

### “Why this tech stack and not something simpler?”

“A simple single FastAPI app and database would be sufficient for an early prototype. We chose Kafka and service boundaries because sensor ingestion, feature computation, prediction, alerting, and dashboards have different rates and failure modes. XGBoost and SHAP gave us a practical, explainable model for structured data; TimescaleDB and Redis separate historical analysis from fast reads.”

### “How did you test the project?”

“I used endpoint/health checks, integration-style demo tests, and a Locust storm-load script in the repository. For the ML path, the correct next step is a time-based backtest on real labelled events, including precision/recall, calibration, and lead time. I would be careful not to call synthetic-training metrics real-world accuracy.”

### “What happens if one service fails?”

“The intended design isolates services through Kafka and durable storage, so other components can continue or recover later. A failed consumer should resume from offsets; the dashboard should show degraded freshness rather than fabricate a current result. For critical alerts, I would add retries, a dead-letter queue, alert escalation, and multi-channel delivery monitoring.”

### “What is one thing you learned that college did not teach you?”

“I learned that ML integration is mostly contract and reliability work. A good model can still produce unsafe output if timestamps, units, feature names, missing values, or message topics do not line up. I now think of feature schemas, data quality, and observability as part of the model.”

### “How did AI-assisted development help?”

“It helped accelerate routine work such as skeleton APIs, documentation drafts, test cases, and code exploration. I treated it as a productivity tool, not an authority: I verified feature names, data flow, error handling, and model assumptions against the code and requirements. For a safety-related system, human review and domain validation are non-negotiable.”

### “Why should we trust your prediction?”

“We should not trust any model blindly. We provide SHAP explanations, input quality/freshness, time-based evaluation, and operational thresholds so humans can review a recommendation. In a production rollout, I would validate against historical events, calibrate probabilities, monitor drift, and make final alert policies jointly with disaster-management experts.”

## 7. Quick Revision Cheat Sheet

- **ARGUS:** microservices platform for explainable flash-flood early warning.
- Inputs: **gauge + weather + optional CV virtual-gauge** data.
- Feature Engine: rolling 1/3/6/24h features, AMI, soil proxy, upstream risk.
- **Kalman filter:** rejects a >3-sigma sensor anomaly and marks it quality-imputed.
- **Kafka:** decouples producers/consumers, buffers bursts, enables replay and independent scaling.
- **TimescaleDB:** durable timestamped feature store; prediction path polls it every 60 seconds.
- **XGBoost:** fast tabular flood-probability classifier; 16-feature fast-track contract.
- **SHAP:** explains the top three factors that pushed one prediction up/down.
- Thresholds: advisory/watch/warning/emergency; lower when soil/monsoon/AMI risk is high.
- **Redis:** 5-minute latest-prediction cache; not the historical source of truth.
- My role: feature engineering, prediction workflow, FastAPI integration, explainable API output.
- Tough Q: *Kafka vs REST?* Kafka isolates services and supports buffering/replay; REST is for queries.
- Tough Q: *XGBoost vs NN?* tabular data, low latency, nonlinear interactions, TreeSHAP.
- Tough Q: *One million sensors?* partition by station/basin, scale consumers on lag, batch writes, monitor freshness.
- Honest caveat: checked-in code has **demo/synthetic fallbacks and integration contracts to complete**.

## Verify Before Claiming in an Interview

These are specific codebase checks, not reasons to panic. Be ready to state them accurately if asked about production readiness.

1. **No trained artifacts or historical CSV are checked in.** `models/` only contains `.gitkeep`; the configured historical CSV is absent. The fast XGBoost path therefore trains on synthetic data when startup training is enabled, or falls back to a heuristic if it cannot load/train.
2. **Demo defaults are widespread.** Ingestion, CV gauging, prediction, alert dispatcher, model monitor, and later services default to `DEMO_MODE=true` in their service files. CV processing simulates readings when no model is loaded; it does not perform actual YOLO/SAM inference in this checkout.
3. **The advertised Kafka pipeline has wiring inconsistencies.** Ingestion uses `weather.api`, whereas the weather consumer subscribes to `weather.api.imd`; Feature Engine publishes `features.vector.{station_id}`, whereas the legacy prediction consumer subscribes to `features.vector`. Kafka subscriptions are exact topic names, not wildcard suffixes.
4. **The ingestion non-demo producer path needs repair.** It imports `get_producer`, which is not defined in `shared/kafka_client.py`; the shared wrapper exposes `KafkaProducerClient`. Also confirm the producer call signature and topic conventions before a live demo.
5. **CV is not wired as a Kafka consumer/publisher in its current service file.** It exposes HTTP endpoints and demo readings, but does not consume `cctv.frames` or publish `virtual.gauge` events there.
6. **Feature names need a contract test.** The Timescale `FeatureBuilder` emits names such as `mean_level_1h`, `cumulative_rainfall_6h`, `soil_moisture_proxy`, and `is_monsoon`; the fast XGBoost model expects `level_1hr_mean`, `cumulative_rainfall_6hr`, `soil_moisture_index`, and `is_monsoon_season`. Missing features default to zero in the predictor. This is the most important fix before claiming live accuracy.
7. **Topology JSON shape differs from FeatureStore's expected shape.** The checked-in file wraps stations under `{"stations": {...}}`, while the FeatureStore expects station IDs at the top level with `upstream/downstream` lists. Validate/adapt the loader before relying on the default file for live spatial features.
8. **Alert delivery is HTTP-driven in the checked-in dispatcher.** The dispatcher implements `POST /api/v1/alert/send` and cooldown logic, but does not consume the prediction Kafka topic. It logs/simulates SMS/IVRS in demo mode; Twilio is only attempted for WhatsApp when credentials and non-demo mode are present.
9. **Predictions are cached in memory and Redis, but the new fast path does not persist prediction history to TimescaleDB.** The `predictions` table appears in the setup script but is not written by the fast publisher. Persisted prediction/audit records should be added for production.
10. **“PINN” is prototype-level without a checkpoint.** The feature engine has real PINN training code, but inference falls back to IDW/physics correction when the model file is absent. The separate legacy prediction PINN also routes trained-model inference to its IDW implementation.
11. **Reliability hardening remains.** The shared Kafka consumer uses auto-commit; production should use successful-processing commits, idempotency, retries/DLQs, topic replication, and consumer-lag monitoring. The repository has Docker/Kubernetes/Terraform scaffolding, but do not claim a verified live cloud deployment unless you have run it.

### Best honest closing line

“The project demonstrates the complete architecture and the core feature/prediction services. The current repository is a strong prototype/demo with production hardening still needed around live data, model artefacts, schema contracts, and message wiring. Those checks taught me exactly why reliability and validation matter in an ML system.”
