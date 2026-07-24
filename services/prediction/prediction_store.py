"""In-memory prediction store.

Caches latest predictions and PINN mesh outputs for API access.
Phase 2 replaces with TimescaleDB.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional

from shared.models.prediction import FloodPrediction, PINNSensorReading

_MAX_HISTORY = 200


class PredictionStore:
    """Cache for predictions and PINN readings."""

    def __init__(self) -> None:
        self._latest: Dict[str, FloodPrediction] = {}
        self._history: Dict[str, Deque[FloodPrediction]] = defaultdict(
            lambda: deque(maxlen=_MAX_HISTORY)
        )
        self._pinn_cells: Dict[str, PINNSensorReading] = {}

    def set_prediction(self, pred: FloodPrediction) -> None:
        """Store a new prediction."""
        self._latest[pred.station_id] = pred
        self._history[pred.station_id].append(pred)

    def get_latest(self, station_id: str) -> Optional[FloodPrediction]:
        """Get most recent prediction for a station."""
        return self._latest.get(station_id)

    def get_history(self, station_id: str, limit: int = 50) -> List[FloodPrediction]:
        """Get prediction history for a station."""
        buf = self._history.get(station_id)
        if buf is None:
            return []
        return list(buf)[-limit:]

    def set_pinn_cells(self, readings: List[PINNSensorReading]) -> None:
        """Update PINN mesh cell readings."""
        for r in readings:
            self._pinn_cells[r.grid_cell_id] = r

    def get_pinn_cell(self, grid_cell_id: str) -> Optional[PINNSensorReading]:
        """Get latest PINN reading for a mesh cell."""
        return self._pinn_cells.get(grid_cell_id)

    def get_all_pinn_cells(self) -> List[PINNSensorReading]:
        """Return all PINN mesh readings."""
        return list(self._pinn_cells.values())
