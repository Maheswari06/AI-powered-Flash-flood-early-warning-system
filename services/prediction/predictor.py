"""XGBoost flood-risk predictor.

Loads a trained XGBoost model and converts a FeatureVector into
a flood probability + risk level classification.

In demo mode (no model file), uses a rule-based heuristic so
the service can run end-to-end without a trained artefact.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

import numpy as np
import structlog

from shared.config import get_settings
from shared.models.feature_engine import FeatureVector
from shared.models.prediction import FloodPrediction, RiskLevel

logger = structlog.get_logger(__name__)
settings = get_settings()

# Feature columns expected by the XGBoost model (order matters)
FEATURE_NAMES: List[str] = [
    "level_mean_1h",
    "level_max_1h",
    "level_delta_1h",
    "level_rate_of_change",
    "rainfall_cumulative_3h",
    "rainfall_cumulative_6h",
    "rainfall_cumulative_24h",
    "rainfall_intensity_max_1h",
    "flow_mean_1h",
    "flow_delta_1h",
    "velocity_mean_30m",
    "velocity_max_30m",
    "upstream_level_mean",
    "upstream_level_max",
    "upstream_flow_mean",
    "upstream_rainfall_mean",
    "num_upstream_alerts",
    "catchment_avg_rainfall_6h",
    "distance_weighted_level",
    "cv_depth_m",
    "cv_velocity_ms",
    "cv_confidence",
    "soil_moisture_pct",
    "antecedent_precip_index",
    "is_monsoon",
    "hour_of_day",
    "day_of_year",
]


class FloodPredictor:
    """XGBoost-based flood probability estimator."""

    def __init__(self) -> None:
        self.model = None
        self.model_version: str = "xgb-v1.0.0"
        self.feature_names: List[str] = FEATURE_NAMES
        self.is_loaded: bool = False
        self._try_load_model()

    def _try_load_model(self) -> None:
        """Attempt to load a persisted XGBoost model (joblib-serialised sklearn estimator)."""
        try:
            import joblib
            from pathlib import Path

            model_path = Path(settings.XGBOOST_MODEL_PATH)
            if model_path.exists():
                self.model = joblib.load(str(model_path))
                self.is_loaded = True
                logger.info("xgboost_model_loaded", path=str(model_path))
            else:
                logger.warning("xgboost_model_not_found_using_heuristic", path=str(model_path))
        except ImportError:
            logger.warning("joblib_not_installed_using_heuristic")

    def _feature_vector_to_array(self, fv: FeatureVector) -> np.ndarray:
        """Flatten a FeatureVector into a 1-D numpy array matching FEATURE_NAMES order."""
        t = fv.temporal
        s = fv.spatial
        values = [
            t.level_mean_1h,
            t.level_max_1h,
            t.level_delta_1h,
            t.level_rate_of_change,
            t.rainfall_cumulative_3h,
            t.rainfall_cumulative_6h,
            t.rainfall_cumulative_24h,
            t.rainfall_intensity_max_1h,
            t.flow_mean_1h or 0.0,
            t.flow_delta_1h or 0.0,
            t.velocity_mean_30m or 0.0,
            t.velocity_max_30m or 0.0,
            s.upstream_level_mean or 0.0,
            s.upstream_level_max or 0.0,
            s.upstream_flow_mean or 0.0,
            s.upstream_rainfall_mean or 0.0,
            float(s.num_upstream_alerts),
            s.catchment_avg_rainfall_6h or 0.0,
            s.distance_weighted_level or 0.0,
            fv.cv_depth_m or 0.0,
            fv.cv_velocity_ms or 0.0,
            fv.cv_confidence or 0.0,
            fv.soil_moisture_pct or 50.0,  # default assumption
            fv.antecedent_precip_index or 0.0,
            float(fv.is_monsoon),
            float(fv.hour_of_day),
            float(fv.day_of_year),
        ]
        return np.array(values, dtype=np.float32).reshape(1, -1)

    def _classify_risk(self, probability: float) -> RiskLevel:
        """Map flood probability to discrete risk level."""
        if probability >= 0.9:
            return RiskLevel.EXTREME
        elif probability >= 0.7:
            return RiskLevel.DANGER
        elif probability >= 0.5:
            return RiskLevel.WARNING
        elif probability >= 0.3:
            return RiskLevel.WATCH
        else:
            return RiskLevel.NORMAL

    def _heuristic_predict(self, fv: FeatureVector) -> float:
        """Rule-based fallback when no trained model is available.

        Weighted combination of key risk indicators normalised to [0, 1].
        """
        t = fv.temporal
        s = fv.spatial

        # Normalise individual signals to 0-1 range
        level_risk = min(t.level_delta_1h / 1.0, 1.0) if t.level_delta_1h > 0 else 0.0
        rain_risk = min(t.rainfall_cumulative_6h / 150.0, 1.0)
        intensity_risk = min(t.rainfall_intensity_max_1h / 50.0, 1.0)
        upstream_risk = min((s.num_upstream_alerts or 0) / 3.0, 1.0)
        cv_depth_risk = min((fv.cv_depth_m or 0.0) / 5.0, 1.0)
        rate_risk = min(t.level_rate_of_change / 0.5, 1.0) if t.level_rate_of_change > 0 else 0.0

        # Weighted sum
        probability = (
            0.25 * rain_risk
            + 0.20 * level_risk
            + 0.15 * rate_risk
            + 0.15 * intensity_risk
            + 0.15 * upstream_risk
            + 0.10 * cv_depth_risk
        )
        return round(min(max(probability, 0.0), 1.0), 4)

    def predict(self, fv: FeatureVector) -> FloodPrediction:
        """Run prediction on a single feature vector and return FloodPrediction.

        Uses XGBoost if a model is loaded, otherwise falls back to a
        weighted heuristic so the system can run in demo mode.
        """
        now = fv.timestamp

        if self.model is not None and self.is_loaded:
            X = self._feature_vector_to_array(fv)
            if hasattr(self.model, "predict_proba"):
                probability = float(self.model.predict_proba(X)[0, 1])
            else:
                probability = float(self.model.predict(X)[0])
        else:
            probability = self._heuristic_predict(fv)

        risk_level = self._classify_risk(probability)

        # Estimate peak level (simple linear extrapolation in demo)
        current_level = fv.temporal.level_max_1h
        rate = fv.temporal.level_rate_of_change
        lead_hours = 6.0
        predicted_peak = round(current_level + rate * lead_hours, 2) if rate > 0 else current_level

        return FloodPrediction(
            station_id=fv.station_id,
            timestamp=now,
            flood_probability=probability,
            risk_level=risk_level,
            predicted_peak_level_m=predicted_peak,
            predicted_peak_time=now + timedelta(hours=lead_hours) if rate > 0 else None,
            lead_time_hours=lead_hours,
            model_version=self.model_version,
            shap_explanations=[],  # filled by SHAPExplainer
            confidence_interval_lower=round(predicted_peak - 0.45, 2) if predicted_peak else None,
            confidence_interval_upper=round(predicted_peak + 0.45, 2) if predicted_peak else None,
        )
