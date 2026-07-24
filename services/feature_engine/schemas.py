"""Pydantic v2 schemas for the Feature Engineering Engine.

Defines the internal data contracts used across kalman_filter,
pinn_mesh, feature_builder, and timescale_writer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ── Quality flags ─────────────────────────────────────────────────────────


class QualityFlag(str, Enum):
    """Quality indicator attached to every sensor reading after QA."""

    GOOD = "GOOD"
    SUSPECT = "SUSPECT"
    MISSING = "MISSING"
    ESTIMATED = "ESTIMATED"
    KALMAN_IMPUTED = "KALMAN_IMPUTED"


# ── Sensor Reading (raw input) ───────────────────────────────────────────


class SensorReading(BaseModel):
    """Normalised sensor reading consumed from Kafka.

    Represents a single gauge or weather observation before
    quality assurance is applied.
    """

    station_id: str = Field(..., description="CWC gauge / grid-cell identifier")
    timestamp: datetime = Field(..., description="Observation UTC timestamp")
    water_level_m: Optional[float] = Field(None, description="Water level (m)")
    flow_cumecs: Optional[float] = Field(None, description="Discharge (m³/s)")
    rainfall_mm_hr: Optional[float] = Field(None, ge=0, description="Rainfall intensity (mm/hr)")
    temperature_c: Optional[float] = Field(None, description="Air temperature °C")
    humidity_pct: Optional[float] = Field(None, ge=0, le=100, description="Relative humidity %")
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    source: str = Field(default="cwc", description="Data source identifier")
    quality_flag: QualityFlag = Field(default=QualityFlag.GOOD)

    model_config = {"json_schema_extra": {"examples": [
        {
            "station_id": "CWC-HP-MANDI",
            "timestamp": "2025-08-15T06:30:00Z",
            "water_level_m": 4.52,
            "flow_cumecs": 312.7,
            "rainfall_mm_hr": None,
            "lat": 31.71,
            "lon": 76.93,
            "source": "cwc",
            "quality_flag": "GOOD",
        }
    ]}}


# ── Kalman Filter output ─────────────────────────────────────────────────


class KalmanOutput(BaseModel):
    """Output of the Extended Kalman Filter quality-assurance step.

    One output per sensor reading; replaces raw value with filtered
    value when an anomaly is detected.
    """

    station_id: str = Field(..., description="Gauge identifier")
    timestamp: datetime = Field(..., description="Observation timestamp")
    raw_value: float = Field(..., description="Original observed water level (m)")
    filtered_value: float = Field(..., description="Kalman-filtered water level (m)")
    rate_of_change: float = Field(..., description="Estimated dL/dt (m/hr)")
    quality_flag: QualityFlag = Field(
        default=QualityFlag.GOOD,
        description="GOOD if accepted, KALMAN_IMPUTED if anomaly replaced",
    )
    innovation: float = Field(..., description="Innovation z - H·x_pred (m)")
    innovation_sigma: float = Field(
        ..., description="Innovation std deviation (√(H·P·Hᵀ + R))"
    )
    innovation_score: float = Field(
        ...,
        description="|innovation| / innovation_sigma — flag if > 3",
    )

    model_config = {"json_schema_extra": {"examples": [
        {
            "station_id": "CWC-HP-MANDI",
            "timestamp": "2025-08-15T06:30:00Z",
            "raw_value": 4.52,
            "filtered_value": 4.50,
            "rate_of_change": 0.03,
            "quality_flag": "GOOD",
            "innovation": 0.02,
            "innovation_sigma": 0.72,
            "innovation_score": 0.028,
        }
    ]}}


# ── PINN Virtual Sensor output ───────────────────────────────────────────


class VirtualSensorOutput(BaseModel):
    """Predicted water level at a virtual (ungauged) location
    produced by the PINN Saint-Venant mesh.
    """

    virtual_id: str = Field(..., description="Virtual sensor identifier")
    timestamp: datetime = Field(..., description="Prediction timestamp")
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    predicted_level_m: float = Field(..., description="Interpolated water level (m)")
    uncertainty_m: float = Field(
        ..., ge=0, description="Prediction uncertainty ± (m)"
    )
    physics_residual: Optional[float] = Field(
        None,
        description="Continuity-equation residual at this location",
    )
    contributing_gauges: List[str] = Field(
        default_factory=list,
        description="Station IDs of real gauges that informed this prediction",
    )

    model_config = {"json_schema_extra": {"examples": [
        {
            "virtual_id": "VIRT-BEAS-001",
            "timestamp": "2025-08-15T06:30:00Z",
            "lat": 31.69,
            "lon": 77.00,
            "predicted_level_m": 4.38,
            "uncertainty_m": 0.25,
            "physics_residual": 0.003,
            "contributing_gauges": ["CWC-HP-MANDI", "CWC-HP-PANDOH"],
        }
    ]}}


# ── Feature Row (output to TimescaleDB) ──────────────────────────────────


class FeatureRow(BaseModel):
    """Enriched feature record written to the TimescaleDB ``feature_store`` table.

    Each row contains the full set of rolling-window features for one
    gauge (real or virtual) at one timestamp.
    """

    village_id: str = Field(..., description="Village / location identifier")
    station_id: Optional[str] = Field(None, description="Source gauge station ID")
    timestamp: datetime = Field(..., description="Feature computation timestamp")
    features: Dict[str, float] = Field(
        ...,
        description="Feature name → value mapping (rolling stats, basin graph, etc.)",
    )
    quality: QualityFlag = Field(
        default=QualityFlag.GOOD,
        description="Aggregate quality flag for this feature row",
    )

    model_config = {"json_schema_extra": {"examples": [
        {
            "village_id": "VIL-HP-MANDI",
            "station_id": "CWC-HP-MANDI",
            "timestamp": "2025-08-15T07:00:00Z",
            "features": {
                "mean_level_1h": 4.48,
                "max_level_1h": 4.62,
                "rate_of_change_1h": 0.23,
                "mean_level_3h": 4.35,
                "max_level_3h": 4.62,
                "rate_of_change_3h": 0.41,
                "cumulative_rainfall_6h": 98.0,
                "cumulative_rainfall_24h": 182.4,
                "soil_moisture_proxy": 0.72,
                "antecedent_moisture_index": 45.2,
                "upstream_risk_score": 0.65,
            },
            "quality": "GOOD",
        }
    ]}}
