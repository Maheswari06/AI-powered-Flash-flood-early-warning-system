"""ARGUS Phase 3 — Scenario Loader.

Loads scripted JSON scenario files that define a sequence of "demo moments"
with pre-canned payloads, delays, and expected responses.

A scenario file (e.g. ``data/scenarios/brahmaputra_monsoon.json``) looks like:

    {
      "scenario_id": "brahmaputra_monsoon",
      "description": "Full 12-minute Brahmaputra flood demo",
      "moments": [
          {
              "step": 1,
              "service": "ingestion",
              "action": "POST /api/v1/ingest",
              "payload": {"station_id": "...", ...},
              "delay_s": 2.0,
              "narration": "Sensor readings arrive from Neamatighat station."
          },
          ...
      ]
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from pydantic import BaseModel, Field

log = structlog.get_logger(__name__)


class DemoMoment(BaseModel):
    """A single step in the demo scenario script."""
    step: int
    service: str
    action: str                        # e.g. "POST /api/v1/ingest"
    payload: Dict[str, Any] = Field(default_factory=dict)
    delay_s: float = 2.0              # seconds to wait after this step
    narration: str = ""                # text to display during this step
    expected_status: str = "ok"


class DemoScenario(BaseModel):
    """A complete demo scenario with ordered moments."""
    scenario_id: str
    description: str = ""
    duration_minutes: float = 12.0
    moments: List[DemoMoment] = Field(default_factory=list)


# ── Built-in scenarios (no file needed) ──────────────────────────────────

BRAHMAPUTRA_MONSOON = DemoScenario(
    scenario_id="brahmaputra_monsoon",
    description="Full 12-minute Brahmaputra monsoon flood demo showcasing all ARGUS modules",
    duration_minutes=12.0,
    moments=[
        DemoMoment(
            step=1,
            service="ingestion",
            action="POST /api/v1/ingest",
            payload={
                "station_id": "brahmaputra_neamatighat",
                "water_level_m": 8.2,
                "rainfall_mm_h": 45.0,
                "source": "demo_orchestrator",
            },
            delay_s=3.0,
            narration="📡 Sensor readings arrive from Neamatighat station — water level 8.2m with heavy rainfall.",
        ),
        DemoMoment(
            step=2,
            service="feature_engine",
            action="GET /api/v1/features/brahmaputra_upper",
            delay_s=2.0,
            narration="⚙️ Feature Engine computes rolling statistics, PINN virtual mesh, and Kalman-filtered estimates.",
        ),
        DemoMoment(
            step=3,
            service="prediction",
            action="GET /api/v1/predict/brahmaputra_upper",
            delay_s=3.0,
            narration="🔮 XGBoost + TFT ensemble forecasts: 87% flood probability in 6 hours.",
        ),
        DemoMoment(
            step=4,
            service="causal_engine",
            action="POST /api/v1/causal/intervene",
            payload={
                "basin_id": "brahmaputra_upper",
                "intervention": {
                    "variable": "dam_pandoh_gate",
                    "value": 0.3,
                    "description": "Open dam gate to 30% capacity"
                },
            },
            delay_s=4.0,
            narration="🧠 Causal GNN runs do-calculus: opening dam gate reduces flood depth by 34%.",
        ),
        DemoMoment(
            step=5,
            service="chorus",
            action="POST /api/v1/chorus/report",
            payload={
                "reporter_id": "demo_villager_001",
                "text": "Majuli mein paani 3 feet tak aa gaya hai",
                "language": "hi",
                "lat": 26.95,
                "lon": 94.17,
            },
            delay_s=2.0,
            narration="📢 CHORUS receives community flood report in Hindi — NLP extracts severity and location.",
        ),
        DemoMoment(
            step=6,
            service="flood_ledger",
            action="POST /api/v1/ledger/demo-trigger",
            payload={
                "basin_id": "brahmaputra_upper",
                "severity": "SEVERE",
                "satellite_confirmed": True,
            },
            delay_s=3.0,
            narration="⛓️ FloodLedger records event on-chain → parametric insurance auto-pays affected farmers.",
        ),
        DemoMoment(
            step=7,
            service="evacuation_rl",
            action="POST /api/v1/evacuation/plan",
            payload={
                "village_id": "majuli_kamalabari",
                "risk_score": 0.85,
                "population": 12000,
                "flood_eta_minutes": 120,
            },
            delay_s=3.0,
            narration="🚁 RL agent generates multi-zone evacuation plan for 12,000 people in Kamalabari.",
        ),
        DemoMoment(
            step=8,
            service="mirror",
            action="POST /api/v1/mirror/replay",
            payload={
                "event_id": "brahmaputra_2023_monsoon",
                "what_if": {
                    "dam_release_pct": 0.3,
                    "alert_lead_time_h": 6,
                },
                "steps": 24,
            },
            delay_s=3.0,
            narration="🔄 MIRROR replays 2023 monsoon with counterfactual: 6h early warning saves 40% more lives.",
        ),
        DemoMoment(
            step=9,
            service="model_monitor",
            action="GET /api/v1/monitor/drift-report",
            delay_s=2.0,
            narration="📊 Model Monitor confirms no significant drift — all models within operational bounds.",
        ),
    ],
)

BUILTIN_SCENARIOS = {
    "brahmaputra_monsoon": BRAHMAPUTRA_MONSOON,
}


class ScenarioLoader:
    """Load demo scenarios from built-in definitions or JSON files."""

    def __init__(self, scenarios_dir: str = "./data/scenarios"):
        self.scenarios_dir = Path(scenarios_dir)
        self._cache: Dict[str, DemoScenario] = dict(BUILTIN_SCENARIOS)

    def list_scenarios(self) -> List[str]:
        """Return available scenario IDs."""
        names = list(self._cache.keys())
        if self.scenarios_dir.exists():
            for f in self.scenarios_dir.glob("*.json"):
                sid = f.stem
                if sid not in names:
                    names.append(sid)
        return names

    def load(self, scenario_id: str) -> DemoScenario:
        """Load a scenario by ID. Checks built-ins first, then disk."""
        if scenario_id in self._cache:
            return self._cache[scenario_id]

        json_path = self.scenarios_dir / f"{scenario_id}.json"
        if json_path.exists():
            data = json.loads(json_path.read_text())
            scenario = DemoScenario(**data)
            self._cache[scenario_id] = scenario
            log.info("scenario_loaded", scenario_id=scenario_id, moments=len(scenario.moments))
            return scenario

        log.warning("scenario_not_found", scenario_id=scenario_id, fallback="brahmaputra_monsoon")
        return BRAHMAPUTRA_MONSOON

    def get_moments(self, scenario_id: str) -> List[DemoMoment]:
        """Return the ordered list of demo moments for a scenario."""
        return self.load(scenario_id).moments
