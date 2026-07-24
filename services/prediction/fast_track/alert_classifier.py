"""Alert classifier — maps probability + adaptive threshold → alert level.

Also assigns a confidence band (LOW / MEDIUM / HIGH) based on
how far the probability is from the nearest threshold boundary.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict

import structlog

from services.prediction.fast_track.threshold_engine import AdaptiveThreshold

logger = structlog.get_logger(__name__)


class AlertLevel(str, Enum):
    """Flood alert classification levels (NDMA aligned)."""

    NORMAL = "NORMAL"
    ADVISORY = "ADVISORY"
    WATCH = "WATCH"
    WARNING = "WARNING"
    EMERGENCY = "EMERGENCY"


class ConfidenceBand(str, Enum):
    """Prediction confidence band."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AlertClassifier:
    """Classifies a flood probability into an alert level
    using adaptive thresholds.

    Usage::

        classifier = AlertClassifier()
        level, confidence = classifier.classify(probability=0.65, thresholds=thresholds)
    """

    def classify(
        self,
        probability: float,
        thresholds: AdaptiveThreshold,
    ) -> tuple[AlertLevel, ConfidenceBand]:
        """Map probability + adaptive thresholds → (AlertLevel, ConfidenceBand).

        Args:
            probability: Flood probability [0.0, 1.0].
            thresholds:  Current adaptive thresholds.

        Returns:
            Tuple of (AlertLevel, ConfidenceBand).
        """
        # Classify level (check from highest down)
        if probability >= thresholds.emergency:
            level = AlertLevel.EMERGENCY
        elif probability >= thresholds.warning:
            level = AlertLevel.WARNING
        elif probability >= thresholds.watch:
            level = AlertLevel.WATCH
        elif probability >= thresholds.advisory:
            level = AlertLevel.ADVISORY
        else:
            level = AlertLevel.NORMAL

        # Confidence: how far probability is from nearest threshold boundary
        confidence = self._compute_confidence(probability, thresholds)

        logger.debug(
            "alert_classified",
            probability=round(probability, 4),
            level=level.value,
            confidence=confidence.value,
        )

        return level, confidence

    @staticmethod
    def _compute_confidence(
        probability: float,
        thresholds: AdaptiveThreshold,
    ) -> ConfidenceBand:
        """Confidence is HIGH when probability is far from any threshold boundary,
        LOW when it's near a boundary (ambiguous classification).

        The margin is measured as the minimum distance to any threshold.
        """
        boundaries = [
            thresholds.advisory,
            thresholds.watch,
            thresholds.warning,
            thresholds.emergency,
        ]
        min_margin = min(abs(probability - b) for b in boundaries)

        if min_margin >= 0.10:
            return ConfidenceBand.HIGH
        elif min_margin >= 0.04:
            return ConfidenceBand.MEDIUM
        else:
            return ConfidenceBand.LOW

    def classify_to_dict(
        self,
        probability: float,
        thresholds: AdaptiveThreshold,
    ) -> Dict:
        """Convenience method returning a serialisable dict."""
        level, confidence = self.classify(probability, thresholds)
        return {
            "alert_level": level.value,
            "confidence": confidence.value,
            "probability": round(probability, 4),
            "thresholds": thresholds.to_dict(),
        }
