"""ARGUS API Gateway — Single entry point for all services (port 8000).

Provides:
  1. Single URL for dashboard (port 8000 instead of 13 different ports)
  2. Cached /dashboard/snapshot endpoint (reduces 13 API calls to 1)
  3. Aggregated /health endpoint for all services
  4. Reverse proxy to all backend services
  5. CORS handling

Run: uvicorn services.api_gateway.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)

# ── Configuration ────────────────────────────────────────────────────────
GATEWAY_PORT = int(os.getenv("GATEWAY_PORT", "8000"))
CACHE_TTL = int(os.getenv("GATEWAY_CACHE_TTL", "30"))

# ── Service Registry ────────────────────────────────────────────────────
SERVICES = {
    "ingestion":    "http://localhost:8001",
    "cv_gauging":   "http://localhost:8002",
    "feature":      "http://localhost:8003",
    "prediction":   "http://localhost:8004",
    "alerts":       "http://localhost:8005",
    "causal":       "http://localhost:8006",
    "ledger":       "http://localhost:8007",
    "chorus":       "http://localhost:8008",
    "federated":    "http://localhost:8009",
    "evacuation":   "http://localhost:8010",
    "mirror":       "http://localhost:8011",
    "scarnet":      "http://localhost:8012",
    "model_monitor": "http://localhost:8013",
    "developer_portal": "http://localhost:5175",
    # Phase 7 services
    "drone_stream":   "http://localhost:8020",
    "ndma":           "http://localhost:8021",
    "iot_gateway":    "http://localhost:8022",
    "flash_flood":    "http://localhost:8023",
    "displacement":   "http://localhost:8024",
    "cell_broadcast": "http://localhost:8025",
}

# Route prefix → service mapping (for reverse proxy)
ROUTE_MAP = {
    "/api/v1/ingest":      "ingestion",
    "/api/v1/virtual-gauge": "cv_gauging",
    "/api/v1/gauge":       "cv_gauging",
    "/api/v1/features":    "feature",
    "/api/v1/predict":     "prediction",
    "/api/v1/predictions": "prediction",
    "/api/v1/prediction":  "prediction",
    "/api/v1/alert":       "alerts",
    "/api/v1/alerts":      "alerts",
    "/api/v1/causal":      "causal",
    "/api/v1/chorus":      "chorus",
    "/api/v1/fl":          "federated",
    "/api/v1/federated":   "federated",
    "/api/v1/ledger":      "ledger",
    "/api/v1/evacuation":  "evacuation",
    "/api/v1/mirror":      "mirror",
    "/api/v1/scarnet":     "scarnet",
    "/api/v1/monitor":     "model_monitor",
    "/api/v1/playground":  "developer_portal",
    "/api/v1/docs":        "developer_portal",
    "/api/v1/registry":    "developer_portal",
    # Phase 7 routes
    "/api/v1/drone":       "drone_stream",
    "/api/v1/ndma":        "ndma",
    "/api/v1/iot":         "iot_gateway",
    "/api/v1/flash-flood": "flash_flood",
    "/api/v1/flash":       "flash_flood",
    "/api/v1/displacement":"displacement",
    "/api/v1/cell-broadcast": "cell_broadcast",
}


# ── Simple in-memory cache ──────────────────────────────────────────────
class SimpleCache:
    """TTL-based in-memory cache. No Redis dependency needed."""

    def __init__(self):
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        if key in self._store:
            ts, val = self._store[key]
            if time.time() - ts < CACHE_TTL:
                return val
            del self._store[key]
        return None

    def set(self, key: str, value: Any):
        self._store[key] = (time.time(), value)

    def invalidate(self, key: str):
        self._store.pop(key, None)


_cache = SimpleCache()


# ── Helpers ──────────────────────────────────────────────────────────────

def _safe_json(result: httpx.Response | Exception) -> dict | None:
    """Safely extract JSON from a response or return None on error."""
    if isinstance(result, Exception):
        return None
    try:
        if result.status_code == 200:
            return result.json()
    except Exception:
        pass
    return None


async def _fetch(client: httpx.AsyncClient, url: str) -> httpx.Response | Exception:
    """Fetch a URL, returning the response or exception."""
    try:
        return await client.get(url, timeout=5.0)
    except Exception as e:
        return e


# ── Lifespan ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("api_gateway_starting", port=GATEWAY_PORT, services=len(SERVICES))
    yield
    logger.info("api_gateway_stopped")


# ── FastAPI App ──────────────────────────────────────────────────────────

app = FastAPI(
    title="ARGUS API Gateway",
    description=(
        "Unified entry point for all ARGUS services. "
        "Provides cached dashboard snapshot, aggregated health check, "
        "and reverse proxy to all 14 backend services."
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


# ── Dashboard Snapshot ───────────────────────────────────────────────────

@app.get("/api/v1/dashboard/snapshot")
async def get_dashboard_snapshot():
    """Aggregate all data the dashboard needs for initial load into one response.

    Reduces dashboard startup from 13 sequential API calls to 1.
    Cached for 30 seconds.
    """
    cached = _cache.get("snapshot")
    if cached:
        return cached

    async with httpx.AsyncClient(timeout=5.0) as client:
        results = await asyncio.gather(
            _fetch(client, f"{SERVICES['prediction']}/api/v1/predictions/all"),
            _fetch(client, f"{SERVICES['causal']}/api/v1/causal/risk/brahmaputra_upper"),
            _fetch(client, f"{SERVICES['chorus']}/api/v1/chorus/signals"),
            _fetch(client, f"{SERVICES['alerts']}/api/v1/alert/log"),
            _fetch(client, f"{SERVICES['evacuation']}/api/v1/evacuation/plan/majuli_2024"),
            _fetch(client, f"{SERVICES['ledger']}/api/v1/ledger/events"),
            _fetch(client, f"{SERVICES['scarnet']}/api/v1/scarnet/latest"),
            _fetch(client, f"{SERVICES['mirror']}/api/v1/mirror/events"),
            _fetch(client, f"{SERVICES['federated']}/api/v1/fl/status"),
            _fetch(client, f"{SERVICES['model_monitor']}/api/v1/monitor/drift-report"),
        )

    snapshot = {
        "predictions":     _safe_json(results[0]),
        "causal_risk":     _safe_json(results[1]),
        "chorus_signals":  _safe_json(results[2]),
        "recent_alerts":   _safe_json(results[3]),
        "evacuation_plan": _safe_json(results[4]),
        "ledger_events":   _safe_json(results[5]),
        "scarnet_latest":  _safe_json(results[6]),
        "mirror_events":   _safe_json(results[7]),
        "federated_status": _safe_json(results[8]),
        "model_drift":     _safe_json(results[9]),
        "snapshot_at":     datetime.now(timezone.utc).isoformat(),
        "services_queried": len(results),
        "services_up": sum(1 for r in results if not isinstance(r, Exception) and r.status_code == 200),
    }

    _cache.set("snapshot", snapshot)
    return snapshot


# ── Basin Summaries (live data for BasinSelector) ────────────────────────

BASIN_REGISTRY = [
    {
        "id": "brahmaputra",
        "name": "Brahmaputra Basin",
        "region": "Northeast India",
        "center": [26.1, 91.7],
        "zoom": 8,
        "color": "#38bdf8",
    },
    {
        "id": "beas",
        "name": "Beas Basin",
        "region": "Himachal Pradesh",
        "center": [31.9, 77.1],
        "zoom": 9,
        "color": "#34d399",
    },
    {
        "id": "godavari",
        "name": "Godavari Basin",
        "region": "Central–South India",
        "center": [19.0, 79.5],
        "zoom": 7,
        "color": "#fbbf24",
    },
]


@app.get("/api/v1/basins/summaries")
async def basins_summaries():
    """Return basin metadata with live station counts and alert status.

    Dashboard BasinSelector fetches this instead of using hardcoded data.
    Enriches static registry with live station counts from prediction service.
    """
    cached = _cache.get("basins_summaries")
    if cached:
        return cached

    enriched = []
    async with httpx.AsyncClient(timeout=3.0) as client:
        for basin in BASIN_REGISTRY:
            entry = {**basin, "stations": 0, "active_alerts": 0}
            try:
                resp = await client.get(
                    f"{SERVICES['prediction']}/api/v1/predictions/stations",
                    params={"basin": basin["id"]},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    entry["stations"] = len(data) if isinstance(data, list) else data.get("count", 0)
            except Exception:
                pass
            try:
                resp = await client.get(
                    f"{SERVICES['alerts']}/api/v1/alerts/active",
                    params={"basin": basin["id"]},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    entry["active_alerts"] = len(data) if isinstance(data, list) else data.get("count", 0)
            except Exception:
                pass
            enriched.append(entry)

    _cache.set("basins_summaries", enriched)
    return enriched


# ── Gauge Aggregation (GaugeHeroPanel) ──────────────────────────────────

@app.get("/api/v1/gauges/active")
async def get_active_gauges():
    """Aggregate CWC gauge readings from ingestion service + IoT water level devices.

    Used by GaugeHeroPanel to show all active river gauge readings in one place.
    Combines CWC fallback/live data with IoT sensor readings.
    """
    cached = _cache.get("gauges_active")
    if cached:
        return cached

    gauges = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        # Fetch from ingestion service (CWC readings)
        try:
            resp = await client.get(f"{SERVICES['ingestion']}/api/v1/ingest/readings")
            if resp.status_code == 200:
                data = resp.json()
                readings = data.get("readings", data) if isinstance(data, dict) else data
                if isinstance(readings, list):
                    for r in readings:
                        gauges.append({
                            "station_id": r.get("station_id", "unknown"),
                            "station_name": r.get("station_name", r.get("station_id", "unknown")),
                            "level_m": r.get("level_m", r.get("water_level", 0)),
                            "danger_level_m": r.get("danger_level_m", 7.0),
                            "warning_level_m": r.get("warning_level_m", 6.0),
                            "flow_cumecs": r.get("flow_cumecs", 0),
                            "quality_flag": r.get("quality_flag", "SYNTHETIC"),
                            "source": r.get("source", "CWC_WRIS"),
                        })
        except Exception:
            pass

        # Fetch IoT water level sensors
        try:
            resp = await client.get(f"{SERVICES['iot_gateway']}/api/v1/iot/devices")
            if resp.status_code == 200:
                devices = resp.json().get("devices", [])
                for d in devices:
                    if d.get("device_type") == "WATER_LEVEL":
                        last = d.get("last_reading", {})
                        gauges.append({
                            "station_id": d.get("device_id", "unknown"),
                            "station_name": f"{d.get('device_id', 'IoT')} ({d.get('basin_id', '')})",
                            "level_m": last.get("value", 0) if isinstance(last, dict) else 0,
                            "danger_level_m": 7.0,
                            "warning_level_m": 6.0,
                            "flow_cumecs": 0,
                            "quality_flag": "REAL",
                            "source": d.get("protocol", "IOT"),
                        })
        except Exception:
            pass

    # If no live gauges, provide CWC fallback data
    if not gauges:
        gauges = [
            {"station_id": "CWC_DIBRUGARH_01", "station_name": "Dibrugarh",
             "level_m": 4.8, "danger_level_m": 7.0, "warning_level_m": 6.0,
             "flow_cumecs": 8500, "quality_flag": "SYNTHETIC", "source": "FALLBACK"},
            {"station_id": "CWC_NEAMATI_01", "station_name": "Neamati (Jorhat)",
             "level_m": 5.3, "danger_level_m": 7.0, "warning_level_m": 6.0,
             "flow_cumecs": 12000, "quality_flag": "SYNTHETIC", "source": "FALLBACK"},
            {"station_id": "CWC_TEZPUR_01", "station_name": "Tezpur",
             "level_m": 6.2, "danger_level_m": 7.0, "warning_level_m": 6.0,
             "flow_cumecs": 15000, "quality_flag": "SYNTHETIC", "source": "FALLBACK"},
            {"station_id": "CWC_GUWAHATI_01", "station_name": "Guwahati (Pandu)",
             "level_m": 3.5, "danger_level_m": 7.0, "warning_level_m": 6.0,
             "flow_cumecs": 7200, "quality_flag": "SYNTHETIC", "source": "FALLBACK"},
            {"station_id": "CWC_KULLU_01", "station_name": "Kullu",
             "level_m": 2.1, "danger_level_m": 5.0, "warning_level_m": 4.0,
             "flow_cumecs": 450, "quality_flag": "SYNTHETIC", "source": "FALLBACK"},
            {"station_id": "CWC_PANDOH_01", "station_name": "Pandoh Dam",
             "level_m": 3.8, "danger_level_m": 5.0, "warning_level_m": 4.0,
             "flow_cumecs": 920, "quality_flag": "SYNTHETIC", "source": "FALLBACK"},
        ]

    result = {"active_count": len(gauges), "gauges": gauges}
    _cache.set("gauges_active", result)
    return result


@app.get("/api/v1/soil/moisture/summary")
async def get_soil_moisture_summary():
    """Soil moisture data for GaugeHeroPanel.

    Aggregates soil moisture readings from IoT gateway sensors.
    """
    cached = _cache.get("soil_moisture")
    if cached:
        return cached

    stations = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(f"{SERVICES['iot_gateway']}/api/v1/iot/devices")
            if resp.status_code == 200:
                devices = resp.json().get("devices", [])
                for d in devices:
                    if d.get("device_type") == "SOIL_MOISTURE":
                        last = d.get("last_reading", {})
                        stations.append({
                            "station_id": d.get("device_id", "unknown"),
                            "station_name": f"{d.get('device_id', 'Soil')} ({d.get('basin_id', '')})",
                            "moisture_m3m3": last.get("value", 0.35) if isinstance(last, dict) else 0.35,
                            "field_capacity_m3m3": 0.42,
                        })
        except Exception:
            pass

    # Fallback soil moisture stations
    if not stations:
        stations = [
            {"station_id": "SOIL_BEAS_01", "station_name": "Beas Upper Kullu",
             "moisture_m3m3": 0.36, "field_capacity_m3m3": 0.42},
            {"station_id": "SOIL_MAJULI_01", "station_name": "Majuli Nimati",
             "moisture_m3m3": 0.38, "field_capacity_m3m3": 0.42},
            {"station_id": "SOIL_JORHAT_01", "station_name": "Jorhat Riverside",
             "moisture_m3m3": 0.31, "field_capacity_m3m3": 0.42},
            {"station_id": "SOIL_KULLU_02", "station_name": "Kullu Valley Floor",
             "moisture_m3m3": 0.34, "field_capacity_m3m3": 0.28},
        ]

    result = {"stations": stations, "count": len(stations)}
    _cache.set("soil_moisture", result)
    return result


# ── Aggregated Health ────────────────────────────────────────────────────

@app.get("/health")
async def aggregate_health():
    """Ping all 14 services and return unified health status.

    Used by the SystemHealth dashboard widget and pre-demo checks.
    """
    cached = _cache.get("health")
    if cached:
        return cached

    async with httpx.AsyncClient(timeout=2.0) as client:
        tasks = [_fetch(client, f"{url}/health") for url in SERVICES.values()]
        checks = await asyncio.gather(*tasks)

    statuses = {}
    for name, result in zip(SERVICES.keys(), checks):
        if isinstance(result, Exception):
            statuses[name] = {"status": "DOWN", "error": str(result)[:100]}
        elif result.status_code == 200:
            latency = int(result.elapsed.total_seconds() * 1000)
            statuses[name] = {"status": "UP", "latency_ms": latency}
        else:
            statuses[name] = {"status": "DEGRADED", "http_code": result.status_code}

    up_count = sum(1 for s in statuses.values() if s["status"] == "UP")
    total = len(statuses)
    all_up = up_count == total

    health_result = {
        "overall": "OPERATIONAL" if all_up else "DEGRADED" if up_count > total // 2 else "CRITICAL",
        "services": statuses,
        "summary": f"{up_count}/{total} services UP",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    _cache.set("health", health_result)
    return health_result


# ── Reverse Proxy ────────────────────────────────────────────────────────

@app.api_route(
    "/api/v1/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy(request: Request, path: str):
    """Reverse proxy — routes /api/v1/* requests to the appropriate backend service."""
    full_path = f"/api/v1/{path}"

    # Find matching service
    target_service = None
    for prefix, service_name in ROUTE_MAP.items():
        if full_path.startswith(prefix):
            target_service = service_name
            break

    if not target_service:
        return JSONResponse(
            {"error": f"No service handles path: {full_path}"},
            status_code=404,
        )

    target_url = f"{SERVICES[target_service]}{full_path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            body = await request.body()
            headers = {
                k: v for k, v in request.headers.items()
                if k.lower() not in ("host", "content-length")
            }

            resp = await client.request(
                method=request.method,
                url=target_url,
                content=body if body else None,
                headers=headers,
            )

            excluded_headers = {"content-encoding", "content-length", "transfer-encoding"}
            resp_headers = {
                k: v for k, v in resp.headers.items()
                if k.lower() not in excluded_headers
            }

            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=resp_headers,
                media_type=resp.headers.get("content-type", "application/json"),
            )

    except httpx.ConnectError:
        return JSONResponse(
            {"error": f"Service '{target_service}' is not reachable", "url": target_url},
            status_code=502,
        )
    except httpx.TimeoutException:
        return JSONResponse(
            {"error": f"Service '{target_service}' timed out", "url": target_url},
            status_code=504,
        )


# ── Root ─────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "service": "ARGUS API Gateway",
        "version": "3.0.0",
        "description": "Unified entry point for all ARGUS services",
        "endpoints": [
            "GET  /api/v1/dashboard/snapshot  — Aggregated dashboard data (cached)",
            "GET  /health                      — All services health status",
            "ANY  /api/v1/*                    — Reverse proxy to backend services",
        ],
        "services_registered": len(SERVICES),
        "cache_ttl_seconds": CACHE_TTL,
    }


# ── Main ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "services.api_gateway.main:app",
        host="0.0.0.0",
        port=GATEWAY_PORT,
        reload=True,
        log_level="info",
    )
