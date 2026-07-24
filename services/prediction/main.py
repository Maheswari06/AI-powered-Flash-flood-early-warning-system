"""Prediction Service — FastAPI application.

Dual-track prediction engine:
  1. Fast track: XGBoost flood-probability predictor + SHAP explainability
  2. Adaptive alert thresholds (NDMA-based, condition-adjusted)

Consumes enriched features from TimescaleDB (polled every 60s),
runs the prediction pipeline, publishes results to Kafka + Redis,
and exposes REST API endpoints for the dashboard and alert dispatcher.

Also retains the original Kafka ``features.vector.*`` consumer for
backward compatibility with the feature engine.

Run: ``uvicorn services.prediction.main:app --reload --port 8004``
"""

from __future__ import annotations

import asyncio
import os
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

import structlog
from fastapi import FastAPI, HTTPException, Query

from shared.config import get_settings
from shared.models.prediction import FloodPrediction, PINNSensorReading, AlertPayload

# Original modules (kept for backward compat)
from services.prediction.predictor import FloodPredictor
from services.prediction.explainer import SHAPExplainer
from services.prediction.pinn import PINNMesh
from services.prediction.consumer import start_prediction_consumer
from services.prediction.alert_publisher import AlertPublisher
from services.prediction.prediction_store import PredictionStore

# New fast-track modules
from services.prediction.fast_track.xgboost_predictor import XGBoostPredictor
from services.prediction.fast_track.shap_explainer import SHAPExplainerV2
from services.prediction.fast_track.threshold_engine import ThresholdEngine
from services.prediction.fast_track.alert_classifier import AlertClassifier, AlertLevel, ConfidenceBand
from services.prediction.consumers.feature_consumer import FeatureConsumer
from services.prediction.publishers.prediction_publisher import PredictionPublisher

# Deep-track TFT multi-horizon predictor
from services.prediction.deep_track.tft_predictor import TFTFloodPredictor

logger = structlog.get_logger(__name__)
settings = get_settings()

# ══════════════════════════════════════════════════════════════════════════
# Singletons
# ══════════════════════════════════════════════════════════════════════════

# Original prediction pipeline (backward compat)
prediction_store = PredictionStore()
predictor = FloodPredictor()
explainer = SHAPExplainer(predictor)
pinn = PINNMesh()
alert_publisher = AlertPublisher()

# New fast-track prediction pipeline
xgb_predictor = XGBoostPredictor(
    model_path=os.getenv("XGBOOST_MODEL_PATH", "./models/xgboost_flood.joblib"),
    training_data_path=os.getenv("TRAINING_DATA_PATH", "./data/cwc_historical_2019_2023.csv"),
    train_on_startup=os.getenv("TRAIN_ON_STARTUP", "true").lower() in ("true", "1", "yes"),
)
shap_explainer = SHAPExplainerV2(model=xgb_predictor.model)
threshold_engine = ThresholdEngine()
alert_classifier = AlertClassifier()
prediction_publisher = PredictionPublisher()

# Deep-track TFT predictor
tft_predictor = TFTFloodPredictor(
    checkpoint_path=os.getenv("TFT_CHECKPOINT_PATH", "./models/tft_flood.ckpt"),
    enabled=os.getenv("TFT_ENABLED", "true").lower() in ("true", "1", "yes"),
)

# In-memory prediction cache (village_id → latest prediction dict)
_predictions_cache: Dict[str, Dict[str, Any]] = {}
_predictions_history: Dict[str, Deque[Dict[str, Any]]] = defaultdict(
    lambda: deque(maxlen=200)
)

# TimescaleDB DSN
_TIMESCALE_DSN = os.getenv(
    "TIMESCALE_URL",
    os.getenv("TIMESCALEDB_DSN", "postgresql://argus:argus@localhost:5432/argus"),
)

DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")


def _seed_demo_predictions():
    """Populate prediction cache with realistic demo data for all 12 villages.

    Called at startup when DEMO_MODE=true and cache is empty, so the dashboard
    and copilot have predictions available immediately.
    """
    import random

    now = datetime.now(timezone.utc)

    villages = [
        ("VIL-HP-MANDI",     "WATCH",     0.62),
        ("VIL-HP-KULLU",     "ADVISORY",  0.48),
        ("VIL-HP-MANALI",    "NORMAL",    0.22),
        ("VIL-HP-BHUNTAR",   "ADVISORY",  0.41),
        ("VIL-HP-PANDOH",    "NORMAL",    0.18),
        ("VIL-HP-LARJI",     "NORMAL",    0.28),
        ("VIL-HP-BANJAR",    "NORMAL",    0.15),
        ("VIL-AS-MAJULI",    "WARNING",   0.81),
        ("VIL-AS-JORHAT",    "WATCH",     0.58),
        ("VIL-AS-DIBRUGARH", "ADVISORY",  0.44),
        ("VIL-AS-TEZPUR",    "ADVISORY",  0.39),
        ("VIL-AS-GUWAHATI",  "NORMAL",    0.25),
    ]

    for vid, level, base_risk in villages:
        risk = round(base_risk + random.uniform(-0.03, 0.03), 4)
        result = {
            "village_id": vid,
            "risk_score": risk,
            "alert_level": level,
            "explanation": [
                {"feature": "cumulative_rainfall_6hr", "shap_value": round(random.uniform(0.05, 0.25), 3), "direction": "UP"},
                {"feature": "soil_moisture_index", "shap_value": round(random.uniform(0.03, 0.15), 3), "direction": "UP"},
                {"feature": "upstream_risk_score", "shap_value": round(random.uniform(0.02, 0.10), 3), "direction": "UP"},
            ],
            "adaptive_threshold": {
                "advisory": 0.35,
                "watch": 0.55,
                "warning": 0.72,
                "emergency": 0.88,
                "adjustment_reason": "monsoon_active + elevated_soil_moisture",
            },
            "timestamp": now.isoformat(),
            "confidence": "HIGH" if risk > 0.6 else "MEDIUM" if risk > 0.35 else "LOW",
            "quality": "DEMO",
        }
        _predictions_cache[vid] = result
        _predictions_history[vid].append(result)

    logger.info("demo_predictions_seeded", count=len(villages))


# ══════════════════════════════════════════════════════════════════════════
# Core prediction pipeline
# ══════════════════════════════════════════════════════════════════════════

def run_prediction_pipeline(
    village_id: str,
    features: Dict[str, float],
    quality: str = "GOOD",
) -> Dict[str, Any]:
    """Execute the full fast-track prediction pipeline for one village.

    Steps:
      1. XGBoost → flood probability
      2. SHAP → top-3 explanation factors
      3. Adaptive thresholds (soil moisture, monsoon, AMI)
      4. Alert classification
      5. Cache + publish

    Returns:
        Prediction result dict matching the API contract.
    """
    now = datetime.now(timezone.utc)

    # 1. XGBoost prediction
    risk_score = xgb_predictor.predict(features)

    # 2. SHAP explanation
    shap_factors = shap_explainer.explain(features)
    explanation = [f.to_dict() for f in shap_factors]

    # 3. Adaptive thresholds
    soil_moisture = features.get("soil_moisture_index", 0.0)
    ami = features.get("antecedent_moisture_index", 0.0)
    is_monsoon = features.get("is_monsoon_season", 0.0) >= 0.5

    thresholds = threshold_engine.compute(
        soil_moisture_index=soil_moisture,
        is_monsoon_season=is_monsoon,
        antecedent_moisture_index=ami,
    )

    # 4. Alert classification
    alert_level, confidence = alert_classifier.classify(risk_score, thresholds)

    # 5. Build result
    result: Dict[str, Any] = {
        "village_id": village_id,
        "risk_score": round(risk_score, 4),
        "alert_level": alert_level.value,
        "explanation": explanation,
        "adaptive_threshold": {
            "advisory": thresholds.advisory,
            "watch": thresholds.watch,
            "warning": thresholds.warning,
            "emergency": thresholds.emergency,
            "adjustment_reason": thresholds.adjustment_reason,
        },
        "timestamp": now.isoformat(),
        "confidence": confidence.value,
        "quality": quality,
    }

    # Cache
    _predictions_cache[village_id] = result
    _predictions_history[village_id].append(result)

    # Publish to Kafka + Redis
    prediction_publisher.publish(village_id, result)

    logger.info(
        "prediction_complete",
        village=village_id,
        risk_score=risk_score,
        alert_level=alert_level.value,
        confidence=confidence.value,
    )

    return result


# ── Feature consumer callback ────────────────────────────────────────────

def _on_features_received(village_id: str, features: Dict[str, float], quality: str) -> None:
    """Callback invoked by FeatureConsumer for each village."""
    try:
        run_prediction_pipeline(village_id, features, quality)
    except Exception as exc:
        logger.exception("prediction_pipeline_error", village=village_id, error=str(exc))


# ══════════════════════════════════════════════════════════════════════════
# Lifespan
# ══════════════════════════════════════════════════════════════════════════

# Feature consumer instance
feature_consumer = FeatureConsumer(dsn=_TIMESCALE_DSN, on_features=_on_features_received)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start all consumers and background tasks on startup."""
    logger.info("prediction_service_starting", version="2.1.0")

    # Start original Kafka consumer (backward compat)
    kafka_task = asyncio.create_task(
        start_prediction_consumer(
            predictor=predictor,
            explainer=explainer,
            pinn=pinn,
            store=prediction_store,
            alert_publisher=alert_publisher,
        )
    )

    # Start TimescaleDB feature consumer (new fast-track path)
    feature_task = asyncio.create_task(feature_consumer.start())

    # Seed demo predictions so dashboard has data on startup
    if DEMO_MODE and not _predictions_cache:
        _seed_demo_predictions()

    yield

    # Shutdown
    kafka_task.cancel()
    await feature_consumer.stop()
    feature_task.cancel()
    prediction_publisher.flush()
    logger.info("prediction_service_stopped")


app = FastAPI(
    title="ARGUS Prediction Service",
    version="2.1.0",
    description=(
        "Triple-track flood prediction: XGBoost fast-path with SHAP explainability, "
        "TFT deep-track multi-horizon quantile forecasting, "
        "+ adaptive alert thresholds. Consumed by dashboard and alert dispatcher."
    ),
    lifespan=lifespan,
)


# ══════════════════════════════════════════════════════════════════════════
# API Endpoints — primary (used by Dhana's dashboard + alert dispatcher)
# ══════════════════════════════════════════════════════════════════════════


@app.get("/api/v1/health")
async def health_v1():
    """Detailed health check."""
    return {
        "status": "ok",
        "service": "prediction",
        "version": "2.1.0",
        "components": {
            "xgboost_loaded": xgb_predictor.is_loaded,
            "xgboost_model_version": xgb_predictor.model_version,
            "shap_ready": shap_explainer._explainer is not None,
            "tft_enabled": tft_predictor.enabled,
            "tft_loaded": tft_predictor.is_loaded,
            "feature_consumer_connected": feature_consumer.is_connected,
            "villages_tracked": len(_predictions_cache),
            "original_predictor_loaded": predictor.is_loaded,
            "pinn_loaded": pinn.is_loaded,
        },
    }


@app.get("/health")
async def health():
    """Simple health check."""
    return {"status": "ok", "service": "prediction"}


# ── Per-village prediction (Dhana's primary endpoint) ────────────────────
@app.get("/api/v1/prediction/{village_id}")
async def get_prediction(village_id: str):
    """Return the latest prediction for a village.

    Response::

        {
            "village_id": str,
            "risk_score": float,          # 0.0–1.0
            "alert_level": str,           # NORMAL/ADVISORY/WATCH/WARNING/EMERGENCY
            "explanation": [...],         # SHAP top 3
            "adaptive_threshold": {
                "watch": float,
                "warning": float,
                "adjustment_reason": str
            },
            "timestamp": datetime,
            "confidence": str             # LOW/MEDIUM/HIGH
        }
    """
    cached = _predictions_cache.get(village_id)
    if cached is not None:
        return cached

    # Fall back to original station-based prediction store
    pred = prediction_store.get_latest(village_id)
    if pred is not None:
        return pred

    raise HTTPException(
        status_code=404,
        detail=f"No prediction available for village {village_id}",
    )


# ── All predictions (for dashboard map) ──────────────────────────────────
@app.get("/api/v1/predictions/all")
async def get_all_predictions():
    """Return latest predictions for ALL villages (dashboard map rendering)."""
    results = list(_predictions_cache.values())

    # Also include original station-based predictions not yet in cache
    for sid in prediction_store._latest:
        if sid not in _predictions_cache:
            pred = prediction_store.get_latest(sid)
            if pred:
                results.append(pred.model_dump(mode="json"))

    return results


# ── Prediction history ──────────────────────────────────────────────────
@app.get("/api/v1/prediction/{village_id}/history")
async def get_prediction_history_v2(
    village_id: str,
    limit: int = Query(default=50, ge=1, le=500),
):
    """Return recent prediction history for a village."""
    hist = _predictions_history.get(village_id)
    if hist:
        return list(hist)[-limit:]

    # Fall back to original store
    return prediction_store.get_history(village_id, limit)


# ══════════════════════════════════════════════════════════════════════════
# API Endpoints — backward compatible (original pipeline)
# ══════════════════════════════════════════════════════════════════════════


@app.get("/api/v1/prediction/{station_id}/latest", response_model=FloodPrediction)
async def get_latest_prediction_legacy(station_id: str):
    """Return the most recent flood prediction for *station_id* (legacy)."""
    pred = prediction_store.get_latest(station_id)
    if pred is None:
        raise HTTPException(status_code=404, detail=f"No prediction for {station_id}")
    return pred


@app.get("/api/v1/pinn/{grid_cell_id}/latest", response_model=PINNSensorReading)
async def get_pinn_cell(grid_cell_id: str):
    """Return latest PINN interpolated reading for a mesh cell."""
    reading = prediction_store.get_pinn_cell(grid_cell_id)
    if reading is None:
        raise HTTPException(status_code=404, detail=f"No PINN data for {grid_cell_id}")
    return reading


@app.get("/api/v1/prediction/bulk", response_model=list[FloodPrediction])
async def get_bulk_predictions(
    station_ids: str = Query(..., description="Comma separated station IDs"),
):
    """Bulk fetch latest predictions (legacy)."""
    ids = [s.strip() for s in station_ids.split(",") if s.strip()]
    return [
        p for sid in ids
        if (p := prediction_store.get_latest(sid)) is not None
    ]


# ── Model metadata ──────────────────────────────────────────────────────
@app.get("/api/v1/model/info")
async def model_info():
    """Return metadata about all loaded models."""
    return {
        "xgboost_fast_track": {
            "version": xgb_predictor.model_version,
            "features": xgb_predictor.feature_names,
            "loaded": xgb_predictor.is_loaded,
            "train_metrics": xgb_predictor.train_metrics,
        },
        "tft_deep_track": tft_predictor.info(),
        "xgboost_legacy": {
            "version": predictor.model_version,
            "features": predictor.feature_names,
            "loaded": predictor.is_loaded,
        },
        "pinn": {
            "grid_cells": pinn.num_cells,
            "loaded": pinn.is_loaded,
        },
        "threshold_engine": {
            "base_thresholds": threshold_engine._base,
        },
    }


# ── Manual prediction trigger (for testing) ─────────────────────────────
@app.post("/api/v1/prediction/{village_id}/run")
async def trigger_prediction(village_id: str, features: Dict[str, float]):
    """Manually trigger a prediction with provided features (for testing)."""
    result = run_prediction_pipeline(village_id, features)
    return result


# ══════════════════════════════════════════════════════════════════════════
# API Endpoints — TFT Deep Track (multi-horizon quantile forecasting)
# ══════════════════════════════════════════════════════════════════════════


@app.get("/api/v1/prediction/{village_id}/deep")
async def get_deep_prediction(village_id: str):
    """Return multi-horizon quantile flood forecast for a village.

    Combines the XGBoost fast-track risk score with TFT deep-track
    multi-horizon probabilistic predictions.

    Response::

        {
            "village_id": str,
            "fast_track": {                   # XGBoost instant risk
                "risk_score": float,
                "alert_level": str,
            },
            "deep_track": {                   # TFT multi-horizon
                "model": str,
                "horizons": [
                    {
                        "minutes": int,
                        "p10": float,
                        "p50": float,
                        "p90": float,
                        "spread": float
                    }, ...
                ],
                "peak_risk_horizon_min": int,
                "peak_risk_value": float,
                "trend": str                  # RISING / FALLING / STABLE
            },
            "timestamp": datetime
        }
    """
    if not tft_predictor.enabled:
        raise HTTPException(
            status_code=503,
            detail="TFT deep track is disabled; set TFT_ENABLED=true",
        )

    # Get cached fast-track prediction
    cached = _predictions_cache.get(village_id)

    # If no cached prediction, generate one from defaults
    if cached is None:
        # Use demo features for uncached villages
        demo_features = {
            "level_1hr_mean": 4.2,
            "level_3hr_mean": 3.9,
            "level_6hr_mean": 3.5,
            "level_24hr_mean": 3.1,
            "level_1hr_max": 5.1,
            "rate_of_change_1hr": 0.15,
            "rate_of_change_3hr": 0.08,
            "cumulative_rainfall_6hr": 45.0,
            "cumulative_rainfall_24hr": 120.0,
            "soil_moisture_index": 0.72,
            "antecedent_moisture_index": 35.0,
            "upstream_risk_score": 0.4,
            "basin_connectivity_score": 0.65,
            "hour_of_day": float(datetime.now(timezone.utc).hour),
            "day_of_year": float(datetime.now(timezone.utc).timetuple().tm_yday),
            "is_monsoon_season": 1.0,
        }
        cached = run_prediction_pipeline(village_id, demo_features)

    xgb_risk = cached.get("risk_score", 0.5)

    # Build feature dict from cached prediction or defaults
    features = {}
    for fname in FEATURE_NAMES:
        features[fname] = cached.get(fname, 0.0)

    # Anchor key features from the XGBoost result
    features.setdefault("level_1hr_mean", 4.2)
    features.setdefault("cumulative_rainfall_6hr", 45.0)
    features.setdefault("soil_moisture_index", 0.72)
    features.setdefault("upstream_risk_score", xgb_risk * 0.6)

    deep = tft_predictor.predict(village_id, features, xgb_risk_score=xgb_risk)

    return {
        "village_id": village_id,
        "fast_track": {
            "risk_score": cached.get("risk_score"),
            "alert_level": cached.get("alert_level"),
            "confidence": cached.get("confidence"),
        },
        "deep_track": deep,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/prediction/deep/info")
async def deep_track_info():
    """Return TFT deep-track model metadata."""
    return tft_predictor.info()


# Make FEATURE_NAMES accessible for the deep endpoint
from services.prediction.deep_track.tft_predictor import FEATURE_NAMES
