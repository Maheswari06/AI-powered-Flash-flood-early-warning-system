"""Cell Broadcast CAP Integration -- Port 8025.

Common Alerting Protocol (CAP) compliant Cell Broadcast alert generation.
Generates ITU-T X.1303bis / OASIS CAP v1.2 XML payloads for integration
with India's planned Cell Broadcast Emergency Alert System (CBEAS).

Gap 7 closure: ARGUS alert_dispatcher sends Twilio SMS/WhatsApp.
Cell Broadcast reaches ALL phones in a geographic area without requiring
phone numbers -- critical for rural areas with unregistered SIMs.
"""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from xml.etree.ElementTree import Element, SubElement, tostring

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

# -- Configuration --------------------------------------------------------
CB_PORT = int(os.getenv("CELL_BROADCAST_PORT", "8025"))
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")

# CAP standard namespace
CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"


# -- Data Models ----------------------------------------------------------


class CellBroadcastRequest(BaseModel):
    basin_id: str = "brahmaputra_upper"
    district: str = "Majuli"
    alert_level: str = "RED"  # GREEN, YELLOW, ORANGE, RED
    headline: str = "Flood Warning"
    description: str = ""
    instruction: str = ""
    latitude: float = 27.0
    longitude: float = 94.5
    radius_km: float = 25.0
    language: str = "en"


class CAPAlert(BaseModel):
    alert_id: str
    cap_xml: str
    status: str = "Actual"
    msg_type: str = "Alert"
    scope: str = "Public"
    severity: str
    urgency: str
    certainty: str
    area_description: str
    generated_at: str
    expires_at: str


# -- In-memory state ------------------------------------------------------

_generated_alerts: Dict[str, CAPAlert] = {}
_stats = {"alerts_generated": 0, "red_alerts": 0}


# -- Lifespan -------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("cell_broadcast_starting", port=CB_PORT, demo_mode=DEMO_MODE)

    if DEMO_MODE:
        _generate_demo_alert()

    logger.info("cell_broadcast_ready", alerts=len(_generated_alerts))
    yield
    logger.info("cell_broadcast_shutdown")


app = FastAPI(
    title="ARGUS Cell Broadcast (CAP)",
    version="1.0.0",
    description="CAP v1.2 compliant Cell Broadcast alert generation",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# -- CAP XML Generation ---------------------------------------------------


def _ndma_to_cap_severity(level: str) -> dict:
    """Map NDMA alert levels to CAP severity/urgency/certainty."""
    return {
        "RED":    {"severity": "Extreme",  "urgency": "Immediate", "certainty": "Observed"},
        "ORANGE": {"severity": "Severe",   "urgency": "Expected",  "certainty": "Likely"},
        "YELLOW": {"severity": "Moderate", "urgency": "Future",    "certainty": "Possible"},
        "GREEN":  {"severity": "Minor",    "urgency": "Past",      "certainty": "Unlikely"},
    }.get(level.upper(), {"severity": "Unknown", "urgency": "Unknown", "certainty": "Unknown"})


def _build_cap_xml(req: CellBroadcastRequest, alert_id: str) -> str:
    """Generate CAP v1.2 XML per OASIS standard."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=6)
    cap_map = _ndma_to_cap_severity(req.alert_level)

    alert = Element("alert", xmlns=CAP_NS)
    SubElement(alert, "identifier").text = alert_id
    SubElement(alert, "sender").text = "argus-hydra@india.gov.in"
    SubElement(alert, "sent").text = now.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    SubElement(alert, "status").text = "Actual"
    SubElement(alert, "msgType").text = "Alert"
    SubElement(alert, "source").text = "ARGUS Flood Early Warning System"
    SubElement(alert, "scope").text = "Public"

    info = SubElement(alert, "info")
    SubElement(info, "language").text = req.language
    SubElement(info, "category").text = "Met"
    SubElement(info, "event").text = "Flood"
    SubElement(info, "responseType").text = "Evacuate" if req.alert_level == "RED" else "Prepare"
    SubElement(info, "urgency").text = cap_map["urgency"]
    SubElement(info, "severity").text = cap_map["severity"]
    SubElement(info, "certainty").text = cap_map["certainty"]
    SubElement(info, "headline").text = req.headline
    SubElement(info, "description").text = req.description or (
        f"Flood warning for {req.district} district, {req.basin_id} basin. "
        f"NDMA alert level: {req.alert_level}."
    )
    SubElement(info, "instruction").text = req.instruction or (
        "Move to higher ground immediately. Follow NDRF and local authority instructions. "
        "Call NDMA helpline 1078 for assistance."
    )
    SubElement(info, "senderName").text = "ARGUS / National Disaster Management Authority"
    SubElement(info, "web").text = "http://argus.india.gov.in"
    SubElement(info, "contact").text = "NDMA Helpline: 1078"
    SubElement(info, "expires").text = expires.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    area = SubElement(info, "area")
    SubElement(area, "areaDesc").text = f"{req.district} District, {req.basin_id} basin"
    SubElement(area, "circle").text = f"{req.latitude},{req.longitude} {req.radius_km}"

    # Indian event codes
    ec = SubElement(info, "eventCode")
    SubElement(ec, "valueName").text = "NDMA_LEVEL"
    SubElement(ec, "value").text = req.alert_level

    return tostring(alert, encoding="unicode", xml_declaration=False)


def _generate_demo_alert():
    """Generate a demo CAP alert for Majuli."""
    req = CellBroadcastRequest(
        basin_id="brahmaputra_upper",
        district="Majuli",
        alert_level="RED",
        headline="SEVERE FLOOD WARNING - Majuli District",
        description=(
            "Brahmaputra river level at Dibrugarh has crossed danger mark. "
            "Majuli island at high risk of inundation. NDRF teams deployed."
        ),
        instruction=(
            "EVACUATE low-lying areas immediately. Move to designated shelters. "
            "Do not cross flooded roads. Call 1078 for rescue."
        ),
        latitude=27.01,
        longitude=94.55,
        radius_km=30.0,
    )
    alert_id = f"CAP-DEMO-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    xml = _build_cap_xml(req, alert_id)
    cap_map = _ndma_to_cap_severity(req.alert_level)

    _generated_alerts[alert_id] = CAPAlert(
        alert_id=alert_id,
        cap_xml=xml,
        severity=cap_map["severity"],
        urgency=cap_map["urgency"],
        certainty=cap_map["certainty"],
        area_description=f"{req.district} District, {req.basin_id}",
        generated_at=datetime.now(timezone.utc).isoformat(),
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
    )
    _stats["alerts_generated"] += 1
    _stats["red_alerts"] += 1


# -- API Endpoints ---------------------------------------------------------


@app.post("/api/v1/cell-broadcast/generate")
async def generate_cap_alert(req: CellBroadcastRequest):
    """Generate a CAP v1.2 XML alert for Cell Broadcast."""
    alert_id = f"CAP-{req.basin_id[:4].upper()}-{uuid.uuid4().hex[:8]}"
    xml = _build_cap_xml(req, alert_id)
    cap_map = _ndma_to_cap_severity(req.alert_level)

    cap_alert = CAPAlert(
        alert_id=alert_id,
        cap_xml=xml,
        severity=cap_map["severity"],
        urgency=cap_map["urgency"],
        certainty=cap_map["certainty"],
        area_description=f"{req.district} District, {req.basin_id}",
        generated_at=datetime.now(timezone.utc).isoformat(),
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
    )
    _generated_alerts[alert_id] = cap_alert
    _stats["alerts_generated"] += 1
    if req.alert_level == "RED":
        _stats["red_alerts"] += 1

    logger.info("cap_alert_generated", alert_id=alert_id, severity=cap_map["severity"])
    return cap_alert.model_dump()


@app.get("/api/v1/cell-broadcast/alerts")
async def get_all_alerts():
    """Return all generated CAP alerts."""
    return {
        "total": len(_generated_alerts),
        "alerts": [a.model_dump() for a in _generated_alerts.values()],
    }


@app.get("/api/v1/cell-broadcast/{alert_id}/xml")
async def get_cap_xml(alert_id: str):
    """Return raw CAP XML for a specific alert."""
    if alert_id not in _generated_alerts:
        raise HTTPException(404, f"Alert not found: {alert_id}")
    xml = _generated_alerts[alert_id].cap_xml
    return Response(
        content=f'<?xml version="1.0" encoding="UTF-8"?>\n{xml}',
        media_type="application/xml",
    )


@app.get("/health")
async def health():
    return {
        "service": "cell_broadcast",
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "demo_mode": DEMO_MODE,
        "cap_version": "1.2 (OASIS)",
        "alerts_generated": _stats["alerts_generated"],
    }


if __name__ == "__main__":
    uvicorn.run("integrations.cell_broadcast.main:app", host="0.0.0.0",
                port=CB_PORT, reload=True)
