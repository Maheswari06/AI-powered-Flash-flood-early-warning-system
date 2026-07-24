"""Evacuation graph — zones, routes, and graph operations.

Defines the village evacuation network used by the RL environment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from shared.models.phase2 import EvacuationZone, EvacuationRoute

logger = structlog.get_logger(__name__)


# ── Default Kullu evacuation graph ──────────────────────────────────────

DEFAULT_ZONES = [
    EvacuationZone(zone_id="z1", village_id="kullu_01", name="Lower Colony", population=320, lat=31.96, lon=77.10, elevation_m=1180),
    EvacuationZone(zone_id="z2", village_id="kullu_01", name="Market Area", population=450, lat=31.958, lon=77.102, elevation_m=1195),
    EvacuationZone(zone_id="z3", village_id="kullu_01", name="River Bank", population=180, lat=31.962, lon=77.098, elevation_m=1170),
    EvacuationZone(zone_id="z4", village_id="kullu_01", name="Hospital Road", population=260, lat=31.955, lon=77.105, elevation_m=1210),
    EvacuationZone(zone_id="z5", village_id="kullu_01", name="School Hill", population=150, lat=31.957, lon=77.11, elevation_m=1240, is_safe_zone=True, capacity=800),
    EvacuationZone(zone_id="z6", village_id="kullu_01", name="Temple Grounds", population=0, lat=31.963, lon=77.112, elevation_m=1260, is_safe_zone=True, capacity=600),
    EvacuationZone(zone_id="z7", village_id="kullu_01", name="Stadium", population=0, lat=31.952, lon=77.108, elevation_m=1250, is_safe_zone=True, capacity=1200),
    # Majuli zones
    EvacuationZone(zone_id="m1", village_id="majuli_01", name="Kamalabari", population=800, lat=26.95, lon=94.17, elevation_m=78),
    EvacuationZone(zone_id="m2", village_id="majuli_01", name="Garamur", population=600, lat=26.93, lon=94.20, elevation_m=80),
    EvacuationZone(zone_id="m3", village_id="majuli_01", name="Jengraimukh", population=450, lat=26.97, lon=94.25, elevation_m=82),
    EvacuationZone(zone_id="m4", village_id="majuli_01", name="High Ground Camp", population=0, lat=26.96, lon=94.22, elevation_m=95, is_safe_zone=True, capacity=2000),
]

DEFAULT_ROUTES = [
    EvacuationRoute(route_id="r1", from_zone="z1", to_zone="z5", distance_km=1.2, travel_time_min=15, capacity_persons_hr=400, road_type="paved"),
    EvacuationRoute(route_id="r2", from_zone="z1", to_zone="z7", distance_km=1.8, travel_time_min=22, capacity_persons_hr=500, road_type="paved"),
    EvacuationRoute(route_id="r3", from_zone="z2", to_zone="z5", distance_km=0.9, travel_time_min=12, capacity_persons_hr=350, road_type="paved"),
    EvacuationRoute(route_id="r4", from_zone="z2", to_zone="z7", distance_km=1.5, travel_time_min=18, capacity_persons_hr=450, road_type="paved"),
    EvacuationRoute(route_id="r5", from_zone="z3", to_zone="z6", distance_km=0.6, travel_time_min=10, capacity_persons_hr=250, road_type="unpaved"),
    EvacuationRoute(route_id="r6", from_zone="z3", to_zone="z5", distance_km=1.5, travel_time_min=20, capacity_persons_hr=300, road_type="bridge"),
    EvacuationRoute(route_id="r7", from_zone="z4", to_zone="z7", distance_km=0.8, travel_time_min=10, capacity_persons_hr=500, road_type="paved"),
    EvacuationRoute(route_id="r8", from_zone="z4", to_zone="z5", distance_km=1.1, travel_time_min=14, capacity_persons_hr=400, road_type="paved"),
    # Majuli routes
    EvacuationRoute(route_id="m_r1", from_zone="m1", to_zone="m4", distance_km=5.0, travel_time_min=40, capacity_persons_hr=200, road_type="unpaved"),
    EvacuationRoute(route_id="m_r2", from_zone="m2", to_zone="m4", distance_km=3.5, travel_time_min=30, capacity_persons_hr=250, road_type="unpaved"),
    EvacuationRoute(route_id="m_r3", from_zone="m3", to_zone="m4", distance_km=4.0, travel_time_min=35, capacity_persons_hr=200, road_type="boat"),
]


class EvacuationGraph:
    """Encapsulates the zone+route graph for a village or region."""

    def __init__(
        self,
        zones: Optional[List[EvacuationZone]] = None,
        routes: Optional[List[EvacuationRoute]] = None,
    ):
        self.zones = zones or list(DEFAULT_ZONES)
        self.routes = routes or list(DEFAULT_ROUTES)
        self._zone_map = {z.zone_id: z for z in self.zones}
        self._route_map = {r.route_id: r for r in self.routes}
        # Adjacency: from_zone -> [(route, to_zone)]
        self._adj: Dict[str, List[Tuple[EvacuationRoute, str]]] = {}
        for r in self.routes:
            self._adj.setdefault(r.from_zone, []).append((r, r.to_zone))

    def get_zone(self, zone_id: str) -> Optional[EvacuationZone]:
        return self._zone_map.get(zone_id)

    def get_populated_zones(self, village_id: Optional[str] = None) -> List[EvacuationZone]:
        """Return zones with population > 0 (need evacuation)."""
        zones = self.zones
        if village_id:
            zones = [z for z in zones if z.village_id == village_id]
        return [z for z in zones if z.population > 0 and not z.is_safe_zone]

    def get_safe_zones(self, village_id: Optional[str] = None) -> List[EvacuationZone]:
        zones = self.zones
        if village_id:
            zones = [z for z in zones if z.village_id == village_id]
        return [z for z in zones if z.is_safe_zone]

    def get_routes_from(self, zone_id: str) -> List[Tuple[EvacuationRoute, str]]:
        """Return (route, destination_zone_id) pairs from a zone."""
        return self._adj.get(zone_id, [])

    def update_flood_risk(self, risk_scores: Dict[str, float]) -> None:
        """Update route flood risks based on current risk scores."""
        for route in self.routes:
            src_zone = self._zone_map.get(route.from_zone)
            if src_zone:
                village_risk = risk_scores.get(src_zone.village_id, 0.0)
                # Routes at lower elevation are more at risk
                elev_factor = max(0, 1.0 - src_zone.elevation_m / 1500)
                route.flood_risk = min(1.0, village_risk * elev_factor)
                route.is_passable = route.flood_risk < 0.8

    def total_population(self, village_id: Optional[str] = None) -> int:
        return sum(z.population for z in self.get_populated_zones(village_id))

    def total_safe_capacity(self, village_id: Optional[str] = None) -> int:
        return sum(z.capacity or 0 for z in self.get_safe_zones(village_id))

    def to_dict(self) -> Dict:
        return {
            "zones": [z.model_dump() for z in self.zones],
            "routes": [r.model_dump() for r in self.routes],
        }

    @classmethod
    def from_file(cls, path: str) -> "EvacuationGraph":
        """Load graph from JSON file."""
        data = json.loads(Path(path).read_text())
        zones = [EvacuationZone(**z) for z in data.get("zones", [])]
        routes = [EvacuationRoute(**r) for r in data.get("routes", [])]
        return cls(zones, routes)

    def save(self, path: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, default=str))
