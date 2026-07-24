"""ARGUS Phase 3 — Health Checker.

Polls every ARGUS micro-service ``/health`` endpoint and reports
aggregate system readiness. Used by the Demo Orchestrator to verify
the stack is up before starting a demo, and by CI for smoke tests.

Usage:
    python -m demo.health_checker          # one-shot check
    python -m demo.health_checker --watch  # continuous (every 10s)
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
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

log = structlog.get_logger(__name__)

# ── Service registry ─────────────────────────────────────────────────────
SERVICE_REGISTRY = {
    "ingestion": {"port": 8001, "critical": True},
    "cv_gauging": {"port": 8002, "critical": False},
    "feature_engine": {"port": 8003, "critical": True},
    "prediction": {"port": 8004, "critical": True},
    "alert_dispatcher": {"port": 8005, "critical": True},
    "causal_engine": {"port": 8006, "critical": True},
    "flood_ledger": {"port": 8007, "critical": False},
    "chorus": {"port": 8008, "critical": False},
    "federated": {"port": 8009, "critical": False},
    "evacuation_rl": {"port": 8010, "critical": False},
    "mirror": {"port": 8011, "critical": False},
    "scarnet": {"port": 8012, "critical": False},
    "model_monitor": {"port": 8013, "critical": False},
}


class HealthCheckResult:
    """Result of a single service health check."""

    def __init__(
        self,
        service: str,
        healthy: bool,
        latency_ms: float = 0.0,
        error: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.service = service
        self.healthy = healthy
        self.latency_ms = latency_ms
        self.error = error
        self.details = details or {}
        self.checked_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service": self.service,
            "healthy": self.healthy,
            "latency_ms": round(self.latency_ms, 1),
            "error": self.error,
            "checked_at": self.checked_at.isoformat(),
        }


class HealthChecker:
    """Check health of all ARGUS services."""

    def __init__(
        self,
        base_host: str = "localhost",
        registry: Optional[Dict[str, Dict]] = None,
        timeout_s: float = 5.0,
    ):
        self.base_host = base_host
        self.registry = registry or SERVICE_REGISTRY
        self.timeout = timeout_s
        self.last_results: List[HealthCheckResult] = []

    async def check_one(self, service: str, port: int) -> HealthCheckResult:
        """Check a single service."""
        url = f"http://{self.base_host}:{port}/health"
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                latency = (time.monotonic() - start) * 1000
                if resp.status_code == 200:
                    return HealthCheckResult(
                        service=service,
                        healthy=True,
                        latency_ms=latency,
                        details=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {},
                    )
                else:
                    return HealthCheckResult(
                        service=service,
                        healthy=False,
                        latency_ms=latency,
                        error=f"HTTP {resp.status_code}",
                    )
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                service=service,
                healthy=False,
                latency_ms=latency,
                error=str(e),
            )

    async def check_all(self) -> List[HealthCheckResult]:
        """Check all services concurrently."""
        tasks = [
            self.check_one(name, info["port"])
            for name, info in self.registry.items()
        ]
        self.last_results = await asyncio.gather(*tasks)
        return self.last_results

    def is_demo_ready(self) -> bool:
        """Are all critical services healthy?"""
        critical = {
            name for name, info in self.registry.items() if info.get("critical")
        }
        return all(
            r.healthy for r in self.last_results if r.service in critical
        )

    def summary(self) -> Dict[str, Any]:
        """Return a JSON-serializable summary."""
        healthy = sum(1 for r in self.last_results if r.healthy)
        total = len(self.last_results)
        return {
            "healthy": healthy,
            "total": total,
            "demo_ready": self.is_demo_ready(),
            "services": [r.to_dict() for r in self.last_results],
            "checked_at": datetime.utcnow().isoformat(),
        }

    def print_table(self):
        """Print a rich table (if available)."""
        if not RICH_AVAILABLE:
            for r in self.last_results:
                icon = "OK" if r.healthy else "FAIL"
                print(f"  [{icon}] {r.service:20s} {r.latency_ms:6.1f}ms {r.error or ''}")
            return

        console = Console()
        table = Table(title="ARGUS Health Check")
        table.add_column("Service", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Latency", justify="right")
        table.add_column("Error", style="red")

        for r in self.last_results:
            status = "[green]✅ OK[/green]" if r.healthy else "[red]❌ DOWN[/red]"
            table.add_row(r.service, status, f"{r.latency_ms:.0f}ms", r.error or "")

        console.print(table)

        demo_status = "[green]READY[/green]" if self.is_demo_ready() else "[red]NOT READY[/red]"
        console.print(f"\nDemo readiness: {demo_status}")


async def _main(watch: bool = False, interval: float = 10.0):
    """CLI entry point."""
    checker = HealthChecker()

    while True:
        await checker.check_all()
        checker.print_table()

        if not watch:
            break
        await asyncio.sleep(interval)


if __name__ == "__main__":
    import sys

    watch_mode = "--watch" in sys.argv
    asyncio.run(_main(watch=watch_mode))
