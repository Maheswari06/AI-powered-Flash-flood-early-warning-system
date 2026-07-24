"""XGBoost flood-probability predictor.

Model: XGBClassifier, 500 estimators, max_depth=6, learning_rate=0.05
Feature set (16 features, order MUST match training):

    FEATURES = [
        'level_1hr_mean', 'level_3hr_mean', 'level_6hr_mean', 'level_24hr_mean',
        'level_1hr_max', 'rate_of_change_1hr', 'rate_of_change_3hr',
        'cumulative_rainfall_6hr', 'cumulative_rainfall_24hr',
        'soil_moisture_index', 'antecedent_moisture_index',
        'upstream_risk_score', 'basin_connectivity_score',
        'hour_of_day', 'day_of_year', 'is_monsoon_season',
    ]

If the model file is missing and ``train_on_startup`` is True,
the predictor trains on synthetic data automatically.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# ── Feature contract (order matters — must match training) ────────────────
FEATURES: List[str] = [
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


def _generate_synthetic_data(
    n_samples: int = 10_000,
    seed: int = 42,
) -> "tuple[np.ndarray, np.ndarray]":
    """Generate synthetic CWC-like training data for the XGBoost model.

    The label is 1 (flood) based on realistic conditional probabilities
    mimicking monsoon flash-flood dynamics in the Beas River basin.

    Returns:
        (X, y) — feature matrix and binary labels.
    """
    rng = np.random.RandomState(seed)

    # Sample features
    level_1hr_mean = rng.uniform(1.0, 8.0, n_samples)
    level_3hr_mean = level_1hr_mean + rng.normal(0, 0.3, n_samples)
    level_6hr_mean = level_1hr_mean + rng.normal(-0.2, 0.5, n_samples)
    level_24hr_mean = level_1hr_mean + rng.normal(-0.5, 0.7, n_samples)
    level_1hr_max = level_1hr_mean + rng.exponential(0.3, n_samples)
    rate_of_change_1hr = rng.normal(0.05, 0.3, n_samples)
    rate_of_change_3hr = rate_of_change_1hr * rng.uniform(0.5, 1.5, n_samples)
    cumulative_rainfall_6hr = rng.exponential(30, n_samples)
    cumulative_rainfall_24hr = cumulative_rainfall_6hr * rng.uniform(1.5, 4, n_samples)
    soil_moisture_index = rng.beta(3, 2, n_samples)  # 0–1
    antecedent_moisture_index = rng.exponential(25, n_samples)
    upstream_risk_score = rng.beta(2, 5, n_samples)
    basin_connectivity_score = rng.uniform(0.3, 1.0, n_samples)
    hour_of_day = rng.randint(0, 24, n_samples).astype(float)
    day_of_year = rng.randint(1, 366, n_samples).astype(float)
    is_monsoon_season = ((day_of_year >= 152) & (day_of_year <= 273)).astype(float)

    X = np.column_stack([
        level_1hr_mean, level_3hr_mean, level_6hr_mean, level_24hr_mean,
        level_1hr_max, rate_of_change_1hr, rate_of_change_3hr,
        cumulative_rainfall_6hr, cumulative_rainfall_24hr,
        soil_moisture_index, antecedent_moisture_index,
        upstream_risk_score, basin_connectivity_score,
        hour_of_day, day_of_year, is_monsoon_season,
    ])

    # Generate labels using realistic conditional probabilities
    logit = (
        -4.0
        + 0.6 * (level_1hr_mean - 4.0)
        + 0.3 * rate_of_change_1hr
        + 0.02 * cumulative_rainfall_6hr
        + 0.01 * cumulative_rainfall_24hr
        + 2.0 * soil_moisture_index
        + 0.01 * antecedent_moisture_index
        + 3.0 * upstream_risk_score
        + 1.5 * is_monsoon_season
    )
    probability = 1.0 / (1.0 + np.exp(-logit))
    y = (rng.random(n_samples) < probability).astype(int)

    logger.info(
        "synthetic_data_generated",
        n_samples=n_samples,
        flood_rate=round(float(y.mean()), 3),
    )
    return X, y


class XGBoostPredictor:
    """XGBoost-based flood probability predictor.

    If no model file exists and ``train_on_startup=True``, trains
    on synthetic data automatically and saves the artifact.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        training_data_path: Optional[str] = None,
        train_on_startup: bool = True,
    ) -> None:
        self.model_path = model_path or os.getenv(
            "XGBOOST_MODEL_PATH", "./models/xgboost_flood.joblib"
        )
        self.training_data_path = training_data_path or os.getenv(
            "TRAINING_DATA_PATH", "./data/cwc_historical_2019_2023.csv"
        )
        self.train_on_startup = train_on_startup
        self.feature_names: List[str] = FEATURES
        self.model = None
        self.model_version: str = "xgb-v2.0.0"
        self.is_loaded: bool = False
        self._train_metrics: Dict = {}

        self._load_or_train()

    def _load_or_train(self) -> None:
        """Load existing model or train a new one."""
        loaded = self._try_load()
        if not loaded and self.train_on_startup:
            self._train_synthetic()

    def _try_load(self) -> bool:
        """Try loading from joblib file."""
        try:
            import joblib
            p = Path(self.model_path)
            if p.exists():
                self.model = joblib.load(str(p))
                self.is_loaded = True
                logger.info("xgboost_model_loaded", path=self.model_path)
                return True
            logger.info("xgboost_model_not_found", path=self.model_path)
        except ImportError:
            logger.warning("joblib_not_installed")
        except Exception as exc:
            logger.error("xgboost_load_error", error=str(exc))
        return False

    def _try_load_csv(self) -> "Optional[tuple[np.ndarray, np.ndarray]]":
        """Try loading real training data from CSV."""
        try:
            import pandas as pd
            p = Path(self.training_data_path)
            if not p.exists():
                return None
            df = pd.read_csv(p)
            # Expect columns matching FEATURES + a 'flood' label column
            if "flood" not in df.columns:
                logger.warning("csv_missing_flood_column", path=self.training_data_path)
                return None
            missing = [f for f in FEATURES if f not in df.columns]
            if missing:
                logger.warning("csv_missing_features", missing=missing)
                return None
            X = df[FEATURES].values
            y = df["flood"].values
            logger.info("training_data_loaded_from_csv", n_samples=len(y), path=self.training_data_path)
            return X, y
        except ImportError:
            return None
        except Exception as exc:
            logger.warning("csv_load_error", error=str(exc))
            return None

    def _train_synthetic(self) -> None:
        """Train XGBoost on CSV data or synthetic data if CSV unavailable."""
        try:
            from xgboost import XGBClassifier
            import joblib
        except ImportError:
            logger.error("xgboost_or_joblib_not_installed_cannot_train")
            return

        # Try real data first, fall back to synthetic
        data = self._try_load_csv()
        if data is not None:
            X, y = data
            data_source = "csv"
        else:
            X, y = _generate_synthetic_data()
            data_source = "synthetic"

        # Temporal split: last 20% = test
        split_idx = int(len(y) * 0.80)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        logger.info(
            "xgboost_training_start",
            data_source=data_source,
            n_train=len(y_train),
            n_test=len(y_test),
        )

        model = XGBClassifier(
            n_estimators=500,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="logloss",
            use_label_encoder=False,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )

        # Evaluate
        from sklearn.metrics import accuracy_score, roc_auc_score, f1_score
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1]

        metrics = {
            "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
            "roc_auc": round(float(roc_auc_score(y_test, y_prob)), 4),
            "f1": round(float(f1_score(y_test, y_pred)), 4),
            "data_source": data_source,
            "n_train": len(y_train),
            "n_test": len(y_test),
        }
        self._train_metrics = metrics
        logger.info("xgboost_training_complete", **metrics)

        # Save model
        Path(self.model_path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, self.model_path)
        logger.info("xgboost_model_saved", path=self.model_path)

        self.model = model
        self.is_loaded = True

    # ── Prediction ─────────────────────────────────────────────────────

    def predict(self, features: Dict[str, float]) -> float:
        """Predict flood probability from a feature dictionary.

        Args:
            features: Dict mapping feature name → float value.
                      Missing features default to 0.0.

        Returns:
            Flood probability in [0.0, 1.0].
        """
        if self.model is None:
            return self._heuristic_predict(features)

        X = np.array([
            features.get(f, 0.0) for f in FEATURES
        ], dtype=np.float32).reshape(1, -1)

        prob = float(self.model.predict_proba(X)[0, 1])
        return round(prob, 4)

    def predict_batch(self, feature_rows: List[Dict[str, float]]) -> List[float]:
        """Predict flood probability for multiple feature rows."""
        if self.model is None:
            return [self._heuristic_predict(f) for f in feature_rows]

        X = np.array([
            [row.get(f, 0.0) for f in FEATURES]
            for row in feature_rows
        ], dtype=np.float32)

        probs = self.model.predict_proba(X)[:, 1]
        return [round(float(p), 4) for p in probs]

    @staticmethod
    def _heuristic_predict(features: Dict[str, float]) -> float:
        """Rule-based fallback when no model is loaded."""
        level_risk = min(features.get("level_1hr_mean", 0.0) / 8.0, 1.0)
        rain_risk = min(features.get("cumulative_rainfall_6hr", 0.0) / 150.0, 1.0)
        rate_risk = min(max(features.get("rate_of_change_1hr", 0.0), 0.0) / 0.5, 1.0)
        soil_risk = features.get("soil_moisture_index", 0.5)
        upstream_risk = features.get("upstream_risk_score", 0.0)

        prob = (
            0.25 * rain_risk
            + 0.20 * level_risk
            + 0.15 * rate_risk
            + 0.20 * soil_risk
            + 0.20 * upstream_risk
        )
        return round(min(max(prob, 0.0), 1.0), 4)

    @property
    def train_metrics(self) -> Dict:
        """Return training metrics from the last training run."""
        return self._train_metrics
