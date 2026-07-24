"""InterventionalEngine — Phase 2 do-calculus engine.

Provides the enhanced intervention query API used by the Phase 2
causal routes (risk scores, intervention simulation, damage-reduction
estimates).
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import structlog

from shared.models.phase2 import (
    CausalNodeType,
    CausalRiskResponse,
    InterventionOption,
    InterventionRequest,
    InterventionResult,
)
from services.causal_engine.dag.causal_dag import CausalDAGManager
from services.causal_engine.inference.causal_gnn import CausalGNNInference

logger = structlog.get_logger(__name__)


class InterventionalEngine:
    """Orchestrates Pearl-style interventions over the causal DAG.

    Combines GNN inference with the DAG structure to produce
    human-readable intervention results including damage-reduction
    estimates and causal pathways.
    """

    def __init__(
        self,
        dag_manager: CausalDAGManager,
        gnn_model: CausalGNNInference,
    ):
        self.dag_manager = dag_manager
        self.gnn = gnn_model
        logger.info("interventional_engine_ready")

    # ── Core API ─────────────────────────────────────────────────────────

    def run_intervention(self, request: InterventionRequest) -> InterventionResult:
        """Execute a do(X=x) intervention and return a rich result."""
        variable = request.effective_variable
        value = request.effective_value
        evidence = dict(request.context)

        # Run GNN forward + counterfactual
        original, counterfactual = self.gnn.intervene(
            do_var=variable,
            do_val=value,
            evidence=evidence,
            targets=request.target_variables or None,
        )

        # Compute causal effects (ATE per target)
        effects: Dict[str, float] = {}
        for k in counterfactual:
            effects[k] = round(counterfactual[k] - original.get(k, 0.0), 6)

        # Derive enhanced fields
        target = request.target_variable
        baseline_depth = original.get(target, 0.0)
        intervened_depth = counterfactual.get(target, 0.0)
        reduction_pct = 0.0
        if baseline_depth > 0:
            reduction_pct = round(
                max(0.0, (baseline_depth - intervened_depth) / baseline_depth) * 100, 1
            )

        confidence = min(1.0, 0.5 + 0.05 * len(evidence))

        # Build causal pathway
        pathway = self._trace_pathway(variable, target)

        recommendation = self._generate_recommendation(
            variable, value, reduction_pct, intervened_depth
        )

        return InterventionResult(
            intervention=request,
            original_values=original,
            counterfactual_values=counterfactual,
            causal_effects=effects,
            baseline_depth_m=round(baseline_depth, 4),
            intervened_depth_m=round(intervened_depth, 4),
            damage_reduction_pct=reduction_pct,
            confidence=round(confidence, 3),
            uncertainty_lower_m=round(intervened_depth * 0.85, 4),
            uncertainty_upper_m=round(intervened_depth * 1.15, 4),
            causal_pathway=pathway,
            recommendation=recommendation,
            time_sensitive_minutes=120,
            time_sensitive_until=datetime.now() + timedelta(minutes=120),
        )

    # ── Risk score ───────────────────────────────────────────────────────

    def compute_risk(
        self,
        basin_id: str,
        observations: Optional[Dict[str, float]] = None,
    ) -> CausalRiskResponse:
        """Compute causal risk score for a basin using GNN predictions."""
        evidence = observations or {}
        predictions = self.gnn.predict(evidence)
        return self.dag_manager.compute_risk_score(predictions)

    # ── Available interventions ──────────────────────────────────────────

    def get_intervention_options(self, basin_id: str) -> List[InterventionOption]:
        return self.dag_manager.get_intervention_options()

    # ── Helpers ──────────────────────────────────────────────────────────

    def _trace_pathway(self, source: str, target: str) -> List[str]:
        """BFS shortest path from *source* to *target* in the DAG."""
        adj = self.dag_manager.get_adjacency()
        visited = {source}
        queue: List[List[str]] = [[source]]
        while queue:
            path = queue.pop(0)
            node = path[-1]
            if node == target:
                return path
            for neighbour in adj.get(node, {}):
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append(path + [neighbour])
        return [source, "...", target]

    @staticmethod
    def _generate_recommendation(
        variable: str, value: float, reduction_pct: float, depth: float
    ) -> str:
        if reduction_pct > 30:
            return (
                f"Strongly recommended: setting {variable}={value:.1f} "
                f"reduces flood depth by {reduction_pct:.0f}%."
            )
        elif reduction_pct > 10:
            return (
                f"Moderately effective: {variable}={value:.1f} "
                f"reduces flood depth by {reduction_pct:.0f}%."
            )
        else:
            return (
                f"Minimal impact: {variable}={value:.1f} reduces depth "
                f"by only {reduction_pct:.0f}%. Consider other interventions."
            )
