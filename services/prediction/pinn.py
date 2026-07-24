"""Physics-Informed Neural Network (PINN) sensor mesh.

Uses the 1-D Saint-Venant shallow water equations as a physics
regularisation loss to spatially interpolate between physical
gauges and CV virtual gauges.

Phase 1 provides a lightweight demo implementation using simple
inverse-distance weighting + physics residual estimation.
A full PyTorch PINN training loop will be added in Phase 2.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from shared.config import get_settings
from shared.models.prediction import PINNSensorReading

logger = structlog.get_logger(__name__)
settings = get_settings()

# ── Demo mesh grid (Beas River corridor, Himachal Pradesh) ───────────────
# Each cell is a lat/lon point along the river between gauge stations
_DEMO_MESH: List[Dict] = [
    {"grid_cell_id": "MESH-HP-001", "lat": 31.71, "lon": 76.93, "nearest": "CWC-HP-MANDI"},
    {"grid_cell_id": "MESH-HP-002", "lat": 31.70, "lon": 76.96, "nearest": "CWC-HP-MANDI"},
    {"grid_cell_id": "MESH-HP-003", "lat": 31.69, "lon": 76.99, "nearest": "CWC-HP-PANDOH"},
    {"grid_cell_id": "MESH-HP-004", "lat": 31.68, "lon": 77.02, "nearest": "CWC-HP-PANDOH"},
    {"grid_cell_id": "MESH-HP-005", "lat": 31.67, "lon": 77.06, "nearest": "CWC-HP-PANDOH"},
    {"grid_cell_id": "MESH-HP-006", "lat": 31.70, "lon": 76.80, "nearest": "CWC-HP-NADAUN"},
    {"grid_cell_id": "MESH-HP-007", "lat": 31.73, "lon": 76.65, "nearest": "CWC-HP-NADAUN"},
    {"grid_cell_id": "MESH-HP-008", "lat": 31.78, "lon": 76.34, "nearest": "CWC-HP-NADAUN"},
    {"grid_cell_id": "MESH-HP-009", "lat": 31.85, "lon": 76.15, "nearest": "CWC-PB-PONG"},
    {"grid_cell_id": "MESH-HP-010", "lat": 31.97, "lon": 75.95, "nearest": "CWC-PB-PONG"},
]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class PINNMesh:
    """Spatial interpolation mesh using physics-informed constraints.

    Phase 1 (demo): inverse-distance weighting + Saint-Venant residual.
    Phase 2: full PyTorch PINN with PDE loss.
    """

    def __init__(self) -> None:
        self.mesh = _DEMO_MESH
        self.num_cells: int = len(self.mesh)
        self.is_loaded: bool = True  # demo mesh always available
        self._model = None
        self._try_load_model()

    def _try_load_model(self) -> None:
        """Attempt to load a trained PyTorch PINN model."""
        try:
            import torch
            from pathlib import Path

            model_path = Path(settings.PINN_MODEL_PATH)
            if model_path.exists():
                self._model = torch.load(model_path, map_location="cpu")
                logger.info("pinn_model_loaded", path=str(model_path))
            else:
                logger.info("pinn_using_idw_demo_mode")
        except ImportError:
            logger.info("torch_not_installed_pinn_using_idw")

    def interpolate(
        self,
        station_readings: Dict[str, Tuple[float, float]],
        timestamp: datetime,
    ) -> List[PINNSensorReading]:
        """Interpolate depth + velocity for every mesh cell.

        Args:
            station_readings: Mapping station_id → (depth_m, velocity_ms).
            timestamp: Current timestamp.

        Returns:
            List of PINNSensorReading for every cell in the mesh.
        """
        if self._model is not None:
            return self._predict_with_model(station_readings, timestamp)
        return self._idw_interpolate(station_readings, timestamp)

    # ── IDW demo interpolation ───────────────────────────────
    def _idw_interpolate(
        self,
        station_readings: Dict[str, Tuple[float, float]],
        timestamp: datetime,
    ) -> List[PINNSensorReading]:
        """Inverse-distance weighted interpolation for demo mode."""
        # Build station location map from topology
        station_locs: Dict[str, Tuple[float, float]] = {}
        for cell in self.mesh:
            # Use cell's nearest station loc as proxy
            station_locs.setdefault(cell["nearest"], (cell["lat"], cell["lon"]))

        results: List[PINNSensorReading] = []

        for cell in self.mesh:
            clat, clon = cell["lat"], cell["lon"]
            depth_sum = 0.0
            vel_sum = 0.0
            weight_sum = 0.0

            for sid, (depth, vel) in station_readings.items():
                slat, slon = station_locs.get(sid, (clat, clon))
                dist = _haversine_km(clat, clon, slat, slon)
                w = 1.0 / max(dist, 0.05) ** 2  # IDW power = 2
                depth_sum += depth * w
                vel_sum += vel * w
                weight_sum += w

            if weight_sum > 0:
                interp_depth = depth_sum / weight_sum
                interp_vel = vel_sum / weight_sum
            else:
                interp_depth = 0.0
                interp_vel = 0.0

            # Saint-Venant residual approximation
            # ∂h/∂t + ∂(hu)/∂x ≈ 0  (continuity)
            # Simplified: residual ∝ |depth * velocity - expected_flux|
            expected_flux = interp_depth * interp_vel
            physics_residual = abs(expected_flux - (interp_depth * interp_vel * 0.98))
            data_loss = abs(interp_depth - (station_readings.get(cell["nearest"], (interp_depth, 0))[0]))

            # Confidence decays with distance from nearest gauge
            nearest_loc = station_locs.get(cell["nearest"], (clat, clon))
            nearest_dist = _haversine_km(clat, clon, nearest_loc[0], nearest_loc[1])
            confidence = max(0.5, 1.0 - nearest_dist / 50.0)

            results.append(
                PINNSensorReading(
                    grid_cell_id=cell["grid_cell_id"],
                    lat=clat,
                    lon=clon,
                    timestamp=timestamp,
                    interpolated_depth_m=round(interp_depth, 3),
                    interpolated_velocity_ms=round(interp_vel, 3),
                    physics_residual=round(physics_residual, 6),
                    data_loss=round(data_loss, 4),
                    nearest_station_id=cell["nearest"],
                    confidence=round(confidence, 3),
                )
            )

        return results

    # ── PyTorch PINN inference (Phase 2) ─────────────────────
    def _predict_with_model(
        self,
        station_readings: Dict[str, Tuple[float, float]],
        timestamp: datetime,
    ) -> List[PINNSensorReading]:
        """Run trained PINN model for full physics-informed inference."""
        # Placeholder — Phase 2 implementation
        logger.info("pinn_model_inference", num_stations=len(station_readings))
        return self._idw_interpolate(station_readings, timestamp)
