"""Kafka consumer for the Prediction service.

Subscribes to ``features.vector.*`` and runs the prediction
pipeline: XGBoost → SHAP → PINN → Alert check.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

import structlog

from shared.config import get_settings
from shared.models.feature_engine import FeatureVector
from shared.models.prediction import AlertPayload, RiskLevel

from services.prediction.predictor import FloodPredictor
from services.prediction.explainer import SHAPExplainer
from services.prediction.pinn import PINNMesh
from services.prediction.prediction_store import PredictionStore
from services.prediction.alert_publisher import AlertPublisher

logger = structlog.get_logger(__name__)
settings = get_settings()

# Risk levels that trigger an alert
_ALERT_LEVELS = {RiskLevel.WARNING, RiskLevel.DANGER, RiskLevel.EXTREME}


def _generate_alert(prediction, explanations) -> AlertPayload:
    """Build an AlertPayload from a FloodPrediction."""
    top_factors = [
        f"{e.feature_name} = {e.feature_value} (contribution: {e.shap_value:+.2f})"
        for e in explanations[:3]
    ]
    actions = []
    if prediction.risk_level == RiskLevel.EXTREME:
        actions = [
            "EVACUATE low-lying areas immediately",
            "Issue CAP alert to all downstream communities",
            "Deploy all rescue assets",
        ]
    elif prediction.risk_level == RiskLevel.DANGER:
        actions = [
            "Issue public warning via CAP",
            "Notify downstream communities",
            "Pre-position rescue boats",
        ]
    elif prediction.risk_level == RiskLevel.WARNING:
        actions = [
            "Increase monitoring frequency",
            "Alert emergency response teams",
            "Prepare evacuation routes",
        ]

    return AlertPayload(
        alert_id=f"ALT-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
        station_id=prediction.station_id,
        timestamp=prediction.timestamp,
        risk_level=prediction.risk_level,
        flood_probability=prediction.flood_probability,
        predicted_peak_level_m=prediction.predicted_peak_level_m,
        predicted_peak_time=prediction.predicted_peak_time,
        lead_time_hours=prediction.lead_time_hours,
        top_contributing_factors=top_factors,
        affected_area_geojson=None,  # Phase 2: inundation mapping
        recommended_actions=actions,
    )


async def _process_feature_vector(
    payload: dict,
    predictor: FloodPredictor,
    explainer: SHAPExplainer,
    pinn: PINNMesh,
    store: PredictionStore,
    alert_publisher: AlertPublisher,
) -> None:
    """Full prediction pipeline for one feature vector."""
    try:
        fv = FeatureVector(**payload)
    except Exception as exc:
        logger.error("invalid_feature_vector", error=str(exc))
        return

    # 1. XGBoost prediction
    prediction = predictor.predict(fv)

    # 2. SHAP explanations
    explanations = explainer.explain(fv, prediction)
    prediction.shap_explanations = explanations

    # 3. Store prediction
    store.set_prediction(prediction)
    logger.info(
        "prediction_complete",
        station=fv.station_id,
        probability=prediction.flood_probability,
        risk=prediction.risk_level.value,
    )

    # 4. PINN mesh interpolation (use current station data)
    station_readings = {
        fv.station_id: (
            fv.cv_depth_m or fv.temporal.level_mean_1h,
            fv.cv_velocity_ms or 0.0,
        )
    }
    pinn_readings = pinn.interpolate(station_readings, fv.timestamp)
    store.set_pinn_cells(pinn_readings)

    # 5. Alert check
    if prediction.risk_level in _ALERT_LEVELS:
        alert = _generate_alert(prediction, explanations)
        alert_publisher.publish(alert)
        logger.warning(
            "alert_dispatched",
            alert_id=alert.alert_id,
            station=alert.station_id,
            risk=alert.risk_level.value,
        )


async def start_prediction_consumer(
    predictor: FloodPredictor,
    explainer: SHAPExplainer,
    pinn: PINNMesh,
    store: PredictionStore,
    alert_publisher: AlertPublisher,
) -> None:
    """Start Kafka consumer for feature vectors."""
    try:
        from confluent_kafka import Consumer

        consumer = Consumer(
            {
                "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "group.id": f"{settings.KAFKA_GROUP_PREFIX}.prediction",
                "auto.offset.reset": "latest",
                "enable.auto.commit": True,
            }
        )
        consumer.subscribe(["features.vector"])
        logger.info("prediction_consumer_started")

        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                await asyncio.sleep(0.01)
                continue
            if msg.error():
                logger.error("kafka_error", error=str(msg.error()))
                continue

            try:
                payload = json.loads(msg.value().decode("utf-8"))
                await _process_feature_vector(
                    payload, predictor, explainer, pinn, store, alert_publisher
                )
            except Exception as exc:
                logger.exception("prediction_pipeline_error", error=str(exc))

    except ImportError:
        logger.warning("confluent_kafka_not_installed_prediction_consumer_skipped")
    except Exception as exc:
        logger.exception("prediction_consumer_crash", error=str(exc))
