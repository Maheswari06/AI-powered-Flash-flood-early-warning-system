"""Evacuation RL Engine — FastAPI service (port 8010).

Multi-agent RL evacuation choreography engine.
Turns flood warnings into actionable rescue plans.

Dual mode:
  - PRETRAINED: PPO agent from checkpoint
  - RULE_BASED: priority-based heuristic (default, always works)

Run: uvicorn services.evacuation_rl.main:app --reload --port 8010
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException

from shared.config import get_settings
from services.evacuation_rl.agent.ppo_agent import EvacuationAgent
from services.evacuation_rl.api.routes import router as evac_router, init_routes

logger = structlog.get_logger(__name__)
settings = get_settings()

# ── Globals ──────────────────────────────────────────────────────────────
_agent: EvacuationAgent | None = None

EVAC_PORT = int(os.getenv("EVAC_RL_PORT", str(settings.EVAC_RL_PORT)))
CONFIG_PATH = os.getenv("EVAC_CONFIG_PATH", "./data/majuli_evacuation_config.json")
CHECKPOINT_PATH = os.getenv("EVAC_MODEL_PATH", settings.EVAC_MODEL_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent
    logger.info("evacuation_rl_starting", port=EVAC_PORT)

    _agent = EvacuationAgent(
        checkpoint_path=CHECKPOINT_PATH,
        config_path=CONFIG_PATH,
        mode="auto",
    )
    init_routes(_agent)

    # Pre-compute the Majuli demo plan
    plan = _agent.compute_evacuation_plan()
    logger.info(
        "evacuation_rl_ready",
        mode=_agent.mode,
        villages=len(_agent.env.villages),
        vehicles=len(_agent.env.vehicles),
        shelters=len(_agent.env.shelters),
        demo_plan_assignments=len(plan.assignments),
    )

    yield
    logger.info("evacuation_rl_shutdown")


app = FastAPI(
    title="ARGUS Evacuation RL Engine",
    version="2.1.0",
    description=(
        "Multi-agent RL evacuation choreography engine. "
        "Turns flood warnings into actionable rescue plans "
        "with vehicle routing, shelter assignment, and road closure awareness."
    ),
    lifespan=lifespan,
)

# Include API routes
app.include_router(evac_router)


# ═══════════════════════════════════════════════════════════════════════
# Health + top-level endpoints
# ═══════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {
        "service": "evacuation_rl",
        "version": "2.1.0",
        "status": "healthy",
        "planner_mode": _agent.mode if _agent else "not_ready",
        "config": Path(CONFIG_PATH).name,
        "villages": len(_agent.env.villages) if _agent else 0,
        "vehicles": len(_agent.env.vehicles) if _agent else 0,
        "shelters": len(_agent.env.shelters) if _agent else 0,
    }


@app.get("/api/v1/health")
async def health_v1():
    return await health()


# ═══════════════════════════════════════════════════════════════════════
# Legacy endpoints (backward compat with Phase 1 graph-based API)
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/v1/evacuation/graph")
async def get_graph():
    """Return the full scenario config as a graph."""
    if not _agent:
        raise HTTPException(503, "Service not ready")
    config = _agent.env.config
    return {
        "villages": config.get("villages", []),
        "vehicles": config.get("vehicles", []),
        "shelters": config.get("shelters", []),
        "roads": config.get("roads", []),
        "flood_arrival": config.get("flood_arrival_by_village", {}),
        "total_time_minutes": config.get("total_time_minutes", 120),
    }


@app.get("/api/v1/evacuation/graph/{village_id}")
async def get_village_graph(village_id: str):
    """Return scenario data for a specific village."""
    if not _agent:
        raise HTTPException(503, "Service not ready")
    config = _agent.env.config
    village = next(
        (v for v in config.get("villages", []) if v["id"] == village_id),
        None,
    )
    if not village:
        raise HTTPException(404, f"Village '{village_id}' not found")

    return {
        "village": village,
        "flood_arrival_min": config.get("flood_arrival_by_village", {}).get(village_id),
        "roads": config.get("roads", []),
        "shelters": config.get("shelters", []),
        "vehicles": config.get("vehicles", []),
    }


# ── Backward compat: old-style plan endpoint ─────────────────────────
@app.post("/api/v1/evacuation/plan")
async def generate_plan_legacy(
    village_id: str = "majuli_ward_7",
    risk_score: float = 0.75,
    trigger_level: str = "WARNING",
):
    """Generate evacuation plan (legacy endpoint)."""
    if not _agent:
        raise HTTPException(503, "Service not ready")
    plan = _agent.compute_evacuation_plan()
    return plan.to_dict()


# ═══════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(
        "services.evacuation_rl.main:app",
        host=settings.SERVICE_HOST,
        port=EVAC_PORT,
        reload=False,
    )
