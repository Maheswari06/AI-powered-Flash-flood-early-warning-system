"""Feature vector builder.

Combines temporal + spatial features with CV and meta/calendar
features into a complete FeatureVector ready for the prediction service.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from shared.models.feature_engine import FeatureVector, SpatialFeatures, TemporalFeatures
from shared.models.cv_gauging import VirtualGaugeReading

logger = structlog.get_logger(__name__)


def build_feature_vector(
    station_id: str,
    now: datetime,
    temporal: TemporalFeatures,
    spatial: SpatialFeatures,
    latest_cv: VirtualGaugeReading | None = None,
) -> FeatureVector:
    """Assemble a complete FeatureVector from sub-components.

    Args:
        station_id: Target station identifier.
        now: Timestamp for this feature vector.
        temporal: Pre-computed temporal features.
        spatial: Pre-computed spatial features.
        latest_cv: Most recent CV reading for the co-located camera (may be None).

    Returns:
        Fully populated FeatureVector.
    """
    # Calendar / meta features
    is_monsoon = now.month in (6, 7, 8, 9)
    hour_of_day = now.hour
    day_of_year = now.timetuple().tm_yday

    # Antecedent Precipitation Index (simplified 5-day weighted sum)
    # API = sum( k^i * P_i ) for i = 0..4, k = 0.85
    # We approximate from 24h cumulative scaled up
    api_estimate = temporal.rainfall_cumulative_24h * 2.5 if temporal.rainfall_cumulative_24h else None

    fv = FeatureVector(
        station_id=station_id,
        timestamp=now,
        temporal=temporal,
        spatial=spatial,
        cv_depth_m=latest_cv.depth_m if latest_cv else None,
        cv_velocity_ms=latest_cv.velocity_ms if latest_cv else None,
        cv_confidence=latest_cv.confidence_score if latest_cv else None,
        soil_moisture_pct=None,  # Phase 2: integrate soil moisture sensor data
        antecedent_precip_index=round(api_estimate, 2) if api_estimate is not None else None,
        is_monsoon=is_monsoon,
        hour_of_day=hour_of_day,
        day_of_year=day_of_year,
        feature_version="1.0.0",
    )

    logger.info(
        "feature_vector_built",
        station=station_id,
        level_delta=temporal.level_delta_1h,
        rain_6h=temporal.rainfall_cumulative_6h,
        cv_depth=fv.cv_depth_m,
    )
    return fv
