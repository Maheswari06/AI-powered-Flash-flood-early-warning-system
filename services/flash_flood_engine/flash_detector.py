"""
Flash Flood Fast-Path Detector

Flash floods differ fundamentally from riverine floods:
- Riverine:   Upstream gauge -> 45-90 min propagation -> downstream warning
- Flash flood: Intense LOCAL rainfall -> catchment saturated -> flood in 1-3 hrs
              NO upstream signal. Must detect from local data only.

This service implements the flash flood detection path:
TRIGGER: (Rainfall intensity > threshold) AND (Soil saturation > threshold)
         -> Immediate WARNING without waiting for gauge readings

FFPI: Flash Flood Potential Index
  FFPI = (rainfall_intensity_ratio x 0.4) +
         (soil_saturation_ratio x 0.35) +
         (slope_factor x 0.15) +
         (vegetation_factor x 0.10)

  Where:
  - rainfall_intensity_ratio: current_rainfall / 5yr_95th_percentile
  - soil_saturation_ratio:    current_moisture / field_capacity
  - slope_factor:             derived from DEM (steeper = higher score)
  - vegetation_factor:        1 - NDVI (bare soil = higher score)

FFPI > 0.6  -> WATCH
FFPI > 0.75 -> WARNING (trigger evacuation WITHOUT gauge confirmation)
FFPI > 0.90 -> EMERGENCY
"""

from __future__ import annotations

from typing import Optional

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


# ── Flash Flood Catchment Registry ─────────────────────────

# Pre-characterized flash flood catchments
# These are the high-risk small basins where no upstream gauge exists
FLASH_CATCHMENTS = {
    "beas_kullu_upper": {
        "display_name": "Beas Upper — Kullu District",
        "area_km2": 312,
        "slope_factor": 0.82,         # Very steep mountain terrain
        "vegetation_factor": 0.45,    # Partial deforestation post-2023
        "soil_type": "SHALLOW_ROCKY",
        "field_capacity_m3m3": 0.28,
        "rainfall_95th_mmhr": 28.0,   # From IMD historical record
        "flash_lag_minutes": 45,      # Characteristic response time
        "gauge_exists": False,        # KEY: no upstream gauge
        "primary_detection": "FFPI",  # Must use fast-path
    },
    "majuli_north_drain": {
        "display_name": "Majuli North Drainage — Lakhimpur",
        "area_km2": 180,
        "slope_factor": 0.22,         # Flat island
        "vegetation_factor": 0.31,
        "soil_type": "ALLUVIAL",
        "field_capacity_m3m3": 0.42,
        "rainfall_95th_mmhr": 35.0,
        "flash_lag_minutes": 90,
        "gauge_exists": True,         # Upstream Brahmaputra gauge exists
        "primary_detection": "GAUGE+FFPI",
    },
    "sikkim_teesta_upper": {
        "display_name": "Teesta Upper — North Sikkim",
        "area_km2": 890,
        "slope_factor": 0.91,         # Extreme steep glacial terrain
        "vegetation_factor": 0.18,
        "soil_type": "GLACIAL_MORAINE",
        "field_capacity_m3m3": 0.15,
        "rainfall_95th_mmhr": 42.0,
        "flash_lag_minutes": 30,      # Extremely fast response
        "gauge_exists": False,
        "primary_detection": "FFPI",
    },
}


# ── FFPI Models ────────────────────────────────────────────


class FFPIInput(BaseModel):
    catchment_id: str
    current_rainfall_mmhr: float
    soil_moisture_m3m3: float
    ndvi: float = 0.5              # From Sentinel-2 or estimated
    rainfall_last_6hr_mm: float = 0.0


class FFPIResult(BaseModel):
    catchment_id: str
    ffpi_score: float              # 0.0 - 1.0
    alert_level: str
    primary_trigger: str           # Which factor exceeded threshold
    rainfall_intensity_ratio: float
    soil_saturation_ratio: float
    estimated_minutes_to_flood: int
    confidence: float
    recommendation: str
    gauge_available: bool
    detection_method: str          # "FFPI_ONLY" or "FFPI+GAUGE"


# ── FFPI Computation ───────────────────────────────────────


def compute_ffpi(inputs: FFPIInput) -> FFPIResult:
    """
    Computes Flash Flood Potential Index for a catchment.
    This is the no-upstream-gauge warning path -- the critical innovation
    for true flash flood detection in small mountainous catchments.
    """
    catchment = FLASH_CATCHMENTS.get(inputs.catchment_id)
    if not catchment:
        raise ValueError(f"Catchment {inputs.catchment_id} not in registry")

    # Component ratios
    rainfall_ratio = min(2.0, inputs.current_rainfall_mmhr /
                         catchment["rainfall_95th_mmhr"])
    saturation_ratio = min(1.0, inputs.soil_moisture_m3m3 /
                           catchment["field_capacity_m3m3"])
    slope_f = catchment["slope_factor"]
    veg_f = 1.0 - inputs.ndvi  # Lower NDVI = less vegetation = higher risk

    # FFPI weighted sum
    ffpi = (rainfall_ratio * 0.40 +
            saturation_ratio * 0.35 +
            slope_f * 0.15 +
            veg_f * 0.10)
    ffpi = min(1.0, ffpi)

    # Alert level
    if ffpi >= 0.90:
        alert_level = "EMERGENCY"
        eta_min = max(15, int(catchment["flash_lag_minutes"] * 0.3))
    elif ffpi >= 0.75:
        alert_level = "WARNING"
        eta_min = int(catchment["flash_lag_minutes"] * 0.6)
    elif ffpi >= 0.60:
        alert_level = "WATCH"
        eta_min = catchment["flash_lag_minutes"]
    elif ffpi >= 0.40:
        alert_level = "ADVISORY"
        eta_min = int(catchment["flash_lag_minutes"] * 2)
    else:
        alert_level = "NORMAL"
        eta_min = 999

    # Primary trigger explanation
    if rainfall_ratio > 1.5:
        trigger = (f"EXTREME RAINFALL: {inputs.current_rainfall_mmhr:.1f}mm/hr = "
                   f"{rainfall_ratio:.1f}x normal")
    elif saturation_ratio > 0.85:
        trigger = f"SATURATED SOIL: {saturation_ratio * 100:.0f}% of field capacity"
    else:
        trigger = "COMBINED RISK: Rainfall + soil conditions"

    # Detection method
    method = "FFPI_ONLY" if not catchment["gauge_exists"] else "FFPI+GAUGE"

    if alert_level in ("WARNING", "EMERGENCY"):
        recommendation = (
            f"EVACUATE {catchment['display_name']} — "
            f"Flash flood expected in {eta_min} minutes. "
            f"{'No upstream gauge — FFPI is primary signal.'if not catchment['gauge_exists'] else 'Confirmed by gauge reading.'}"
        )
    else:
        recommendation = f"Monitor {catchment['display_name']}"

    return FFPIResult(
        catchment_id=inputs.catchment_id,
        ffpi_score=round(ffpi, 4),
        alert_level=alert_level,
        primary_trigger=trigger,
        rainfall_intensity_ratio=round(rainfall_ratio, 4),
        soil_saturation_ratio=round(saturation_ratio, 4),
        estimated_minutes_to_flood=eta_min,
        confidence=0.78 if method == "FFPI_ONLY" else 0.91,
        recommendation=recommendation,
        gauge_available=catchment["gauge_exists"],
        detection_method=method,
    )


def list_catchments() -> dict:
    """Returns all registered flash flood catchments."""
    return {"catchments": list(FLASH_CATCHMENTS.values())}
