"""Pydantic v2 schemas for the Prediction service.

Covers XGBoost flood-risk predictions, SHAP explanations,
PINN sensor-mesh readings, and alert payloads dispatched
to the Alert Dispatcher service.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Flood risk classification following CWC standard levels."""

    NORMAL = "NORMAL"
    WATCH = "WATCH"         # ≥ 0.3 probability
    WARNING = "WARNING"     # ≥ 0.5 probability
    DANGER = "DANGER"       # ≥ 0.7 probability
    EXTREME = "EXTREME"     # ≥ 0.9 probability


class SHAPExplanation(BaseModel):
    """Per-feature SHAP contribution for one prediction."""

    feature_name: str
    shap_value: float = Field(..., description="SHAP contribution (log-odds scale)")
    feature_value: float = Field(..., description="Actual feature value used")
    rank: int = Field(..., ge=1, description="Importance rank (1 = most important)")

    model_config = {"json_schema_extra": {"examples": [
        {
            "feature_name": "rainfall_cumulative_6h",
            "shap_value": 0.84,
            "feature_value": 98.0,
            "rank": 1,
        }
    ]}}


class FloodPrediction(BaseModel):
    """XGBoost flood-risk prediction produced for every feature vector.

    Kafka topic: ``prediction.flood.{station_id}``
    """

    station_id: str = Field(..., description="Target station identifier")
    timestamp: datetime = Field(..., description="Prediction UTC timestamp")
    flood_probability: float = Field(
        ..., ge=0.0, le=1.0, description="Flood probability [0, 1]"
    )
    risk_level: RiskLevel = Field(..., description="Categorical risk classification")
    predicted_peak_level_m: Optional[float] = Field(
        None, description="Predicted peak water level (m) in next 6 h"
    )
    predicted_peak_time: Optional[datetime] = Field(
        None, description="Estimated time of peak"
    )
    lead_time_hours: float = Field(
        ..., ge=0, description="Forecast lead time in hours"
    )
    model_version: str = Field(
        default="xgb-v1.0.0", description="Model artefact version"
    )
    shap_explanations: List[SHAPExplanation] = Field(
        default_factory=list,
        description="Top-k SHAP feature contributions",
    )
    confidence_interval_lower: Optional[float] = Field(
        None, description="Lower bound (5th percentile) of peak level"
    )
    confidence_interval_upper: Optional[float] = Field(
        None, description="Upper bound (95th percentile) of peak level"
    )

    model_config = {"json_schema_extra": {"examples": [
        {
            "station_id": "CWC-KAR-001",
            "timestamp": "2025-08-15T07:05:00Z",
            "flood_probability": 0.78,
            "risk_level": "DANGER",
            "predicted_peak_level_m": 6.25,
            "predicted_peak_time": "2025-08-15T13:00:00Z",
            "lead_time_hours": 6.0,
            "model_version": "xgb-v1.0.0",
            "shap_explanations": [
                {
                    "feature_name": "rainfall_cumulative_6h",
                    "shap_value": 0.84,
                    "feature_value": 98.0,
                    "rank": 1,
                }
            ],
            "confidence_interval_lower": 5.80,
            "confidence_interval_upper": 6.70,
        }
    ]}}


class PINNSensorReading(BaseModel):
    """Physics-Informed Neural Network interpolated sensor output.

    The PINN mesh fills spatial gaps between physical gauges
    using Saint-Venant shallow water equations as physics loss.

    Kafka topic: ``pinn.mesh.{grid_cell_id}``
    """

    grid_cell_id: str = Field(..., description="Virtual mesh cell identifier")
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    timestamp: datetime
    interpolated_depth_m: float = Field(..., ge=0, description="PINN estimated depth (m)")
    interpolated_velocity_ms: float = Field(..., ge=0, description="PINN estimated velocity (m/s)")
    physics_residual: float = Field(
        ...,
        description="Saint-Venant PDE residual — lower is better",
    )
    data_loss: float = Field(..., description="Observed vs predicted MSE component")
    nearest_station_id: Optional[str] = Field(
        None, description="Nearest physical gauge used for anchoring"
    )
    confidence: float = Field(..., ge=0, le=1, description="PINN prediction confidence")

    model_config = {"json_schema_extra": {"examples": [
        {
            "grid_cell_id": "MESH-HP-032",
            "lat": 31.85,
            "lon": 77.12,
            "timestamp": "2025-08-15T07:05:00Z",
            "interpolated_depth_m": 2.45,
            "interpolated_velocity_ms": 1.32,
            "physics_residual": 0.0021,
            "data_loss": 0.015,
            "nearest_station_id": "CWC-KAR-001",
            "confidence": 0.91,
        }
    ]}}


class AlertPayload(BaseModel):
    """Alert dispatched to the Alert Dispatcher service.

    Kafka topic: ``alerts.dispatch``
    """

    alert_id: str = Field(..., description="Unique alert UUID")
    station_id: str
    timestamp: datetime
    risk_level: RiskLevel
    flood_probability: float = Field(..., ge=0, le=1)
    predicted_peak_level_m: Optional[float] = None
    predicted_peak_time: Optional[datetime] = None
    lead_time_hours: float = Field(..., ge=0)
    top_contributing_factors: List[str] = Field(
        default_factory=list,
        description="Human-readable top SHAP factors",
    )
    affected_area_geojson: Optional[dict] = Field(
        None, description="GeoJSON polygon of estimated inundation"
    )
    recommended_actions: List[str] = Field(
        default_factory=list,
        description="Auto-generated recommended actions",
    )

    model_config = {"json_schema_extra": {"examples": [
        {
            "alert_id": "ALT-20250815-001",
            "station_id": "CWC-KAR-001",
            "timestamp": "2025-08-15T07:05:00Z",
            "risk_level": "DANGER",
            "flood_probability": 0.78,
            "predicted_peak_level_m": 6.25,
            "predicted_peak_time": "2025-08-15T13:00:00Z",
            "lead_time_hours": 6.0,
            "top_contributing_factors": [
                "Heavy 6h cumulative rainfall (98 mm)",
                "Rapid water level rise (+0.23 m/hr)",
                "Two upstream stations in alert",
            ],
            "affected_area_geojson": None,
            "recommended_actions": [
                "Issue public warning via CAP",
                "Notify downstream communities",
                "Pre-position rescue boats",
            ],
        }
    ]}}
