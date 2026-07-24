"""ARGUS Oracle Trainer — Batch training pipeline for XGBoost flood classifiers.

Trains one XGBoost model per basin using historical sensor data.
Supports three data sources: TimescaleDB, Parquet files, or synthetic generation.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Feature Constants ────────────────────────────────────────────────────

FEATURES = [
    "water_level_m",
    "rainfall_mm_hr",
    "soil_moisture",
    "temperature_c",
    "level_velocity",          # rate of change: level[t] - level[t-1]
    "soil_saturation_index",   # derived: soil_moisture / 0.95 (max capacity)
    "hour_of_day",
    "day_of_year",
    "is_monsoon_season",       # binary: 1 if month in [6,7,8,9]
]


# ── Data Loading ─────────────────────────────────────────────────────────

def load_historical_data(basin_id: str) -> pd.DataFrame:
    """Load historical sensor data for a basin.

    Tries three sources in order:
      1. TimescaleDB (asyncpg/psycopg2)
      2. Parquet file at ./data/historical/{basin_id}_5yr.parquet
      3. Synthetic generation (2000 rows with realistic ranges)

    Args:
        basin_id: Basin identifier (e.g., 'brahmaputra_upper')

    Returns:
        DataFrame with columns: timestamp, station_id, village_id,
        water_level_m, rainfall_mm_hr, soil_moisture, temperature_c,
        flood_occurred, weight
    """
    # Try 1: TimescaleDB
    try:
        dsn = os.getenv(
            "TIMESCALEDB_DSN",
            "postgresql://argus:argus@localhost:5432/argus_db"
        )
        import psycopg2
        conn = psycopg2.connect(dsn)
        query = """
            SELECT timestamp, station_id, village_id, water_level_m,
                   rainfall_mm_hr, soil_moisture, temperature_c,
                   flood_occurred, 1.0 as weight
            FROM sensor_readings
            WHERE basin_id = %(basin_id)s
            AND timestamp > NOW() - INTERVAL '5 years'
            ORDER BY timestamp ASC
        """
        df = pd.read_sql(query, conn, params={"basin_id": basin_id})
        conn.close()
        if len(df) > 0:
            logger.info("Loaded %d rows from TimescaleDB for %s", len(df), basin_id)
            return df
    except Exception as e:
        logger.debug("TimescaleDB unavailable: %s", str(e)[:100])

    # Try 2: Parquet file
    try:
        parquet_path = Path(f"./data/historical/{basin_id}_5yr.parquet")
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            logger.info("Loaded %d rows from parquet for %s", len(df), basin_id)
            return df
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug("Parquet load failed: %s", str(e)[:100])

    # Try 3: Synthetic generation
    logger.warning("Using synthetic training data for %s", basin_id)
    return _generate_synthetic_data(basin_id, n_rows=2000)


def _generate_synthetic_data(basin_id: str, n_rows: int = 2000) -> pd.DataFrame:
    """Generate synthetic historical sensor data with realistic ranges."""
    rng = np.random.RandomState(hash(basin_id) % 2**31)

    timestamps = pd.date_range(
        start="2019-01-01", periods=n_rows, freq="6h"
    )

    # Generate base signals
    water_level = rng.uniform(0.5, 8.0, n_rows)
    rainfall = rng.uniform(0, 80, n_rows)
    soil_moisture = rng.uniform(0.1, 0.95, n_rows)
    temperature = rng.uniform(15, 40, n_rows)

    # Flood occurs when water level > 5.0 AND rainfall > 30 (with noise)
    flood_prob = 0.12
    flood_occurred = rng.binomial(1, flood_prob, n_rows)

    # Make floods correlate with high water/rain
    high_risk = (water_level > 5.0) & (rainfall > 30)
    flood_occurred[high_risk] = rng.binomial(1, 0.7, high_risk.sum())

    stations = [f"{basin_id}_stn_{i}" for i in range(4)]
    villages = [f"{basin_id}_village_{i}" for i in range(8)]

    df = pd.DataFrame({
        "timestamp": timestamps,
        "station_id": rng.choice(stations, n_rows),
        "village_id": rng.choice(villages, n_rows),
        "water_level_m": np.round(water_level, 2),
        "rainfall_mm_hr": np.round(rainfall, 1),
        "soil_moisture": np.round(soil_moisture, 3),
        "temperature_c": np.round(temperature, 1),
        "flood_occurred": flood_occurred,
        "weight": np.ones(n_rows),
    })

    return df


# ── Batch Training ───────────────────────────────────────────────────────

def batch_train_basin(
    basin_id: str,
    data: Optional[pd.DataFrame] = None,
) -> dict:
    """Train XGBoost classifier for a basin.

    Args:
        basin_id: Basin identifier
        data: Optional pre-loaded DataFrame. If None, loads from historical sources.

    Returns:
        dict with model, validation metrics, and feature importances
    """
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import f1_score, precision_score, recall_score

    try:
        from xgboost import XGBClassifier
    except ImportError:
        from sklearn.ensemble import GradientBoostingClassifier as XGBClassifier

    if data is None:
        data = load_historical_data(basin_id)

    # Add derived features
    data = _add_derived_features(data)

    feature_cols = [c for c in FEATURES if c in data.columns]
    X = data[feature_cols].fillna(0)
    y = data["flood_occurred"].astype(int)

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    try:
        model = XGBClassifier(n_estimators=100, max_depth=5, random_state=42)
        model.fit(X_train, y_train)
    except Exception:
        from sklearn.ensemble import GradientBoostingClassifier
        model = GradientBoostingClassifier(n_estimators=100, max_depth=5, random_state=42)
        model.fit(X_train, y_train)

    y_pred = model.predict(X_val)
    f1 = f1_score(y_val, y_pred, zero_division=0)
    precision = precision_score(y_val, y_pred, zero_division=0)
    recall = recall_score(y_val, y_pred, zero_division=0)

    importances = dict(zip(feature_cols, model.feature_importances_.tolist()))

    logger.info(
        "Batch training complete: basin=%s F1=%.3f P=%.3f R=%.3f",
        basin_id, f1, precision, recall,
    )

    return {
        "basin_id": basin_id,
        "model": model,
        "validation_f1": round(f1, 4),
        "validation_precision": round(precision, 4),
        "validation_recall": round(recall, 4),
        "feature_importances": importances,
        "n_train": len(X_train),
        "n_val": len(X_val),
    }


def _add_derived_features(data: pd.DataFrame) -> pd.DataFrame:
    """Add derived features for XGBoost training."""
    df = data.copy()
    if "level_velocity" not in df.columns and "water_level_m" in df.columns:
        df["level_velocity"] = df["water_level_m"].diff().fillna(0)
    if "soil_saturation_index" not in df.columns and "soil_moisture" in df.columns:
        df["soil_saturation_index"] = df["soil_moisture"] / 0.95
    if "hour_of_day" not in df.columns:
        if "timestamp" in df.columns:
            df["hour_of_day"] = pd.to_datetime(df["timestamp"]).dt.hour
        else:
            df["hour_of_day"] = 12
    if "day_of_year" not in df.columns:
        if "timestamp" in df.columns:
            df["day_of_year"] = pd.to_datetime(df["timestamp"]).dt.dayofyear
        else:
            df["day_of_year"] = 180
    if "is_monsoon_season" not in df.columns:
        if "timestamp" in df.columns:
            months = pd.to_datetime(df["timestamp"]).dt.month
            df["is_monsoon_season"] = months.isin([6, 7, 8, 9]).astype(int)
        else:
            df["is_monsoon_season"] = 0
    return df
