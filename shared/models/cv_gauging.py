"""Pydantic v2 schemas for the CV Virtual Gauging service.

Output produced by the computer-vision pipeline that reads
CCTV streams and estimates water depth + velocity.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class VirtualGaugeReading(BaseModel):
    """CV-derived gauge measurement published to Kafka.

    Kafka topic: ``virtual.gauge.{camera_id}``
    """

    camera_id: str = Field(..., description="Source camera identifier")
    timestamp: datetime = Field(..., description="Frame capture UTC timestamp")
    depth_m: float = Field(..., ge=0, description="Estimated water depth in metres")
    velocity_ms: float = Field(..., ge=0, description="Estimated surface velocity in m/s")
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Combined YOLO + SAM confidence"
    )
    water_mask_geojson: Optional[Any] = Field(
        None, description="GeoJSON polygon of detected water surface"
    )
    alert_flag: bool = Field(
        default=False,
        description="True when depth exceeds warning threshold",
    )
    uncertainty_pct: float = Field(
        default=15.0,
        ge=0,
        description="±uncertainty band on depth estimate (%)",
    )

    model_config = {"json_schema_extra": {"examples": [
        {
            "camera_id": "CAM-BEAS-01",
            "timestamp": "2025-08-15T06:30:05Z",
            "depth_m": 3.12,
            "velocity_ms": 1.87,
            "confidence_score": 0.82,
            "water_mask_geojson": None,
            "alert_flag": True,
            "uncertainty_pct": 15.0,
        }
    ]}}
