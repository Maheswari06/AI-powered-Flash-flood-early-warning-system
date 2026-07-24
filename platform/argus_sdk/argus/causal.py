"""
ARGUS SDK — Causal Inference Client

Provides programmatic access to the ARGUS Causal Engine API.
Enables "what-if" interventional queries and counterfactual analysis.

Usage:
    from argus import CausalClient

    client = CausalClient("https://argus.my-deployment.org")

    # What happens if we open the dam gate to 80%?
    result = client.intervention(
        variable="dam_gate_opening",
        value=0.8,
        outcome="downstream_flood_depth"
    )
    print(f"Expected flood depth: {result['expected_outcome']}m")
    print(f"Confidence interval: [{result['ci_lower']}, {result['ci_upper']}]m")
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class CausalClient:
    """
    Client for the ARGUS Causal Engine API.
    Supports interventional (do-calculus) and counterfactual queries.
    """

    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=60.0,  # Causal queries can be slow
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )

    def intervention(
        self,
        variable: str,
        value: float,
        outcome: str = "flood_depth",
        n_samples: int = 200,
    ) -> Dict[str, Any]:
        """
        Compute P(outcome | do(variable = value)) using the backdoor adjustment.

        This is NOT correlation — it's causal intervention.
        "What would flood depth be IF we SET dam_gate to 80%?"

        Args:
            variable: Intervention variable (e.g., "dam_gate_opening")
            value: Value to set (e.g., 0.8 for 80% open)
            outcome: Outcome variable to predict (default: "flood_depth")
            n_samples: Monte Carlo samples for uncertainty (default: 200)

        Returns:
            Dict with expected_outcome, ci_lower, ci_upper, counterfactual_delta
        """
        r = self._client.post(
            "/api/v1/causal/intervention",
            json={
                "variable": variable,
                "value": value,
                "outcome": outcome,
                "n_samples": n_samples,
            },
        )
        r.raise_for_status()
        return r.json()

    def counterfactual(
        self,
        event_id: str,
        changes: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Counterfactual analysis: "Would the flood have been prevented
        IF the dam gate had been opened 2 hours earlier?"

        Args:
            event_id: Historical flood event to analyze
            changes: Variables to counterfactually change
                     (e.g., {"dam_gate_opening": 0.8, "gate_open_time": -120})

        Returns:
            Dict with original_outcome, counterfactual_outcome, delta, confidence
        """
        r = self._client.post(
            "/api/v1/causal/counterfactual",
            json={"event_id": event_id, "changes": changes},
        )
        r.raise_for_status()
        return r.json()

    def get_dag(self) -> Dict[str, Any]:
        """
        Get the current causal DAG structure.

        Returns:
            Dict with nodes, edges, intervention_points
        """
        r = self._client.get("/api/v1/causal/dag")
        r.raise_for_status()
        return r.json()

    def get_intervention_options(self) -> List[Dict[str, Any]]:
        """
        Get available intervention variables and their valid ranges.

        Returns:
            List of dicts with variable, description, min_value, max_value
        """
        r = self._client.get("/api/v1/causal/intervention/options")
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
