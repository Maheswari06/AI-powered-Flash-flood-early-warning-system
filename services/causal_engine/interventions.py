"""Interventional API — do-calculus queries against the causal DAG.

Provides helper functions consumed by the FastAPI endpoints in main.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

import structlog

from shared.models.phase2 import (
    InterventionRequest,
    InterventionResult,
)
from services.causal_engine.gnn import CausalGNNEngine

logger = structlog.get_logger(__name__)


class InterventionAPI:
    """Stateless wrapper around the CausalGNNEngine for intervention queries."""

    def __init__(self, engine: CausalGNNEngine):
        self.engine = engine

    def run(
        self,
        request: InterventionRequest,
    ) -> InterventionResult:
        """Execute a do(X=x) intervention and return causal effects."""
        evidence = dict(request.context)
        original, counterfactual = self.engine.intervene(
            do_var=request.variable,
            do_val=request.value,
            evidence=evidence,
            targets=request.target_variables or None,
        )
        # Average Treatment Effect
        effects: Dict[str, float] = {}
        for k in counterfactual:
            effects[k] = round(counterfactual[k] - original.get(k, 0.0), 6)

        confidence = min(1.0, 0.5 + 0.1 * len(evidence))  # heuristic
        result = InterventionResult(
            intervention=request,
            original_values=original,
            counterfactual_values=counterfactual,
            causal_effects=effects,
            confidence=round(confidence, 3),
        )
        logger.info(
            "intervention_done",
            variable=request.variable,
            value=request.value,
            effects=effects,
        )
        return result

    def batch_interventions(
        self,
        requests: List[InterventionRequest],
    ) -> List[InterventionResult]:
        """Run multiple interventions."""
        return [self.run(r) for r in requests]

    def sensitivity_analysis(
        self,
        variable: str,
        values: List[float],
        target: str,
        context: Dict[str, float],
    ) -> List[Dict]:
        """Sweep a variable across values and observe target response."""
        results = []
        for v in values:
            req = InterventionRequest(
                variable=variable,
                value=v,
                target_variables=[target],
                context=context,
            )
            res = self.run(req)
            results.append({
                "do_value": v,
                "original": res.original_values.get(target, 0.0),
                "counterfactual": res.counterfactual_values.get(target, 0.0),
                "effect": res.causal_effects.get(target, 0.0),
            })
        return results
