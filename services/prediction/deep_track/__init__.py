"""TFT Deep Track — multi-horizon quantile flood forecasting.

Uses a Temporal Fusion Transformer (TFT) to produce probabilistic
forecasts at multiple time horizons: 15, 30, 45, 60, 90, 120 minutes.
Each horizon includes quantile bands (p10 / p50 / p90) for
uncertainty-aware decision-making.
"""

from services.prediction.deep_track.tft_predictor import TFTFloodPredictor

__all__ = ["TFTFloodPredictor"]
