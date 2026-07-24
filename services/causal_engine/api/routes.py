"""Phase 2 Causal Engine API routes.

Mounted by ``main.py`` via ``app.include_router(causal_router)``.
The ``init_router`` function wires up the global singletons at startup.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException

from shared.models.phase2 import (
    CausalRiskResponse,
    DAGStructureResponse,
    InterventionOption,
    InterventionRequest,
    InterventionResult,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/causal", tags=["causal-engine-v2"])

# These are set at startup by init_router()
_dag_manager = None
_intervention_engine = None


def init_router(dag_manager, intervention_engine) -> None:  # noqa: ANN001
    """Wire the singletons created during lifespan into the router."""
    global _dag_manager, _intervention_engine
    _dag_manager = dag_manager
    _intervention_engine = intervention_engine
    logger.info("causal_v2_routes_initialised")


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("/risk/{basin_id}", response_model=CausalRiskResponse)
async def causal_risk(basin_id: str, observations: Optional[str] = None):
    """Return the current causal risk score for a basin."""
    if _intervention_engine is None:
        raise HTTPException(503, "Interventional engine not ready")
    obs: Dict[str, float] = {}
    if observations:
        import json

        try:
            obs = json.loads(observations)
        except Exception:
            pass
    return _intervention_engine.compute_risk(basin_id, obs)


@router.get("/dag/{basin_id}", response_model=DAGStructureResponse)
async def dag_structure(basin_id: str):
    """Return DAG structure for dashboard visualisation."""
    if _dag_manager is None:
        raise HTTPException(503, "DAG manager not ready")
    return _dag_manager.get_dag_structure()


@router.get("/interventions/{basin_id}", response_model=List[InterventionOption])
async def intervention_options(basin_id: str):
    """Return available intervention nodes and their value ranges."""
    if _intervention_engine is None:
        raise HTTPException(503, "Interventional engine not ready")
    return _intervention_engine.get_intervention_options(basin_id)


@router.post("/intervene/v2", response_model=InterventionResult)
async def intervene_v2(request: InterventionRequest):
    """Enhanced do(X=x) intervention (Phase 2)."""
    if _intervention_engine is None:
        raise HTTPException(503, "Interventional engine not ready")
    try:
        return _intervention_engine.run_intervention(request)
    except KeyError as exc:
        raise HTTPException(400, f"Unknown variable: {exc}")
