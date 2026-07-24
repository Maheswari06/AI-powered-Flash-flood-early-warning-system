"""Temporal feature computation.

Operates on the sliding-window ring buffers in FeatureStore
to produce TemporalFeatures for a given station.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

import numpy as np
import structlog

from shared.config import get_settings
from shared.models.feature_engine import TemporalFeatures
from shared.models.ingestion import GaugeReading, WeatherData
from shared.models.cv_gauging import VirtualGaugeReading

logger = structlog.get_logger(__name__)
settings = get_settings()


def _safe_mean(vals: List[float]) -> float:
    """Return mean of a list, or 0.0 if empty."""
    return float(np.mean(vals)) if vals else 0.0


def _safe_max(vals: List[float]) -> float:
    """Return max of a list, or 0.0 if empty."""
    return float(np.max(vals)) if vals else 0.0


def _filter_by_window(
    readings: list,
    now: datetime,
    window: timedelta,
    ts_attr: str = "timestamp",
) -> list:
    """Filter readings to those within [now - window, now]."""
    cutoff = now - window
    return [r for r in readings if getattr(r, ts_attr) >= cutoff]


def compute_temporal_features(
    station_id: str,
    now: datetime,
    gauge_readings: List[GaugeReading],
    weather_readings: List[WeatherData],
    cv_readings: List[VirtualGaugeReading],
) -> TemporalFeatures:
    """Compute time-series derived features from raw sensor buffers.

    Args:
        station_id: Target station identifier.
        now: Current computation timestamp.
        gauge_readings: Raw gauge observations (sorted chronologically).
        weather_readings: Raw weather observations near this station.
        cv_readings: CV virtual gauge readings for the paired camera.

    Returns:
        TemporalFeatures populated with rolling statistics.
    """
    # ── Gauge features (1 h window) ──────────────────────────
    g1h = _filter_by_window(gauge_readings, now, timedelta(hours=1))
    levels_1h = [g.level_m for g in g1h]
    flows_1h = [g.flow_cumecs for g in g1h]

    level_mean_1h = _safe_mean(levels_1h)
    level_max_1h = _safe_max(levels_1h)

    # Delta: latest minus earliest in window
    level_delta_1h = (levels_1h[-1] - levels_1h[0]) if len(levels_1h) >= 2 else 0.0
    level_rate_of_change = level_delta_1h  # per hour (window = 1 h)

    flow_mean_1h = _safe_mean(flows_1h) if flows_1h else None
    flow_delta_1h = (flows_1h[-1] - flows_1h[0]) if len(flows_1h) >= 2 else None

    # ── Rainfall features ────────────────────────────────────
    w1h = _filter_by_window(weather_readings, now, timedelta(hours=1))
    w3h = _filter_by_window(weather_readings, now, timedelta(hours=3))
    w6h = _filter_by_window(weather_readings, now, timedelta(hours=6))
    w24h = _filter_by_window(weather_readings, now, timedelta(hours=24))

    rain_1h = [w.rainfall_mm_hr for w in w1h]
    rainfall_cumulative_3h = sum(w.rainfall_mm_hr for w in w3h) * (5.0 / 60.0)  # 5-min interval → mm
    rainfall_cumulative_6h = sum(w.rainfall_mm_hr for w in w6h) * (5.0 / 60.0)
    rainfall_cumulative_24h = sum(w.rainfall_mm_hr for w in w24h) * (5.0 / 60.0)
    rainfall_intensity_max_1h = _safe_max(rain_1h)

    # ── CV velocity (30 min) ─────────────────────────────────
    cv30m = _filter_by_window(cv_readings, now, timedelta(minutes=30))
    velocities = [c.velocity_ms for c in cv30m]
    velocity_mean_30m = _safe_mean(velocities) if velocities else None
    velocity_max_30m = _safe_max(velocities) if velocities else None

    return TemporalFeatures(
        station_id=station_id,
        timestamp=now,
        level_mean_1h=round(level_mean_1h, 3),
        level_max_1h=round(level_max_1h, 3),
        level_delta_1h=round(level_delta_1h, 3),
        level_rate_of_change=round(level_rate_of_change, 3),
        rainfall_cumulative_3h=round(rainfall_cumulative_3h, 2),
        rainfall_cumulative_6h=round(rainfall_cumulative_6h, 2),
        rainfall_cumulative_24h=round(rainfall_cumulative_24h, 2),
        rainfall_intensity_max_1h=round(rainfall_intensity_max_1h, 2),
        flow_mean_1h=round(flow_mean_1h, 2) if flow_mean_1h is not None else None,
        flow_delta_1h=round(flow_delta_1h, 2) if flow_delta_1h is not None else None,
        velocity_mean_30m=round(velocity_mean_30m, 3) if velocity_mean_30m is not None else None,
        velocity_max_30m=round(velocity_max_30m, 3) if velocity_max_30m is not None else None,
    )
