"""
Notification Hub — ARGUS Push Notification Management Service.
Port: 8014

Manages Web Push subscriptions, dispatches alert notifications,
and provides SSE streaming for real-time dashboard updates.
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("notification_hub")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")

# ── Configuration ─────────────────────────────────────────────
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_CLAIMS_EMAIL = os.getenv("VAPID_CLAIMS_EMAIL", "mailto:admin@argus.hydra.gov.in")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/3")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
PORT = int(os.getenv("NOTIFICATION_HUB_PORT", "8014"))

# ── In-memory stores (production: use Redis) ──────────────────
subscriptions: dict[str, list[dict]] = {}  # village_id -> [subscription_info, ...]
alert_history: list[dict] = []
sse_clients: list[asyncio.Queue] = []


# ── Models ─────────────────────────────────────────────────────
class PushSubscription(BaseModel):
    """Web Push API subscription object."""
    endpoint: str
    keys: dict  # p256dh + auth


class SubscribeRequest(BaseModel):
    subscription: PushSubscription
    village_id: str


class AlertPayload(BaseModel):
    """Incoming alert from the prediction / alert-dispatcher service."""
    station_id: str
    village_id: Optional[str] = None
    alert_level: str = "WATCH"
    title: Optional[str] = None
    body: Optional[str] = None
    risk_score: Optional[float] = None
    predicted_level: Optional[float] = None
    timestamp: Optional[str] = None


class NotificationResult(BaseModel):
    sent: int = 0
    failed: int = 0
    queued: int = 0


# ── Helpers ────────────────────────────────────────────────────
def _build_push_payload(alert: AlertPayload) -> dict:
    """Build the notification JSON payload."""
    level = alert.alert_level
    title = alert.title or f"ARGUS: {level} Alert"
    body = alert.body or (
        f"Station {alert.station_id} — "
        f"Predicted level: {alert.predicted_level:.2f}m"
        if alert.predicted_level
        else f"Alert level changed to {level}"
    )
    return {
        "title": title,
        "body": body,
        "alert_level": level,
        "station_id": alert.station_id,
        "village_id": alert.village_id,
        "risk_score": alert.risk_score,
        "url": "/pwa/",
    }


async def _send_web_push(sub_info: dict, payload: dict) -> bool:
    """Send a Web Push notification. Uses pywebpush if available."""
    try:
        from pywebpush import webpush, WebPushException
        webpush(
            subscription_info=sub_info,
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_CLAIMS_EMAIL},
        )
        return True
    except ImportError:
        logger.warning("pywebpush not installed — push notification skipped")
        return False
    except Exception as e:
        logger.error(f"Web push failed: {e}")
        return False


async def _broadcast_sse(event_type: str, data: dict):
    """Send to all connected SSE clients."""
    message = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    dead = []
    for i, q in enumerate(sse_clients):
        try:
            q.put_nowait(message)
        except asyncio.QueueFull:
            dead.append(i)
    for i in reversed(dead):
        sse_clients.pop(i)


# ── Kafka consumer (background task) ──────────────────────────
async def _consume_alerts():
    """Consume alert events from Kafka and dispatch notifications."""
    try:
        from aiokafka import AIOKafkaConsumer
        consumer = AIOKafkaConsumer(
            "flood.alerts",
            bootstrap_servers=KAFKA_BOOTSTRAP,
            group_id="notification-hub",
            auto_offset_reset="latest",
            value_deserializer=lambda v: json.loads(v.decode()),
        )
        await consumer.start()
        logger.info("Kafka consumer started — listening on flood.alerts")
        try:
            async for msg in consumer:
                try:
                    alert = AlertPayload(**msg.value)
                    await dispatch_alert(alert)
                except Exception as e:
                    logger.error(f"Error processing alert: {e}")
        finally:
            await consumer.stop()
    except ImportError:
        logger.warning("aiokafka not installed — Kafka consumer disabled")
    except Exception as e:
        logger.error(f"Kafka consumer error: {e}")


async def dispatch_alert(alert: AlertPayload) -> NotificationResult:
    """Dispatch an alert: send push notifications + SSE broadcast."""
    result = NotificationResult()
    payload = _build_push_payload(alert)
    ts = alert.timestamp or datetime.now(timezone.utc).isoformat()

    # Record in history
    history_entry = {**payload, "timestamp": ts}
    alert_history.insert(0, history_entry)
    if len(alert_history) > 500:
        alert_history.pop()

    # Broadcast via SSE
    await _broadcast_sse("alert", history_entry)

    # Skip push for NORMAL
    if alert.alert_level == "NORMAL":
        return result

    # Send push to subscribed users
    village_id = alert.village_id or ""
    targets = subscriptions.get(village_id, []) + subscriptions.get("__all__", [])

    for sub_info in targets:
        ok = await _send_web_push(sub_info, payload)
        if ok:
            result.sent += 1
        else:
            result.failed += 1

    logger.info(
        f"Alert dispatched: {alert.alert_level} for {alert.station_id} "
        f"— sent={result.sent} failed={result.failed}"
    )
    return result


# ── App lifecycle ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_consume_alerts())
    logger.info(f"Notification Hub starting on port {PORT}")
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# ── FastAPI app ────────────────────────────────────────────────
app = FastAPI(
    title="ARGUS Notification Hub",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ─────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "service": "notification_hub",
        "status": "healthy",
        "subscriptions": sum(len(v) for v in subscriptions.values()),
        "sse_clients": len(sse_clients),
        "history_size": len(alert_history),
    }


@app.post("/notifications/subscribe")
async def subscribe(req: SubscribeRequest):
    """Register a push subscription for a village."""
    village_id = req.village_id or "__all__"
    sub_info = req.subscription.dict()

    if village_id not in subscriptions:
        subscriptions[village_id] = []

    # Avoid duplicates
    existing = [s["endpoint"] for s in subscriptions[village_id]]
    if sub_info["endpoint"] not in existing:
        subscriptions[village_id].append(sub_info)
        logger.info(f"New subscription for village {village_id}")

    return {"status": "subscribed", "village_id": village_id}


@app.delete("/notifications/unsubscribe")
async def unsubscribe(endpoint: str, village_id: str = "__all__"):
    """Remove a push subscription."""
    if village_id in subscriptions:
        subscriptions[village_id] = [
            s for s in subscriptions[village_id] if s["endpoint"] != endpoint
        ]
    return {"status": "unsubscribed"}


@app.post("/notifications/dispatch")
async def dispatch(alert: AlertPayload):
    """Manually dispatch an alert notification."""
    result = await dispatch_alert(alert)
    return result


@app.get("/alerts/history/{village_id}")
async def get_alert_history(village_id: str, limit: int = Query(20, le=100)):
    """Get recent alert history for a village."""
    filtered = [
        a for a in alert_history
        if a.get("village_id") == village_id or a.get("village_id") is None
    ][:limit]
    return {"alerts": filtered, "total": len(filtered)}


@app.get("/predictions/stream")
async def sse_stream(request: Request, basin: str = Query("brahmaputra")):
    """Server-Sent Events stream for real-time prediction updates."""

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        sse_clients.append(queue)
        try:
            # Send initial keepalive
            yield f"event: connected\ndata: {json.dumps({'basin': basin})}\n\n"

            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield message
                except asyncio.TimeoutError:
                    # Keepalive
                    yield ": keepalive\n\n"
        finally:
            if queue in sse_clients:
                sse_clients.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/notifications/vapid-key")
async def get_vapid_key():
    """Return the public VAPID key for client-side push subscription."""
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=503, detail="VAPID key not configured")
    return {"public_key": VAPID_PUBLIC_KEY}


# ── Entrypoint ─────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
