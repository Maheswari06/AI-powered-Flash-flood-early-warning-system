"""Centralised configuration for all ARGUS services.

Loads values from environment variables (via ``python-dotenv``)
so that every micro-service shares the same config surface area.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


class Settings:
    """Simple settings object — reads from env vars with sensible defaults."""

    # ── Kafka ────────────────────────────────────────────────
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_GROUP_PREFIX: str = os.getenv("KAFKA_GROUP_PREFIX", "argus")

    # ── External APIs ────────────────────────────────────────
    CWC_API_KEY: str = os.getenv("CWC_API_KEY", "")
    IMD_API_KEY: str = os.getenv("IMD_API_KEY", "")

    # ── File paths ───────────────────────────────────────────
    CCTV_REGISTRY_PATH: str = os.getenv("CCTV_REGISTRY_PATH", "./data/cctv_registry.json")
    YOLO_MODEL_PATH: str = os.getenv("YOLO_MODEL_PATH", "./models/yolo11n.pt")
    SAM_MODEL_PATH: str = os.getenv("SAM_MODEL_PATH", "./models/sam2_tiny.pt")
    DEMO_VIDEO_PATH: str = os.getenv("DEMO_VIDEO_PATH", "./data/himachal_flood_demo.mp4")

    # ── CV Gauging ───────────────────────────────────────────
    CV_CONFIDENCE_THRESHOLD: float = float(os.getenv("CV_CONFIDENCE_THRESHOLD", "0.4"))
    PIXEL_TO_METER_DEFAULT: float = float(os.getenv("PIXEL_TO_METER_DEFAULT", "0.05"))

    # ── Prediction ───────────────────────────────────────────
    XGBOOST_MODEL_PATH: str = os.getenv("XGBOOST_MODEL_PATH", "./models/xgboost_flood.joblib")
    PINN_MODEL_PATH: str = os.getenv("PINN_MODEL_PATH", "./models/pinn_mesh_v1.pt")
    PREDICTION_INTERVAL_S: int = int(os.getenv("PREDICTION_INTERVAL_S", "300"))
    SHAP_TOP_K: int = int(os.getenv("SHAP_TOP_K", "5"))
    SHAP_TOP_N: int = int(os.getenv("SHAP_TOP_N", "3"))
    TRAIN_ON_STARTUP: bool = os.getenv("TRAIN_ON_STARTUP", "true").lower() in ("true", "1", "yes")
    FEATURE_POLL_INTERVAL_SEC: int = int(os.getenv("FEATURE_POLL_INTERVAL_SEC", "60"))

    # ── Redis ────────────────────────────────────────────────
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    PREDICTION_REDIS_TTL: int = int(os.getenv("PREDICTION_REDIS_TTL", "300"))

    # ── Feature Engine ───────────────────────────────────────
    FEATURE_WINDOW_1H: int = int(os.getenv("FEATURE_WINDOW_1H", "12"))   # 12 × 5 min = 1 h
    FEATURE_WINDOW_3H: int = int(os.getenv("FEATURE_WINDOW_3H", "36"))
    FEATURE_WINDOW_6H: int = int(os.getenv("FEATURE_WINDOW_6H", "72"))
    FEATURE_WINDOW_24H: int = int(os.getenv("FEATURE_WINDOW_24H", "288"))
    # ── TimescaleDB ──────────────────────────────────────
    TIMESCALEDB_DSN: str = os.getenv(
        "TIMESCALEDB_DSN", "postgresql://argus:argus@localhost:5432/argus"
    )

    # ── PINN ─────────────────────────────────────────────
    PINN_CHECKPOINT_PATH: str = os.getenv("PINN_CHECKPOINT_PATH", "./models/pinn_beas_river.pt")
    # ── Alert Dispatcher ─────────────────────────────────────
    ALERT_KAFKA_TOPIC: str = os.getenv("ALERT_KAFKA_TOPIC", "alerts.dispatch")
    ALERT_COOLDOWN_S: int = int(os.getenv("ALERT_COOLDOWN_S", "900"))  # 15 min

    # ═══════════════════════  PHASE 2  ════════════════════════

    # ── Causal Engine ────────────────────────────────────────
    CAUSAL_DAG_PATH: str = os.getenv("CAUSAL_DAG_PATH", "./shared/causal_dag/beas_brahmaputra_v1.json")
    CAUSAL_GNN_HIDDEN: int = int(os.getenv("CAUSAL_GNN_HIDDEN", "64"))
    CAUSAL_GNN_LAYERS: int = int(os.getenv("CAUSAL_GNN_LAYERS", "3"))
    CAUSAL_ENGINE_PORT: int = int(os.getenv("CAUSAL_ENGINE_PORT", "8006"))
    CAUSAL_DAG_CONFIG_PATH: str = os.getenv("CAUSAL_DAG_CONFIG_PATH", "./data/dags/brahmaputra_dag.json")
    CAUSAL_GNN_MODEL_PATH: str = os.getenv("CAUSAL_GNN_MODEL_PATH", "./models/causal_gnn_brahmaputra.pt")
    N_MONTE_CARLO: int = int(os.getenv("N_MONTE_CARLO", "100"))

    # ── FloodLedger ──────────────────────────────────────────
    LEDGER_DB_PATH: str = os.getenv("LEDGER_DB_PATH", "./data/flood_ledger.db")
    LEDGER_PORT: int = int(os.getenv("FLOOD_LEDGER_PORT", "8007"))
    LEDGER_DIFFICULTY: int = int(os.getenv("LEDGER_DIFFICULTY", "2"))  # PoW leading zeros
    HARDHAT_RPC_URL: str = os.getenv("HARDHAT_RPC_URL", "http://localhost:8545")
    ASSET_REGISTRY_PATH: str = os.getenv("ASSET_REGISTRY_PATH", "./data/insured_assets.csv")
    CONTRACT_ADDRESS: str = os.getenv("CONTRACT_ADDRESS", "")

    # ── CHORUS ───────────────────────────────────────────────
    CHORUS_PORT: int = int(os.getenv("CHORUS_PORT", "8008"))
    CHORUS_WINDOW_MIN: int = int(os.getenv("CHORUS_WINDOW_MIN", "60"))
    CHORUS_CREDIBILITY_THRESHOLD: float = float(os.getenv("CHORUS_CREDIBILITY_THRESHOLD", "0.3"))
    CHORUS_CONSENSUS_THRESHOLD: int = int(os.getenv("CHORUS_CONSENSUS_THRESHOLD", "3"))
    CHORUS_CONSENSUS_WINDOW_MIN: int = int(os.getenv("CHORUS_CONSENSUS_WINDOW_MIN", "10"))
    WHATSAPP_WEBHOOK_SECRET: str = os.getenv("WHATSAPP_WEBHOOK_SECRET", "")
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_NUMBER: str = os.getenv("TWILIO_WHATSAPP_NUMBER", "")
    WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL_SIZE", "base")
    INDIC_BERT_CHECKPOINT: str = os.getenv("INDIC_BERT_CHECKPOINT", "ai4bharat/indic-bert")
    GEOHASH_PRECISION: int = int(os.getenv("GEOHASH_PRECISION", "5"))
    LANDMARK_DB_PATH: str = os.getenv("LANDMARK_DB_PATH", "./data/landmarks.csv")

    # ── Federated Learning ───────────────────────────────────
    FL_SERVER_PORT: int = int(os.getenv("FL_SERVER_PORT", "8009"))
    FL_ROUNDS: int = int(os.getenv("FL_ROUNDS", "10"))
    FL_MIN_CLIENTS: int = int(os.getenv("FL_MIN_CLIENTS", "2"))
    FL_AGGREGATION: str = os.getenv("FL_AGGREGATION", "fedavg")
    FL_DP_EPSILON: float = float(os.getenv("FL_DP_EPSILON", "1.0"))
    FL_DP_DELTA: float = float(os.getenv("FL_DP_DELTA", "1e-5"))
    FLOWER_SERVER_ADDRESS: str = os.getenv("FLOWER_SERVER_ADDRESS", "0.0.0.0:8080")
    FEDERATED_ROUNDS: int = int(os.getenv("FEDERATED_ROUNDS", "10"))
    DP_NOISE_MULTIPLIER: float = float(os.getenv("DP_NOISE_MULTIPLIER", "1.1"))
    DP_CLIP_NORM: float = float(os.getenv("DP_CLIP_NORM", "1.0"))
    SYNTHETIC_DATA_DIR: str = os.getenv("SYNTHETIC_DATA_DIR", "./data/synthetic")

    # ── Evacuation RL ────────────────────────────────────────
    EVAC_RL_PORT: int = int(os.getenv("EVAC_RL_PORT", "8010"))
    EVAC_MODEL_PATH: str = os.getenv("EVAC_MODEL_PATH", "./models/evac_ppo.zip")
    EVAC_GRAPH_PATH: str = os.getenv("EVAC_GRAPH_PATH", "./data/evacuation_graph.json")
    EVAC_RETRAIN_INTERVAL_S: int = int(os.getenv("EVAC_RETRAIN_INTERVAL_S", "3600"))

    # ── MIRROR ───────────────────────────────────────────────
    MIRROR_PORT: int = int(os.getenv("MIRROR_PORT", "8011"))
    MIRROR_MAX_STEPS: int = int(os.getenv("MIRROR_MAX_STEPS", "48"))  # max replay steps

    # ═══════════════════════  PHASE 3  ════════════════════════

    # ── Model Monitor ────────────────────────────────────────
    MODEL_MONITOR_PORT: int = int(os.getenv("MODEL_MONITOR_PORT", "8013"))
    DRIFT_CHECK_INTERVAL_S: int = int(os.getenv("DRIFT_CHECK_INTERVAL_S", "3600"))
    DRIFT_RETRAIN_THRESHOLD: float = float(os.getenv("DRIFT_RETRAIN_THRESHOLD", "0.3"))

    # ── MLflow (optional) ────────────────────────────────────
    MLFLOW_TRACKING_URI: str = os.getenv("MLFLOW_TRACKING_URI", "")
    MLFLOW_EXPERIMENT: str = os.getenv("MLFLOW_EXPERIMENT", "argus-flood")

    # ── GAN Synthetic Data ───────────────────────────────────
    GAN_CHECKPOINT_PATH: str = os.getenv("GAN_CHECKPOINT_PATH", "./models/flood_gan.pt")
    SYNTHETIC_DATA_PATH: str = os.getenv("SYNTHETIC_DATA_PATH", "./data/synthetic/brahmaputra_500.parquet")

    # ── TFT Deep Track ───────────────────────────────────────
    TFT_CHECKPOINT_PATH: str = os.getenv("TFT_CHECKPOINT_PATH", "./models/tft_flood.ckpt")
    TFT_ENABLED: bool = os.getenv("TFT_ENABLED", "true").lower() in ("true", "1", "yes")

    # ═══════════════════════  PHASE 3  ════════════════════════

    # ── ScarNet — Satellite Terrain Monitor ──────────────────
    SCARNET_PORT: int = int(os.getenv("SCARNET_PORT", "8012"))
    SCARNET_DEMO_MODE: bool = os.getenv("SCARNET_DEMO_MODE", "true").lower() in ("true", "1", "yes")
    NASA_EARTHDATA_TOKEN: str = os.getenv("NASA_EARTHDATA_TOKEN", "")
    SENTINEL_AWS_BUCKET: str = os.getenv("SENTINEL_AWS_BUCKET", "sentinel-s2-l2a")
    SENTINEL_AWS_REGION: str = os.getenv("SENTINEL_AWS_REGION", "eu-central-1")
    UNET_CHECKPOINT: str = os.getenv("UNET_CHECKPOINT", "./models/unet_change_detect.pt")
    SENTINEL2_BEFORE_TILE: str = os.getenv("SENTINEL2_BEFORE_TILE", "./data/sentinel2/beas_valley_2022_08_before.tif")
    SENTINEL2_AFTER_TILE: str = os.getenv("SENTINEL2_AFTER_TILE", "./data/sentinel2/beas_valley_2023_09_after.tif")

    # ── API Gateway ──────────────────────────────────────────
    GATEWAY_PORT: int = int(os.getenv("GATEWAY_PORT", "8000"))
    GATEWAY_CACHE_TTL: int = int(os.getenv("GATEWAY_CACHE_TTL", "30"))

    # ── General ──────────────────────────────────────────────
    SERVICE_HOST: str = os.getenv("SERVICE_HOST", "0.0.0.0")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a singleton Settings instance."""
    return Settings()
