"""ScarNet — Satellite Terrain Change Detection Service (port 8012).

Detects terrain changes from Sentinel-2 imagery that affect flood risk:
deforestation, urbanization, slope failures, river channel shifts.

Automatically updates PINN physics model when significant change detected.
Generates a "terrain health score" for authorities.

Run: uvicorn services.scarnet.main:app --reload --port 8012
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.scarnet.satellite.sentinel_client import SentinelClient
from services.scarnet.detection.change_detector import TerrainChangeDetector
from services.scarnet.updater.pinn_updater import PINNTerrainUpdater
from services.scarnet.scheduler.scan_scheduler import ScanScheduler
from services.scarnet.api.routes import router as scarnet_router, init_routes

logger = structlog.get_logger(__name__)

# ── Configuration ────────────────────────────────────────────────────────
SCARNET_PORT = int(os.getenv("SCARNET_PORT", "8012"))
DEMO_MODE = os.getenv("SCARNET_DEMO_MODE", "true").lower() in ("true", "1", "yes")
UNET_CHECKPOINT = os.getenv("UNET_CHECKPOINT", "./models/unet_change_detect.pt")
NASA_EARTHDATA_TOKEN = os.getenv("NASA_EARTHDATA_TOKEN", "")
SENTINEL_AWS_BUCKET = os.getenv("SENTINEL_AWS_BUCKET", "sentinel-s2-l2a")

# ── Globals ──────────────────────────────────────────────────────────────
_scheduler: ScanScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler

    logger.info("scarnet_starting", port=SCARNET_PORT, demo_mode=DEMO_MODE)

    # Initialize components
    sentinel_client = SentinelClient(
        nasa_token=NASA_EARTHDATA_TOKEN,
        aws_bucket=SENTINEL_AWS_BUCKET,
        demo_mode=DEMO_MODE,
    )

    detector = TerrainChangeDetector(unet_checkpoint=UNET_CHECKPOINT)
    pinn_updater = PINNTerrainUpdater()

    _scheduler = ScanScheduler(
        sentinel_client=sentinel_client,
        detector=detector,
        pinn_updater=pinn_updater,
        demo_mode=DEMO_MODE,
    )

    # Inject scheduler into routes
    init_routes(_scheduler)

    # Run initial demo scan
    _scheduler.start()

    tiles_ok = sentinel_client.tiles_available()
    logger.info(
        "scarnet_ready",
        demo_mode=DEMO_MODE,
        tiles_available=tiles_ok,
        unet_available=detector.use_unet,
    )

    yield

    # Shutdown
    if _scheduler:
        await _scheduler.stop()
    logger.info("scarnet_stopped")


# ── FastAPI App ──────────────────────────────────────────────────────────

app = FastAPI(
    title="ARGUS ScarNet — Satellite Terrain Monitor",
    description=(
        "Detects terrain changes from satellite imagery that affect flood risk. "
        "Watches for deforestation, urbanization, slope failures, and river channel shifts. "
        "Automatically recalibrates the PINN physics model.\n\n"
        "**Why it matters:** Most flood models assume terrain is static. It's not. "
        "A hillside that was forested 3 years ago drains differently today. "
        "ScarNet keeps ARGUS calibrated as climate change reshapes terrain."
    ),
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scarnet_router)


# ── Health ───────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    has_result = _scheduler is not None and _scheduler.latest_result is not None
    return {
        "service": "scarnet",
        "status": "UP",
        "version": "3.0.0",
        "demo_mode": DEMO_MODE,
        "latest_scan_available": has_result,
        "terrain_health_score": (
            _scheduler.latest_result.terrain_health_score if has_result else None
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Root ─────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "service": "ARGUS ScarNet — Satellite Terrain Monitor",
        "version": "3.0.0",
        "description": "Terrain change detection → automatic PINN recalibration",
        "endpoints": [
            "GET  /api/v1/scarnet/latest",
            "GET  /api/v1/scarnet/history/{catchment_id}",
            "GET  /api/v1/scarnet/tiles/before",
            "GET  /api/v1/scarnet/tiles/after",
            "GET  /api/v1/scarnet/risk-delta/{catchment_id}",
            "POST /api/v1/scarnet/trigger-demo",
            "GET  /health",
        ],
    }


# ── Main ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "services.scarnet.main:app",
        host="0.0.0.0",
        port=SCARNET_PORT,
        reload=True,
        log_level="info",
    )
