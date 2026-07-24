"""SHAP TreeExplainer with human-readable output.

Pre-computes ``shap.TreeExplainer(model)`` at service startup
(not per request) for fast inference.

Outputs top-N factors as human-readable strings with direction
(INCREASES_RISK / DECREASES_RISK) and contribution percentages.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import numpy as np
import structlog

from services.prediction.fast_track.xgboost_predictor import FEATURES

logger = structlog.get_logger(__name__)

# ── Human-readable labels for each feature ────────────────────────────────
FEATURE_LABELS: Dict[str, str] = {
    "level_1hr_mean": "Average water level (1hr)",
    "level_3hr_mean": "Average water level (3hr)",
    "level_6hr_mean": "Average water level (6hr)",
    "level_24hr_mean": "Average water level (24hr)",
    "level_1hr_max": "Peak water level (1hr)",
    "rate_of_change_1hr": "Water level rise rate (1hr)",
    "rate_of_change_3hr": "Water level rise rate (3hr)",
    "cumulative_rainfall_6hr": "Rainfall intensity (6hr)",
    "cumulative_rainfall_24hr": "Cumulative rainfall (24hr)",
    "soil_moisture_index": "Soil saturation index",
    "antecedent_moisture_index": "Prior rainfall accumulation",
    "upstream_risk_score": "Upstream river level rise",
    "basin_connectivity_score": "Basin connectivity",
    "hour_of_day": "Time of day",
    "day_of_year": "Day of year",
    "is_monsoon_season": "Monsoon season",
}

# ── Unit / value formatters for human-readable display ────────────────────
_VALUE_FORMATTERS: Dict[str, str] = {
    "level_1hr_mean": "{:.2f}m",
    "level_3hr_mean": "{:.2f}m",
    "level_6hr_mean": "{:.2f}m",
    "level_24hr_mean": "{:.2f}m",
    "level_1hr_max": "{:.2f}m",
    "rate_of_change_1hr": "{:.2f}m/hr",
    "rate_of_change_3hr": "{:.2f}m/hr",
    "cumulative_rainfall_6hr": "{:.0f}mm",
    "cumulative_rainfall_24hr": "{:.0f}mm",
    "soil_moisture_index": "{:.0%} saturated",
    "antecedent_moisture_index": "{:.1f}mm",
    "upstream_risk_score": "{:.0%} risk",
    "basin_connectivity_score": "{:.2f}",
    "hour_of_day": "{:.0f}h",
    "day_of_year": "day {:.0f}",
    "is_monsoon_season": "{}",
}


class SHAPExplanation:
    """Single SHAP factor contribution."""

    __slots__ = ("factor", "contribution_pct", "value", "direction", "feature_name", "shap_value")

    def __init__(
        self,
        factor: str,
        contribution_pct: int,
        value: str,
        direction: str,
        feature_name: str,
        shap_value: float,
    ) -> None:
        self.factor = factor
        self.contribution_pct = contribution_pct
        self.value = value
        self.direction = direction
        self.feature_name = feature_name
        self.shap_value = shap_value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "factor": self.factor,
            "contribution_pct": self.contribution_pct,
            "value": self.value,
            "direction": self.direction,
            "feature_name": self.feature_name,
            "shap_value": round(self.shap_value, 4),
        }


class SHAPExplainerV2:
    """SHAP TreeExplainer wrapper with human-readable output.

    Pre-computes the TreeExplainer at startup so that per-request
    ``explain()`` calls are fast (no model re-parsing).

    Usage::

        explainer = SHAPExplainerV2(model)
        factors = explainer.explain(features_dict)
    """

    def __init__(self, model: Any, top_n: int = 3) -> None:
        """
        Args:
            model: Trained XGBClassifier (or None for heuristic fallback).
            top_n: Number of top factors to return.
        """
        self._model = model
        self.top_n = int(os.getenv("SHAP_TOP_N", str(top_n)))
        self._explainer = None
        self._init_explainer()

    def _init_explainer(self) -> None:
        """Pre-compute SHAP TreeExplainer (one-time at startup)."""
        if self._model is None:
            logger.info("shap_explainer_using_heuristic_no_model")
            return
        try:
            import shap
            self._explainer = shap.TreeExplainer(self._model)
            logger.info("shap_tree_explainer_precomputed")
        except ImportError:
            logger.warning("shap_not_installed_using_heuristic")
        except Exception as exc:
            logger.warning("shap_init_error", error=str(exc))

    def explain(self, features: Dict[str, float]) -> List[SHAPExplanation]:
        """Generate top-N human-readable SHAP explanations.

        Args:
            features: Dict mapping feature name → float value.

        Returns:
            List of SHAPExplanation objects sorted by abs(contribution).
        """
        if self._explainer is not None:
            return self._explain_shap(features)
        return self._explain_heuristic(features)

    # ── Real SHAP ─────────────────────────────────────────────────────

    def _explain_shap(self, features: Dict[str, float]) -> List[SHAPExplanation]:
        """Use pre-computed TreeExplainer for real SHAP values."""
        X = np.array(
            [features.get(f, 0.0) for f in FEATURES],
            dtype=np.float32,
        ).reshape(1, -1)

        shap_values = self._explainer.shap_values(X)

        # Handle multi-output (take class-1 for binary)
        if isinstance(shap_values, list):
            sv = shap_values[1].flatten() if len(shap_values) > 1 else shap_values[0].flatten()
        elif shap_values.ndim == 3:
            sv = shap_values[0, :, 1]
        else:
            sv = shap_values.flatten()

        feature_values = X.flatten()
        abs_sv = np.abs(sv)
        total_abs = float(abs_sv.sum()) or 1.0

        # Top N by absolute SHAP value
        top_indices = np.argsort(abs_sv)[::-1][: self.top_n]

        results: List[SHAPExplanation] = []
        for idx in top_indices:
            fname = FEATURES[idx]
            shap_val = float(sv[idx])
            fval = float(feature_values[idx])
            contribution_pct = int(round(abs(shap_val) / total_abs * 100))

            results.append(SHAPExplanation(
                factor=FEATURE_LABELS.get(fname, fname),
                contribution_pct=contribution_pct,
                value=self._format_value(fname, fval),
                direction="INCREASES_RISK" if shap_val > 0 else "DECREASES_RISK",
                feature_name=fname,
                shap_value=shap_val,
            ))

        return results

    # ── Heuristic fallback ────────────────────────────────────────────

    def _explain_heuristic(self, features: Dict[str, float]) -> List[SHAPExplanation]:
        """Rank features by normalised pseudo-importance."""
        # Weight each feature by a hand-tuned importance proxy
        importance_weights: Dict[str, float] = {
            "cumulative_rainfall_6hr": 0.18,
            "upstream_risk_score": 0.16,
            "rate_of_change_1hr": 0.14,
            "soil_moisture_index": 0.12,
            "level_1hr_max": 0.10,
            "cumulative_rainfall_24hr": 0.08,
            "antecedent_moisture_index": 0.07,
            "rate_of_change_3hr": 0.05,
            "level_1hr_mean": 0.04,
            "basin_connectivity_score": 0.03,
            "is_monsoon_season": 0.03,
        }

        scored: List[tuple] = []
        for fname in FEATURES:
            fval = features.get(fname, 0.0)
            weight = importance_weights.get(fname, 0.01)
            # Pseudo-SHAP = weight * normalised value
            pseudo = weight * min(abs(fval) / max(abs(fval), 1.0), 1.0)
            scored.append((fname, fval, pseudo))

        scored.sort(key=lambda x: abs(x[2]), reverse=True)
        total = sum(abs(s[2]) for s in scored) or 1.0

        results: List[SHAPExplanation] = []
        for fname, fval, pseudo in scored[: self.top_n]:
            results.append(SHAPExplanation(
                factor=FEATURE_LABELS.get(fname, fname),
                contribution_pct=int(round(abs(pseudo) / total * 100)),
                value=self._format_value(fname, fval),
                direction="INCREASES_RISK" if pseudo > 0 else "DECREASES_RISK",
                feature_name=fname,
                shap_value=round(pseudo, 4),
            ))

        return results

    # ── Formatting helpers ────────────────────────────────────────────

    @staticmethod
    def _format_value(feature_name: str, value: float) -> str:
        """Format a feature value with appropriate units."""
        if feature_name == "is_monsoon_season":
            return "Yes" if value >= 0.5 else "No"
        fmt = _VALUE_FORMATTERS.get(feature_name, "{:.2f}")
        try:
            return fmt.format(value)
        except (ValueError, IndexError):
            return str(round(value, 2))

    def update_model(self, model: Any) -> None:
        """Hot-swap the underlying model and re-init the explainer."""
        self._model = model
        self._init_explainer()
