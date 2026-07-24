"""TFT Deep-Track Flood Predictor.

Temporal Fusion Transformer for multi-horizon probabilistic flood
forecasting.  Produces quantile-based uncertainty estimates at
horizons: 15, 30, 45, 60, 90, 120 minutes.

If ``pytorch_forecasting`` is not installed or no checkpoint is found,
the predictor falls back to a physics-informed synthetic curve that
produces realistic rising-limb hydrographs for demo purposes.

Config env vars
===============
  TFT_CHECKPOINT_PATH  — path to saved TFT Lightning checkpoint
  TFT_ENABLED          — "true" to enable deep track (default: true)
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# ── Forecast horizons (minutes) ──────────────────────────────────────────
HORIZONS_MIN: List[int] = [15, 30, 45, 60, 90, 120]

# ── Quantile targets ────────────────────────────────────────────────────
QUANTILES: List[float] = [0.10, 0.50, 0.90]
QUANTILE_NAMES: List[str] = ["p10", "p50", "p90"]

# ── 16-feature contract (must match XGBoost fast-track) ──────────────────
FEATURE_NAMES: List[str] = [
    "level_1hr_mean",
    "level_3hr_mean",
    "level_6hr_mean",
    "level_24hr_mean",
    "level_1hr_max",
    "rate_of_change_1hr",
    "rate_of_change_3hr",
    "cumulative_rainfall_6hr",
    "cumulative_rainfall_24hr",
    "soil_moisture_index",
    "antecedent_moisture_index",
    "upstream_risk_score",
    "basin_connectivity_score",
    "hour_of_day",
    "day_of_year",
    "is_monsoon_season",
]


class TFTFloodPredictor:
    """Multi-horizon quantile flood forecaster using TFT or synthetic fallback.

    Parameters
    ----------
    checkpoint_path : str | None
        Path to a PyTorch Lightning TFT checkpoint.
    enabled : bool
        Master toggle.  When False, ``predict()`` returns None.
    """

    def __init__(
        self,
        checkpoint_path: Optional[str] = None,
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        self.checkpoint_path = checkpoint_path or os.getenv(
            "TFT_CHECKPOINT_PATH", "./models/tft_flood.ckpt"
        )
        self.model: Any = None
        self.is_loaded: bool = False
        self.model_version: str = "tft-v1.0.0"

        if self.enabled:
            self._try_load_model()

    # ─────────────────────────────────────────────────────────────────────
    # Model loading
    # ─────────────────────────────────────────────────────────────────────

    def _try_load_model(self) -> None:
        """Try loading a TemporalFusionTransformer checkpoint."""
        try:
            from pytorch_forecasting import TemporalFusionTransformer

            if os.path.isfile(self.checkpoint_path):
                self.model = TemporalFusionTransformer.load_from_checkpoint(
                    self.checkpoint_path
                )
                self.model.eval()
                self.is_loaded = True
                logger.info("tft_model_loaded", path=self.checkpoint_path)
            else:
                logger.warning(
                    "tft_checkpoint_not_found_using_synthetic_fallback",
                    path=self.checkpoint_path,
                )
        except ImportError:
            logger.warning("pytorch_forecasting_not_installed_using_synthetic_fallback")
        except Exception as exc:
            logger.warning("tft_load_failed_using_synthetic_fallback", error=str(exc))

    # ─────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────

    def predict(
        self,
        village_id: str,
        features: Dict[str, float],
        xgb_risk_score: float = 0.0,
    ) -> Optional[Dict[str, Any]]:
        """Run multi-horizon quantile prediction.

        Parameters
        ----------
        village_id : str
            Target village identifier.
        features : dict
            16-feature dict (same keys as fast-track XGBoost).
        xgb_risk_score : float
            XGBoost risk score (used to anchor synthetic curve).

        Returns
        -------
        dict | None
            Deep-track prediction payload, or None if disabled.
        """
        if not self.enabled:
            return None

        now = datetime.now(timezone.utc)

        if self.is_loaded and self.model is not None:
            horizons = self._predict_with_model(features)
        else:
            horizons = self._predict_synthetic(features, xgb_risk_score)

        # Compute peak risk horizon (horizon with highest p90)
        peak_idx = int(np.argmax([h["p90"] for h in horizons]))
        peak_horizon = HORIZONS_MIN[peak_idx]
        peak_value = horizons[peak_idx]["p90"]

        # Compute overall trend
        first_p50 = horizons[0]["p50"]
        last_p50 = horizons[-1]["p50"]
        if last_p50 > first_p50 * 1.15:
            trend = "RISING"
        elif last_p50 < first_p50 * 0.85:
            trend = "FALLING"
        else:
            trend = "STABLE"

        return {
            "village_id": village_id,
            "model": "tft" if self.is_loaded else "synthetic_fallback",
            "model_version": self.model_version,
            "horizons": [
                {
                    "minutes": HORIZONS_MIN[i],
                    "p10": round(horizons[i]["p10"], 4),
                    "p50": round(horizons[i]["p50"], 4),
                    "p90": round(horizons[i]["p90"], 4),
                    "spread": round(horizons[i]["p90"] - horizons[i]["p10"], 4),
                }
                for i in range(len(HORIZONS_MIN))
            ],
            "peak_risk_horizon_min": peak_horizon,
            "peak_risk_value": round(peak_value, 4),
            "trend": trend,
            "timestamp": now.isoformat(),
        }

    # ─────────────────────────────────────────────────────────────────────
    # TFT model inference
    # ─────────────────────────────────────────────────────────────────────

    def _predict_with_model(
        self, features: Dict[str, float]
    ) -> List[Dict[str, float]]:
        """Run actual TFT model for quantile predictions.

        This is the real inference path — called only when the model
        checkpoint is successfully loaded.
        """
        try:
            import torch
            from pytorch_forecasting import TemporalFusionTransformer

            # Build input tensor  — TFT expects (batch, time_steps, features)
            # We construct a single-sample batch with the latest features
            # replicated across a synthetic lookback window (24 steps × 5 min = 2 h)
            lookback = 24
            feat_arr = np.array(
                [features.get(k, 0.0) for k in FEATURE_NAMES], dtype=np.float32
            )

            # Create a synthetic lookback by applying tiny perturbations
            rng = np.random.RandomState(42)
            window = np.tile(feat_arr, (lookback, 1))
            for t in range(lookback):
                noise_scale = 0.01 * (lookback - t)  # more noise further back
                window[t] += rng.normal(0, noise_scale, len(feat_arr))

            # Convert to model input format
            x = torch.tensor(window, dtype=torch.float32).unsqueeze(0)

            with torch.no_grad():
                raw_output = self.model(x)

            # Parse output — shape (1, n_horizons, n_quantiles)
            if isinstance(raw_output, dict):
                pred = raw_output["prediction"]
            elif isinstance(raw_output, tuple):
                pred = raw_output[0]
            else:
                pred = raw_output

            pred_np = pred.squeeze(0).cpu().numpy()

            horizons = []
            for i in range(min(len(HORIZONS_MIN), pred_np.shape[0])):
                row = pred_np[i]
                if len(row) >= 3:
                    horizons.append(
                        {"p10": float(row[0]), "p50": float(row[1]), "p90": float(row[2])}
                    )
                else:
                    v = float(row[0]) if len(row) > 0 else 0.5
                    horizons.append(
                        {"p10": v * 0.7, "p50": v, "p90": v * 1.3}
                    )

            # Pad if fewer horizons than expected
            while len(horizons) < len(HORIZONS_MIN):
                last = horizons[-1]
                horizons.append(
                    {
                        "p10": last["p10"] * 1.05,
                        "p50": last["p50"] * 1.05,
                        "p90": last["p90"] * 1.05,
                    }
                )

            return horizons

        except Exception as exc:
            logger.warning("tft_inference_failed_falling_back", error=str(exc))
            return self._predict_synthetic(features, xgb_risk_score=0.5)

    # ─────────────────────────────────────────────────────────────────────
    # Synthetic fallback — physics-informed rising-limb curve
    # ─────────────────────────────────────────────────────────────────────

    def _predict_synthetic(
        self,
        features: Dict[str, float],
        xgb_risk_score: float = 0.0,
    ) -> List[Dict[str, float]]:
        """Generate realistic synthetic multi-horizon flood risk curves.

        Uses a physics-informed rising-limb hydrograph model:
          risk(t) = base + amplitude × (1 − e^{−t/τ})

        where:
          - base = current XGBoost risk score (anchoring)
          - amplitude = f(rainfall, soil_moisture, upstream_risk)
          - τ = time constant ∝ basin response time

        Uncertainty bands widen with horizon (heteroscedastic).
        """
        # Extract key drivers
        rainfall_6h = features.get("cumulative_rainfall_6hr", 0.0)
        rainfall_24h = features.get("cumulative_rainfall_24hr", 0.0)
        soil_moisture = features.get("soil_moisture_index", 0.5)
        upstream_risk = features.get("upstream_risk_score", 0.0)
        rate_of_change = features.get("rate_of_change_1hr", 0.0)
        level_mean = features.get("level_1hr_mean", 3.0)
        is_monsoon = features.get("is_monsoon_season", 0.0)

        # Base risk — anchor to XGBoost
        base = max(0.05, min(0.95, xgb_risk_score))

        # Amplitude — how much the risk can grow
        rain_factor = min(1.0, rainfall_6h / 100.0)       # normalize to 0-1
        soil_factor = soil_moisture                         # already 0-1
        upstream_factor = upstream_risk                     # already 0-1
        monsoon_boost = 0.15 if is_monsoon >= 0.5 else 0.0

        amplitude = (
            0.3 * rain_factor
            + 0.25 * soil_factor
            + 0.2 * upstream_factor
            + 0.1 * min(1.0, max(0.0, rate_of_change))
            + monsoon_boost
        )
        amplitude = min(0.6, amplitude)  # cap so base + amplitude ≤ ~1.0

        # Time constant τ (minutes) — faster response in saturated basins
        tau = 60.0 * (1.0 - 0.5 * soil_factor)  # 30-60 min
        tau = max(20.0, tau)

        # Generate predictions for each horizon
        horizons: List[Dict[str, float]] = []
        rng = np.random.RandomState(
            hash(str(features.get("hour_of_day", 0))) % (2**31)
        )

        for t_min in HORIZONS_MIN:
            # Rising limb: risk(t) = base + amplitude × (1 - e^{-t/τ})
            growth = amplitude * (1.0 - math.exp(-t_min / tau))
            p50 = base + growth

            # Add slight stochastic perturbation (seeded for determinism)
            p50 += rng.normal(0, 0.02)

            # Clamp to [0, 1]
            p50 = max(0.01, min(0.99, p50))

            # Uncertainty spread — widens with horizon (heteroscedastic)
            # σ = 0.03 + 0.001 × t_min  →  ±0.03 at 15 min, ±0.15 at 120 min
            sigma = 0.03 + 0.001 * t_min

            # Quantile bands (Gaussian approximation)
            z_10 = -1.2816  # 10th percentile z-score
            z_90 = 1.2816   # 90th percentile z-score

            p10 = max(0.01, min(0.99, p50 + z_10 * sigma))
            p90 = max(0.01, min(0.99, p50 + z_90 * sigma))

            horizons.append({"p10": p10, "p50": p50, "p90": p90})

        return horizons

    # ─────────────────────────────────────────────────────────────────────
    # Info
    # ─────────────────────────────────────────────────────────────────────

    def info(self) -> Dict[str, Any]:
        """Return metadata about the TFT predictor."""
        return {
            "enabled": self.enabled,
            "model_loaded": self.is_loaded,
            "model_version": self.model_version,
            "checkpoint_path": self.checkpoint_path,
            "horizons_minutes": HORIZONS_MIN,
            "quantiles": QUANTILE_NAMES,
            "features": FEATURE_NAMES,
            "fallback_mode": "synthetic_rising_limb" if not self.is_loaded else "none",
        }
