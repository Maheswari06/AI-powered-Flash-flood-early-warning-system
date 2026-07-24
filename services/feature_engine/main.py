"""Feature Engine — FastAPI service.

Consumes raw gauge, weather, and CV readings from Kafka,
applies Kalman-filter quality assurance, runs the PINN virtual
sensor mesh, constructs rolling-window features, and writes
enriched feature rows to TimescaleDB.

Also publishes FeatureVectors to ``features.vector.{station_id}``
for the Prediction service.

Run: ``uvicorn services.feature_engine.main:app --reload --port 8003``
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional

import structlog
from fastapi import FastAPI, HTTPException, Query

from shared.config import get_settings
from shared.models.feature_engine import FeatureVector, SpatialFeatures, TemporalFeatures

from services.feature_engine.store import FeatureStore
from services.feature_engine.temporal import compute_temporal_features
from services.feature_engine.spatial import compute_spatial_features
from services.feature_engine.builder import build_feature_vector
from services.feature_engine.publisher import FeaturePublisher

# New modules
from services.feature_engine.kalman_filter import KalmanFilterBank
from services.feature_engine.pinn_mesh import PINNMesh
from services.feature_engine.feature_builder import FeatureBuilder
from services.feature_engine.db.timescale_writer import TimescaleWriter
from services.feature_engine.consumers.gauge_consumer import GaugeConsumer
from services.feature_engine.consumers.weather_consumer import WeatherConsumer
from services.feature_engine.schemas import FeatureRow, VirtualSensorOutput

logger = structlog.get_logger(__name__)
settings = get_settings()

# ── In-memory stores & shared components ─────────────────────────────────
feature_store = FeatureStore()
publisher = FeaturePublisher()
kalman_bank = KalmanFilterBank()
pinn_mesh = PINNMesh(checkpoint_path=os.getenv("PINN_CHECKPOINT_PATH", "./models/pinn_beas_river.pt"))
feature_builder = FeatureBuilder(topology=feature_store.topology)

# TimescaleDB writer
_TIMESCALE_DSN = os.getenv(
    "TIMESCALEDB_DSN",
    "postgresql://argus:argus@localhost:5432/argus",
)
timescale_writer = TimescaleWriter(dsn=_TIMESCALE_DSN)

# Consumers
gauge_consumer = GaugeConsumer(store=feature_store, kalman_bank=kalman_bank)
weather_consumer = WeatherConsumer(store=feature_store)

# Station → village mapping (demo defaults)
_STATION_VILLAGE_MAP: Dict[str, str] = {
    "CWC-HP-MANDI": "VIL-HP-MANDI",
    "CWC-HP-PANDOH": "VIL-HP-PANDOH",
    "CWC-HP-NADAUN": "VIL-HP-NADAUN",
    "CWC-PB-PONG": "VIL-PB-PONG",
}

# Gauge positions along the Beas river reach (km from headwaters)
_GAUGE_POSITIONS_KM: Dict[str, float] = {
    "CWC-HP-MANDI": 0.0,
    "CWC-HP-PANDOH": 15.0,
    "CWC-HP-NADAUN": 40.0,
    "CWC-PB-PONG": 70.0,
}

# Feature recomputation interval (seconds)
_RECOMPUTE_INTERVAL_S = int(os.getenv("FEATURE_RECOMPUTE_INTERVAL_S", "60"))


# ── Background recomputation loop ────────────────────────────────────────

async def _recompute_loop() -> None:
    """Periodically recompute features for all stations, run PINN mesh,
    and write enriched rows to TimescaleDB."""
    while True:
        await asyncio.sleep(_RECOMPUTE_INTERVAL_S)
        now = datetime.now(timezone.utc)
        station_ids = feature_store.get_all_station_ids()
        logger.info("recompute_features", num_stations=len(station_ids))

        # ── 1. Gather current levels for PINN mesh ──────────
        gauge_readings_map: Dict[str, float] = {}
        for sid in station_ids:
            readings = feature_store.get_gauge_readings(sid, n=1)
            if readings:
                gauge_readings_map[sid] = readings[-1].level_m

        # ── 2. Run PINN virtual sensor mesh ─────────────────
        virtual_outputs: List[VirtualSensorOutput] = []
        if gauge_readings_map:
            try:
                virtual_outputs = pinn_mesh.interpolate(
                    gauge_readings=gauge_readings_map,
                    gauge_positions_km=_GAUGE_POSITIONS_KM,
                    timestamp=now,
                )
            except Exception as exc:
                logger.exception("pinn_mesh_error", error=str(exc))

        # ── 3. Compute features for each station ────────────
        feature_rows: List[FeatureRow] = []

        for sid in station_ids:
            try:
                node = feature_store.topology.get(sid, {})
                lat = node.get("lat", 0.0) if isinstance(node, dict) else 0.0
                lon = node.get("lon", 0.0) if isinstance(node, dict) else 0.0

                gauge_readings = feature_store.get_gauge_readings(sid)
                weather_readings = feature_store.get_weather_near(lat, lon)
                cv_readings = feature_store.get_cv_readings(sid)

                # -- Original FeatureVector pipeline (for Kafka publish) --
                temporal = compute_temporal_features(
                    station_id=sid, now=now,
                    gauge_readings=gauge_readings,
                    weather_readings=weather_readings,
                    cv_readings=cv_readings,
                )
                spatial = compute_spatial_features(
                    station_id=sid, now=now,
                    topology=feature_store.topology,
                    gauge_buffers={k: list(v) for k, v in feature_store.gauge_buffer.items()},
                    weather_buffers={k: list(v) for k, v in feature_store.weather_buffer.items()},
                )
                latest_cv = cv_readings[-1] if cv_readings else None
                fv = build_feature_vector(sid, now, temporal, spatial, latest_cv)
                feature_store.set_latest(sid, fv)
                publisher.publish(fv)

                # -- New rolling-window FeatureRow pipeline (for TimescaleDB) --
                level_history = [(r.timestamp, r.level_m) for r in gauge_readings]
                rainfall_history = [
                    (w.timestamp, w.rainfall_mm_hr)
                    for w in weather_readings
                ]
                upstream_levels = {
                    uid: gauge_readings_map[uid]
                    for uid in feature_store.get_upstream_ids(sid)
                    if uid in gauge_readings_map
                }

                village_id = _STATION_VILLAGE_MAP.get(sid, f"VIL-{sid}")
                row = feature_builder.build(
                    station_id=sid,
                    village_id=village_id,
                    now=now,
                    level_history=level_history,
                    rainfall_history=rainfall_history,
                    upstream_levels=upstream_levels,
                )
                feature_rows.append(row)

            except Exception as exc:
                logger.exception("feature_compute_error", station=sid, error=str(exc))

        # ── 3b. Build FeatureRows for virtual sensors ───────
        for vs in virtual_outputs:
            try:
                row = FeatureRow(
                    village_id=f"VIL-{vs.virtual_id}",
                    station_id=vs.virtual_id,
                    timestamp=now,
                    features={
                        "predicted_level_m": vs.predicted_level_m,
                        "uncertainty_m": vs.uncertainty_m,
                        "physics_residual": vs.physics_residual or 0.0,
                        "is_virtual": 1.0,
                    },
                    quality="GOOD",
                )
                feature_rows.append(row)
            except Exception as exc:
                logger.exception("virtual_feature_error", virtual_id=vs.virtual_id)

        # ── 4. Write to TimescaleDB ─────────────────────────
        if feature_rows and timescale_writer.is_connected:
            written = await timescale_writer.write_batch(feature_rows)
            logger.info("timescale_batch_complete", written=written, total=len(feature_rows))


# ── lifespan ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start Kafka consumers, PINN mesh, and TimescaleDB on startup."""
    logger.info("feature_engine_starting")

    # Connect to TimescaleDB
    await timescale_writer.connect()

    # Start background tasks
    gauge_task = asyncio.create_task(gauge_consumer.start())
    weather_task = asyncio.create_task(weather_consumer.start())
    recompute_task = asyncio.create_task(_recompute_loop())

    yield

    # Shutdown
    gauge_consumer.stop()
    weather_consumer.stop()
    gauge_task.cancel()
    weather_task.cancel()
    recompute_task.cancel()
    await timescale_writer.close()
    logger.info("feature_engine_stopped")


app = FastAPI(
    title="ARGUS Feature Engine",
    version="2.0.0",
    description=(
        "Real-time feature engineering for flood prediction — "
        "Kalman QA, PINN virtual sensor mesh, rolling-window features, TimescaleDB"
    ),
    lifespan=lifespan,
)


# ══════════════════════════════════════════════════════════════════════════
# API Endpoints
# ══════════════════════════════════════════════════════════════════════════


# ── Health ───────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Service health check with component status."""
    return {
        "status": "ok",
        "service": "feature_engine",
        "version": "2.0.0",
        "components": {
            "timescaledb": timescale_writer.is_connected,
            "pinn_mesh": pinn_mesh._model is not None,
            "kalman_stations": len(kalman_bank.get_state_summary()),
            "stations_tracked": len(feature_store.get_all_station_ids()),
        },
    }


# ── Latest feature vector (original pipeline) ───────────────────────────
@app.get("/api/v1/features/{station_id}/latest", response_model=FeatureVector)
async def get_latest_features(station_id: str):
    """Return the most-recently computed feature vector for *station_id*."""
    fv = feature_store.get_latest(station_id)
    if fv is None:
        raise HTTPException(status_code=404, detail=f"No features for station {station_id}")
    return fv


# ── Temporal features only ───────────────────────────────────────────────
@app.get("/api/v1/features/{station_id}/temporal", response_model=TemporalFeatures)
async def get_temporal_features(station_id: str):
    """Return latest temporal features for debugging / inspection."""
    fv = feature_store.get_latest(station_id)
    if fv is None:
        raise HTTPException(status_code=404, detail=f"No features for station {station_id}")
    return fv.temporal


# ── Spatial features only ────────────────────────────────────────────────
@app.get("/api/v1/features/{station_id}/spatial", response_model=SpatialFeatures)
async def get_spatial_features(station_id: str):
    """Return latest spatial features for debugging / inspection."""
    fv = feature_store.get_latest(station_id)
    if fv is None:
        raise HTTPException(status_code=404, detail=f"No features for station {station_id}")
    return fv.spatial


# ── Bulk latest features ────────────────────────────────────────────────
@app.get("/api/v1/features/bulk", response_model=list[FeatureVector])
async def get_bulk_features(
    station_ids: str = Query(..., description="Comma-separated station IDs"),
):
    """Return latest features for multiple stations at once."""
    ids = [s.strip() for s in station_ids.split(",") if s.strip()]
    results = []
    for sid in ids:
        fv = feature_store.get_latest(sid)
        if fv is not None:
            results.append(fv)
    return results


# ── Kalman filter state ─────────────────────────────────────────────────
@app.get("/api/v1/kalman/state")
async def get_kalman_state():
    """Return current Kalman filter state for all tracked stations."""
    return kalman_bank.get_state_summary()


# ── PINN virtual sensor readings ────────────────────────────────────────
@app.get("/api/v1/pinn/virtual-sensors")
async def get_virtual_sensors():
    """Run the PINN mesh and return current virtual sensor readings."""
    now = datetime.now(timezone.utc)
    gauge_readings: Dict[str, float] = {}
    for sid in feature_store.get_all_station_ids():
        readings = feature_store.get_gauge_readings(sid, n=1)
        if readings:
            gauge_readings[sid] = readings[-1].level_m

    if not gauge_readings:
        raise HTTPException(status_code=404, detail="No gauge data available for PINN interpolation")

    outputs = pinn_mesh.interpolate(
        gauge_readings=gauge_readings,
        gauge_positions_km=_GAUGE_POSITIONS_KM,
        timestamp=now,
    )
    return [o.model_dump(mode="json") for o in outputs]


# ── Feature rows from TimescaleDB ───────────────────────────────────────
@app.get("/api/v1/feature-store/{village_id}/latest")
async def get_latest_feature_row(village_id: str):
    """Return the latest FeatureRow from TimescaleDB for a village."""
    row = await timescale_writer.get_latest(village_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No feature row for village {village_id}")
    return row.model_dump(mode="json")


@app.get("/api/v1/feature-store/{village_id}/range")
async def get_feature_range(
    village_id: str,
    start: str = Query(..., description="ISO start timestamp"),
    end: str = Query(..., description="ISO end timestamp"),
):
    """Return FeatureRows from TimescaleDB within a time range."""
    rows = await timescale_writer.get_range(village_id, start, end)
    return [r.model_dump(mode="json") for r in rows]


# ── Station topology ────────────────────────────────────────────────────
@app.get("/api/v1/topology")
async def get_topology():
    """Return the station topology / adjacency graph."""
    return feature_store.topology
