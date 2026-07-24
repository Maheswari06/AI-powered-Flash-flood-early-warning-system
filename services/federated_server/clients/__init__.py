"""Federated Learning client — runs as each "node" (state/country).

Each node trains on LOCAL data only and shares only gradient updates
(model weight deltas) — never raw sensor data.

For the hackathon: all 3 nodes are simulated locally with different
synthetic datasets. This is standard FL demo practice.

Nodes:
  - Assam (Brahmaputra basin — monsoon-heavy, large flood events)
  - Himachal Pradesh (Beas basin — mountain flash floods, dam releases)
  - Bangladesh (cross-border delta — tidal + upstream flooding)
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# Try to import Flower
try:
    import flwr as fl  # type: ignore[import-untyped]
    _FLOWER_AVAILABLE = True
except ImportError:
    fl = None
    _FLOWER_AVAILABLE = False
    logger.warning("flwr_not_available", hint="pip install flwr")


# ── Simple neural network for federated training ────────────────────
class FloodMLP:
    """Lightweight MLP for flood prediction (federated-trainable).

    Architecture: input(16) → hidden(32) → hidden(32) → output(1)
    Uses only NumPy — no PyTorch dependency required.
    """

    def __init__(self, n_features: int = 16, hidden: int = 32, lr: float = 0.01):
        self.lr = lr
        np.random.seed(42)
        # Xavier initialization
        self.weights = {
            "W1": np.random.randn(n_features, hidden).astype(np.float32) * np.sqrt(2.0 / n_features),
            "b1": np.zeros(hidden, dtype=np.float32),
            "W2": np.random.randn(hidden, hidden).astype(np.float32) * np.sqrt(2.0 / hidden),
            "b2": np.zeros(hidden, dtype=np.float32),
            "W3": np.random.randn(hidden, 1).astype(np.float32) * np.sqrt(2.0 / hidden),
            "b3": np.zeros(1, dtype=np.float32),
        }

    def get_weights(self) -> List[np.ndarray]:
        """Return model weights as a flat list of numpy arrays."""
        return [self.weights[k] for k in sorted(self.weights.keys())]

    def set_weights(self, params: List[np.ndarray]) -> None:
        """Set model weights from a flat list."""
        for i, k in enumerate(sorted(self.weights.keys())):
            self.weights[k] = params[i].astype(np.float32)

    def forward(self, X: np.ndarray) -> np.ndarray:
        """Forward pass with ReLU activations and sigmoid output."""
        h1 = np.maximum(0, X @ self.weights["W1"] + self.weights["b1"])  # ReLU
        h2 = np.maximum(0, h1 @ self.weights["W2"] + self.weights["b2"])  # ReLU
        out = h2 @ self.weights["W3"] + self.weights["b3"]
        return 1.0 / (1.0 + np.exp(-np.clip(out, -500, 500)))  # Sigmoid

    def train(self, X: np.ndarray, y: np.ndarray, epochs: int = 5) -> float:
        """Train for a few epochs and return final loss."""
        n = len(X)
        total_loss = 0.0
        for epoch in range(epochs):
            # Forward
            h1 = np.maximum(0, X @ self.weights["W1"] + self.weights["b1"])
            h2 = np.maximum(0, h1 @ self.weights["W2"] + self.weights["b2"])
            out = h2 @ self.weights["W3"] + self.weights["b3"]
            pred = 1.0 / (1.0 + np.exp(-np.clip(out, -500, 500)))

            # Binary cross-entropy loss
            eps = 1e-7
            loss = -np.mean(y * np.log(pred + eps) + (1 - y) * np.log(1 - pred + eps))

            # Backward (simplified gradient computation)
            d_out = (pred - y) / n
            d_W3 = h2.T @ d_out
            d_b3 = d_out.sum(axis=0)

            d_h2 = d_out @ self.weights["W3"].T
            d_h2[h2 <= 0] = 0  # ReLU gradient

            d_W2 = h1.T @ d_h2
            d_b2 = d_h2.sum(axis=0)

            d_h1 = d_h2 @ self.weights["W2"].T
            d_h1[h1 <= 0] = 0

            d_W1 = X.T @ d_h1
            d_b1 = d_h1.sum(axis=0)

            # Update weights
            self.weights["W1"] -= self.lr * d_W1
            self.weights["b1"] -= self.lr * d_b1
            self.weights["W2"] -= self.lr * d_W2
            self.weights["b2"] -= self.lr * d_b2
            self.weights["W3"] -= self.lr * d_W3
            self.weights["b3"] -= self.lr * d_b3

            total_loss = float(loss)

        return total_loss

    def evaluate(self, X: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
        """Evaluate and return (loss, accuracy)."""
        pred = self.forward(X)
        eps = 1e-7
        loss = -np.mean(y * np.log(pred + eps) + (1 - y) * np.log(1 - pred + eps))
        acc = np.mean((pred > 0.5).astype(float) == y)
        return float(loss), float(acc)


# ── Synthetic data generation per region ──────────────────────────────

def generate_synthetic_data(
    node_id: str, n_samples: int = 500, n_features: int = 16
) -> Tuple[np.ndarray, np.ndarray]:
    """Generate region-specific synthetic flood data.

    Different regions have different flood patterns:
    - Assam: high rainfall, river discharge dominant
    - Himachal: elevation + snowmelt + dam release dominant
    - Bangladesh: tidal surge + upstream discharge
    """
    seed_map = {"assam": 42, "himachal": 123, "bangladesh": 456}
    np.random.seed(seed_map.get(node_id, 0))

    X = np.random.randn(n_samples, n_features).astype(np.float32)

    if node_id == "assam":
        # Rainfall (col 0) and river discharge (col 1) are dominant
        y = ((X[:, 0] * 0.5 + X[:, 1] * 0.4 + X[:, 2] * 0.1 + np.random.randn(n_samples) * 0.3) > 0.3).astype(np.float32).reshape(-1, 1)
    elif node_id == "himachal":
        # Elevation (col 3) and dam release (col 4) are dominant
        y = ((X[:, 3] * 0.3 + X[:, 4] * 0.4 + X[:, 0] * 0.2 + np.random.randn(n_samples) * 0.25) > 0.2).astype(np.float32).reshape(-1, 1)
    elif node_id == "bangladesh":
        # Tidal (col 5) + upstream discharge (col 1) + rain (col 0)
        y = ((X[:, 5] * 0.3 + X[:, 1] * 0.3 + X[:, 0] * 0.3 + np.random.randn(n_samples) * 0.2) > 0.25).astype(np.float32).reshape(-1, 1)
    else:
        y = ((X.mean(axis=1) + np.random.randn(n_samples) * 0.3) > 0.0).astype(np.float32).reshape(-1, 1)

    return X, y


# ── Flower client (when flwr is available) ───────────────────────────

if _FLOWER_AVAILABLE:
    class ARGUSFederatedClient(fl.client.NumPyClient):
        """Flower federated learning client for ARGUS.

        Each state/country node runs this client.
        Trains on LOCAL data only.
        Shares only model weight updates — never raw data.
        """

        def __init__(self, node_id: str, local_data_path: Optional[str] = None):
            self.node_id = node_id
            self.model = FloodMLP()
            self.X, self.y = generate_synthetic_data(node_id)
            logger.info("fl_client_init", node=node_id, samples=len(self.X))

        def get_parameters(self, config) -> List[np.ndarray]:
            return self.model.get_weights()

        def fit(self, parameters, config) -> Tuple[List[np.ndarray], int, Dict]:
            self.model.set_weights(parameters)
            loss = self.model.train(self.X, self.y, epochs=5)
            return self.model.get_weights(), len(self.X), {"loss": float(loss), "node": self.node_id}

        def evaluate(self, parameters, config) -> Tuple[float, int, Dict]:
            self.model.set_weights(parameters)
            loss, accuracy = self.model.evaluate(self.X, self.y)
            return float(loss), len(self.X), {"accuracy": float(accuracy), "node": self.node_id}
