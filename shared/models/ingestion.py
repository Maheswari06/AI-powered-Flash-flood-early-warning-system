"""Pydantic v2 schemas for the Data Ingestion Pipeline.

These schemas define the contract for all data flowing from
external sources (CWC, IMD, CCTV) into Kafka topics.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class QualityFlag(str, Enum):
    """Quality indicator attached to every gauge reading."""

    GOOD = "GOOD"
    SUSPECT = "SUSPECT"
    MISSING = "MISSING"
    ESTIMATED = "ESTIMATED"


class GaugeReading(BaseModel):
    """Real-time river gauge observation from CWC WISP.

    Kafka topic: ``gauge.realtime.{station_id}``
    """

    station_id: str = Field(..., description="CWC station identifier")
    timestamp: datetime = Field(..., description="Observation UTC timestamp")
    level_m: float = Field(..., description="Water level in metres")
    flow_cumecs: float = Field(..., description="Discharge in m³/s")
    quality_flag: QualityFlag = Field(
        default=QualityFlag.GOOD, description="Data quality indicator"
    )

    model_config = {"json_schema_extra": {"examples": [
        {
            "station_id": "CWC-KAR-001",
            "timestamp": "2025-08-15T06:30:00Z",
            "level_m": 4.52,
            "flow_cumecs": 312.7,
            "quality_flag": "GOOD",
        }
    ]}}


class WeatherData(BaseModel):
    """Gridded rainfall / weather observation from IMD.

    Kafka topic: ``weather.api.imd``
    """

    lat: float = Field(..., ge=-90, le=90, description="Latitude")
    lon: float = Field(..., ge=-180, le=180, description="Longitude")
    timestamp: datetime = Field(..., description="Observation UTC timestamp")
    rainfall_mm_hr: float = Field(..., ge=0, description="Rainfall intensity mm/hr")
    temp_c: Optional[float] = Field(None, description="Temperature °C")
    humidity_pct: Optional[float] = Field(None, ge=0, le=100, description="Relative humidity %")

    model_config = {"json_schema_extra": {"examples": [
        {
            "lat": 31.10,
            "lon": 77.17,
            "timestamp": "2025-08-15T06:00:00Z",
            "rainfall_mm_hr": 28.4,
            "temp_c": 22.1,
            "humidity_pct": 93.0,
        }
    ]}}


class CCTVFrame(BaseModel):
    """CCTV stream metadata for a single camera frame.

    Kafka topic: ``cctv.frames.{camera_id}``
    """

    camera_id: str = Field(..., description="Unique camera identifier")
    location_name: str = Field(..., description="Human-readable location name")
    rtsp_url: str = Field(..., description="RTSP stream URL")
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    timestamp: datetime = Field(..., description="Frame capture UTC timestamp")

    model_config = {"json_schema_extra": {"examples": [
        {
            "camera_id": "CAM-BEAS-01",
            "location_name": "Beas River – Manali Bridge",
            "rtsp_url": "rtsp://192.168.1.100:554/stream",
            "lat": 32.24,
            "lon": 77.19,
            "timestamp": "2025-08-15T06:30:05Z",
        }
    ]}}
