"""CausalGNNInference — Phase 2 GNN inference wrapper.

Wraps the legacy CausalGNNEngine with integration to the new
CausalDAGManager for Phase 2 routes.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import structlog

from shared.models.phase2 import CausalDAG
from services.causal_engine.dag.causal_dag import CausalDAGManager
from services.causal_engine.gnn import CausalGNNEngine

logger = structlog.get_logger(__name__)


class CausalGNNInference:
    """Phase 2 GNN inference that delegates to :class:`CausalGNNEngine`.

    Parameters
    ----------
    dag_manager:
        The DAG manager holding the current basin graph.
    model_path:
        Path to the serialised GNN checkpoint (unused in demo mode).
    hidden:
        Hidden dimension for the GCN layers.
    """

    def __init__(
        self,
        dag_manager: CausalDAGManager,
        model_path: str = "",
        hidden: int = 64,
    ):
        self.dag_manager = dag_manager
        self.model_path = model_path
        self.hidden = hidden
        self._engine: Optional[CausalGNNEngine] = None

        # Build the underlying engine if a DAG is already loaded
        if dag_manager.dag_model is not None:
            self._build_engine(dag_manager.dag_model)

    def _build_engine(self, dag: CausalDAG) -> None:
        self._engine = CausalGNNEngine(dag, hidden=self.hidden)
        logger.info("causal_gnn_inference_ready", nodes=len(dag.nodes))

    @property
    def engine(self) -> CausalGNNEngine:
        if self._engine is None:
            dag = self.dag_manager.dag_model
            if dag is None:
                raise RuntimeError("No DAG loaded in CausalDAGManager")
            self._build_engine(dag)
        assert self._engine is not None
        return self._engine

    # ── Public API ───────────────────────────────────────────────────────

    def predict(self, evidence: Dict[str, float]) -> Dict[str, float]:
        """Forward pass through the causal GNN."""
        return self.engine.predict(evidence)

    def intervene(
        self,
        do_var: str,
        do_val: float,
        evidence: Dict[str, float],
        targets: Optional[List[str]] = None,
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        """do(X=x) — returns (original, counterfactual) value dicts."""
        return self.engine.intervene(do_var, do_val, evidence, targets)

    def get_adjacency_dict(self) -> Dict[str, Dict[str, float]]:
        return self.engine.get_adjacency_dict()
