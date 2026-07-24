"""Pre-trained causal DAG for the Beas–Brahmaputra river basins.

This JSON-serialisable DAG is loaded by the CausalEngine at startup.
Nodes represent observable hydro-meteorological variables; edges encode
discovered causal relationships with propagation lags.
"""

from __future__ import annotations

import json
from pathlib import Path

from shared.models.phase2 import CausalDAG, CausalNode, CausalEdge

# ── Default DAG (hard-coded for demo; real version comes from notebooks) ──

_DEFAULT_NODES = [
    CausalNode(node_id="rainfall_upper", variable="rainfall", station_id="IMD_KULLU"),
    CausalNode(node_id="rainfall_lower", variable="rainfall", station_id="IMD_MANDI"),
    CausalNode(node_id="snowmelt", variable="snowmelt", station_id="SAT_BEAS_GLACIER"),
    CausalNode(node_id="soil_moisture", variable="soil_moisture", station_id="ISRO_SM"),
    CausalNode(node_id="upstream_level", variable="water_level", station_id="CWC_PANDOH"),
    CausalNode(node_id="midstream_level", variable="water_level", station_id="CWC_MANDI"),
    CausalNode(node_id="downstream_level", variable="water_level", station_id="CWC_SUJANPUR"),
    CausalNode(node_id="dam_release", variable="dam_discharge", station_id="BBMB_PANDOH"),
    CausalNode(node_id="tributary_flow", variable="discharge", station_id="CWC_TIRTHAN"),
    CausalNode(node_id="assam_brahmaputra", variable="water_level", station_id="CWC_GUWAHATI"),
    CausalNode(node_id="assam_rainfall", variable="rainfall", station_id="IMD_GUWAHATI"),
    CausalNode(node_id="flood_risk", variable="flood_risk"),
]

_DEFAULT_EDGES = [
    CausalEdge(source="rainfall_upper", target="upstream_level", weight=0.85, lag_hours=3.0, mechanism="hydrological"),
    CausalEdge(source="rainfall_upper", target="soil_moisture", weight=0.60, lag_hours=1.0, mechanism="hydrological"),
    CausalEdge(source="rainfall_lower", target="midstream_level", weight=0.70, lag_hours=2.0, mechanism="hydrological"),
    CausalEdge(source="snowmelt", target="upstream_level", weight=0.55, lag_hours=12.0, mechanism="hydrological"),
    CausalEdge(source="soil_moisture", target="midstream_level", weight=0.45, lag_hours=1.5, mechanism="hydrological"),
    CausalEdge(source="upstream_level", target="midstream_level", weight=0.90, lag_hours=4.0, mechanism="hydrological"),
    CausalEdge(source="dam_release", target="midstream_level", weight=0.80, lag_hours=2.0, mechanism="anthropogenic"),
    CausalEdge(source="midstream_level", target="downstream_level", weight=0.88, lag_hours=5.0, mechanism="hydrological"),
    CausalEdge(source="tributary_flow", target="midstream_level", weight=0.50, lag_hours=3.0, mechanism="hydrological"),
    CausalEdge(source="downstream_level", target="flood_risk", weight=0.92, lag_hours=0.5, mechanism="hydrological"),
    CausalEdge(source="soil_moisture", target="flood_risk", weight=0.40, lag_hours=0.0, mechanism="hydrological"),
    CausalEdge(source="assam_rainfall", target="assam_brahmaputra", weight=0.80, lag_hours=6.0, mechanism="meteorological"),
    CausalEdge(source="assam_brahmaputra", target="flood_risk", weight=0.85, lag_hours=1.0, mechanism="hydrological"),
]


def build_default_dag() -> CausalDAG:
    """Return the hard-coded default DAG."""
    # wire up parent/child lists
    child_map: dict[str, list[str]] = {}
    parent_map: dict[str, list[str]] = {}
    for e in _DEFAULT_EDGES:
        child_map.setdefault(e.source, []).append(e.target)
        parent_map.setdefault(e.target, []).append(e.source)
    for n in _DEFAULT_NODES:
        n.parents = parent_map.get(n.node_id, [])
        n.children = child_map.get(n.node_id, [])
    return CausalDAG(nodes=_DEFAULT_NODES, edges=_DEFAULT_EDGES)


def load_dag(path: str | Path | None = None) -> CausalDAG:
    """Load DAG from JSON file, falling back to the default."""
    if path and Path(path).exists():
        raw = json.loads(Path(path).read_text())
        return CausalDAG(**raw)
    return build_default_dag()


def save_dag(dag: CausalDAG, path: str | Path) -> None:
    """Persist DAG as JSON."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dag.model_dump_json(indent=2))
