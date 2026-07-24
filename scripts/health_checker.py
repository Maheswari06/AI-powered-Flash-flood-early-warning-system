#!/usr/bin/env python3
"""ARGUS Health Checker — validates all services before demo.

Usage:
    python scripts/health_checker.py          # check all
    python scripts/health_checker.py --fast   # skip slow endpoints
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass

import httpx

# ── Service registry ────────────────────────────────────────────────────
SERVICES = {
    "Ingestion":        {"url": "http://localhost:8001", "phase": 1},
    "CV Gauging":       {"url": "http://localhost:8002", "phase": 1},
    "Feature Engine":   {"url": "http://localhost:8003", "phase": 1},
    "Prediction":       {"url": "http://localhost:8004", "phase": 1},
    "Alert Dispatcher": {"url": "http://localhost:8005", "phase": 1},
    "Causal Engine":    {"url": "http://localhost:8006", "phase": 2},
    "FloodLedger":      {"url": "http://localhost:8007", "phase": 2},
    "CHORUS":           {"url": "http://localhost:8008", "phase": 2},
    "Federated Server": {"url": "http://localhost:8009", "phase": 2},
    "Evacuation RL":    {"url": "http://localhost:8010", "phase": 2},
    "MIRROR":           {"url": "http://localhost:8011", "phase": 2},
    "ScarNet":          {"url": "http://localhost:8012", "phase": 3},
    "Model Monitor":    {"url": "http://localhost:8013", "phase": 3},
    "API Gateway":      {"url": "http://localhost:8000", "phase": 3},
}


@dataclass
class HealthResult:
    name: str
    phase: int
    status: str  # UP, DOWN, DEGRADED
    latency_ms: int = 0
    error: str = ""


async def check_service(client: httpx.AsyncClient, name: str, info: dict) -> HealthResult:
    """Ping a single service's /health endpoint."""
    url = info["url"]
    phase = info["phase"]
    try:
        t0 = time.monotonic()
        resp = await client.get(f"{url}/health", timeout=3.0)
        latency = int((time.monotonic() - t0) * 1000)
        if resp.status_code == 200:
            return HealthResult(name, phase, "UP", latency)
        return HealthResult(name, phase, "DEGRADED", latency, f"HTTP {resp.status_code}")
    except httpx.ConnectError:
        return HealthResult(name, phase, "DOWN", 0, "Connection refused")
    except httpx.TimeoutException:
        return HealthResult(name, phase, "DOWN", 0, "Timeout (>3s)")
    except Exception as e:
        return HealthResult(name, phase, "DOWN", 0, str(e))


async def check_all() -> list[HealthResult]:
    """Check all services concurrently."""
    async with httpx.AsyncClient() as client:
        tasks = [check_service(client, name, info) for name, info in SERVICES.items()]
        return await asyncio.gather(*tasks)


def print_report(results: list[HealthResult]) -> bool:
    """Print a formatted health report. Returns True if all UP."""
    STATUS_ICON = {"UP": "🟢", "DOWN": "🔴", "DEGRADED": "🟡"}

    print()
    print("════════════════════════════════════════════════════════")
    print("  ARGUS — Service Health Report")
    print("════════════════════════════════════════════════════════")

    for phase in [1, 2, 3]:
        phase_results = [r for r in results if r.phase == phase]
        if not phase_results:
            continue
        print(f"\n  Phase {phase}:")
        for r in phase_results:
            icon = STATUS_ICON.get(r.status, "⚪")
            latency = f"{r.latency_ms:>4d}ms" if r.status == "UP" else "     "
            err = f"  ({r.error})" if r.error else ""
            print(f"    {icon} {r.name:<20s} {r.status:<10s} {latency}{err}")

    up = sum(1 for r in results if r.status == "UP")
    total = len(results)
    down = sum(1 for r in results if r.status == "DOWN")

    print()
    print("────────────────────────────────────────────────────────")
    overall = "OPERATIONAL" if down == 0 else "DEGRADED" if down < total // 2 else "CRITICAL"
    icon = "🟢" if overall == "OPERATIONAL" else "🟡" if overall == "DEGRADED" else "🔴"
    print(f"  {icon} Overall: {overall}  ({up}/{total} services UP)")
    print("════════════════════════════════════════════════════════")
    print()

    return down == 0


def main():
    results = asyncio.run(check_all())
    all_ok = print_report(results)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
