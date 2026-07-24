"""ScarNet API routes.

Endpoints:
  GET  /api/v1/scarnet/latest                  — Latest scan result
  GET  /api/v1/scarnet/history/{catchment_id}   — Historical terrain health timeline
  GET  /api/v1/scarnet/tiles/before             — Before-image thumbnail data
  GET  /api/v1/scarnet/tiles/after              — After-image thumbnail data
  GET  /api/v1/scarnet/risk-delta/{catchment_id} — Flood risk change from terrain degradation
  POST /api/v1/scarnet/trigger-demo             — Trigger demo scan immediately
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException

from services.scarnet.scheduler.scan_scheduler import ScanScheduler

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/scarnet", tags=["scarnet"])

# Injected at startup
_scheduler: Optional[ScanScheduler] = None


def init_routes(scheduler: ScanScheduler):
    """Inject the ScanScheduler instance into route handlers."""
    global _scheduler
    _scheduler = scheduler


def _require_scheduler() -> ScanScheduler:
    if _scheduler is None:
        raise HTTPException(503, "ScarNet scheduler not initialized")
    return _scheduler


# ── GET /latest ──────────────────────────────────────────────────────────

@router.get("/latest")
async def get_latest_scan():
    """Latest terrain scan result with health score, changes, and PINN update status."""
    sched = _require_scheduler()
    result = sched.latest_result

    if result is None:
        return {
            "status": "no_scan_yet",
            "message": "No terrain scan has been performed yet. Trigger a demo scan.",
            "terrain_health_score": None,
        }

    return {
        "status": "ok",
        **result.to_dict(),
    }


# ── GET /history/{catchment_id} ──────────────────────────────────────────

@router.get("/history/{catchment_id}")
async def get_scan_history(catchment_id: str):
    """Historical terrain health score timeline for a catchment."""
    sched = _require_scheduler()

    timeline = [
        {
            "date": r.after_date,
            "terrain_health_score": r.terrain_health_score,
            "changes_detected": len(r.changes),
            "total_area_changed_ha": r.total_area_changed_ha,
        }
        for r in sched.scan_history
    ]

    # Add synthetic historical data for demo richness
    if len(timeline) <= 1:
        timeline = [
            {"date": "2020-06-15", "terrain_health_score": 0.95, "changes_detected": 0, "total_area_changed_ha": 0},
            {"date": "2020-12-15", "terrain_health_score": 0.94, "changes_detected": 1, "total_area_changed_ha": 1.2},
            {"date": "2021-06-15", "terrain_health_score": 0.91, "changes_detected": 1, "total_area_changed_ha": 3.5},
            {"date": "2021-12-15", "terrain_health_score": 0.88, "changes_detected": 2, "total_area_changed_ha": 5.8},
            {"date": "2022-06-15", "terrain_health_score": 0.85, "changes_detected": 1, "total_area_changed_ha": 2.1},
            {"date": "2022-12-15", "terrain_health_score": 0.82, "changes_detected": 2, "total_area_changed_ha": 7.3},
            {"date": "2023-06-15", "terrain_health_score": 0.76, "changes_detected": 3, "total_area_changed_ha": 11.4},
            *timeline,
        ]

    return {
        "catchment_id": catchment_id,
        "timeline": timeline,
        "trend": "declining" if len(timeline) > 1 and timeline[-1]["terrain_health_score"] < timeline[0]["terrain_health_score"] else "stable",
    }


# ── GET /tiles/before ───────────────────────────────────────────────────

@router.get("/tiles/before")
async def get_before_tile():
    """Return metadata and NDVI heatmap data for the before image."""
    sched = _require_scheduler()
    tiles = sched.sentinel_client.get_demo_tiles()

    return {
        "available": tiles["before"] is not None,
        "date": tiles.get("before_date", "2022-08-15"),
        "location": tiles.get("location", "Beas Valley, Himachal Pradesh"),
        "bbox": tiles.get("bbox"),
        "description": "Pre-change baseline — intact forest cover, normal river channel",
    }


# ── GET /tiles/after ────────────────────────────────────────────────────

@router.get("/tiles/after")
async def get_after_tile():
    """Return metadata and NDVI heatmap data for the after image."""
    sched = _require_scheduler()
    tiles = sched.sentinel_client.get_demo_tiles()

    return {
        "available": tiles["after"] is not None,
        "date": tiles.get("after_date", "2023-09-15"),
        "location": tiles.get("location", "Beas Valley, Himachal Pradesh"),
        "bbox": tiles.get("bbox"),
        "description": "Post-change — deforestation detected, urbanization expanded, slope instability",
    }


# ── GET /risk-delta/{catchment_id} ──────────────────────────────────────

@router.get("/risk-delta/{catchment_id}")
async def get_risk_delta(catchment_id: str):
    """Quantified flood risk change from terrain degradation."""
    sched = _require_scheduler()
    result = sched.latest_result

    if result is None:
        return {
            "catchment_id": catchment_id,
            "flood_risk_increase_pct": 0,
            "primary_cause": "NONE",
            "area_affected_ha": 0,
            "human_readable": "No terrain scan available yet.",
        }

    # Find the most impactful change
    if not result.changes:
        return {
            "catchment_id": catchment_id,
            "flood_risk_increase_pct": 0,
            "primary_cause": "NONE",
            "area_affected_ha": 0,
            "human_readable": f"Catchment {catchment_id}: terrain stable, no flood risk increase detected.",
        }

    primary = max(result.changes, key=lambda c: c.area_hectares * c.severity_weight)
    total_risk_pct = sum(
        min(30, c.area_hectares * c.severity_weight * 0.5) for c in result.changes
    )
    total_risk_pct = min(95, total_risk_pct)

    return {
        "catchment_id": catchment_id,
        "flood_risk_increase_pct": round(total_risk_pct, 1),
        "primary_cause": primary.change_type,
        "area_affected_ha": round(result.total_area_changed_ha, 2),
        "changes_count": len(result.changes),
        "terrain_health_score": result.terrain_health_score,
        "human_readable": (
            f"Catchment {catchment_id}: flood risk increased {total_risk_pct:.0f}% "
            f"due to {primary.change_type.lower().replace('_', ' ')} "
            f"({primary.area_hectares:.1f} ha). "
            f"Total {result.total_area_changed_ha:.1f} ha affected across "
            f"{len(result.changes)} detected changes."
        ),
    }


# ── POST /trigger-demo ──────────────────────────────────────────────────

@router.post("/trigger-demo")
async def trigger_demo_scan():
    """Trigger the demo terrain scan immediately.

    Runs change detection on pre-generated Beas Valley tiles.
    Called by the Dashboard's ScarNet demo button.
    """
    sched = _require_scheduler()

    logger.info("demo_scan_triggered", source="api")
    result = await sched.run_demo_scan()

    return {
        "status": "completed",
        "terrain_health_score": result.terrain_health_score,
        "changes_detected": len(result.changes),
        "pinn_update_required": result.pinn_update_required,
        "total_area_changed_ha": result.total_area_changed_ha,
        "summary": result.summary,
        "scan_duration_ms": result.scan_duration_ms,
        "changes": [
            {
                "type": c.change_type,
                "area_ha": round(c.area_hectares, 2),
                "severity": c.severity,
                "impact": c.flood_risk_impact,
            }
            for c in result.changes
        ],
    }
