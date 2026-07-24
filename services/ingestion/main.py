"""Ingestion Pipeline — FastAPI service (port 8001).

Multi-source data ingestion: CWC river gauges, IMD weather,
and CCTV frame metadata → Kafka topics for downstream processing.

Endpoints:
  POST /api/v1/ingest/gauge         → ingest a CWC gauge reading
  POST /api/v1/ingest/weather       → ingest IMD weather data
  POST /api/v1/ingest/cctv-frame    → register CCTV frame metadata
  GET  /api/v1/ingest/sources       → list active data sources
  GET  /api/v1/ingest/stats         → ingestion statistics
  GET  /health                      → liveness
"""

from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from shared.config import get_settings
from shared.models.ingestion import GaugeReading, WeatherData, CCTVFrame

logger = structlog.get_logger(__name__)
settings = get_settings()

# ── Configuration ────────────────────────────────────────────────────────
INGESTION_PORT = int(os.getenv("INGESTION_PORT", "8001"))
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")

# ── In-memory state ─────────────────────────────────────────────────────
_stats: Dict[str, int] = {"gauge": 0, "weather": 0, "cctv": 0}
_sources: List[Dict[str, Any]] = []
_kafka_producer = None
_last_readings: Dict[str, Any] = {}


class IngestResponse(BaseModel):
    status: str = "accepted"
    topic: str = ""
    timestamp: str = ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _kafka_producer, _sources
    logger.info("ingestion_starting", port=INGESTION_PORT, demo_mode=DEMO_MODE)

    # Initialize Kafka producer (best-effort)
    if not DEMO_MODE:
        try:
            from shared.kafka_client import get_producer
            _kafka_producer = get_producer()
            logger.info("kafka_producer_ready")
        except Exception as e:
            logger.warning("kafka_unavailable", error=str(e))

    # Pre-load data sources from registry
    registry_path = settings.CCTV_REGISTRY_PATH
    try:
        with open(registry_path) as f:
            cctv_data = json.load(f)
            _sources.extend([
                {"type": "cctv", "id": cam["camera_id"], "name": cam.get("location_name", cam["camera_id"])}
                for cam in cctv_data.get("cameras", cctv_data if isinstance(cctv_data, list) else [])
            ])
    except Exception:
        _sources.append({"type": "cctv", "id": "CAM-BEAS-01", "name": "Beas River – Manali Bridge"})

    # Add standard sources
    _sources.extend([
        {"type": "gauge", "id": "CWC-WISP", "name": "CWC Water Info System"},
        {"type": "weather", "id": "IMD-API", "name": "IMD Gridded Rainfall"},
    ])

    logger.info("ingestion_ready", sources=len(_sources))
    yield
    logger.info("ingestion_shutdown")


app = FastAPI(
    title="ARGUS Ingestion Pipeline",
    version="1.0.0",
    description="Multi-source flood data ingestion — CWC gauges, IMD weather, CCTV streams",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _publish(topic: str, data: dict):
    """Publish to Kafka (or log in demo mode)."""
    if _kafka_producer:
        try:
            _kafka_producer.produce(topic, json.dumps(data).encode())
            _kafka_producer.flush(timeout=1)
        except Exception as e:
            logger.warning("kafka_publish_failed", topic=topic, error=str(e))
    else:
        logger.debug("demo_publish", topic=topic, keys=list(data.keys()))


@app.post("/api/v1/ingest/gauge", response_model=IngestResponse)
async def ingest_gauge(reading: GaugeReading):
    """Ingest a CWC river gauge reading."""
    data = reading.model_dump(mode="json")
    topic = f"gauge.realtime"
    _publish(topic, data)
    _stats["gauge"] += 1
    _last_readings[f"gauge:{reading.station_id}"] = data
    return IngestResponse(status="accepted", topic=topic, timestamp=reading.timestamp.isoformat())


@app.post("/api/v1/ingest/weather", response_model=IngestResponse)
async def ingest_weather(weather: WeatherData):
    """Ingest IMD weather observation."""
    data = weather.model_dump(mode="json")
    topic = "weather.api"
    _publish(topic, data)
    _stats["weather"] += 1
    return IngestResponse(status="accepted", topic=topic, timestamp=weather.timestamp.isoformat())


@app.post("/api/v1/ingest/cctv-frame", response_model=IngestResponse)
async def ingest_cctv_frame(frame: CCTVFrame):
    """Register CCTV frame metadata for CV processing."""
    data = frame.model_dump(mode="json")
    topic = f"cctv.frames"
    _publish(topic, data)
    _stats["cctv"] += 1
    return IngestResponse(status="accepted", topic=topic, timestamp=frame.timestamp.isoformat())


@app.get("/api/v1/ingest/sources")
async def list_sources():
    """List all registered data sources."""
    return {"sources": _sources, "total": len(_sources)}


@app.get("/api/v1/ingest/stats")
async def get_stats():
    """Return ingestion statistics."""
    return {
        "ingested": _stats,
        "total": sum(_stats.values()),
        "demo_mode": DEMO_MODE,
        "kafka_connected": _kafka_producer is not None,
    }


@app.get("/health")
async def health():
    return {
        "service": "ingestion",
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "demo_mode": DEMO_MODE,
        "kafka_connected": _kafka_producer is not None,
        "ingested_total": sum(_stats.values()),
    }


if __name__ == "__main__":
    uvicorn.run("services.ingestion.main:app", host="0.0.0.0", port=INGESTION_PORT, reload=True)
