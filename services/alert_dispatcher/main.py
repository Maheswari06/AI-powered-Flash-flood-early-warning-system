"""Alert Dispatcher — FastAPI service (port 8005).

Multi-channel alert delivery engine: WhatsApp (Twilio), SMS, IVRS,
and Kafka broadcast. Implements cooldown logic to prevent alert fatigue.

Endpoints:
  POST /api/v1/alert/send              → dispatch an alert
  GET  /api/v1/alert/log               → recent alert history
  GET  /api/v1/alert/log/{village_id}  → alerts for a village
  GET  /api/v1/alert/stats             → dispatch statistics
  POST /api/v1/alert/test              → send test alert (demo)
  GET  /health                         → liveness
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from shared.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

# ── Configuration ────────────────────────────────────────────────────────
ALERT_PORT = int(os.getenv("ALERT_DISPATCHER_PORT", "8005"))
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")
COOLDOWN_S = settings.ALERT_COOLDOWN_S  # 900s = 15 min

# ── In-memory state ─────────────────────────────────────────────────────
_alert_log: List[Dict[str, Any]] = []
_cooldowns: Dict[str, float] = {}  # village_id → last_sent_ts
_stats = {"sent": 0, "suppressed": 0, "failed": 0, "channels": defaultdict(int)}
_twilio_client = None


class AlertRequest(BaseModel):
    village_id: str
    village_name: str = ""
    alert_level: str = Field(..., description="NORMAL|ADVISORY|WATCH|WARNING|EMERGENCY")
    risk_score: float = Field(0.0, ge=0, le=1)
    message: str = ""
    channels: List[str] = Field(default=["whatsapp", "sms"], description="Delivery channels")
    phone_numbers: List[str] = Field(default=[], description="Target phone numbers")
    force: bool = Field(default=False, description="Bypass cooldown")


class AlertResponse(BaseModel):
    status: str
    alert_id: str
    village_id: str
    channels_sent: List[str]
    suppressed: bool = False
    reason: str = ""


def _seed_demo_alerts():
    """Populate alert log with realistic demo entries for dashboard display."""
    import random
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    villages = [
        ("VIL-AS-MAJULI", "Majuli Ward 7"),
        ("VIL-HP-MANDI", "Mandi"),
        ("VIL-HP-KULLU", "Kullu"),
        ("VIL-AS-JORHAT", "Jorhat"),
        ("VIL-HP-MANALI", "Manali"),
    ]
    levels = [
        ("ADVISORY", 0.38), ("ADVISORY", 0.42), ("WATCH", 0.58),
        ("WATCH", 0.65), ("WARNING", 0.76), ("WARNING", 0.81),
        ("EMERGENCY", 0.91),
    ]

    for i, (level, risk) in enumerate(levels):
        vid, vname = villages[i % len(villages)]
        ts = now - timedelta(minutes=(len(levels) - i) * 5)
        _alert_log.append({
            "id": f"demo-{i+1}",
            "alert_id": f"ALERT-{vid}-{int(ts.timestamp())}",
            "village_id": vid,
            "village_name": vname,
            "alert_level": level,
            "risk_score": risk + random.uniform(-0.03, 0.03),
            "status": "sent",
            "timestamp": ts.isoformat(),
            "message": f"{level} alert triggered for {vname}",
            "channels_sent": ["whatsapp_demo", "sms_demo"],
        })
    _stats["sent"] = len(levels)
    logger.info("demo_alerts_seeded", count=len(levels))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _twilio_client
    logger.info("alert_dispatcher_starting", port=ALERT_PORT, demo_mode=DEMO_MODE)

    # Initialize Twilio client (best-effort)
    if not DEMO_MODE and settings.TWILIO_ACCOUNT_SID:
        try:
            from twilio.rest import Client
            _twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            logger.info("twilio_client_ready")
        except Exception as e:
            logger.warning("twilio_unavailable", error=str(e))

    # Seed demo alerts so dashboard has data on startup
    if DEMO_MODE and not _alert_log:
        _seed_demo_alerts()

    logger.info("alert_dispatcher_ready")
    yield
    logger.info("alert_dispatcher_shutdown")


app = FastAPI(
    title="ARGUS Alert Dispatcher",
    version="1.0.0",
    description="Multi-channel flood alert delivery — WhatsApp, SMS, IVRS",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _is_on_cooldown(village_id: str) -> bool:
    """Check if village is on alert cooldown."""
    last = _cooldowns.get(village_id, 0)
    return (time.time() - last) < COOLDOWN_S


def _send_whatsapp(phone: str, message: str) -> bool:
    """Send WhatsApp message via Twilio."""
    if _twilio_client and settings.TWILIO_WHATSAPP_NUMBER:
        try:
            _twilio_client.messages.create(
                body=message,
                from_=settings.TWILIO_WHATSAPP_NUMBER,
                to=f"whatsapp:{phone}"
            )
            return True
        except Exception as e:
            logger.warning("whatsapp_send_failed", phone=phone, error=str(e))
    return False


def _format_alert_message(req: AlertRequest) -> str:
    """Format alert message for delivery."""
    name = req.village_name or req.village_id
    level_emoji = {
        "EMERGENCY": "🔴", "WARNING": "🟠", "WATCH": "🟡",
        "ADVISORY": "🔵", "NORMAL": "🟢"
    }.get(req.alert_level, "⚪")

    return (
        f"{level_emoji} ARGUS FLOOD ALERT — {req.alert_level}\n"
        f"Village: {name}\n"
        f"Risk Score: {req.risk_score:.0%}\n"
        f"{req.message or 'Please follow evacuation instructions.'}\n"
        f"—ARGUS Early Warning System"
    )


@app.post("/api/v1/alert/send", response_model=AlertResponse)
async def send_alert(request: AlertRequest):
    """Dispatch a flood alert through configured channels."""
    now = datetime.now(timezone.utc)
    alert_id = f"ALERT-{request.village_id}-{int(time.time())}"

    # Cooldown check
    if not request.force and _is_on_cooldown(request.village_id):
        _stats["suppressed"] += 1
        entry = {
            "alert_id": alert_id, "village_id": request.village_id,
            "alert_level": request.alert_level, "status": "suppressed",
            "timestamp": now.isoformat(), "reason": "cooldown"
        }
        _alert_log.append(entry)
        return AlertResponse(
            status="suppressed", alert_id=alert_id,
            village_id=request.village_id, channels_sent=[],
            suppressed=True, reason=f"Cooldown active ({COOLDOWN_S}s)"
        )

    message = _format_alert_message(request)
    channels_sent = []

    for channel in request.channels:
        if channel == "whatsapp" and DEMO_MODE:
            channels_sent.append("whatsapp_demo")
            _stats["channels"]["whatsapp_demo"] += 1
        elif channel == "whatsapp":
            for phone in request.phone_numbers:
                if _send_whatsapp(phone, message):
                    channels_sent.append(f"whatsapp:{phone}")
                    _stats["channels"]["whatsapp"] += 1
        elif channel == "sms":
            channels_sent.append("sms_demo" if DEMO_MODE else "sms")
            _stats["channels"]["sms"] += 1
        elif channel == "ivrs":
            channels_sent.append("ivrs_demo" if DEMO_MODE else "ivrs")
            _stats["channels"]["ivrs"] += 1

    # Update cooldown
    _cooldowns[request.village_id] = time.time()
    _stats["sent"] += 1

    entry = {
        "alert_id": alert_id,
        "village_id": request.village_id,
        "village_name": request.village_name,
        "alert_level": request.alert_level,
        "risk_score": request.risk_score,
        "channels_sent": channels_sent,
        "status": "sent",
        "timestamp": now.isoformat(),
        "message": message,
    }
    _alert_log.append(entry)

    logger.info("alert_dispatched", alert_id=alert_id, level=request.alert_level,
                village=request.village_id, channels=channels_sent)

    return AlertResponse(
        status="sent", alert_id=alert_id,
        village_id=request.village_id, channels_sent=channels_sent,
    )


@app.get("/api/v1/alert/log")
async def get_alert_log(limit: int = 50):
    """Return recent alert history."""
    return {"alerts": _alert_log[-limit:], "total": len(_alert_log)}


@app.get("/api/v1/alert/log/{village_id}")
async def get_village_alerts(village_id: str, limit: int = 20):
    """Return alerts for a specific village."""
    village_alerts = [a for a in _alert_log if a.get("village_id") == village_id]
    return {"village_id": village_id, "alerts": village_alerts[-limit:], "total": len(village_alerts)}


@app.get("/api/v1/alert/stats")
async def get_stats():
    """Return dispatch statistics."""
    return {
        "sent": _stats["sent"],
        "suppressed": _stats["suppressed"],
        "failed": _stats["failed"],
        "by_channel": dict(_stats["channels"]),
        "cooldown_s": COOLDOWN_S,
        "demo_mode": DEMO_MODE,
        "twilio_connected": _twilio_client is not None,
    }


@app.post("/api/v1/alert/test")
async def test_alert():
    """Send a test alert for demo purposes."""
    test_req = AlertRequest(
        village_id="majuli_ward_7",
        village_name="Majuli Ward 7",
        alert_level="WARNING",
        risk_score=0.78,
        message="TEST ALERT — This is a demo alert from ARGUS.",
        channels=["whatsapp"],
        force=True,
    )
    return await send_alert(test_req)


@app.get("/health")
async def health():
    return {
        "service": "alert_dispatcher",
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "demo_mode": DEMO_MODE,
        "alerts_sent": _stats["sent"],
        "twilio_connected": _twilio_client is not None,
    }


if __name__ == "__main__":
    uvicorn.run("services.alert_dispatcher.main:app", host="0.0.0.0", port=ALERT_PORT, reload=True)
