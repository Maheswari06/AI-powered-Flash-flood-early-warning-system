"""MIRROR — Counterfactual Replay Engine (port 8011).

Phase 2 rewrite: historical flood event replay with 4 standard
counterfactuals, intervention slider, PDF report generation.

Endpoints:
  GET  /api/v1/mirror/events                       → list available events
  GET  /api/v1/mirror/event/{id}/counterfactuals    → run all counterfactuals
  GET  /api/v1/mirror/event/{id}/counterfactual/{cf_id} → single CF
  GET  /api/v1/mirror/event/{id}/timeline           → intervention slider data
  GET  /api/v1/mirror/event/{id}/report             → download PDF report
  POST /api/v1/mirror/event/{id}/custom             → custom CF with params
  POST /api/v1/mirror/demo                          → run Himachal 2023 demo

  # Legacy compat
  POST /api/v1/mirror/replay                        → run old-style query
  GET  /api/v1/mirror/presets                        → list preset scenarios
  POST /api/v1/mirror/compare                        → quick comparison
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import List, Optional

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

from shared.config import get_settings
from shared.models.phase2 import CounterfactualQuery, CounterfactualResult

# New Phase 2 modules
from services.mirror.replay.event_loader import FloodEventLoader
from services.mirror.replay.counterfactual_engine import (
    CounterfactualEngine,
    CounterfactualResult as CFResult,
    STANDARD_COUNTERFACTUALS,
)
from services.mirror.report.report_generator import MirrorReportGenerator

# Legacy simulator (backward compat)
from services.mirror.simulator import MirrorEngine

logger = structlog.get_logger(__name__)
settings = get_settings()

# ── Globals ──────────────────────────────────────────────────────────────
_loader: FloodEventLoader | None = None
_cf_engine: CounterfactualEngine | None = None
_report_gen: MirrorReportGenerator | None = None
_legacy_engine: MirrorEngine | None = None
_demo_results: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loader, _cf_engine, _report_gen, _legacy_engine, _demo_results
    logger.info("mirror_starting", port=settings.MIRROR_PORT, version="2.1.0")

    # Initialize modules
    _loader = FloodEventLoader()
    _cf_engine = CounterfactualEngine()
    _report_gen = MirrorReportGenerator()

    # Legacy engine for backward compat
    try:
        _legacy_engine = MirrorEngine(max_steps=settings.MIRROR_MAX_STEPS)
    except Exception:
        logger.warning("legacy_engine_unavailable")

    # Pre-compute Himachal 2023 demo
    demo_event = _loader.load_demo_event()
    demo_cfs = _cf_engine.run_all(demo_event)
    _demo_results = {
        "event": demo_event.to_dict(),
        "counterfactuals": [cf.to_dict() for cf in demo_cfs],
        "slider_data": _cf_engine.get_intervention_slider_data(demo_event),
    }
    logger.info(
        "mirror_ready",
        events=len(_loader.list_events()),
        demo_cfs=len(demo_cfs),
        best_intervention=demo_cfs[0].cf_label if demo_cfs else "none",
        lives_saveable=demo_cfs[0].lives_saved_estimate if demo_cfs else 0,
    )
    yield
    logger.info("mirror_shutdown")


app = FastAPI(
    title="HYDRA MIRROR — Counterfactual Replay Engine",
    version="2.1.0",
    lifespan=lifespan,
)


# ═══════════════════════════════════════════════════════════════════════
#  Health
# ═══════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {
        "service": "mirror",
        "version": "2.1.0",
        "status": "healthy",
        "events_loaded": len(_loader.list_events()) if _loader else 0,
        "demo_ready": bool(_demo_results),
        "counterfactuals_available": list(STANDARD_COUNTERFACTUALS.keys()),
        "max_steps": settings.MIRROR_MAX_STEPS,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Phase 2 Endpoints
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/v1/mirror/events")
async def list_events():
    """List all available historical flood events."""
    if not _loader:
        raise HTTPException(503, "Loader not ready")
    return {"events": _loader.list_events()}


@app.get("/api/v1/mirror/event/{event_id}/counterfactuals")
async def get_counterfactuals(event_id: str):
    """Run all standard counterfactuals for a given event."""
    if not _loader or not _cf_engine:
        raise HTTPException(503, "Engine not ready")

    # Check demo cache first
    if event_id == "himachal_2023" and _demo_results:
        return _demo_results

    event = _loader.load_event(event_id)
    if not event:
        raise HTTPException(404, f"Event '{event_id}' not found")

    results = _cf_engine.run_all(event)
    return {
        "event": event.to_dict(),
        "counterfactuals": [r.to_dict() for r in results],
        "slider_data": _cf_engine.get_intervention_slider_data(event),
    }


@app.get("/api/v1/mirror/event/{event_id}/counterfactual/{cf_id}")
async def get_single_counterfactual(event_id: str, cf_id: str):
    """Run a single counterfactual for a given event."""
    if not _loader or not _cf_engine:
        raise HTTPException(503, "Engine not ready")

    event = _loader.load_event(event_id)
    if not event:
        raise HTTPException(404, f"Event '{event_id}' not found")

    result = _cf_engine.run_counterfactual(event, cf_id)
    if not result:
        raise HTTPException(404, f"Counterfactual '{cf_id}' not found. "
                           f"Available: {list(STANDARD_COUNTERFACTUALS.keys())}")

    return {
        "event_id": event_id,
        "counterfactual": result.to_dict(),
    }


@app.get("/api/v1/mirror/event/{event_id}/timeline")
async def get_intervention_timeline(event_id: str):
    """Get intervention slider data for the frontend."""
    if not _loader or not _cf_engine:
        raise HTTPException(503, "Engine not ready")

    # Check demo cache
    if event_id == "himachal_2023" and _demo_results:
        return _report_gen.generate_intervention_timeline(
            _demo_results["slider_data"]
        )

    event = _loader.load_event(event_id)
    if not event:
        raise HTTPException(404, f"Event '{event_id}' not found")

    slider_data = _cf_engine.get_intervention_slider_data(event)
    return _report_gen.generate_intervention_timeline(slider_data)


@app.get("/api/v1/mirror/event/{event_id}/report")
async def download_report(event_id: str):
    """Download a PDF counterfactual report for the event."""
    if not _loader or not _cf_engine or not _report_gen:
        raise HTTPException(503, "Engine not ready")

    event = _loader.load_event(event_id)
    if not event:
        raise HTTPException(404, f"Event '{event_id}' not found")

    # Use cached results if available
    if event_id == "himachal_2023" and _demo_results:
        cfs = _demo_results["counterfactuals"]
    else:
        results = _cf_engine.run_all(event)
        cfs = [r.to_dict() for r in results]

    pdf_bytes = _report_gen.generate_pdf(event.to_dict(), cfs)

    content_type = "application/pdf"
    filename = f"MIRROR_{event_id}_report.pdf"
    if not pdf_bytes[:4] == b"%PDF":
        content_type = "text/plain"
        filename = f"MIRROR_{event_id}_report.txt"

    return Response(
        content=pdf_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/api/v1/mirror/event/{event_id}/custom")
async def run_custom_counterfactual(
    event_id: str,
    intervention_time_min: float = Query(-60, description="Minutes before peak (negative)"),
    depth_factor: float = Query(0.85, description="Depth reduction factor (0-1)"),
    rainfall_factor: float = Query(1.0, description="Rainfall adjustment factor"),
    actions: str = Query("Custom intervention", description="Comma-separated actions"),
):
    """Run a custom counterfactual with user-specified parameters."""
    if not _loader or not _cf_engine:
        raise HTTPException(503, "Engine not ready")

    event = _loader.load_event(event_id)
    if not event:
        raise HTTPException(404, f"Event '{event_id}' not found")

    action_list = [a.strip() for a in actions.split(",")]
    result = _cf_engine.run_with_custom_intervention(
        event,
        intervention_time_min=intervention_time_min,
        actions=action_list,
        depth_factor=depth_factor,
        rainfall_factor=rainfall_factor,
    )
    return {"event_id": event_id, "counterfactual": result.to_dict()}


@app.post("/api/v1/mirror/demo")
async def run_demo():
    """Run the Himachal Pradesh 2023 demo — returns pre-computed results."""
    if not _demo_results:
        raise HTTPException(503, "Demo not pre-computed")

    best = _demo_results["counterfactuals"][0] if _demo_results["counterfactuals"] else {}
    return {
        **_demo_results,
        "summary": {
            "event_name": _demo_results["event"].get("name"),
            "actual_deaths": _demo_results["event"].get("lives_lost"),
            "best_intervention": best.get("cf_label"),
            "max_lives_saveable": best.get("lives_saved_estimate"),
            "total_counterfactuals": len(_demo_results["counterfactuals"]),
        },
    }


# ═══════════════════════════════════════════════════════════════════════
#  Legacy Compat Endpoints (Phase 1 API)
# ═══════════════════════════════════════════════════════════════════════

@app.post("/api/v1/mirror/replay")
async def legacy_replay(query: CounterfactualQuery) -> dict:
    """Run a counterfactual scenario (legacy API)."""
    if _legacy_engine:
        result = _legacy_engine.replay(query)
        return result.model_dump()
    raise HTTPException(503, "Legacy engine not available — use /event/{id}/counterfactuals")


@app.get("/api/v1/mirror/presets")
async def legacy_presets():
    """List preset scenarios (legacy API)."""
    if _legacy_engine:
        presets = _legacy_engine.get_preset_scenarios()
        return [
            {"query_id": p.query_id, "scenario_name": p.scenario_name,
             "modifications": p.modifications}
            for p in presets
        ]
    # Fallback: return standard counterfactuals as presets
    return [
        {"query_id": cf_id, "scenario_name": cf_id, "modifications": {}}
        for cf_id in STANDARD_COUNTERFACTUALS
    ]


@app.post("/api/v1/mirror/compare")
async def legacy_compare(
    base_rainfall: float = 20.0,
    modified_rainfall: float = 10.0,
    base_soil: float = 0.6,
    modified_soil: float = 0.6,
):
    """Quick comparison (legacy API)."""
    if not _legacy_engine:
        raise HTTPException(503, "Legacy engine not available")
    base_q = CounterfactualQuery(
        query_id="compare_base", scenario_name="Base",
        modifications={"base_rainfall_mm_hr": base_rainfall, "base_soil_moisture": base_soil,
                       "rainfall_factor": 1.0},
    )
    mod_q = CounterfactualQuery(
        query_id="compare_modified", scenario_name="Modified",
        modifications={"base_rainfall_mm_hr": base_rainfall, "rainfall_mm_hr": modified_rainfall,
                       "soil_moisture": modified_soil},
    )
    base_r = _legacy_engine.replay(base_q)
    mod_r = _legacy_engine.replay(mod_q)
    return {
        "base": {"peak_risk": base_r.modified_outcome.get("peak_risk"),
                 "peak_level_m": base_r.modified_outcome.get("peak_level_m")},
        "modified": {"peak_risk": mod_r.modified_outcome.get("peak_risk"),
                     "peak_level_m": mod_r.modified_outcome.get("peak_level_m")},
        "risk_delta": round(
            (mod_r.modified_outcome.get("peak_risk", 0) or 0)
            - (base_r.modified_outcome.get("peak_risk", 0) or 0), 4),
    }


# ═══════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(
        "services.mirror.main:app",
        host=settings.SERVICE_HOST,
        port=settings.MIRROR_PORT,
        reload=False,
    )
