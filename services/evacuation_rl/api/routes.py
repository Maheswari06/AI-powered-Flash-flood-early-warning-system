"""Evacuation RL API routes.

GET  /api/v1/evacuation/plan/{scenario_id}  — current plan
POST /api/v1/evacuation/compute             — force recompute
GET  /api/v1/evacuation/village/{village_id} — per-village plan
GET  /api/v1/evacuation/notifications       — notification log
POST /api/v1/evacuation/demo                — run Majuli demo
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException

from services.evacuation_rl.agent.ppo_agent import EvacuationAgent, EvacuationPlan

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/evacuation", tags=["evacuation"])

# Module-level references (set from main.py)
_agent: Optional[EvacuationAgent] = None
_cached_plans: Dict[str, Dict] = {}
_notifications: List[Dict[str, Any]] = []


def init_routes(agent: EvacuationAgent) -> None:
    """Initialize routes with agent reference."""
    global _agent
    _agent = agent


@router.get("/plan/{scenario_id}")
async def get_plan(scenario_id: str):
    """Return current evacuation plan (cached)."""
    if scenario_id in _cached_plans:
        return _cached_plans[scenario_id]

    if not _agent:
        raise HTTPException(503, "Service not ready")

    plan = _agent.compute_evacuation_plan()
    result = plan.to_dict()
    _cached_plans[scenario_id] = result
    return result


@router.post("/compute")
async def compute_plan(
    scenario_id: str = "majuli_2024",
    risk_score: float = 0.85,
):
    """Force-recompute evacuation plan."""
    if not _agent:
        raise HTTPException(503, "Service not ready")

    plan = _agent.compute_evacuation_plan()
    result = plan.to_dict()
    _cached_plans[scenario_id] = result

    # Log notification
    _notifications.append({
        "type": "plan_computed",
        "scenario_id": scenario_id,
        "assignments": len(plan.assignments),
        "people_covered": plan.total_people_covered,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return result


@router.get("/village/{village_id}")
async def get_village_plan(village_id: str):
    """Return per-village evacuation details."""
    # Search cached plans
    for sid, plan in _cached_plans.items():
        for assignment in plan.get("assignments", []):
            if assignment.get("village_id") == village_id:
                return {
                    "village_id": village_id,
                    "scenario_id": sid,
                    "assignment": assignment,
                }

    # Compute fresh
    if _agent:
        plan = _agent.compute_evacuation_plan()
        for a in plan.assignments:
            ad = a.to_dict() if hasattr(a, "to_dict") else a
            if ad.get("village_id") == village_id:
                return {
                    "village_id": village_id,
                    "scenario_id": "majuli_2024",
                    "assignment": ad,
                }

    raise HTTPException(404, f"No plan found for village {village_id}")


@router.get("/notifications")
async def get_notifications():
    """Return all notifications."""
    return _notifications


@router.post("/demo")
async def run_demo():
    """Run Majuli demo scenario with pre-configured data.

    Returns plan immediately and logs notifications.
    """
    if not _agent:
        raise HTTPException(503, "Service not ready")

    plan = _agent.compute_evacuation_plan()
    result = plan.to_dict()
    _cached_plans["majuli_2024"] = result

    # Generate notifications for each assignment
    for a in plan.assignments:
        ad = a.to_dict() if hasattr(a, "to_dict") else a
        _notifications.append({
            "type": "evacuation_alert",
            "village_id": ad.get("village_id"),
            "village_name": ad.get("village_name"),
            "vehicle": ad.get("vehicle_id"),
            "shelter": ad.get("shelter_name"),
            "eta_minutes": ad.get("eta_minutes"),
            "priority": ad.get("priority"),
            "message": (
                f"EVACUATION ALERT: {ad.get('village_name')} — "
                f"Vehicle {ad.get('vehicle_id')} departing for "
                f"{ad.get('shelter_name')}. "
                f"ETA: {ad.get('eta_minutes')} min. "
                f"Population: {ad.get('population')}."
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    _notifications.append({
        "type": "demo_complete",
        "scenario_id": "majuli_2024",
        "total_covered": plan.total_people_covered,
        "completion_min": plan.estimated_completion_minutes,
        "planner": plan.planner_mode,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "status": "demo_complete",
        "plan": result,
        "notifications_sent": len(plan.assignments),
    }
