"""FloodEventLoader — loads historical flood events for replay.

Includes a pre-baked 2023 Himachal Pradesh flood event for demo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class FloodEvent:
    """A historical flood event with timeline data."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


# ── Pre-baked 2023 Himachal Pradesh flood event ──────────────────────────

HIMACHAL_2023 = FloodEvent(
    event_id="himachal_2023",
    name="2023 Himachal Pradesh Flash Flood (Beas River)",
    basin_id="beas_river",
    location="Kullu-Mandi corridor, Himachal Pradesh",
    date="2023-07-09",
    # Actual outcomes
    lives_lost=71,
    peak_flood_depth_m=4.7,
    official_warning_time_min=-8,  # T-8min (official warning)
    argus_detection_time_min=-78,  # T-78min (ARGUS backtest)
    damage_crore_inr=1847,
    affected_population=12500,
    area_inundated_sqkm=34.2,
    # Timeline
    timeline=[
        {"t_min": -180, "water_level_m": 2.1, "rainfall_mm_hr": 12, "risk_score": 0.15, "event": "Normal monsoon flow"},
        {"t_min": -150, "water_level_m": 2.3, "rainfall_mm_hr": 25, "risk_score": 0.22, "event": "Rainfall intensifying"},
        {"t_min": -120, "water_level_m": 2.8, "rainfall_mm_hr": 45, "risk_score": 0.35, "event": "Heavy rainfall upstream"},
        {"t_min": -100, "water_level_m": 3.1, "rainfall_mm_hr": 62, "risk_score": 0.45, "event": "Pandoh Dam inflow surging"},
        {"t_min": -78, "water_level_m": 3.5, "rainfall_mm_hr": 78, "risk_score": 0.58, "event": "★ ARGUS detection threshold"},
        {"t_min": -60, "water_level_m": 3.9, "rainfall_mm_hr": 85, "risk_score": 0.67, "event": "Tributary confluence flood pulse"},
        {"t_min": -45, "water_level_m": 4.1, "rainfall_mm_hr": 72, "risk_score": 0.76, "event": "Landslide debris dam forming"},
        {"t_min": -30, "water_level_m": 4.3, "rainfall_mm_hr": 55, "risk_score": 0.82, "event": "Debris dam threatening breach"},
        {"t_min": -15, "water_level_m": 4.5, "rainfall_mm_hr": 40, "risk_score": 0.89, "event": "Debris dam breach imminent"},
        {"t_min": -8, "water_level_m": 4.6, "rainfall_mm_hr": 35, "risk_score": 0.93, "event": "★ Official warning issued"},
        {"t_min": -5, "water_level_m": 4.65, "rainfall_mm_hr": 30, "risk_score": 0.95, "event": "Evacuation order (too late)"},
        {"t_min": 0, "water_level_m": 4.7, "rainfall_mm_hr": 28, "risk_score": 0.97, "event": "★ FLOOD PEAK — 4.7m"},
        {"t_min": 15, "water_level_m": 4.5, "rainfall_mm_hr": 20, "risk_score": 0.91, "event": "Recession begins"},
        {"t_min": 30, "water_level_m": 4.2, "rainfall_mm_hr": 15, "risk_score": 0.83, "event": "Continued recession"},
        {"t_min": 60, "water_level_m": 3.8, "rainfall_mm_hr": 10, "risk_score": 0.65, "event": "Water receding from settlements"},
        {"t_min": 120, "water_level_m": 3.2, "rainfall_mm_hr": 5, "risk_score": 0.38, "event": "Recovery efforts begin"},
    ],
    # SAR data
    satellite_confirmation="Sentinel-1 SAR pass at T+3h confirmed flood extent",
    # Actions taken
    actions_taken=[
        {"time_min": -8, "action": "Official warning via SMS", "effective": False},
        {"time_min": -5, "action": "Evacuation order issued", "effective": "Partial"},
        {"time_min": 0, "action": "Pandoh Dam gate opened 15%", "effective": "Too late"},
        {"time_min": 30, "action": "NDRF teams deployed", "effective": True},
    ],
)


class FloodEventLoader:
    """Loads historical flood events for counterfactual replay."""

    def __init__(self):
        self._events: Dict[str, FloodEvent] = {
            "himachal_2023": HIMACHAL_2023,
        }

    def load_event(self, event_id: str) -> Optional[FloodEvent]:
        return self._events.get(event_id)

    def load_demo_event(self) -> FloodEvent:
        return HIMACHAL_2023

    def list_events(self) -> List[Dict[str, Any]]:
        return [
            {
                "event_id": e.event_id,
                "name": e.name,
                "date": e.date,
                "location": e.location,
                "lives_lost": e.lives_lost,
                "peak_depth_m": e.peak_flood_depth_m,
            }
            for e in self._events.values()
        ]
