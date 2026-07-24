"""Spatial feature computation.

Computes cross-station / neighbourhood features using the
station topology graph (upstream/downstream adjacency).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import numpy as np
import structlog

from shared.config import get_settings
from shared.models.feature_engine import SpatialFeatures
from shared.models.ingestion import GaugeReading, WeatherData

logger = structlog.get_logger(__name__)
settings = get_settings()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance between two lat/lon points in km."""
    R = 6371.0
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def compute_spatial_features(
    station_id: str,
    now: datetime,
    topology: Dict,
    gauge_buffers: Dict[str, list],
    weather_buffers: Dict[str, list],
) -> SpatialFeatures:
    """Compute neighbourhood / cross-station features.

    Args:
        station_id: Target station.
        now: Current timestamp.
        topology: Station adjacency graph loaded from FeatureStore.
        gauge_buffers: Mapping station_id → list of GaugeReading.
        weather_buffers: Mapping grid_cell → list of WeatherData.

    Returns:
        SpatialFeatures with upstream aggregates and distance-weighted level.
    """
    node = topology.get(station_id, {})
    upstream_ids: List[str] = node.get("upstream", []) if isinstance(node, dict) else []
    target_lat = node.get("lat", 0.0) if isinstance(node, dict) else 0.0
    target_lon = node.get("lon", 0.0) if isinstance(node, dict) else 0.0

    cutoff = now - timedelta(hours=1)

    upstream_levels: List[float] = []
    upstream_flows: List[float] = []
    upstream_rainfalls: List[float] = []
    num_alerts = 0
    weighted_level_sum = 0.0
    weight_sum = 0.0

    for uid in upstream_ids:
        # Gauge
        readings = gauge_buffers.get(uid, [])
        recent = [r for r in readings if r.timestamp >= cutoff]
        if recent:
            latest = recent[-1]
            upstream_levels.append(latest.level_m)
            upstream_flows.append(latest.flow_cumecs)
            # Simple alert heuristic: level > 5 m
            if latest.level_m > 5.0:
                num_alerts += 1

            # Distance weighting
            u_node = topology.get(uid, {})
            u_lat = u_node.get("lat", 0.0) if isinstance(u_node, dict) else 0.0
            u_lon = u_node.get("lon", 0.0) if isinstance(u_node, dict) else 0.0
            dist = _haversine_km(target_lat, target_lon, u_lat, u_lon)
            w = 1.0 / max(dist, 0.1)
            weighted_level_sum += latest.level_m * w
            weight_sum += w

    # Upstream rainfall — check nearby weather cells for each upstream station
    for uid in upstream_ids:
        u_node = topology.get(uid, {})
        if isinstance(u_node, dict):
            cell_key = f"{u_node.get('lat', 0):.1f}_{u_node.get('lon', 0):.1f}"
            w_buf = weather_buffers.get(cell_key, [])
            recent_w = [w for w in w_buf if w.timestamp >= cutoff]
            if recent_w:
                upstream_rainfalls.append(recent_w[-1].rainfall_mm_hr)

    # Catchment-level 6 h rainfall
    cutoff_6h = now - timedelta(hours=6)
    catchment_rain = []
    for cell_key, wbuf in weather_buffers.items():
        r6 = [w.rainfall_mm_hr for w in wbuf if w.timestamp >= cutoff_6h]
        if r6:
            catchment_rain.extend(r6)
    catchment_avg_6h = float(np.mean(catchment_rain)) * (5.0 / 60.0) if catchment_rain else None

    return SpatialFeatures(
        station_id=station_id,
        timestamp=now,
        upstream_level_mean=round(float(np.mean(upstream_levels)), 3) if upstream_levels else None,
        upstream_level_max=round(float(np.max(upstream_levels)), 3) if upstream_levels else None,
        upstream_flow_mean=round(float(np.mean(upstream_flows)), 2) if upstream_flows else None,
        upstream_rainfall_mean=round(float(np.mean(upstream_rainfalls)), 2) if upstream_rainfalls else None,
        num_upstream_alerts=num_alerts,
        catchment_avg_rainfall_6h=round(catchment_avg_6h, 2) if catchment_avg_6h is not None else None,
        distance_weighted_level=round(weighted_level_sum / weight_sum, 3) if weight_sum > 0 else None,
    )
