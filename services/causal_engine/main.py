"""Causal Engine — FastAPI service (port 8006).

ARGUS's brain: implements Judea Pearl's do-calculus for flood intervention queries.

Modes:
  CONTINUOUS: reads predictions, builds causal risk scores, publishes causal.risk.*
  QUERY: responds to API calls asking "what happens if I do X?"

Exposes:
  POST /api/v1/causal/intervene              → do(X=x) intervention (THE HEADLINE)
  GET  /api/v1/causal/risk/{basin_id}        → causal risk score
  GET  /api/v1/causal/dag/{basin_id}         → DAG structure for dashboard
  GET  /api/v1/causal/interventions/{basin_id} → available intervention nodes
  GET  /api/v1/causal/dag                    → full DAG (legacy)
  POST /api/v1/causal/predict                → forward inference (legacy)
  GET  /health                               → liveness
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Dict, List

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from shared.config import get_settings
from shared.models.phase2 import (
    CausalDAG,
    InterventionRequest,
    InterventionResult,
)

# Phase 2 enhanced modules
from services.causal_engine.dag.causal_dag import CausalDAGManager
from services.causal_engine.inference.causal_gnn import CausalGNNInference
from services.causal_engine.inference.interventional_engine import InterventionalEngine
from services.causal_engine.api.routes import router as causal_router, init_router

# Legacy modules (backward-compatible)
from services.causal_engine.dag import load_dag, save_dag
from services.causal_engine.gnn import CausalGNNEngine
from services.causal_engine.interventions import InterventionAPI

logger = structlog.get_logger(__name__)
settings = get_settings()

CAUSAL_ENGINE_PORT = int(os.getenv("CAUSAL_ENGINE_PORT", "8006"))
CAUSAL_DAG_CONFIG = os.getenv("CAUSAL_DAG_CONFIG_PATH", "./data/dags/brahmaputra_dag.json")
CAUSAL_GNN_MODEL = os.getenv("CAUSAL_GNN_MODEL_PATH", "./models/causal_gnn_brahmaputra.pt")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")

# ── Globals wired at startup ─────────────────────────────────────────────
_engine: CausalGNNEngine | None = None
_api: InterventionAPI | None = None
_dag: CausalDAG | None = None
_dag_manager: CausalDAGManager | None = None
_gnn_inference: CausalGNNInference | None = None
_intervention_engine: InterventionalEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine, _api, _dag, _dag_manager, _gnn_inference, _intervention_engine
    logger.info("causal_engine_starting", port=CAUSAL_ENGINE_PORT, demo_mode=DEMO_MODE)

    # ── Phase 2: Enhanced DAG + GNN + Interventional Engine ──────────
    _dag_manager = CausalDAGManager(basin_id="brahmaputra_upper")
    try:
        _dag_manager.load_from_config(CAUSAL_DAG_CONFIG)
        logger.info("phase2_dag_loaded", config=CAUSAL_DAG_CONFIG)
    except FileNotFoundError:
        logger.warning("phase2_dag_config_missing", path=CAUSAL_DAG_CONFIG)
        # Fall back to legacy DAG
        _dag = load_dag(settings.CAUSAL_DAG_PATH)
        _dag_manager.load_from_model(_dag)

    # Init Phase 2 GNN inference
    _gnn_inference = CausalGNNInference(
        dag_manager=_dag_manager,
        model_path=CAUSAL_GNN_MODEL,
        hidden=settings.CAUSAL_GNN_HIDDEN,
    )

    # Init Phase 2 Interventional Engine
    _intervention_engine = InterventionalEngine(
        dag_manager=_dag_manager,
        gnn_model=_gnn_inference,
    )

    # Wire Phase 2 API routes
    init_router(_dag_manager, _intervention_engine)

    # ── Legacy: keep existing engine working ─────────────────────────
    if _dag is None:
        _dag = _dag_manager.dag_model or load_dag(settings.CAUSAL_DAG_PATH)
    logger.info("dag_loaded", nodes=len(_dag.nodes), edges=len(_dag.edges))

    _engine = CausalGNNEngine(
        _dag,
        hidden=settings.CAUSAL_GNN_HIDDEN,
        n_layers=settings.CAUSAL_GNN_LAYERS,
    )
    _api = InterventionAPI(_engine)
    save_dag(_dag, settings.CAUSAL_DAG_PATH)

    logger.info("causal_engine_ready", demo_mode=DEMO_MODE)
    yield
    logger.info("causal_engine_shutdown")


app = FastAPI(
    title="ARGUS Causal Engine",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount Phase 2 routes ─────────────────────────────────────────────────
app.include_router(causal_router)


# ═══════════════════════════════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {
        "service": "causal_engine",
        "version": "2.0.0",
        "status": "healthy",
        "dag_nodes": len(_dag.nodes) if _dag else 0,
        "dag_edges": len(_dag.edges) if _dag else 0,
    }


@app.get("/api/v1/causal/dag")
async def get_dag():
    """Return the full causal DAG."""
    if not _dag:
        raise HTTPException(503, "DAG not loaded")
    return _dag.model_dump()


@app.post("/api/v1/causal/predict")
async def predict(evidence: Dict[str, float]):
    """Forward pass through the causal graph."""
    if not _engine:
        raise HTTPException(503, "Engine not ready")
    result = _engine.predict(evidence)
    return {"evidence": evidence, "predictions": result}


@app.post("/api/v1/causal/intervene")
async def intervene(request: InterventionRequest) -> InterventionResult:
    """Execute a do(X=x) intervention."""
    if not _api:
        raise HTTPException(503, "Engine not ready")
    if request.variable not in _engine.idx:
        raise HTTPException(
            400,
            f"Unknown variable '{request.variable}'. "
            f"Available: {list(_engine.idx.keys())}",
        )
    return _api.run(request)


@app.post("/api/v1/causal/sensitivity")
async def sensitivity(
    variable: str,
    target: str,
    min_val: float = 0.0,
    max_val: float = 1.0,
    steps: int = 10,
    context: Dict[str, float] | None = None,
):
    """Sweep a variable across a range and observe target response."""
    if not _api:
        raise HTTPException(503, "Engine not ready")
    import numpy as np

    values = np.linspace(min_val, max_val, steps).tolist()
    results = _api.sensitivity_analysis(
        variable=variable,
        values=values,
        target=target,
        context=context or {},
    )
    return {"variable": variable, "target": target, "sweep": results}


@app.get("/api/v1/causal/adjacency")
async def adjacency():
    """Return adjacency dictionary."""
    if not _engine:
        raise HTTPException(503, "Engine not ready")
    return _engine.get_adjacency_dict()


# ═══════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(
        "services.causal_engine.main:app",
        host="0.0.0.0",
        port=CAUSAL_ENGINE_PORT,
        reload=False,
    )
