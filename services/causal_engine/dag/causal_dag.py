"""CausalDAGManager — Phase 2 enhanced DAG manager.

Manages basin-specific causal directed acyclic graphs with support for
loading from config files, extracting intervention nodes, and
providing DAG structure for the dashboard.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from shared.models.phase2 import (
    CausalDAG,
    CausalEdge,
    CausalNode,
    CausalNodeType,
    CausalRiskResponse,
    DAGStructureResponse,
    InterventionOption,
)

logger = structlog.get_logger(__name__)


class CausalDAGManager:
    """Manages a causal DAG for a specific river basin.

    Provides helpers used by the Phase 2 GNN inference and
    interventional engine.
    """

    def __init__(self, basin_id: str = "brahmaputra_upper"):
        self.basin_id = basin_id
        self.dag_model: Optional[CausalDAG] = None
        self._adjacency: Dict[str, Dict[str, float]] = {}
        logger.info("dag_manager_created", basin_id=basin_id)

    # ── Loading helpers ──────────────────────────────────────────────────

    def load_from_config(self, config_path: str) -> None:
        """Load DAG from a JSON config file.

        Raises ``FileNotFoundError`` when the file does not exist.
        """
        p = Path(config_path)
        if not p.exists():
            raise FileNotFoundError(f"DAG config not found: {config_path}")

        data = json.loads(p.read_text())
        self.dag_model = CausalDAG(**data)
        self._build_adjacency()
        logger.info(
            "dag_loaded_from_config",
            path=config_path,
            nodes=len(self.dag_model.nodes),
            edges=len(self.dag_model.edges),
        )

    def load_from_model(self, dag: CausalDAG) -> None:
        """Adopt an existing ``CausalDAG`` pydantic model."""
        self.dag_model = dag
        self._build_adjacency()
        logger.info(
            "dag_loaded_from_model",
            nodes=len(self.dag_model.nodes),
            edges=len(self.dag_model.edges),
        )

    # ── Graph queries ────────────────────────────────────────────────────

    @property
    def nodes(self) -> List[CausalNode]:
        return self.dag_model.nodes if self.dag_model else []

    @property
    def edges(self) -> List[CausalEdge]:
        return self.dag_model.edges if self.dag_model else []

    @property
    def node_ids(self) -> List[str]:
        return [n.node_id for n in self.nodes]

    def get_node(self, node_id: str) -> Optional[CausalNode]:
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        return None

    def _build_adjacency(self) -> None:
        self._adjacency = {}
        for edge in self.edges:
            self._adjacency.setdefault(edge.source, {})[edge.target] = edge.weight

    def get_adjacency(self) -> Dict[str, Dict[str, float]]:
        return dict(self._adjacency)

    # ── Intervention helpers ─────────────────────────────────────────────

    def intervention_nodes(self) -> List[CausalNode]:
        """Return all nodes of type INTERVENTION."""
        return [n for n in self.nodes if n.node_type == CausalNodeType.INTERVENTION]

    def outcome_nodes(self) -> List[CausalNode]:
        """Return all nodes of type OUTCOME."""
        return [n for n in self.nodes if n.node_type == CausalNodeType.OUTCOME]

    def get_intervention_options(self) -> List[InterventionOption]:
        """Return structured intervention options for the API."""
        options: List[InterventionOption] = []
        for n in self.intervention_nodes():
            options.append(
                InterventionOption(
                    variable=n.variable,
                    node_type=n.node_type.value,
                    unit=n.unit or "",
                    min_value=n.min_value if n.min_value is not None else 0.0,
                    max_value=n.max_value if n.max_value is not None else 1.0,
                    default_value=n.default_value,
                    description=n.structural_eq or f"Intervention on {n.variable}",
                )
            )
        return options

    # ── Dashboard helpers ────────────────────────────────────────────────

    def get_dag_structure(self) -> DAGStructureResponse:
        """Return the DAG in the format expected by the dashboard."""
        return DAGStructureResponse(
            basin_id=self.basin_id,
            nodes=[
                {
                    "node_id": n.node_id,
                    "variable": n.variable,
                    "node_type": n.node_type.value,
                    "unit": n.unit or "",
                    "default_value": n.default_value,
                }
                for n in self.nodes
            ],
            edges=[
                {
                    "source": e.source,
                    "target": e.target,
                    "weight": e.weight,
                    "lag_hours": e.lag_hours,
                    "mechanism": e.mechanism or "",
                }
                for e in self.edges
            ],
            intervention_nodes=[n.node_id for n in self.intervention_nodes()],
            outcome_nodes=[n.node_id for n in self.outcome_nodes()],
        )

    def compute_risk_score(
        self,
        node_values: Optional[Dict[str, float]] = None,
    ) -> CausalRiskResponse:
        """Compute a heuristic causal risk score for the basin.

        In production this would be driven by real-time GNN output;
        here we return a plausible demo value.
        """
        values = node_values or {}
        # Simple heuristic: weighted average of outcome node values
        outcome_vals = [values.get(n.node_id, n.default_value) for n in self.outcome_nodes()]
        score = sum(outcome_vals) / max(len(outcome_vals), 1)
        score = max(0.0, min(1.0, score))

        if score >= 0.75:
            level = "CRITICAL"
        elif score >= 0.5:
            level = "HIGH"
        elif score >= 0.25:
            level = "MODERATE"
        else:
            level = "LOW"

        return CausalRiskResponse(
            basin_id=self.basin_id,
            causal_risk_score=round(score, 4),
            risk_level=level,
            top_contributing_nodes=[
                {"node_id": n.node_id, "value": values.get(n.node_id, n.default_value)}
                for n in self.outcome_nodes()
            ],
            node_contributions=values,
        )
