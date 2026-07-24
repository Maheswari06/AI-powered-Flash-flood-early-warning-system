"""ARGUS Load Test — Storm Event Simulation.

Simulates traffic during a live storm event with concurrent requests
across all demo-critical endpoints.

Usage:
    # Install: pip install locust
    # Headless (CI):
    locust -f tests/load/test_storm_load.py --host=http://localhost:8000 \
           --headless -u 50 -r 10 --run-time 60s

    # Web UI:
    locust -f tests/load/test_storm_load.py --host=http://localhost:8000
    # Then open http://localhost:8089

Target: p95 latency < 2s for all tasks at 50 concurrent users.
"""

from locust import HttpUser, task, between, events
import time


class ARGUSStormUser(HttpUser):
    """Simulates a dashboard user during a live storm event."""

    wait_time = between(1, 3)

    # ── Most frequent: Dashboard polling ─────────────────

    @task(5)
    def poll_predictions(self):
        """Dashboard polls predictions every few seconds."""
        self.client.get("/api/v1/predictions/all", name="[poll] predictions")

    @task(4)
    def get_dashboard_snapshot(self):
        """Initial dashboard load — aggregated snapshot."""
        self.client.get("/api/v1/dashboard/snapshot", name="[poll] snapshot")

    @task(3)
    def get_causal_risk(self):
        """Causal risk panel polling."""
        self.client.get(
            "/api/v1/causal/risk/brahmaputra_upper",
            name="[poll] causal_risk",
        )

    @task(3)
    def get_chorus_signals(self):
        """CHORUS community intelligence polling."""
        self.client.get("/api/v1/chorus/signals", name="[poll] chorus")

    # ── Medium frequency: Panel data ─────────────────────

    @task(2)
    def get_evacuation_plan(self):
        """Evacuation plan display."""
        self.client.get(
            "/api/v1/evacuation/plan/majuli_2024",
            name="[panel] evacuation",
        )

    @task(2)
    def get_scarnet_latest(self):
        """ScarNet terrain health polling."""
        self.client.get("/api/v1/scarnet/latest", name="[panel] scarnet")

    @task(2)
    def get_alert_log(self):
        """Alert sidebar polling."""
        self.client.get("/api/v1/alert/log", name="[panel] alerts")

    @task(1)
    def get_ledger_events(self):
        """FloodLedger blockchain events."""
        self.client.get("/api/v1/ledger/events", name="[panel] ledger")

    # ── Low frequency: Heavy computation ─────────────────

    @task(1)
    def compute_intervention(self):
        """Causal intervention — heaviest computation."""
        self.client.post(
            "/api/v1/causal/intervene",
            json={
                "basin_id": "brahmaputra_upper",
                "intervention": {
                    "variable": "dam_pandoh_gate",
                    "value": 0.25,
                    "unit": "fraction_open",
                },
                "target_variable": "downstream_flood_depth",
            },
            name="[compute] intervention",
        )

    # ── Health checks ────────────────────────────────────

    @task(1)
    def health_check(self):
        """Aggregated health check."""
        self.client.get("/health", name="[health] aggregate")


class ARGUSDemoUser(HttpUser):
    """Simulates the demo scenario being triggered during the pitch."""

    wait_time = between(5, 10)
    weight = 1  # Lower weight — fewer of these users

    @task(1)
    def trigger_scarnet_demo(self):
        """ScarNet demo scan trigger."""
        self.client.post(
            "/api/v1/scarnet/trigger-demo",
            name="[demo] scarnet_scan",
        )

    @task(1)
    def trigger_chorus_demo(self):
        """CHORUS demo report submission."""
        self.client.post(
            "/api/v1/chorus/demo",
            json={"text": "नदी बहुत तेज़ बह रही है", "location": "majuli_bridge"},
            name="[demo] chorus_report",
        )

    @task(1)
    def trigger_evacuation_demo(self):
        """Evacuation demo plan computation."""
        self.client.post(
            "/api/v1/evacuation/demo",
            name="[demo] evacuation",
        )
