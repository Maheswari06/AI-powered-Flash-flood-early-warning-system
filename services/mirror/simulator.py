"""MIRROR Simulator — Counterfactual what-if flood replay engine.

Simulates alternative flood scenarios by modifying initial conditions
and replaying through a simplified hydrological model to answer
questions like "What if rainfall was 50% less?" or "What if the dam
released water 2 hours earlier?"
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import structlog

from shared.models.phase2 import CounterfactualQuery, CounterfactualResult

logger = structlog.get_logger(__name__)


class HydroSimulator:
    """Simplified hydrological simulator for counterfactual replay.

    Uses a 1D kinematic wave approximation with:
      - Rainfall → runoff → channel routing
      - Soil moisture antecedent condition
      - Dam release schedules
    """

    def __init__(self, dt_hours: float = 1.0, max_steps: int = 48):
        self.dt = dt_hours
        self.max_steps = max_steps
        # Default parameters (Beas-like)
        self.manning_n = 0.035      # Manning's roughness
        self.slope = 0.005          # channel slope
        self.channel_width = 50.0   # meters
        self.catchment_area = 300.0 # km²
        self.cn_base = 75           # SCS curve number

    def simulate(
        self,
        rainfall_mm_hr: List[float],
        soil_moisture: float = 0.5,
        dam_release_cumecs: List[float] | None = None,
        initial_level_m: float = 2.0,
    ) -> List[Dict[str, Any]]:
        """Simulate flood scenario and return time-stepped results.

        Args:
            rainfall_mm_hr: Rainfall intensity per time step
            soil_moisture: Initial soil moisture [0, 1]
            dam_release_cumecs: Dam discharge per step (m³/s)
            initial_level_m: Starting water level

        Returns:
            List of dicts with water_level, discharge, risk per step
        """
        n_steps = min(len(rainfall_mm_hr), self.max_steps)
        if dam_release_cumecs is None:
            dam_release_cumecs = [0.0] * n_steps

        # Adjust curve number for soil moisture (AMC)
        cn = self.cn_base
        if soil_moisture > 0.7:
            cn = min(98, cn * 1.15)  # wet soil → more runoff
        elif soil_moisture < 0.3:
            cn = max(40, cn * 0.85)  # dry soil → more infiltration
        s_retention = 25400 / cn - 254  # mm

        timeline: List[Dict[str, Any]] = []
        level = initial_level_m
        discharge = 0.0

        for t in range(n_steps):
            rain = rainfall_mm_hr[t] if t < len(rainfall_mm_hr) else 0.0
            dam_q = dam_release_cumecs[t] if t < len(dam_release_cumecs) else 0.0

            # SCS runoff (simplified)
            p = rain * self.dt  # total rainfall this step (mm)
            if p > 0.2 * s_retention:
                runoff_mm = (p - 0.2 * s_retention) ** 2 / (p + 0.8 * s_retention)
            else:
                runoff_mm = 0.0

            # Convert runoff to discharge (m³/s)
            runoff_volume = runoff_mm * 1e-3 * self.catchment_area * 1e6  # m³
            runoff_q = runoff_volume / (self.dt * 3600)  # m³/s

            # Total discharge
            discharge = runoff_q + dam_q
            # Attenuation (simple Muskingum-like)
            discharge *= 0.85 if t > 0 else 1.0

            # Manning's equation for water depth
            # Q = (1/n) * A * R^(2/3) * S^(1/2)
            # Simplified: level ∝ Q^(3/5)
            if discharge > 0:
                area = discharge * self.manning_n / (math.sqrt(self.slope))
                depth = area / max(self.channel_width, 1)
                level = initial_level_m + depth ** 0.6
            else:
                level = max(initial_level_m * 0.98, level - 0.05)

            # Risk score (simple threshold mapping)
            risk = self._level_to_risk(level)

            timeline.append({
                "step": t,
                "time_offset_hours": t * self.dt,
                "rainfall_mm_hr": round(rain, 1),
                "runoff_mm": round(runoff_mm, 2),
                "discharge_cumecs": round(discharge, 1),
                "dam_release_cumecs": round(dam_q, 1),
                "water_level_m": round(level, 3),
                "risk_score": round(risk, 3),
            })

        return timeline

    def _level_to_risk(self, level: float) -> float:
        """Map water level to risk score [0, 1]."""
        # Sigmoid mapping centered at danger level (5m)
        danger_level = 5.0
        return 1.0 / (1.0 + math.exp(-(level - danger_level) * 1.5))


class MirrorEngine:
    """Counterfactual replay engine using the HydroSimulator."""

    def __init__(self, max_steps: int = 48):
        self.simulator = HydroSimulator(max_steps=max_steps)
        self.max_steps = max_steps
        self._scenario_cache: Dict[str, CounterfactualResult] = {}

    def replay(self, query: CounterfactualQuery) -> CounterfactualResult:
        """Execute a counterfactual scenario."""
        mods = query.modifications

        # Base scenario: default conditions
        n_steps = self.max_steps
        base_rainfall = [mods.get("base_rainfall_mm_hr", 15.0)] * n_steps
        base_soil = mods.get("base_soil_moisture", 0.6)
        base_dam = [mods.get("base_dam_release", 50.0)] * n_steps
        base_level = mods.get("base_initial_level", 2.5)

        # Run base scenario
        base_timeline = self.simulator.simulate(
            rainfall_mm_hr=base_rainfall,
            soil_moisture=base_soil,
            dam_release_cumecs=base_dam,
            initial_level_m=base_level,
        )

        # Modified scenario: apply user modifications
        mod_rainfall = list(base_rainfall)
        if "rainfall_factor" in mods:
            mod_rainfall = [r * mods["rainfall_factor"] for r in mod_rainfall]
        if "rainfall_mm_hr" in mods:
            mod_rainfall = [mods["rainfall_mm_hr"]] * n_steps

        mod_soil = mods.get("soil_moisture", base_soil)
        mod_dam = list(base_dam)
        if "dam_release" in mods:
            mod_dam = [mods["dam_release"]] * n_steps
        if "dam_delay_hours" in mods:
            delay = int(mods["dam_delay_hours"])
            mod_dam = [0.0] * delay + mod_dam[: n_steps - delay]

        mod_level = mods.get("initial_level", base_level)

        # Run modified scenario
        mod_timeline = self.simulator.simulate(
            rainfall_mm_hr=mod_rainfall,
            soil_moisture=mod_soil,
            dam_release_cumecs=mod_dam,
            initial_level_m=mod_level,
        )

        # Compute outcomes
        base_peak_risk = max(s["risk_score"] for s in base_timeline)
        base_peak_level = max(s["water_level_m"] for s in base_timeline)
        mod_peak_risk = max(s["risk_score"] for s in mod_timeline)
        mod_peak_level = max(s["water_level_m"] for s in mod_timeline)

        risk_delta = mod_peak_risk - base_peak_risk

        # Estimate lives impact (heuristic: 1000 people at risk per 0.1 risk above 0.5)
        base_danger_steps = sum(1 for s in base_timeline if s["risk_score"] > 0.5)
        mod_danger_steps = sum(1 for s in mod_timeline if s["risk_score"] > 0.5)
        lives_impact = (base_danger_steps - mod_danger_steps) * 50  # rough estimate

        result = CounterfactualResult(
            query=query,
            timeline=mod_timeline,
            base_outcome={
                "peak_risk": base_peak_risk,
                "peak_level_m": base_peak_level,
                "danger_hours": base_danger_steps,
            },
            modified_outcome={
                "peak_risk": mod_peak_risk,
                "peak_level_m": mod_peak_level,
                "danger_hours": mod_danger_steps,
            },
            risk_delta=round(risk_delta, 4),
            lives_impact=lives_impact,
        )

        self._scenario_cache[query.query_id] = result
        logger.info(
            "counterfactual_done",
            scenario=query.scenario_name,
            risk_delta=round(risk_delta, 4),
            lives_impact=lives_impact,
        )
        return result

    def get_cached(self, query_id: str) -> Optional[CounterfactualResult]:
        return self._scenario_cache.get(query_id)

    def list_scenarios(self) -> List[str]:
        return list(self._scenario_cache.keys())

    def get_preset_scenarios(self) -> List[CounterfactualQuery]:
        """Return preset what-if scenarios for demo."""
        return [
            CounterfactualQuery(
                query_id="preset_half_rain",
                scenario_name="What if rainfall was 50% less?",
                modifications={"rainfall_factor": 0.5, "base_rainfall_mm_hr": 20.0},
            ),
            CounterfactualQuery(
                query_id="preset_double_rain",
                scenario_name="What if rainfall doubled?",
                modifications={"rainfall_factor": 2.0, "base_rainfall_mm_hr": 20.0},
            ),
            CounterfactualQuery(
                query_id="preset_early_dam",
                scenario_name="What if dam released water 4 hours earlier?",
                modifications={"dam_delay_hours": -4, "base_dam_release": 100.0},
            ),
            CounterfactualQuery(
                query_id="preset_dry_soil",
                scenario_name="What if soil was completely dry?",
                modifications={"soil_moisture": 0.1, "base_rainfall_mm_hr": 20.0},
            ),
            CounterfactualQuery(
                query_id="preset_saturated_soil",
                scenario_name="What if soil was fully saturated?",
                modifications={"soil_moisture": 0.95, "base_rainfall_mm_hr": 20.0},
            ),
            CounterfactualQuery(
                query_id="preset_no_dam",
                scenario_name="What if dam held all water (no release)?",
                modifications={"dam_release": 0.0, "base_rainfall_mm_hr": 20.0},
            ),
        ]
