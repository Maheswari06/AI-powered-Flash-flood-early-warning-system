"""Pydantic v2 schemas for the Feature Engineering service.

The feature engine consumes raw data from Kafka and produces
enriched feature vectors ready for the prediction service.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class TemporalFeatures(BaseModel):
    """Time-series derived features for a single station/camera."""

    station_id: str = Field(..., description="Gauge or camera ID")
    timestamp: datetime
    level_mean_1h: float = Field(..., description="Mean water level over last 1 hour")
    level_max_1h: float = Field(..., description="Max water level over last 1 hour")
    level_delta_1h: float = Field(..., description="Change in level over 1 hour (m)")
    level_rate_of_change: float = Field(..., description="dL/dt in m/hr")
    rainfall_cumulative_3h: float = Field(..., description="Cumulative rainfall past 3 h (mm)")
    rainfall_cumulative_6h: float = Field(..., description="Cumulative rainfall past 6 h (mm)")
    rainfall_cumulative_24h: float = Field(..., description="Cumulative rainfall past 24 h (mm)")
    rainfall_intensity_max_1h: float = Field(..., description="Peak rainfall mm/hr in last hour")
    flow_mean_1h: Optional[float] = Field(None, description="Mean discharge past 1 h (m³/s)")
    flow_delta_1h: Optional[float] = Field(None, description="Discharge change past 1 h")
    velocity_mean_30m: Optional[float] = Field(None, description="Mean CV velocity past 30 min (m/s)")
    velocity_max_30m: Optional[float] = Field(None, description="Max CV velocity past 30 min (m/s)")

    model_config = {"json_schema_extra": {"examples": [
        {
            "station_id": "CWC-KAR-001",
            "timestamp": "2025-08-15T07:00:00Z",
            "level_mean_1h": 4.48,
            "level_max_1h": 4.62,
            "level_delta_1h": 0.23,
            "level_rate_of_change": 0.23,
            "rainfall_cumulative_3h": 56.2,
            "rainfall_cumulative_6h": 98.0,
            "rainfall_cumulative_24h": 182.4,
            "rainfall_intensity_max_1h": 32.1,
            "flow_mean_1h": 310.5,
            "flow_delta_1h": 25.3,
            "velocity_mean_30m": 1.72,
            "velocity_max_30m": 2.10,
        }
    ]}}


class SpatialFeatures(BaseModel):
    """Spatial / cross-station neighbourhood features."""

    station_id: str
    timestamp: datetime
    upstream_level_mean: Optional[float] = Field(None, description="Mean level of upstream stations (m)")
    upstream_level_max: Optional[float] = Field(None, description="Max level of upstream stations (m)")
    upstream_flow_mean: Optional[float] = Field(None, description="Mean discharge upstream (m³/s)")
    upstream_rainfall_mean: Optional[float] = Field(None, description="Mean rainfall upstream (mm/hr)")
    num_upstream_alerts: int = Field(0, description="Count of upstream stations in alert state")
    catchment_avg_rainfall_6h: Optional[float] = Field(None, description="Catchment-wide 6 h rainfall (mm)")
    distance_weighted_level: Optional[float] = Field(
        None,
        description="Inverse-distance-weighted level of neighbouring stations",
    )

    model_config = {"json_schema_extra": {"examples": [
        {
            "station_id": "CWC-KAR-001",
            "timestamp": "2025-08-15T07:00:00Z",
            "upstream_level_mean": 5.10,
            "upstream_level_max": 5.92,
            "upstream_flow_mean": 425.0,
            "upstream_rainfall_mean": 22.8,
            "num_upstream_alerts": 2,
            "catchment_avg_rainfall_6h": 88.0,
            "distance_weighted_level": 4.85,
        }
    ]}}


class FeatureVector(BaseModel):
    """Combined feature vector published to ``features.vector.{station_id}``.

    Consumed by the Prediction service (XGBoost + PINN).
    """

    station_id: str = Field(..., description="Target station identifier")
    timestamp: datetime
    temporal: TemporalFeatures
    spatial: SpatialFeatures
    cv_depth_m: Optional[float] = Field(None, description="Latest CV depth (m)")
    cv_velocity_ms: Optional[float] = Field(None, description="Latest CV velocity (m/s)")
    cv_confidence: Optional[float] = Field(None, ge=0, le=1)
    soil_moisture_pct: Optional[float] = Field(None, ge=0, le=100, description="Soil moisture %")
    antecedent_precip_index: Optional[float] = Field(None, description="API 5-day weighted rainfall")
    is_monsoon: bool = Field(default=False, description="True if within Jun-Sep monsoon window")
    hour_of_day: int = Field(..., ge=0, le=23)
    day_of_year: int = Field(..., ge=1, le=366)
    feature_version: str = Field(default="1.0.0", description="Schema version for tracking")

    model_config = {"json_schema_extra": {"examples": [
        {
            "station_id": "CWC-KAR-001",
            "timestamp": "2025-08-15T07:00:00Z",
            "temporal": {
                "station_id": "CWC-KAR-001",
                "timestamp": "2025-08-15T07:00:00Z",
                "level_mean_1h": 4.48,
                "level_max_1h": 4.62,
                "level_delta_1h": 0.23,
                "level_rate_of_change": 0.23,
                "rainfall_cumulative_3h": 56.2,
                "rainfall_cumulative_6h": 98.0,
                "rainfall_cumulative_24h": 182.4,
                "rainfall_intensity_max_1h": 32.1,
            },
            "spatial": {
                "station_id": "CWC-KAR-001",
                "timestamp": "2025-08-15T07:00:00Z",
                "upstream_level_mean": 5.10,
                "upstream_level_max": 5.92,
                "upstream_flow_mean": 425.0,
                "upstream_rainfall_mean": 22.8,
                "num_upstream_alerts": 2,
                "catchment_avg_rainfall_6h": 88.0,
                "distance_weighted_level": 4.85,
            },
            "cv_depth_m": 3.12,
            "cv_velocity_ms": 1.87,
            "cv_confidence": 0.82,
            "soil_moisture_pct": 72.0,
            "antecedent_precip_index": 45.2,
            "is_monsoon": True,
            "hour_of_day": 7,
            "day_of_year": 227,
            "feature_version": "1.0.0",
        }
    ]}}
