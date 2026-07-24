"""In-memory feature store and raw-data ring buffers.

Maintains sliding windows of raw readings so that temporal
and spatial features can be computed on demand.

Phase 2 replaces this with TimescaleDB + Redis.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

import structlog

from shared.config import get_settings
from shared.models.feature_engine import FeatureVector
from shared.models.ingestion import GaugeReading, WeatherData
from shared.models.cv_gauging import VirtualGaugeReading

logger = structlog.get_logger(__name__)
settings = get_settings()

# Maximum number of readings to keep per station in memory
_MAX_BUFFER = 300  # ~25 hours at 5-min interval


class FeatureStore:
    """Holds raw readings + latest computed feature vectors in memory."""

    def __init__(self) -> None:
        # Ring buffers keyed by station_id / camera_id
        self.gauge_buffer: Dict[str, Deque[GaugeReading]] = defaultdict(
            lambda: deque(maxlen=_MAX_BUFFER)
        )
        self.weather_buffer: Dict[str, Deque[WeatherData]] = defaultdict(
            lambda: deque(maxlen=_MAX_BUFFER)
        )
        self.cv_buffer: Dict[str, Deque[VirtualGaugeReading]] = defaultdict(
            lambda: deque(maxlen=_MAX_BUFFER)
        )

        # Latest computed feature vector per station
        self._latest_features: Dict[str, FeatureVector] = {}

        # Station topology (directed adjacency: upstream → downstream)
        self.topology: Dict[str, List[str]] = self._load_topology()

    # ── topology ─────────────────────────────────────────────
    @staticmethod
    def _load_topology() -> Dict[str, List[str]]:
        """Load station adjacency from a JSON file or return demo defaults."""
        topo_path = Path("./data/station_topology.json")
        if topo_path.exists():
            with open(topo_path) as f:
                return json.load(f)
        # Demo topology — Beas River basin (Himachal Pradesh)
        return {
            "CWC-HP-MANDI": {
                "downstream": ["CWC-HP-PANDOH"],
                "upstream": [],
                "lat": 31.71,
                "lon": 76.93,
            },
            "CWC-HP-PANDOH": {
                "downstream": ["CWC-HP-NADAUN"],
                "upstream": ["CWC-HP-MANDI"],
                "lat": 31.67,
                "lon": 77.06,
            },
            "CWC-HP-NADAUN": {
                "downstream": ["CWC-PB-PONG"],
                "upstream": ["CWC-HP-PANDOH"],
                "lat": 31.78,
                "lon": 76.34,
            },
            "CWC-PB-PONG": {
                "downstream": [],
                "upstream": ["CWC-HP-NADAUN"],
                "lat": 31.97,
                "lon": 75.95,
            },
        }

    # ── ingest raw readings ──────────────────────────────────
    def add_gauge(self, reading: GaugeReading) -> None:
        """Append a gauge reading to the ring buffer."""
        self.gauge_buffer[reading.station_id].append(reading)
        logger.debug("store_gauge", station=reading.station_id, level=reading.level_m)

    def add_weather(self, reading: WeatherData) -> None:
        """Append a weather reading. Key by nearest-station heuristic (lat/lon grid cell)."""
        cell_key = f"{reading.lat:.1f}_{reading.lon:.1f}"
        self.weather_buffer[cell_key].append(reading)

    def add_cv(self, reading: VirtualGaugeReading) -> None:
        """Append a CV gauge reading."""
        self.cv_buffer[reading.camera_id].append(reading)

    # ── feature vector cache ─────────────────────────────────
    def set_latest(self, station_id: str, fv: FeatureVector) -> None:
        """Cache the most-recently computed feature vector."""
        self._latest_features[station_id] = fv

    def get_latest(self, station_id: str) -> Optional[FeatureVector]:
        """Retrieve cached feature vector (or None)."""
        return self._latest_features.get(station_id)

    # ── helpers ──────────────────────────────────────────────
    def get_upstream_ids(self, station_id: str) -> List[str]:
        """Return list of upstream station IDs for *station_id*."""
        node = self.topology.get(station_id, {})
        if isinstance(node, dict):
            return node.get("upstream", [])
        return []

    def get_all_station_ids(self) -> List[str]:
        """Return all known station IDs from topology."""
        return list(self.topology.keys())

    def get_gauge_readings(self, station_id: str, n: int | None = None) -> List[GaugeReading]:
        """Return the last *n* gauge readings for a station."""
        buf = self.gauge_buffer.get(station_id)
        if buf is None:
            return []
        if n is None:
            return list(buf)
        return list(buf)[-n:]

    def get_weather_near(self, lat: float, lon: float, n: int | None = None) -> List[WeatherData]:
        """Return weather readings for the grid cell nearest to (lat, lon)."""
        cell_key = f"{lat:.1f}_{lon:.1f}"
        buf = self.weather_buffer.get(cell_key)
        if buf is None:
            return []
        if n is None:
            return list(buf)
        return list(buf)[-n:]

    def get_cv_readings(self, camera_id: str, n: int | None = None) -> List[VirtualGaugeReading]:
        """Return last *n* CV readings for a camera."""
        buf = self.cv_buffer.get(camera_id)
        if buf is None:
            return []
        if n is None:
            return list(buf)
        return list(buf)[-n:]
