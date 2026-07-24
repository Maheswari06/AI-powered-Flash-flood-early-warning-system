"""Causal DAG loading / saving utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import structlog

from shared.models.phase2 import CausalDAG, CausalNode, CausalEdge, CausalNodeType

logger = structlog.get_logger(__name__)

# ── Default demo DAG (used when no file exists on disk) ──────────────────

_DEFAULT_NODES = [
    CausalNode(node_id="rainfall", variable="rainfall", node_type=CausalNodeType.OBSERVABLE, unit="mm/hr", default_value=0.0),
    CausalNode(node_id="soil_moisture", variable="soil_moisture", node_type=CausalNodeType.OBSERVABLE, unit="fraction", default_value=0.4),
    CausalNode(node_id="upstream_level", variable="upstream_level", node_type=CausalNodeType.OBSERVABLE, unit="m", default_value=2.0),
    CausalNode(node_id="dam_release", variable="dam_release", node_type=CausalNodeType.INTERVENTION, unit="m3/s", default_value=100.0, min_value=0.0, max_value=5000.0),
    CausalNode(node_id="downstream_flood_depth", variable="downstream_flood_depth", node_type=CausalNodeType.OUTCOME, unit="m", default_value=0.0),
    CausalNode(node_id="inundation_area", variable="inundation_area", node_type=CausalNodeType.OUTCOME, unit="km2", default_value=0.0),
]

_DEFAULT_EDGES = [
    CausalEdge(source="rainfall", target="soil_moisture", weight=0.6, mechanism="meteorological"),
    CausalEdge(source="rainfall", target="upstream_level", weight=0.8, lag_hours=2.0, mechanism="hydrological"),
    CausalEdge(source="soil_moisture", target="upstream_level", weight=0.3, mechanism="hydrological"),
    CausalEdge(source="upstream_level", target="downstream_flood_depth", weight=0.7, lag_hours=4.0, mechanism="hydrological"),
    CausalEdge(source="dam_release", target="downstream_flood_depth", weight=0.5, mechanism="anthropogenic"),
    CausalEdge(source="downstream_flood_depth", target="inundation_area", weight=0.9, mechanism="hydrological"),
]


def _default_dag() -> CausalDAG:
    return CausalDAG(
        dag_id="beas_brahmaputra_v1",
        basin_id="brahmaputra_upper",
        nodes=list(_DEFAULT_NODES),
        edges=list(_DEFAULT_EDGES),
    )


def load_dag(path: str) -> CausalDAG:
    """Load a CausalDAG from a JSON file, or return the built-in demo DAG."""
    p = Path(path)
    if p.exists():
        try:
            data = json.loads(p.read_text())
            dag = CausalDAG(**data)
            logger.info("dag_loaded_from_file", path=str(p), nodes=len(dag.nodes))
            return dag
        except Exception as exc:
            logger.warning("dag_load_failed", path=str(p), error=str(exc))
    else:
        logger.info("dag_file_missing_using_default", path=str(p))

    dag = _default_dag()
    # Persist so next restart finds it
    save_dag(dag, path)
    return dag


def save_dag(dag: CausalDAG, path: str) -> None:
    """Persist a CausalDAG to JSON."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dag.model_dump_json(indent=2))
    logger.info("dag_saved", path=str(p), nodes=len(dag.nodes))
