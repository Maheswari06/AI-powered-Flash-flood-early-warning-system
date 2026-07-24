"""Adaptive alert threshold engine.

Base thresholds follow NDMA (National Disaster Management Authority)
standard levels. Thresholds are lowered (easier to trigger) under
high-risk environmental conditions:

    - soil_moisture_index > 0.8  → ×0.85
    - is_monsoon_season          → ×0.90
    - antecedent_moisture_index > 0.6 → ×0.92

Adjustments are multiplicative. Minimum cap: 0.20.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple

import structlog

logger = structlog.get_logger(__name__)

# ── Base thresholds (NDMA standard) ───────────────────────────────────────
_BASE_ADVISORY  = 0.35
_BASE_WATCH     = 0.55
_BASE_WARNING   = 0.72
_BASE_EMERGENCY = 0.88
_MIN_THRESHOLD  = 0.20


class AdaptiveThreshold:
    """Container for adaptive alert thresholds with audit trail."""

    __slots__ = (
        "advisory", "watch", "warning", "emergency",
        "adjustment_reason", "adjustments_applied",
    )

    def __init__(
        self,
        advisory: float,
        watch: float,
        warning: float,
        emergency: float,
        adjustment_reason: str,
        adjustments_applied: List[str],
    ) -> None:
        self.advisory = advisory
        self.watch = watch
        self.warning = warning
        self.emergency = emergency
        self.adjustment_reason = adjustment_reason
        self.adjustments_applied = adjustments_applied

    def to_dict(self) -> Dict:
        return {
            "advisory": round(self.advisory, 4),
            "watch": round(self.watch, 4),
            "warning": round(self.warning, 4),
            "emergency": round(self.emergency, 4),
            "adjustment_reason": self.adjustment_reason,
            "adjustments_applied": self.adjustments_applied,
        }


class ThresholdEngine:
    """Computes adaptive alert thresholds based on current conditions.

    Usage::

        engine = ThresholdEngine()
        thresholds = engine.compute(
            soil_moisture_index=0.85,
            is_monsoon_season=True,
            antecedent_moisture_index=0.65,
        )
        # thresholds.warning → lowered from 0.72 to ~0.53
    """

    def __init__(
        self,
        base_advisory: float = _BASE_ADVISORY,
        base_watch: float = _BASE_WATCH,
        base_warning: float = _BASE_WARNING,
        base_emergency: float = _BASE_EMERGENCY,
        min_threshold: float = _MIN_THRESHOLD,
    ) -> None:
        self._base = {
            "advisory": base_advisory,
            "watch": base_watch,
            "warning": base_warning,
            "emergency": base_emergency,
        }
        self._min = min_threshold

    def compute(
        self,
        soil_moisture_index: float = 0.0,
        is_monsoon_season: bool = False,
        antecedent_moisture_index: float = 0.0,
    ) -> AdaptiveThreshold:
        """Compute adaptive thresholds given current environmental conditions.

        Args:
            soil_moisture_index: 0–1, current soil moisture fraction.
            is_monsoon_season:   True during Jun–Sep.
            antecedent_moisture_index: 0–1 normalised AMI.

        Returns:
            AdaptiveThreshold with adjusted levels and audit trail.
        """
        multiplier = 1.0
        adjustments: List[str] = []

        # ── Condition-based adjustments (multiplicative) ──────
        if soil_moisture_index > 0.8:
            multiplier *= 0.85
            adjustments.append(
                f"Soil moisture high ({soil_moisture_index:.0%}) → thresholds ×0.85"
            )

        if is_monsoon_season:
            multiplier *= 0.90
            adjustments.append("Monsoon season active → thresholds ×0.90")

        if antecedent_moisture_index > 0.6:
            multiplier *= 0.92
            adjustments.append(
                f"Antecedent moisture high ({antecedent_moisture_index:.2f}) → thresholds ×0.92"
            )

        # Apply multiplier with floor
        advisory  = max(self._base["advisory"]  * multiplier, self._min)
        watch     = max(self._base["watch"]     * multiplier, self._min)
        warning   = max(self._base["warning"]   * multiplier, self._min)
        emergency = max(self._base["emergency"] * multiplier, self._min)

        # Build reason string
        if adjustments:
            reason = "; ".join(adjustments)
        else:
            reason = "No adjustments — using NDMA base thresholds"

        logger.debug(
            "adaptive_thresholds_computed",
            multiplier=round(multiplier, 4),
            advisory=round(advisory, 4),
            watch=round(watch, 4),
            warning=round(warning, 4),
            emergency=round(emergency, 4),
        )

        return AdaptiveThreshold(
            advisory=round(advisory, 4),
            watch=round(watch, 4),
            warning=round(warning, 4),
            emergency=round(emergency, 4),
            adjustment_reason=reason,
            adjustments_applied=adjustments,
        )
