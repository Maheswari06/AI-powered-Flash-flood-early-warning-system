#!/usr/bin/env python3
"""Autonomous Crisis Node — standalone offline flood monitor.

Runs in an infinite loop with zero cloud dependency:

  1. Read from local sensor (or use cached last reading)
  2. Run ORACLE TinyML inference → risk_score
  3. Evaluate village-specific threshold → escalate if needed
  4. Best-effort cloud sync (non-blocking)

Usage::

    # Normal operation (Majuli island)
    python -m services.acn_node.acn_node --node majuli

    # Demo mode — simulates rising water over 5 minutes
    python -m services.acn_node.acn_node --demo --node majuli

    # Compare Majuli vs Himachal on same data
    python -m services.acn_node.acn_node --demo --node majuli
    python -m services.acn_node.acn_node --demo --node himachal
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import structlog

from services.acn_node.oracle_model import OracleModel
from services.acn_node.offline_cache import OfflineCache
from services.acn_node.lora_sim import LoRaSirenSim
from services.acn_node.alert_escalator import AlertEscalator

logger = structlog.get_logger(__name__)

# ANSI colours
_BOLD = "\033[1m"
_CYAN = "\033[96m"
_GREEN = "\033[92m"
_DIM = "\033[2m"
_RESET = "\033[0m"

# Config directory (relative to project root)
_CONFIG_DIR = Path(__file__).resolve().parent / "config"


# ══════════════════════════════════════════════════════════════════════════
# Config loading
# ══════════════════════════════════════════════════════════════════════════

def load_node_config(node_id: str) -> Dict[str, Any]:
    """Load node config from ``config/{node_id}_node.json``."""
    path = _CONFIG_DIR / f"{node_id}_node.json"
    if not path.exists():
        logger.error("config_not_found", path=str(path))
        sys.exit(1)
    with open(path) as f:
        cfg = json.load(f)
    logger.info("config_loaded", node=node_id, path=str(path))
    return cfg


# ══════════════════════════════════════════════════════════════════════════
# Sensor reading (real or cached fallback)
# ══════════════════════════════════════════════════════════════════════════

def get_sensor_reading_or_cache(
    cache: OfflineCache,
    config: Dict[str, Any],
) -> Dict[str, float]:
    """Attempt to read from a local sensor; fall back to cached reading.

    In a real deployment this would talk to GPIO / serial / I²C.
    Here we simulate a "sensor read" with small Gaussian noise around
    the last cached value, or around the normal range midpoint.
    """
    cached = cache.get_latest()
    if cached and cached.get("features"):
        base = cached["features"]
    else:
        sensor_cfg = config.get("sensor", {})
        normal = sensor_cfg.get("normal_range", [2.0, 5.0])
        mid = (normal[0] + normal[1]) / 2.0
        now = datetime.now(timezone.utc)
        base = {
            "level_m": mid,
            "rainfall_mm": 5.0,
            "soil_moisture": 0.40,
            "rate_of_change": 0.0,
            "hour": float(now.hour),
            "is_monsoon": 1.0 if now.month in (6, 7, 8, 9) else 0.0,
        }

    # Add small noise to simulate live sensor
    features = {
        "level_m": base["level_m"] + np.random.normal(0, 0.05),
        "rainfall_mm": max(0, base.get("rainfall_mm", 5.0) + np.random.normal(0, 1.0)),
        "soil_moisture": np.clip(
            base.get("soil_moisture", 0.4) + np.random.normal(0, 0.02), 0, 1
        ),
        "rate_of_change": base.get("rate_of_change", 0.0) + np.random.normal(0, 0.01),
        "hour": float(datetime.now(timezone.utc).hour),
        "is_monsoon": base.get("is_monsoon", 0.0),
    }
    return features


# ══════════════════════════════════════════════════════════════════════════
# Cloud sync (best-effort, non-blocking)
# ══════════════════════════════════════════════════════════════════════════

def try_cloud_sync_async(
    cache: OfflineCache,
    config: Dict[str, Any],
) -> None:
    """Best-effort sync of unsynced readings to cloud API (non-blocking)."""
    cloud_cfg = config.get("cloud_sync", {})
    if not cloud_cfg.get("enabled", False):
        return

    def _sync():
        unsynced = cache.get_unsynced(limit=20)
        if not unsynced:
            return
        endpoint = cloud_cfg.get("endpoint", "")
        try:
            import httpx

            for reading in unsynced:
                resp = httpx.post(
                    endpoint,
                    json=reading["features"],
                    timeout=5.0,
                )
                if resp.status_code < 300:
                    cache.mark_synced([reading["id"]])
            logger.debug("cloud_sync_complete", synced=len(unsynced))
        except ImportError:
            logger.debug("httpx_not_installed_skip_cloud_sync")
        except Exception as exc:
            logger.debug("cloud_sync_failed", error=str(exc))

    threading.Thread(target=_sync, daemon=True, name="cloud-sync").start()


# ══════════════════════════════════════════════════════════════════════════
# Demo mode — simulate rising water
# ══════════════════════════════════════════════════════════════════════════

def generate_demo_readings(config: Dict[str, Any]) -> list[Dict[str, float]]:
    """Generate a time series that ramps from normal to flood over *duration*.

    Uses a sigmoid curve to model the flood onset, matching the demo
    parameters in the node config.
    """
    demo = config.get("demo", {})
    duration = demo.get("duration_sec", 300)
    trigger_at = demo.get("trigger_at_sec", 180)
    poll = config.get("poll_interval_sec", 30)

    start_level = demo.get("start_level_m", 3.0)
    peak_level = demo.get("peak_level_m", 7.0)
    rain_start = demo.get("rainfall_start_mm", 5.0)
    rain_peak = demo.get("rainfall_peak_mm", 80.0)
    soil_start = demo.get("soil_moisture_start", 0.40)
    soil_peak = demo.get("soil_moisture_peak", 0.90)

    n_steps = max(1, duration // poll)
    readings: list[Dict[str, float]] = []

    now = datetime.now(timezone.utc)

    for i in range(n_steps):
        t = i * poll  # elapsed seconds
        # Sigmoid centred at trigger_at
        progress = 1.0 / (1.0 + math.exp(-0.05 * (t - trigger_at)))

        level = start_level + (peak_level - start_level) * progress
        rainfall = rain_start + (rain_peak - rain_start) * progress
        soil = soil_start + (soil_peak - soil_start) * progress

        # Rate of change (derivative of sigmoid × amplitude)
        d_progress = progress * (1.0 - progress) * 0.05
        roc = (peak_level - start_level) * d_progress

        # Add realistic noise
        level += np.random.normal(0, 0.08)
        rainfall = max(0, rainfall + np.random.normal(0, 2.0))
        soil = float(np.clip(soil + np.random.normal(0, 0.02), 0, 1))

        readings.append(
            {
                "level_m": round(level, 3),
                "rainfall_mm": round(rainfall, 1),
                "soil_moisture": round(soil, 3),
                "rate_of_change": round(roc, 4),
                "hour": float(now.hour),
                "is_monsoon": 1.0,  # demo assumes monsoon
            }
        )

    return readings


def run_demo(
    node_id: str,
    config: Dict[str, Any],
    oracle: OracleModel,
    escalator: AlertEscalator,
    cache: OfflineCache,
) -> None:
    """Run the demo simulation — rising water over configured duration."""
    readings = generate_demo_readings(config)
    poll = config.get("poll_interval_sec", 30)
    warning_thresh = config.get("warning_threshold", 0.60)
    demo_cfg = config.get("demo", {})
    duration = demo_cfg.get("duration_sec", 300)

    print(
        f"\n{_BOLD}{_CYAN}"
        f"╔══════════════════════════════════════════════════════════╗\n"
        f"║  ARGUS ACN Demo — {config.get('node_name', node_id):<38}║\n"
        f"║  Region:  {config.get('region', '?'):<46}║\n"
        f"║  Model:   {oracle.backend:<46}║\n"
        f"║  Duration: {duration}s  |  Poll: {poll}s  |  Steps: {len(readings):<11}║\n"
        f"║  Warning threshold: {warning_thresh:<36}║\n"
        f"╚══════════════════════════════════════════════════════════╝"
        f"{_RESET}\n"
    )

    for i, features in enumerate(readings):
        elapsed_sec = i * poll
        elapsed_str = f"{elapsed_sec // 60}m{elapsed_sec % 60:02d}s"

        # ORACLE inference
        risk_score = oracle.predict(features)

        # Console status line
        bar_len = 30
        filled = int(risk_score * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)

        if risk_score >= config.get("emergency_threshold", 0.82):
            colour = "\033[91m"  # red
        elif risk_score >= warning_thresh:
            colour = "\033[93m"  # yellow
        else:
            colour = _GREEN

        print(
            f"{_DIM}[{elapsed_str}]{_RESET}  "
            f"Level: {features['level_m']:5.2f}m  "
            f"Rain: {features['rainfall_mm']:5.1f}mm  "
            f"Soil: {features['soil_moisture']:.2f}  "
            f"RoC: {features['rate_of_change']:+.3f}  "
            f"Risk: {colour}{risk_score:.4f}{_RESET} {colour}|{bar}|{_RESET}"
        )

        # Escalate if above warning
        if risk_score > warning_thresh:
            escalator.escalate(risk_score, features)
        else:
            cache.store_reading(features, risk_score, "NORMAL")

        # Cloud sync attempt
        try_cloud_sync_async(cache, config)

        # Sleep (compressed for demo: ~2s per step instead of real poll_interval)
        time.sleep(2.0)

    # Summary
    stats = cache.stats()
    print(
        f"\n{_BOLD}{_CYAN}Demo complete.{_RESET}  "
        f"Readings: {stats['total_readings']}  |  "
        f"Unsynced: {stats['unsynced']}  |  "
        f"DB: {stats['db_file']}\n"
    )


# ══════════════════════════════════════════════════════════════════════════
# Normal operation loop
# ══════════════════════════════════════════════════════════════════════════

def run_loop(
    node_id: str,
    config: Dict[str, Any],
    oracle: OracleModel,
    escalator: AlertEscalator,
    cache: OfflineCache,
) -> None:
    """Infinite loop — no internet required."""
    poll = config.get("poll_interval_sec", 30)
    warning_thresh = config.get("warning_threshold", 0.60)

    print(
        f"\n{_BOLD}{_CYAN}ACN Node '{node_id}' running  "
        f"(poll every {poll}s, Ctrl+C to stop){_RESET}\n"
    )

    try:
        while True:
            # 1. Sensor reading (or cached fallback)
            features = get_sensor_reading_or_cache(cache, config)

            # 2. ORACLE inference
            risk_score = oracle.predict(features)

            # 3. Threshold evaluation → escalate
            if risk_score > warning_thresh:
                escalator.escalate(risk_score, features)
            else:
                cache.store_reading(features, risk_score, "NORMAL")
                logger.debug(
                    "reading_normal",
                    node=node_id,
                    risk_score=round(risk_score, 4),
                    level_m=round(features["level_m"], 2),
                )

            # 4. Cloud sync (best-effort)
            try_cloud_sync_async(cache, config)

            time.sleep(poll)

    except KeyboardInterrupt:
        print(f"\n{_DIM}ACN node '{node_id}' stopped by user.{_RESET}")
    finally:
        cache.close()


# ══════════════════════════════════════════════════════════════════════════
# CLI entry point
# ══════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ARGUS Autonomous Crisis Node — offline flood monitor",
    )
    parser.add_argument(
        "--node",
        default="majuli",
        choices=["majuli", "himachal"],
        help="Node profile to load (default: majuli)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demo simulation (rising water over 5 minutes)",
    )
    parser.add_argument(
        "--model-dir",
        default="./models",
        help="Directory containing ORACLE model files",
    )
    parser.add_argument(
        "--data-dir",
        default="./data",
        help="Directory for SQLite cache files",
    )
    args = parser.parse_args()

    # Load config
    config = load_node_config(args.node)
    node_id = config.get("node_id", args.node)

    # Initialise components
    oracle = OracleModel(
        model_dir=args.model_dir,
        tflite_name=config.get("oracle_model", f"oracle_{node_id}.tflite"),
        fallback_name=config.get("oracle_fallback", f"xgboost_{node_id}.joblib"),
        node_id=node_id,
    )

    cache = OfflineCache(
        node_id=node_id,
        db_dir=args.data_dir,
        max_readings=config.get("max_cache_readings", 500),
    )

    siren = LoRaSirenSim(
        node_id=node_id,
        duration_sec=config.get("escalation", {}).get("siren_duration_sec", 10),
    )

    escalator = AlertEscalator(
        node_id=node_id,
        config=config,
        cache=cache,
        siren=siren,
    )

    # Run
    if args.demo:
        run_demo(node_id, config, oracle, escalator, cache)
    else:
        run_loop(node_id, config, oracle, escalator, cache)


if __name__ == "__main__":
    main()
