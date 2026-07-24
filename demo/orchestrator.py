"""ARGUS Phase 3 — Demo Orchestrator.

Walks judges through a scripted 12-minute scenario that exercises
every ARGUS module end-to-end:

  1. Ingestion + Feature Engine → real-time readings
  2. Prediction → XGBoost / TFT multi-horizon forecast
  3. Causal Engine → GNN do-calculus intervention
  4. CHORUS → community report aggregation
  5. FloodLedger → parametric insurance payout
  6. EvacuationRL → multi-zone plan
  7. MIRROR → counterfactual replay
  8. Model Monitor → drift check

Usage (CLI):
    python -m demo.orchestrator run --scenario brahmaputra_monsoon
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import structlog

try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

try:
    import typer

    TYPER_AVAILABLE = True
except ImportError:
    TYPER_AVAILABLE = False

from demo.scenario_loader import ScenarioLoader, DemoMoment

log = structlog.get_logger(__name__)

# ── Service endpoint registry ────────────────────────────────────────────
DEFAULT_ENDPOINTS = {
    "ingestion": "http://localhost:8001",
    "cv_gauging": "http://localhost:8002",
    "feature_engine": "http://localhost:8003",
    "prediction": "http://localhost:8004",
    "alert_dispatcher": "http://localhost:8005",
    "acn_node": "http://localhost:8006",
    "causal_engine": "http://localhost:8006",
    "chorus": "http://localhost:8008",
    "federated": "http://localhost:8009",
    "flood_ledger": "http://localhost:8007",
    "evacuation_rl": "http://localhost:8010",
    "mirror": "http://localhost:8011",
    "scarnet": "http://localhost:8012",
    "model_monitor": "http://localhost:8013",
}


class DemoOrchestrator:
    """Walks through a demo scenario, hitting service endpoints in sequence."""

    def __init__(
        self,
        endpoints: Optional[Dict[str, str]] = None,
        scenario_name: str = "brahmaputra_monsoon",
        speed: float = 1.0,
    ):
        self.endpoints = endpoints or DEFAULT_ENDPOINTS
        self.scenario_name = scenario_name
        self.speed = speed
        self.loader = ScenarioLoader()
        self.results: List[Dict[str, Any]] = []
        self.console = Console() if RICH_AVAILABLE else None

    async def _call(
        self, service: str, method: str, path: str, **kwargs
    ) -> Dict[str, Any]:
        """Call a service endpoint with error handling."""
        url = f"{self.endpoints.get(service, 'http://localhost:8000')}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                if method == "GET":
                    resp = await client.get(url, **kwargs)
                else:
                    resp = await client.post(url, **kwargs)
                resp.raise_for_status()
                return {"status": "ok", "data": resp.json()}
            except Exception as e:
                log.warning("service_call_failed", service=service, path=path, error=str(e))
                return {"status": "error", "error": str(e)}

    # ── Demo Steps ───────────────────────────────────────────────────────

    async def step_health_check(self) -> Dict[str, Any]:
        """Step 0: Verify all services are reachable."""
        results = {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            for name, base_url in self.endpoints.items():
                try:
                    resp = await client.get(f"{base_url}/health")
                    results[name] = "healthy" if resp.status_code == 200 else f"status={resp.status_code}"
                except Exception:
                    results[name] = "unreachable"
        return results

    async def step_ingest_readings(self) -> Dict[str, Any]:
        """Step 1: Push synthetic sensor readings via ingestion."""
        return await self._call(
            "ingestion", "POST", "/api/v1/ingest",
            json={
                "station_id": "brahmaputra_neamatighat",
                "water_level_m": 8.2,
                "rainfall_mm_h": 45.0,
                "timestamp": datetime.utcnow().isoformat(),
                "source": "demo_orchestrator",
            },
        )

    async def step_get_prediction(self) -> Dict[str, Any]:
        """Step 2: Fetch multi-horizon flood prediction."""
        return await self._call(
            "prediction", "GET", "/api/v1/predict/brahmaputra_upper"
        )

    async def step_causal_intervene(self) -> Dict[str, Any]:
        """Step 3: Run causal do-calculus intervention."""
        return await self._call(
            "causal_engine", "POST", "/api/v1/causal/intervene",
            json={
                "basin_id": "brahmaputra_upper",
                "intervention": {
                    "variable": "dam_pandoh_gate",
                    "value": 0.3,
                    "description": "Open dam gate to 30%"
                },
            },
        )

    async def step_chorus_report(self) -> Dict[str, Any]:
        """Step 4: Submit a simulated CHORUS community report."""
        return await self._call(
            "chorus", "POST", "/api/v1/chorus/report",
            json={
                "reporter_id": "demo_villager_001",
                "text": "Paani bahut badh gaya hai, Majuli mein 3 feet paani",
                "language": "hi",
                "lat": 26.95,
                "lon": 94.17,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    async def step_flood_ledger_trigger(self) -> Dict[str, Any]:
        """Step 5: Trigger parametric insurance via FloodLedger."""
        return await self._call(
            "flood_ledger", "POST", "/api/v1/ledger/demo-trigger",
            json={
                "basin_id": "brahmaputra_upper",
                "severity": "SEVERE",
                "satellite_confirmed": True,
            },
        )

    async def step_evacuation_plan(self) -> Dict[str, Any]:
        """Step 6: Request RL evacuation plan."""
        return await self._call(
            "evacuation_rl", "POST", "/api/v1/evacuation/plan",
            json={
                "village_id": "majuli_kamalabari",
                "risk_score": 0.85,
                "population": 12000,
                "flood_eta_minutes": 120,
            },
        )

    async def step_mirror_replay(self) -> Dict[str, Any]:
        """Step 7: Run MIRROR counterfactual replay."""
        return await self._call(
            "mirror", "POST", "/api/v1/mirror/replay",
            json={
                "event_id": "brahmaputra_2023_monsoon",
                "what_if": {
                    "dam_release_pct": 0.3,
                    "alert_lead_time_h": 6,
                },
                "steps": 24,
            },
        )

    async def step_drift_check(self) -> Dict[str, Any]:
        """Step 8: Check model drift status."""
        return await self._call(
            "model_monitor", "GET", "/api/v1/monitor/drift-report"
        )

    # ── Orchestration ────────────────────────────────────────────────────

    async def run_full_demo(self) -> List[Dict[str, Any]]:
        """Execute all demo steps sequentially with rich output."""
        steps = [
            ("Health Check", self.step_health_check),
            ("Ingest Readings", self.step_ingest_readings),
            ("Flood Prediction", self.step_get_prediction),
            ("Causal Intervention", self.step_causal_intervene),
            ("CHORUS Report", self.step_chorus_report),
            ("FloodLedger Payout", self.step_flood_ledger_trigger),
            ("Evacuation Plan", self.step_evacuation_plan),
            ("MIRROR Replay", self.step_mirror_replay),
            ("Drift Check", self.step_drift_check),
        ]

        self.results = []

        if RICH_AVAILABLE and self.console:
            self.console.print(Panel(
                "[bold cyan]ARGUS Demo Orchestrator[/bold cyan]\n"
                f"Scenario: {self.scenario_name} | Speed: {self.speed}x",
                title="🌊 ARGUS",
            ))

        for i, (name, step_fn) in enumerate(steps, 1):
            if RICH_AVAILABLE and self.console:
                self.console.print(f"\n[bold yellow]Step {i}/{len(steps)}:[/bold yellow] {name}")

            start = time.monotonic()
            result = await step_fn()
            elapsed = time.monotonic() - start

            entry = {
                "step": i,
                "name": name,
                "elapsed_s": round(elapsed, 2),
                "result": result,
            }
            self.results.append(entry)

            status_icon = "✅" if result.get("status") == "ok" else "❌"
            if RICH_AVAILABLE and self.console:
                self.console.print(f"  {status_icon} {name} ({elapsed:.1f}s)")
            else:
                log.info("demo_step", step=i, name=name, status=result.get("status"), elapsed=f"{elapsed:.1f}s")

            # Pause between steps for dramatic effect
            await asyncio.sleep(max(0.5 / self.speed, 0.1))

        # Summary
        ok_count = sum(1 for r in self.results if r["result"].get("status") == "ok")
        total = len(self.results)

        if RICH_AVAILABLE and self.console:
            self.console.print(Panel(
                f"[bold green]{ok_count}/{total} steps passed[/bold green]",
                title="Demo Complete",
            ))

        return self.results


# ── CLI entry point ──────────────────────────────────────────────────────

def _run_demo(
    scenario: str = "brahmaputra_monsoon",
    speed: float = 1.0,
):
    """CLI wrapper to run the demo."""
    orchestrator = DemoOrchestrator(scenario_name=scenario, speed=speed)
    results = asyncio.run(orchestrator.run_full_demo())
    return results


if TYPER_AVAILABLE:
    app = typer.Typer(help="ARGUS Demo Orchestrator")

    @app.command()
    def run(
        scenario: str = typer.Option("brahmaputra_monsoon", help="Scenario name"),
        speed: float = typer.Option(1.0, help="Playback speed multiplier"),
    ):
        """Run the full ARGUS demo scenario."""
        _run_demo(scenario=scenario, speed=speed)

    if __name__ == "__main__":
        app()
else:
    if __name__ == "__main__":
        _run_demo()
