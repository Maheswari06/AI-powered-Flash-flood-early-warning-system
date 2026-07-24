"""Rolling-window feature construction.

For each gauge (real + virtual), computes features over
windows [1h, 3h, 6h, 24h]:

  - mean_level, max_level, rate_of_change
  - cumulative_rainfall, soil_moisture_proxy
  - upstream_risk_score (weighted avg of upstream gauge levels)
  - antecedent_moisture_index (exponential decay of 72 h rainfall)
  - soil_saturation_index (proxy formula)

Output: FeatureRow(village_id, timestamp, features: Dict[str, float])
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from services.feature_engine.schemas import FeatureRow, KalmanOutput, QualityFlag

logger = structlog.get_logger(__name__)

# Rolling window definitions (hours)
_WINDOWS = [1, 3, 6, 24]

# Antecedent moisture index: exponential decay constant k
_AMI_DECAY_K = 0.85
_AMI_LOOKBACK_HOURS = 72

# Soil saturation index constants
_SOIL_SAT_FIELD_CAPACITY = 0.35  # m³/m³
_SOIL_SAT_POROSITY = 0.45        # m³/m³


def _filter_window(
    readings: List[Tuple[datetime, float]],
    now: datetime,
    window_hours: int,
) -> List[float]:
    """Return values within [now - window, now]."""
    cutoff = now - timedelta(hours=window_hours)
    return [v for ts, v in readings if ts >= cutoff]


class FeatureBuilder:
    """Builds rolling-window feature vectors for real and virtual gauges.

    Usage::

        builder = FeatureBuilder(topology)
        row = builder.build(
            station_id="CWC-HP-MANDI",
            village_id="VIL-HP-MANDI",
            now=datetime.now(timezone.utc),
            level_history=[(ts1, 4.5), (ts2, 4.6), ...],
            rainfall_history=[(ts1, 12.0), ...],
            upstream_levels={"CWC-HP-PANDOH": 5.2, ...},
        )
    """

    def __init__(self, topology: Dict) -> None:
        """
        Args:
            topology: Station adjacency graph
                      {station_id: {upstream: [...], lat, lon, ...}}
        """
        self.topology = topology

    def build(
        self,
        station_id: str,
        village_id: str,
        now: datetime,
        level_history: List[Tuple[datetime, float]],
        rainfall_history: List[Tuple[datetime, float]],
        upstream_levels: Optional[Dict[str, float]] = None,
        soil_moisture_api: Optional[float] = None,
        quality_flag: QualityFlag = QualityFlag.GOOD,
    ) -> FeatureRow:
        """Compute the full feature set for one gauge at one timestamp.

        Args:
            station_id:       Gauge station identifier.
            village_id:       Associated village identifier.
            now:              Computation timestamp.
            level_history:    List of (timestamp, water_level_m) tuples.
            rainfall_history: List of (timestamp, rainfall_mm_hr) tuples.
            upstream_levels:  Current levels at upstream stations.
            soil_moisture_api: External soil moisture value (0–1) or None.
            quality_flag:     Aggregate quality from Kalman filter.

        Returns:
            FeatureRow ready for TimescaleDB insertion.
        """
        features: Dict[str, float] = {}

        # ── Rolling window level features ─────────────────────
        for w in _WINDOWS:
            vals = _filter_window(level_history, now, w)
            suffix = f"_{w}h"
            features[f"mean_level{suffix}"] = round(float(np.mean(vals)), 3) if vals else 0.0
            features[f"max_level{suffix}"] = round(float(np.max(vals)), 3) if vals else 0.0
            if len(vals) >= 2:
                features[f"rate_of_change{suffix}"] = round(
                    (vals[-1] - vals[0]) / max(w, 1), 4
                )
            else:
                features[f"rate_of_change{suffix}"] = 0.0

        # ── Rolling window rainfall features ──────────────────
        for w in _WINDOWS:
            rain_vals = _filter_window(rainfall_history, now, w)
            suffix = f"_{w}h"
            # Cumulative rainfall: sum(mm/hr) * interval_hours / n_readings
            # Approximate: sum * (interval / 60) assuming 5-min readings
            features[f"cumulative_rainfall{suffix}"] = round(
                sum(rain_vals) * (5.0 / 60.0), 2
            ) if rain_vals else 0.0

        # ── Soil moisture proxy ───────────────────────────────
        if soil_moisture_api is not None:
            features["soil_moisture_proxy"] = round(soil_moisture_api, 3)
        else:
            # Proxy: based on recent rainfall and exponential decay
            features["soil_moisture_proxy"] = round(
                self._compute_soil_moisture_proxy(rainfall_history, now), 3
            )

        # ── Antecedent Moisture Index (72 h exponential decay) ──
        features["antecedent_moisture_index"] = round(
            self._compute_ami(rainfall_history, now), 3
        )

        # ── Soil Saturation Index ─────────────────────────────
        features["soil_saturation_index"] = round(
            self._compute_soil_saturation(rainfall_history, now, soil_moisture_api), 3
        )

        # ── Basin graph: upstream risk score ──────────────────
        features["upstream_risk_score"] = round(
            self._compute_upstream_risk(station_id, upstream_levels), 3
        )

        # ── Calendar features ─────────────────────────────────
        features["hour_of_day"] = float(now.hour)
        features["day_of_year"] = float(now.timetuple().tm_yday)
        features["is_monsoon"] = 1.0 if now.month in (6, 7, 8, 9) else 0.0

        return FeatureRow(
            village_id=village_id,
            station_id=station_id,
            timestamp=now,
            features=features,
            quality=quality_flag,
        )

    # ── Private helpers ──────────────────────────────────────────────────

    @staticmethod
    def _compute_ami(
        rainfall_history: List[Tuple[datetime, float]],
        now: datetime,
    ) -> float:
        """Antecedent Moisture Index: exponential decay of past 72 h rainfall.

        AMI = Σ (k^i × P_i)  for i = 0..N  with k = 0.85
        where P_i are hourly rainfall totals going backward in time.
        """
        cutoff = now - timedelta(hours=_AMI_LOOKBACK_HOURS)
        recent = [(ts, v) for ts, v in rainfall_history if ts >= cutoff]
        if not recent:
            return 0.0

        # Bin into hourly buckets
        hourly: Dict[int, float] = {}
        for ts, v in recent:
            hours_ago = max(0, int((now - ts).total_seconds() / 3600))
            hourly[hours_ago] = hourly.get(hours_ago, 0.0) + v * (5.0 / 60.0)

        ami = 0.0
        for hours_ago, precip_mm in hourly.items():
            ami += (_AMI_DECAY_K ** hours_ago) * precip_mm
        return ami

    @staticmethod
    def _compute_soil_moisture_proxy(
        rainfall_history: List[Tuple[datetime, float]],
        now: datetime,
    ) -> float:
        """Proxy soil moisture from recent rainfall accumulation.

        Uses a simple exponential moving average of 48 h rainfall
        normalised to [0, 1] range.
        """
        cutoff = now - timedelta(hours=48)
        recent_rain = [v for ts, v in rainfall_history if ts >= cutoff]
        if not recent_rain:
            return 0.0
        cumulative = sum(recent_rain) * (5.0 / 60.0)  # mm
        # Saturated at ~200 mm cumulative
        return min(cumulative / 200.0, 1.0)

    @staticmethod
    def _compute_soil_saturation(
        rainfall_history: List[Tuple[datetime, float]],
        now: datetime,
        soil_moisture_api: Optional[float] = None,
    ) -> float:
        """Soil Saturation Index (SSI).

        SSI = θ / θ_s  where θ = soil moisture, θ_s = porosity.
        If API value not available, estimate from rainfall proxy.
        """
        if soil_moisture_api is not None:
            theta = soil_moisture_api * _SOIL_SAT_POROSITY
        else:
            cutoff = now - timedelta(hours=48)
            recent_rain = [v for ts, v in rainfall_history if ts >= cutoff]
            cumulative = sum(recent_rain) * (5.0 / 60.0) if recent_rain else 0.0
            # Rough conversion: mm rain → volumetric moisture
            theta = min(cumulative / 500.0 * _SOIL_SAT_POROSITY, _SOIL_SAT_POROSITY)
        return theta / _SOIL_SAT_POROSITY

    def _compute_upstream_risk(
        self,
        station_id: str,
        upstream_levels: Optional[Dict[str, float]],
    ) -> float:
        """Upstream risk score: distance-weighted average of upstream gauge levels,
        normalised against CWC danger level (6.0 m assumed for demo).

        Returns a score in [0, 1] range.
        """
        if not upstream_levels:
            return 0.0

        node = self.topology.get(station_id, {})
        upstream_ids = node.get("upstream", []) if isinstance(node, dict) else []
        if not upstream_ids:
            return 0.0

        target_lat = node.get("lat", 0.0) if isinstance(node, dict) else 0.0
        target_lon = node.get("lon", 0.0) if isinstance(node, dict) else 0.0

        danger_level = 6.0  # CWC danger threshold (demo)
        weighted_sum = 0.0
        weight_total = 0.0

        for uid in upstream_ids:
            level = upstream_levels.get(uid)
            if level is None:
                continue
            u_node = self.topology.get(uid, {})
            u_lat = u_node.get("lat", target_lat) if isinstance(u_node, dict) else target_lat
            u_lon = u_node.get("lon", target_lon) if isinstance(u_node, dict) else target_lon

            # Simple Euclidean distance proxy (degrees → ~111 km)
            dist = np.sqrt((target_lat - u_lat) ** 2 + (target_lon - u_lon) ** 2) * 111.0
            w = 1.0 / max(dist, 0.1)

            risk = min(level / danger_level, 1.0)
            weighted_sum += risk * w
            weight_total += w

        if weight_total == 0:
            return 0.0
        return weighted_sum / weight_total
