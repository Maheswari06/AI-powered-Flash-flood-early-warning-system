"""ORACLE TinyML model wrapper for Autonomous Crisis Node.

Attempts to load a TensorFlow Lite model for ultra-low-latency edge
inference.  Falls back to an XGBoost joblib model (same 6-feature
contract) when ``tflite_runtime`` is unavailable.

Input features (order-sensitive, length = 6):
    [level_m, rainfall_mm, soil_moisture, rate_of_change, hour, is_monsoon]

Output:
    risk_score ∈ [0.0, 1.0]

Inference budget: < 500 ms (warning logged if exceeded).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# Feature order expected by both TFLite and XGBoost models
FEATURES: List[str] = [
    "level_m",
    "rainfall_mm",
    "soil_moisture",
    "rate_of_change",
    "hour",
    "is_monsoon",
]

_INFERENCE_BUDGET_MS = 500


class OracleModel:
    """TFLite-first model wrapper with XGBoost fallback.

    Parameters
    ----------
    model_dir : str
        Directory containing model files (e.g. ``./models``).
    tflite_name : str
        TFLite model filename, e.g. ``oracle_majuli.tflite``.
    fallback_name : str
        XGBoost joblib filename, e.g. ``xgboost_majuli.joblib``.
    node_id : str
        Human-readable node identifier for logging.
    """

    def __init__(
        self,
        model_dir: str = "./models",
        tflite_name: str = "oracle_majuli.tflite",
        fallback_name: str = "xgboost_majuli.joblib",
        node_id: str = "unknown",
    ) -> None:
        self._node_id = node_id
        self._model_dir = Path(model_dir)
        self._tflite_path = self._model_dir / tflite_name
        self._fallback_path = self._model_dir / fallback_name

        self._interpreter = None  # TFLite interpreter
        self._xgb_model = None  # XGBoost model
        self._input_details = None
        self._output_details = None
        self._backend: str = "heuristic"  # tflite | xgboost | heuristic

        self._load_model()

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def is_loaded(self) -> bool:
        return self._backend in ("tflite", "xgboost")

    # ── Loading ──────────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Try TFLite → XGBoost → heuristic fallback."""
        if self._try_load_tflite():
            return
        if self._try_load_xgboost():
            return
        logger.warning(
            "oracle_using_heuristic_fallback",
            node=self._node_id,
            reason="No TFLite or XGBoost model found",
        )

    def _try_load_tflite(self) -> bool:
        """Attempt to load TFLite model."""
        if not self._tflite_path.exists():
            logger.info("tflite_model_not_found", path=str(self._tflite_path))
            return False
        try:
            import tflite_runtime.interpreter as tflite  # type: ignore[import-untyped]

            self._interpreter = tflite.Interpreter(model_path=str(self._tflite_path))
            self._interpreter.allocate_tensors()
            self._input_details = self._interpreter.get_input_details()
            self._output_details = self._interpreter.get_output_details()
            self._backend = "tflite"
            logger.info(
                "tflite_model_loaded",
                node=self._node_id,
                path=str(self._tflite_path),
            )
            return True
        except ImportError:
            logger.info("tflite_runtime_not_installed", node=self._node_id)
            return False
        except Exception as exc:
            logger.error("tflite_load_error", node=self._node_id, error=str(exc))
            return False

    def _try_load_xgboost(self) -> bool:
        """Attempt to load XGBoost joblib model."""
        if not self._fallback_path.exists():
            logger.info("xgboost_fallback_not_found", path=str(self._fallback_path))
            return False
        try:
            import joblib

            self._xgb_model = joblib.load(self._fallback_path)
            self._backend = "xgboost"
            logger.info(
                "xgboost_fallback_loaded",
                node=self._node_id,
                path=str(self._fallback_path),
            )
            return True
        except ImportError:
            logger.info("joblib_not_installed", node=self._node_id)
            return False
        except Exception as exc:
            logger.error("xgboost_load_error", node=self._node_id, error=str(exc))
            return False

    # ── Inference ────────────────────────────────────────────────────────

    def predict(self, features: Dict[str, float]) -> float:
        """Run ORACLE inference on a 6-feature vector.

        Parameters
        ----------
        features : dict
            Must contain keys from ``FEATURES``.

        Returns
        -------
        float
            Flood risk score ∈ [0.0, 1.0].
        """
        t0 = time.monotonic()

        # Build ordered input array
        x = np.array(
            [features.get(f, 0.0) for f in FEATURES],
            dtype=np.float32,
        )

        if self._backend == "tflite":
            score = self._predict_tflite(x)
        elif self._backend == "xgboost":
            score = self._predict_xgboost(x)
        else:
            score = self._predict_heuristic(x)

        elapsed_ms = (time.monotonic() - t0) * 1000
        if elapsed_ms > _INFERENCE_BUDGET_MS:
            logger.warning(
                "inference_budget_exceeded",
                node=self._node_id,
                elapsed_ms=round(elapsed_ms, 1),
                budget_ms=_INFERENCE_BUDGET_MS,
            )

        logger.debug(
            "oracle_inference",
            node=self._node_id,
            backend=self._backend,
            risk_score=round(score, 4),
            elapsed_ms=round(elapsed_ms, 1),
        )

        return float(np.clip(score, 0.0, 1.0))

    def _predict_tflite(self, x: np.ndarray) -> float:
        """TFLite inference."""
        input_shape = self._input_details[0]["shape"]
        x_input = x.reshape(input_shape).astype(np.float32)
        self._interpreter.set_tensor(self._input_details[0]["index"], x_input)
        self._interpreter.invoke()
        output = self._interpreter.get_tensor(self._output_details[0]["index"])
        return float(output.flat[0])

    def _predict_xgboost(self, x: np.ndarray) -> float:
        """XGBoost fallback inference."""
        x_2d = x.reshape(1, -1)
        if hasattr(self._xgb_model, "predict_proba"):
            probs = self._xgb_model.predict_proba(x_2d)
            return float(probs[0, 1]) if probs.shape[1] > 1 else float(probs[0, 0])
        else:
            return float(self._xgb_model.predict(x_2d)[0])

    def _predict_heuristic(self, x: np.ndarray) -> float:
        """Physics-informed heuristic when no model is available.

        Weighted combination of normalised features tuned for Indian
        river basins (Brahmaputra/Beas).
        """
        level_m = x[0]
        rainfall_mm = x[1]
        soil_moisture = x[2]
        rate_of_change = x[3]
        is_monsoon = x[5]

        # Normalise to [0, 1] with domain-reasonable ranges
        level_norm = np.clip(level_m / 8.0, 0, 1)
        rain_norm = np.clip(rainfall_mm / 100.0, 0, 1)
        soil_norm = np.clip(soil_moisture, 0, 1)
        roc_norm = np.clip(rate_of_change / 2.0, 0, 1)

        # Weighted combination
        score = (
            0.35 * level_norm
            + 0.25 * rain_norm
            + 0.15 * soil_norm
            + 0.15 * roc_norm
            + 0.10 * is_monsoon
        )

        # Non-linear amplification for high-risk conditions
        if level_norm > 0.7 and rain_norm > 0.5:
            score = min(1.0, score * 1.3)

        return float(score)

    # ── Batch inference (for demo replay) ────────────────────────────────

    def predict_batch(self, feature_rows: List[Dict[str, float]]) -> List[float]:
        """Run prediction on multiple readings."""
        return [self.predict(f) for f in feature_rows]
