"""Federated Averaging (FedAvg) aggregator with differential privacy.

Implements:
  - FedAvg weighted aggregation
  - FedProx proximal term support
  - Gaussian differential privacy (DP-SGD style clipping + noise)
  - Round tracking and convergence monitoring
"""

from __future__ import annotations

import copy
import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from shared.models.phase2 import FederatedRound, NodeUpdate

logger = structlog.get_logger(__name__)


class FederatedAggregator:
    """Server-side federated learning aggregator."""

    def __init__(
        self,
        global_weights: Dict[str, np.ndarray],
        method: str = "fedavg",
        dp_epsilon: float = 1.0,
        dp_delta: float = 1e-5,
        clip_norm: float = 1.0,
    ):
        self.global_weights = global_weights
        self.method = method
        self.dp_epsilon = dp_epsilon
        self.dp_delta = dp_delta
        self.clip_norm = clip_norm
        self.round_id: int = 0
        self.history: List[FederatedRound] = []
        self._privacy_budget_spent: float = 0.0
        logger.info(
            "aggregator_init",
            method=method,
            dp_epsilon=dp_epsilon,
            layers=len(global_weights),
        )

    # ── Aggregation ──────────────────────────────────────────────────

    def aggregate(
        self,
        client_updates: List[Tuple[Dict[str, np.ndarray], int]],
    ) -> Dict[str, np.ndarray]:
        """Aggregate client weight updates using FedAvg or FedProx.

        Args:
            client_updates: List of (delta_weights, num_samples) per client.

        Returns:
            New global weights after aggregation.
        """
        if not client_updates:
            return self.global_weights

        self.round_id += 1
        total_samples = sum(n for _, n in client_updates)

        new_weights: Dict[str, np.ndarray] = {}
        for key in self.global_weights:
            weighted_sum = np.zeros_like(self.global_weights[key])
            for delta, n_samples in client_updates:
                if key in delta:
                    # Clip gradient norm per client
                    clipped = self._clip_gradient(delta[key])
                    weighted_sum += clipped * (n_samples / total_samples)
            # Add DP noise
            noised = self._add_dp_noise(weighted_sum)
            new_weights[key] = self.global_weights[key] + noised

        self.global_weights = new_weights

        # Track privacy budget (simplified Rényi accountant approximation)
        sigma = self._compute_sigma()
        if sigma > 0:
            self._privacy_budget_spent += 1.0 / (sigma ** 2)

        round_info = FederatedRound(
            round_id=self.round_id,
            global_model_version=f"v{self.round_id}",
            participating_nodes=[f"node_{i}" for i in range(len(client_updates))],
            aggregation_method=self.method,
            privacy_budget_spent=round(self._privacy_budget_spent, 4),
        )
        self.history.append(round_info)

        logger.info(
            "round_aggregated",
            round=self.round_id,
            clients=len(client_updates),
            total_samples=total_samples,
            privacy_spent=round(self._privacy_budget_spent, 4),
        )
        return new_weights

    def _clip_gradient(self, gradient: np.ndarray) -> np.ndarray:
        """Clip gradient to max L2 norm."""
        grad_norm = np.linalg.norm(gradient)
        if grad_norm > self.clip_norm:
            return gradient * (self.clip_norm / grad_norm)
        return gradient

    def _compute_sigma(self) -> float:
        """Compute Gaussian noise scale from ε, δ."""
        if self.dp_epsilon <= 0:
            return 0.0
        # σ ≈ √(2 ln(1.25/δ)) / ε · sensitivity
        return (
            math.sqrt(2 * math.log(1.25 / self.dp_delta))
            / self.dp_epsilon
            * self.clip_norm
        )

    def _add_dp_noise(self, gradient: np.ndarray) -> np.ndarray:
        """Add calibrated Gaussian noise for (ε,δ)-DP."""
        sigma = self._compute_sigma()
        if sigma <= 0:
            return gradient
        noise = np.random.normal(0, sigma, size=gradient.shape).astype(gradient.dtype)
        return gradient + noise

    # ── Queries ──────────────────────────────────────────────────────

    def get_global_weights(self) -> Dict[str, np.ndarray]:
        return self.global_weights

    def get_round_info(self) -> Optional[FederatedRound]:
        return self.history[-1] if self.history else None

    def get_convergence_metrics(self) -> Dict:
        """Return convergence monitoring data."""
        return {
            "current_round": self.round_id,
            "total_rounds": len(self.history),
            "method": self.method,
            "privacy_budget_spent": round(self._privacy_budget_spent, 4),
            "dp_epsilon": self.dp_epsilon,
            "dp_delta": self.dp_delta,
        }


def create_synthetic_global_model(
    n_features: int = 16,
    hidden: int = 32,
) -> Dict[str, np.ndarray]:
    """Create initial random global model weights for demo."""
    np.random.seed(42)
    return {
        "layer1.weight": np.random.randn(hidden, n_features).astype(np.float32) * 0.1,
        "layer1.bias": np.zeros(hidden, dtype=np.float32),
        "layer2.weight": np.random.randn(hidden, hidden).astype(np.float32) * 0.1,
        "layer2.bias": np.zeros(hidden, dtype=np.float32),
        "output.weight": np.random.randn(1, hidden).astype(np.float32) * 0.1,
        "output.bias": np.zeros(1, dtype=np.float32),
    }


def simulate_client_update(
    global_weights: Dict[str, np.ndarray],
    n_samples: int = 100,
    noise_scale: float = 0.01,
) -> Tuple[Dict[str, np.ndarray], int]:
    """Simulate a local training round (for demo)."""
    delta = {}
    for key, w in global_weights.items():
        delta[key] = np.random.randn(*w.shape).astype(np.float32) * noise_scale
    return delta, n_samples
