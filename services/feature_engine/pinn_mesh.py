"""Physics-Informed Neural Network (PINN) virtual sensor mesh.

Implements a simplified 1-D Saint-Venant shallow-water model:

    Continuity:  ∂A/∂t + ∂Q/∂x = 0

A small PyTorch neural net (3 layers, 64 units) is trained so that
    Loss = data_loss + λ · physics_residual_loss   (λ = 0.1)

At inference time the network interpolates water levels at *M*
virtual locations between real gauges along a river reach.

For demo: loads a pre-trained checkpoint from
    ``./models/pinn_beas_river.pt``
A ``retrain()`` method is available for batch retraining.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from services.feature_engine.schemas import VirtualSensorOutput

logger = structlog.get_logger(__name__)

# ── Attempt to import torch; fall-back gracefully ─────────────────────────
try:
    import torch
    import torch.nn as nn

    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False
    logger.warning("pytorch_not_installed_using_numpy_fallback")


# ── Default virtual sensor locations (Beas-river demo) ────────────────────
_DEFAULT_VIRTUAL_SENSORS: List[Dict] = [
    {"virtual_id": "VIRT-BEAS-001", "lat": 31.69, "lon": 76.99, "x_km": 5.0},
    {"virtual_id": "VIRT-BEAS-002", "lat": 31.68, "lon": 77.02, "x_km": 10.0},
    {"virtual_id": "VIRT-BEAS-003", "lat": 31.72, "lon": 76.75, "x_km": 20.0},
    {"virtual_id": "VIRT-BEAS-004", "lat": 31.75, "lon": 76.55, "x_km": 35.0},
    {"virtual_id": "VIRT-BEAS-005", "lat": 31.85, "lon": 76.25, "x_km": 55.0},
]

# Physics constant
_LAMBDA_PHYSICS = 0.1  # Weight of physics residual loss
_GRAVITY = 9.81
_CHANNEL_WIDTH_M = 50.0  # Approximate channel width for A = W * h


# ═══════════════════════════════════════════════════════════════════════════
# PyTorch PINN model
# ═══════════════════════════════════════════════════════════════════════════

if _TORCH_AVAILABLE:

    class SaintVenantPINN(nn.Module):
        """Small feed-forward net enforcing Saint-Venant continuity.

        Input:  (x_normalised, t_normalised)   — spatial position + time
        Output: (h_predicted,)                  — water level
        """

        def __init__(self, hidden: int = 64) -> None:
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(2, hidden),
                nn.Tanh(),
                nn.Linear(hidden, hidden),
                nn.Tanh(),
                nn.Linear(hidden, hidden),
                nn.Tanh(),
                nn.Linear(hidden, 1),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:  # type: ignore[override]
            """Forward pass.  x shape: (N, 2) → output: (N, 1)."""
            return self.net(x)

else:
    # Stub so the rest of the module can reference the class
    class SaintVenantPINN:  # type: ignore[no-redef]
        pass


# ═══════════════════════════════════════════════════════════════════════════
# PINN Mesh Manager
# ═══════════════════════════════════════════════════════════════════════════


class PINNMesh:
    """Manages the PINN virtual-sensor mesh.

    Usage::

        mesh = PINNMesh()
        mesh.load_checkpoint("./models/pinn_beas_river.pt")
        outputs = mesh.interpolate(gauge_readings, timestamp)
    """

    def __init__(
        self,
        virtual_sensors: Optional[List[Dict]] = None,
        checkpoint_path: Optional[str] = None,
        reach_length_km: float = 70.0,
    ) -> None:
        self.virtual_sensors = virtual_sensors or _DEFAULT_VIRTUAL_SENSORS
        self.reach_length_km = reach_length_km
        self._model: Optional[SaintVenantPINN] = None  # type: ignore[annotation-unchecked]

        if checkpoint_path:
            self.load_checkpoint(checkpoint_path)

    # ── checkpoint I/O ─────────────────────────────────────────────────

    def load_checkpoint(self, path: str) -> None:
        """Load a pre-trained PINN checkpoint from disk."""
        p = Path(path)
        if not _TORCH_AVAILABLE:
            logger.warning("pinn_skip_load_no_torch", path=path)
            return
        if not p.exists():
            logger.warning("pinn_checkpoint_not_found", path=path)
            return

        self._model = SaintVenantPINN()
        try:
            state = torch.load(p, map_location="cpu", weights_only=True)
            self._model.load_state_dict(state)
            self._model.eval()
            logger.info("pinn_checkpoint_loaded", path=path)
        except RuntimeError as exc:
            logger.error(
                "pinn_checkpoint_load_failed",
                path=path,
                error=str(exc),
                hint="Architecture mismatch — falling back to NumPy IDW mode",
            )
            self._model = None

    # ── inference ──────────────────────────────────────────────────────

    def interpolate(
        self,
        gauge_readings: Dict[str, float],
        gauge_positions_km: Dict[str, float],
        timestamp: datetime,
    ) -> List[VirtualSensorOutput]:
        """Interpolate water levels at virtual sensor locations.

        Args:
            gauge_readings:     station_id → water_level_m for real gauges.
            gauge_positions_km: station_id → distance along reach (km).
            timestamp:          Current observation timestamp.

        Returns:
            List of VirtualSensorOutput for each virtual location.
        """
        if self._model is not None and _TORCH_AVAILABLE:
            return self._interpolate_pinn(gauge_readings, gauge_positions_km, timestamp)
        return self._interpolate_numpy(gauge_readings, gauge_positions_km, timestamp)

    # ── PINN-based interpolation ───────────────────────────────────────

    def _interpolate_pinn(
        self,
        gauge_readings: Dict[str, float],
        gauge_positions_km: Dict[str, float],
        timestamp: datetime,
    ) -> List[VirtualSensorOutput]:
        """Use the loaded PyTorch PINN for interpolation."""
        assert self._model is not None

        # Normalise time to [0, 1] — use hour-of-day / 24 as proxy
        t_norm = timestamp.hour / 24.0

        results: List[VirtualSensorOutput] = []
        contributing = list(gauge_readings.keys())

        with torch.no_grad():
            for vs in self.virtual_sensors:
                x_norm = vs["x_km"] / self.reach_length_km
                inp = torch.tensor([[x_norm, t_norm]], dtype=torch.float32)
                h_pred = float(self._model(inp).item())

                # Uncertainty from ensemble spread — approximate via
                # distance to nearest real gauge
                uncertainty = self._estimate_uncertainty(
                    vs["x_km"], gauge_positions_km, gauge_readings,
                )

                results.append(VirtualSensorOutput(
                    virtual_id=vs["virtual_id"],
                    timestamp=timestamp,
                    lat=vs["lat"],
                    lon=vs["lon"],
                    predicted_level_m=round(h_pred, 3),
                    uncertainty_m=round(uncertainty, 3),
                    physics_residual=None,  # Would need autograd for real residual
                    contributing_gauges=contributing,
                ))

        logger.info("pinn_interpolation_done", n_virtual=len(results), method="pytorch")
        return results

    # ── NumPy fallback (IDW + physics correction) ──────────────────────

    def _interpolate_numpy(
        self,
        gauge_readings: Dict[str, float],
        gauge_positions_km: Dict[str, float],
        timestamp: datetime,
    ) -> List[VirtualSensorOutput]:
        """Inverse-distance-weighted interpolation with a basic
        Saint-Venant continuity correction as NumPy fallback."""
        if not gauge_readings:
            return []

        # Sort real gauges by position
        sorted_gauges = sorted(gauge_positions_km.items(), key=lambda kv: kv[1])
        positions = np.array([p for _, p in sorted_gauges])
        levels = np.array([gauge_readings[sid] for sid, _ in sorted_gauges])
        contributing = [sid for sid, _ in sorted_gauges]

        results: List[VirtualSensorOutput] = []

        for vs in self.virtual_sensors:
            x_v = vs["x_km"]

            # Inverse-distance weighting
            dists = np.abs(positions - x_v)
            dists = np.clip(dists, 0.1, None)  # avoid /0
            weights = 1.0 / dists
            weights /= weights.sum()
            h_idw = float(np.dot(weights, levels))

            # Simple continuity correction: if upstream level is higher,
            # apply a small gradient-based adjustment
            # dh/dx ≈ (h_downstream - h_upstream) / Δx
            if len(levels) >= 2:
                grad = np.gradient(levels, positions)
                # Interpolate gradient at virtual location
                grad_at_v = float(np.interp(x_v, positions, grad))
                # Continuity residual ≈ dA/dt + W * dh/dx ≈ physics residual
                physics_residual = abs(grad_at_v * _CHANNEL_WIDTH_M)
            else:
                grad_at_v = 0.0
                physics_residual = 0.0

            # Nudge level by physics correction
            h_corrected = h_idw - _LAMBDA_PHYSICS * grad_at_v

            uncertainty = self._estimate_uncertainty(x_v, gauge_positions_km, gauge_readings)

            results.append(VirtualSensorOutput(
                virtual_id=vs["virtual_id"],
                timestamp=timestamp,
                lat=vs["lat"],
                lon=vs["lon"],
                predicted_level_m=round(h_corrected, 3),
                uncertainty_m=round(uncertainty, 3),
                physics_residual=round(physics_residual, 4),
                contributing_gauges=contributing,
            ))

        logger.info("pinn_interpolation_done", n_virtual=len(results), method="numpy_fallback")
        return results

    # ── uncertainty heuristic ──────────────────────────────────────────

    @staticmethod
    def _estimate_uncertainty(
        x_km: float,
        gauge_positions_km: Dict[str, float],
        gauge_readings: Dict[str, float],
    ) -> float:
        """Heuristic uncertainty: grows with distance to nearest real gauge."""
        if not gauge_positions_km:
            return 1.0
        positions = np.array(list(gauge_positions_km.values()))
        min_dist = float(np.min(np.abs(positions - x_km)))
        # Base uncertainty 0.1 m + 0.02 m per km from nearest gauge
        return 0.1 + 0.02 * min_dist

    # ── batch retraining ───────────────────────────────────────────────

    def retrain(
        self,
        training_data: List[Tuple[float, float, float]],
        epochs: int = 500,
        lr: float = 1e-3,
        save_path: Optional[str] = None,
    ) -> Dict[str, float]:
        """Re-train the PINN on historical data (batch job, not real-time).

        Args:
            training_data: List of (x_km, t_normalised, h_observed) tuples.
            epochs: Training epochs.
            lr: Learning rate.
            save_path: If set, save the checkpoint here.

        Returns:
            Dictionary with final loss values.
        """
        if not _TORCH_AVAILABLE:
            logger.error("retrain_requires_pytorch")
            return {"error": "pytorch_not_installed"}

        model = SaintVenantPINN()
        optimiser = torch.optim.Adam(model.parameters(), lr=lr)

        # Prepare tensors
        data = np.array(training_data, dtype=np.float32)
        x_t = torch.tensor(data[:, :2], requires_grad=True)
        h_obs = torch.tensor(data[:, 2:3])

        # Normalise spatial coordinate
        x_t_norm = x_t.clone()
        x_t_norm[:, 0] = x_t_norm[:, 0] / self.reach_length_km

        logger.info("pinn_retrain_start", n_samples=len(training_data), epochs=epochs)

        final_losses: Dict[str, float] = {}

        for epoch in range(epochs):
            optimiser.zero_grad()

            h_pred = model(x_t_norm)

            # ── Data loss ────────────────────────────────
            data_loss = torch.mean((h_pred - h_obs) ** 2)

            # ── Physics loss: continuity ∂A/∂t + ∂Q/∂x = 0
            # A ≈ W·h, Q ≈ W·h·v  →  simplified: W·∂h/∂t + ∂(W·h·v)/∂x ≈ 0
            # Using autograd to get ∂h/∂x and ∂h/∂t
            grads = torch.autograd.grad(
                h_pred.sum(), x_t_norm,
                create_graph=True, retain_graph=True,
            )[0]
            dh_dx = grads[:, 0:1]  # ∂h/∂x
            dh_dt = grads[:, 1:2]  # ∂h/∂t

            # Continuity residual: ∂h/∂t + c·∂h/∂x ≈ 0
            # where c is a characteristic wave speed (simplified)
            c = torch.sqrt(torch.tensor(_GRAVITY) * torch.abs(h_pred).detach() + 1e-6)
            physics_residual = dh_dt + c * dh_dx
            physics_loss = torch.mean(physics_residual ** 2)

            loss = data_loss + _LAMBDA_PHYSICS * physics_loss
            loss.backward()
            optimiser.step()

            if (epoch + 1) % 100 == 0 or epoch == 0:
                logger.info(
                    "pinn_train_epoch",
                    epoch=epoch + 1,
                    data_loss=round(data_loss.item(), 6),
                    physics_loss=round(physics_loss.item(), 6),
                    total_loss=round(loss.item(), 6),
                )

        final_losses = {
            "data_loss": round(data_loss.item(), 6),
            "physics_loss": round(physics_loss.item(), 6),
            "total_loss": round(loss.item(), 6),
        }

        # Save checkpoint
        if save_path:
            torch.save(model.state_dict(), save_path)
            logger.info("pinn_checkpoint_saved", path=save_path)

        self._model = model
        self._model.eval()
        return final_losses
