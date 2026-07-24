"""SHAP explainer for XGBoost predictions.

Produces ranked feature-contribution explanations so that
downstream consumers (dashboard, alert dispatcher) can
display *why* a flood risk was raised.
"""

from __future__ import annotations

from typing import List

import numpy as np
import structlog

from shared.config import get_settings
from shared.models.feature_engine import FeatureVector
from shared.models.prediction import FloodPrediction, SHAPExplanation

logger = structlog.get_logger(__name__)
settings = get_settings()


class SHAPExplainer:
    """Wraps SHAP TreeExplainer for the XGBoost model."""

    def __init__(self, predictor) -> None:
        self._predictor = predictor
        self._explainer = None
        self._try_init()

    def _try_init(self) -> None:
        """Attempt to initialise SHAP explainer from the loaded model."""
        if not self._predictor.is_loaded or self._predictor.model is None:
            logger.info("shap_using_heuristic_fallback")
            return
        try:
            import shap
            self._explainer = shap.TreeExplainer(self._predictor.model)
            logger.info("shap_explainer_loaded")
        except ImportError:
            logger.warning("shap_not_installed_using_heuristic")
        except Exception as exc:
            logger.warning("shap_init_failed", error=str(exc))

    def explain(self, fv: FeatureVector, prediction: FloodPrediction) -> List[SHAPExplanation]:
        """Compute SHAP explanations for a prediction.

        Returns top-k features sorted by absolute SHAP value.
        Falls back to a heuristic ranking when SHAP is unavailable.
        """
        top_k = settings.SHAP_TOP_K

        if self._explainer is not None:
            return self._explain_with_shap(fv, top_k)
        else:
            return self._explain_heuristic(fv, top_k)

    # ── SHAP-based ───────────────────────────────────────────
    def _explain_with_shap(self, fv: FeatureVector, top_k: int) -> List[SHAPExplanation]:
        """Use real SHAP values from TreeExplainer."""
        import xgboost as xgb

        X = self._predictor._feature_vector_to_array(fv)
        dmat = xgb.DMatrix(X, feature_names=self._predictor.feature_names)
        shap_values = self._explainer.shap_values(dmat)

        if isinstance(shap_values, list):
            shap_values = shap_values[0]

        sv = shap_values.flatten()
        feature_values = X.flatten()
        abs_sv = np.abs(sv)
        top_indices = np.argsort(abs_sv)[::-1][:top_k]

        explanations = []
        for rank, idx in enumerate(top_indices, start=1):
            explanations.append(
                SHAPExplanation(
                    feature_name=self._predictor.feature_names[idx],
                    shap_value=round(float(sv[idx]), 4),
                    feature_value=round(float(feature_values[idx]), 4),
                    rank=rank,
                )
            )
        return explanations

    # ── Heuristic fallback ───────────────────────────────────
    def _explain_heuristic(self, fv: FeatureVector, top_k: int) -> List[SHAPExplanation]:
        """Rank features by simple normalised importance when SHAP is unavailable."""
        t = fv.temporal
        s = fv.spatial

        candidates = [
            ("rainfall_cumulative_6h", t.rainfall_cumulative_6h, t.rainfall_cumulative_6h / 150.0),
            ("level_delta_1h", t.level_delta_1h, t.level_delta_1h / 1.0),
            ("level_rate_of_change", t.level_rate_of_change, t.level_rate_of_change / 0.5),
            ("rainfall_intensity_max_1h", t.rainfall_intensity_max_1h, t.rainfall_intensity_max_1h / 50.0),
            ("num_upstream_alerts", float(s.num_upstream_alerts), s.num_upstream_alerts / 3.0),
            ("cv_depth_m", fv.cv_depth_m or 0.0, (fv.cv_depth_m or 0.0) / 5.0),
            ("rainfall_cumulative_24h", t.rainfall_cumulative_24h, t.rainfall_cumulative_24h / 300.0),
            ("upstream_level_max", s.upstream_level_max or 0.0, (s.upstream_level_max or 0.0) / 8.0),
            ("level_max_1h", t.level_max_1h, t.level_max_1h / 6.0),
            ("cv_velocity_ms", fv.cv_velocity_ms or 0.0, (fv.cv_velocity_ms or 0.0) / 3.0),
        ]

        # Sort by pseudo-importance descending
        candidates.sort(key=lambda c: abs(c[2]), reverse=True)

        explanations = []
        for rank, (name, value, pseudo_shap) in enumerate(candidates[:top_k], start=1):
            explanations.append(
                SHAPExplanation(
                    feature_name=name,
                    shap_value=round(float(pseudo_shap), 4),
                    feature_value=round(float(value), 4),
                    rank=rank,
                )
            )
        return explanations
