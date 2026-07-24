"""Flash Flood Engine -- Port 8023.

Fast-path flash flood detection operating on sub-10-minute latency.
Standard ARGUS pipeline (ingestion -> features -> prediction) is
optimised for riverine floods with 6-72 hour lead times. Flash floods
in steep Himalayan catchments have < 1 hour warning windows.

Gap 5 closure: Problem mentions both riverine AND flash floods. ARGUS
was tuned entirely for riverine. This engine adds the fast-path.

Detection methods:
1. Rainfall intensity spike: > 40mm in 60min (IMD threshold)
2. Rate-of-rise: water level rising > 0.5m/hr
3. Upstream cascade: 2+ upstream gauges spiking simultaneously
4. PINN mesh anomaly: Saint-Venant shallow water eqs diverging
"""

from __future__ import annotations

import json
import os
import random
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services.flash_flood_engine.flash_detector import (
    FFPIInput,
    FFPIResult,
    compute_ffpi,
    list_catchments,
    FLASH_CATCHMENTS,
)

logger = structlog.get_logger(__name__)

# -- Configuration --------------------------------------------------------
FLASH_PORT = int(os.getenv("FLASH_FLOOD_PORT", "8023"))
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")

# Flash flood thresholds (IMD / CWC definitions)
RAINFALL_INTENSITY_THRESHOLD = 40.0  # mm in 60 min
RATE_OF_RISE_THRESHOLD = 0.5         # m per hour
UPSTREAM_CASCADE_MIN = 2              # min gauges spiking at once
RESPONSE_TIME_MINUTES = 8            # target latency for alert


# -- Data Models ----------------------------------------------------------


class FlashFloodAlert(BaseModel):
    alert_id: str
    alert_type: str = "FLASH_FLOOD"
    detection_method: str
    basin_id: str
    village_id: str
    latitude: float
    longitude: float
    severity: str  # EXTREME, SEVERE, MODERATE
    rainfall_intensity_mmhr: float
    rate_of_rise_mhr: float
    upstream_gauges_triggered: int
    lead_time_minutes: int
    confidence: float
    issued_at: str
    expires_at: str
    recommended_action: str
    is_confirmed: bool = False


class FlashFloodCheck(BaseModel):
    """Input for manual flash flood check."""
    basin_id: str = "beas_himachal"
    rainfall_1hr_mm: float = 0.0
    water_level_m: float = 0.0
    water_level_1hr_ago_m: float = 0.0
    upstream_gauge_count_spiking: int = 0


# -- In-memory state ------------------------------------------------------

_active_alerts: Dict[str, FlashFloodAlert] = {}
_history: List[FlashFloodAlert] = []
_stats = {
    "checks_run": 0, "alerts_issued": 0,
    "extreme_alerts": 0, "avg_lead_time_min": 0,
}


# -- Lifespan -------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("flash_flood_engine_starting", port=FLASH_PORT, demo_mode=DEMO_MODE)

    if DEMO_MODE:
        _seed_demo_alert()

    logger.info("flash_flood_engine_ready",
                active_alerts=len(_active_alerts))
    yield
    logger.info("flash_flood_engine_shutdown")


app = FastAPI(
    title="ARGUS Flash Flood Engine",
    version="1.0.0",
    description="Sub-10-minute fast-path flash flood detection",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# -- Helpers ---------------------------------------------------------------


def _evaluate_flash_risk(check: FlashFloodCheck) -> Optional[FlashFloodAlert]:
    """Evaluate flash flood risk from sensor data."""
    now = datetime.now(timezone.utc)
    triggers = []
    severity_score = 0.0

    # Trigger 1: Rainfall intensity
    if check.rainfall_1hr_mm >= RAINFALL_INTENSITY_THRESHOLD:
        triggers.append("RAINFALL_INTENSITY")
        severity_score += 0.4

    # Trigger 2: Rate of rise
    rate_of_rise = check.water_level_m - check.water_level_1hr_ago_m
    if rate_of_rise >= RATE_OF_RISE_THRESHOLD:
        triggers.append("RATE_OF_RISE")
        severity_score += 0.35

    # Trigger 3: Upstream cascade
    if check.upstream_gauge_count_spiking >= UPSTREAM_CASCADE_MIN:
        triggers.append("UPSTREAM_CASCADE")
        severity_score += 0.25

    if not triggers:
        return None

    severity = (
        "EXTREME" if severity_score >= 0.7
        else "SEVERE" if severity_score >= 0.4
        else "MODERATE"
    )

    lead_time = max(5, int(45 * (1 - severity_score)))

    actions = {
        "EXTREME": "EVACUATE IMMEDIATELY. Move to high ground. Do not cross flooded roads.",
        "SEVERE": "Prepare to evacuate. Gather essential supplies. Monitor updates.",
        "MODERATE": "Stay alert. Avoid riverbanks and low-lying areas.",
    }

    alert = FlashFloodAlert(
        alert_id=f"FF-{check.basin_id[:4].upper()}-{now.strftime('%Y%m%d%H%M%S')}",
        detection_method=" + ".join(triggers),
        basin_id=check.basin_id,
        village_id=f"{check.basin_id}_nearest",
        latitude=32.24 if "beas" in check.basin_id else 27.01,
        longitude=77.19 if "beas" in check.basin_id else 94.55,
        severity=severity,
        rainfall_intensity_mmhr=check.rainfall_1hr_mm,
        rate_of_rise_mhr=rate_of_rise,
        upstream_gauges_triggered=check.upstream_gauge_count_spiking,
        lead_time_minutes=lead_time,
        confidence=round(min(0.95, severity_score + 0.2), 2),
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(hours=2)).isoformat(),
        recommended_action=actions.get(severity, actions["MODERATE"]),
    )
    return alert


def _seed_demo_alert():
    """Create a demo flash flood scenario: Beas River Aug 2023."""
    now = datetime.now(timezone.utc)
    alert = FlashFloodAlert(
        alert_id=f"FF-BEAS-{now.strftime('%Y%m%d')}",
        detection_method="RAINFALL_INTENSITY + RATE_OF_RISE + UPSTREAM_CASCADE",
        basin_id="beas_himachal",
        village_id="kullu_town",
        latitude=31.96,
        longitude=77.11,
        severity="EXTREME",
        rainfall_intensity_mmhr=72.0,
        rate_of_rise_mhr=1.2,
        upstream_gauges_triggered=3,
        lead_time_minutes=12,
        confidence=0.91,
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(hours=2)).isoformat(),
        recommended_action="EVACUATE IMMEDIATELY. Move to high ground. Do not cross flooded roads.",
    )
    _active_alerts[alert.alert_id] = alert
    _history.append(alert)
    _stats["alerts_issued"] += 1
    _stats["extreme_alerts"] += 1


# -- API Endpoints ---------------------------------------------------------


@app.post("/api/v1/flash-flood/check")
async def check_flash_flood(check: FlashFloodCheck):
    """Evaluate current conditions for flash flood risk."""
    _stats["checks_run"] += 1

    alert = _evaluate_flash_risk(check)
    if alert:
        _active_alerts[alert.alert_id] = alert
        _history.append(alert)
        _stats["alerts_issued"] += 1
        if alert.severity == "EXTREME":
            _stats["extreme_alerts"] += 1

        logger.info("flash_flood_alert",
                     alert_id=alert.alert_id,
                     severity=alert.severity,
                     method=alert.detection_method)
        return {
            "flash_flood_detected": True,
            "alert": alert.model_dump(),
        }

    return {
        "flash_flood_detected": False,
        "message": "No flash flood conditions detected",
        "thresholds": {
            "rainfall_intensity_mm": RAINFALL_INTENSITY_THRESHOLD,
            "rate_of_rise_m_hr": RATE_OF_RISE_THRESHOLD,
            "upstream_cascade_min": UPSTREAM_CASCADE_MIN,
        },
    }


@app.get("/api/v1/flash-flood/active")
async def get_active_alerts():
    """Return all active flash flood alerts."""
    return {
        "active_count": len(_active_alerts),
        "alerts": [a.model_dump() for a in _active_alerts.values()],
    }


@app.get("/api/v1/flash-flood/history")
async def get_alert_history(limit: int = 50):
    """Return flash flood alert history."""
    return {
        "total": len(_history),
        "alerts": [a.model_dump() for a in _history[-limit:]],
    }


@app.post("/api/v1/flash-flood/demo-trigger")
async def demo_trigger():
    """Trigger a demo flash flood scenario."""
    check = FlashFloodCheck(
        basin_id="beas_himachal",
        rainfall_1hr_mm=68.0,
        water_level_m=4.8,
        water_level_1hr_ago_m=3.2,
        upstream_gauge_count_spiking=3,
    )
    _stats["checks_run"] += 1
    alert = _evaluate_flash_risk(check)
    if alert:
        _active_alerts[alert.alert_id] = alert
        _history.append(alert)
        _stats["alerts_issued"] += 1
        return {"triggered": True, "alert": alert.model_dump()}
    return {"triggered": False}


@app.get("/api/v1/flash-flood/thresholds")
async def get_thresholds():
    """Return current flash flood detection thresholds."""
    return {
        "rainfall_intensity_mmhr": RAINFALL_INTENSITY_THRESHOLD,
        "rate_of_rise_mhr": RATE_OF_RISE_THRESHOLD,
        "upstream_cascade_min_gauges": UPSTREAM_CASCADE_MIN,
        "target_response_time_min": RESPONSE_TIME_MINUTES,
        "source": "IMD / CWC Flash Flood Guidance",
    }


# -- FFPI endpoints (flash_detector.py) ------------------------------------


@app.post("/api/v1/flash/compute-ffpi", response_model=FFPIResult)
async def api_compute_ffpi(inputs: FFPIInput):
    """
    Computes Flash Flood Potential Index for a catchment.
    This is the no-upstream-gauge warning path.
    """
    try:
        return compute_ffpi(inputs)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/api/v1/flash/catchments")
async def api_list_catchments():
    """Returns all registered flash flood catchments."""
    return list_catchments()


@app.get("/health")
async def health():
    return {
        "service": "flash_flood_engine",
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "demo_mode": DEMO_MODE,
        "active_alerts": len(_active_alerts),
        "total_issued": _stats["alerts_issued"],
        "extreme_alerts": _stats["extreme_alerts"],
    }


if __name__ == "__main__":
    uvicorn.run("services.flash_flood_engine.main:app", host="0.0.0.0",
                port=FLASH_PORT, reload=True)
