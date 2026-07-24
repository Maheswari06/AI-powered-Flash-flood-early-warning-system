"""ARGUS TFT Trainer — Temporal Fusion Transformer for multi-horizon flood forecasting.

Trains a TFT model per basin using PyTorch Forecasting.
Logs metrics and checkpoints to MLflow.
"""

from __future__ import annotations

import pytorch_lightning as pl
import pandas as pd
import mlflow

from pytorch_forecasting import TemporalFusionTransformer, TimeSeriesDataSet
from pytorch_forecasting.data import GroupNormalizer
from pytorch_forecasting.metrics import QuantileLoss
from pytorch_lightning.callbacks import ModelCheckpoint, EarlyStopping

import structlog

logger = structlog.get_logger(__name__)


def train_tft_for_basin(
    basin_id: str,
    data: pd.DataFrame,
    max_encoder_length: int = 72,
    max_prediction_length: int = 6,
    batch_size: int = 64,
    max_epochs: int = 50,
    learning_rate: float = 0.001,
    hidden_size: int = 32,
    attention_head_size: int = 4,
    dropout: float = 0.1,
    gpus: int = 0,
    checkpoint_dir: str = "./models/tft_checkpoints",
) -> dict:
    """Train a TFT model for a specific river basin.

    Args:
        basin_id: Unique basin identifier
        data: DataFrame with columns: timestamp, station_id, water_level_m,
              rainfall_mm_hr, soil_moisture, temperature_c, time_idx, group
        max_encoder_length: Lookback window (hours)
        max_prediction_length: Forecast horizon (hours)
        batch_size: Training batch size
        max_epochs: Maximum training epochs
        learning_rate: Adam learning rate
        hidden_size: TFT hidden layer size
        attention_head_size: Attention heads
        dropout: Dropout rate
        gpus: Number of GPUs (0 for CPU)
        checkpoint_dir: Directory for model checkpoints

    Returns:
        dict with model path, validation metrics, and training info
    """
    logger.info("tft_training_start", basin=basin_id, epochs=max_epochs)

    # Ensure required columns exist
    required_cols = ["time_idx", "group", "water_level_m"]
    for col in required_cols:
        if col not in data.columns:
            raise ValueError(f"Missing required column: {col}")

    # Define time-varying known and unknown reals
    time_varying_known = [c for c in ["hour_of_day", "day_of_year", "is_monsoon"]
                          if c in data.columns]
    time_varying_unknown = [c for c in ["water_level_m", "rainfall_mm_hr",
                                         "soil_moisture", "temperature_c"]
                            if c in data.columns]

    # Build TimeSeriesDataSet
    training_cutoff = data["time_idx"].max() - max_prediction_length

    training = TimeSeriesDataSet(
        data[data["time_idx"] <= training_cutoff],
        time_idx="time_idx",
        target="water_level_m",
        group_ids=["group"],
        min_encoder_length=max_encoder_length // 2,
        max_encoder_length=max_encoder_length,
        min_prediction_length=1,
        max_prediction_length=max_prediction_length,
        time_varying_known_reals=time_varying_known if time_varying_known else None,
        time_varying_unknown_reals=time_varying_unknown,
        target_normalizer=GroupNormalizer(
            groups=["group"],
            transformation="softplus",
        ),
        add_relative_time_idx=True,
        add_target_scales=True,
        add_encoder_length=True,
    )

    validation = TimeSeriesDataSet.from_dataset(
        training,
        data,
        predict=True,
        stop_randomization=True,
    )

    train_dataloader = training.to_dataloader(
        train=True, batch_size=batch_size, num_workers=0
    )
    val_dataloader = validation.to_dataloader(
        train=False, batch_size=batch_size * 2, num_workers=0
    )

    # Configure callbacks
    early_stop = EarlyStopping(
        monitor="val_loss",
        min_delta=1e-4,
        patience=5,
        verbose=True,
        mode="min",
    )
    checkpoint = ModelCheckpoint(
        dirpath=checkpoint_dir,
        filename=f"tft_{basin_id}_{{epoch:02d}}_{{val_loss:.4f}}",
        monitor="val_loss",
        mode="min",
        save_top_k=1,
    )

    # Build TFT model
    tft = TemporalFusionTransformer.from_dataset(
        training,
        learning_rate=learning_rate,
        hidden_size=hidden_size,
        attention_head_size=attention_head_size,
        dropout=dropout,
        hidden_continuous_size=hidden_size // 2,
        output_size=7,  # 7 quantiles
        loss=QuantileLoss(),
        log_interval=10,
        reduce_on_plateau_patience=3,
    )

    logger.info(
        "tft_model_created",
        basin=basin_id,
        params=sum(p.numel() for p in tft.parameters()),
    )

    # Train
    trainer = pl.Trainer(
        max_epochs=max_epochs,
        accelerator="gpu" if gpus > 0 else "cpu",
        devices=gpus if gpus > 0 else 1,
        callbacks=[early_stop, checkpoint],
        gradient_clip_val=0.1,
        enable_progress_bar=True,
    )

    # Log to MLflow
    try:
        mlflow.set_experiment(f"argus-tft-{basin_id}")
        with mlflow.start_run(run_name=f"tft_{basin_id}"):
            mlflow.log_params({
                "basin_id": basin_id,
                "max_encoder_length": max_encoder_length,
                "max_prediction_length": max_prediction_length,
                "hidden_size": hidden_size,
                "attention_head_size": attention_head_size,
                "dropout": dropout,
                "learning_rate": learning_rate,
                "max_epochs": max_epochs,
            })

            trainer.fit(tft, train_dataloaders=train_dataloader, val_dataloaders=val_dataloader)

            best_path = checkpoint.best_model_path
            val_loss = checkpoint.best_model_score

            mlflow.log_metric("val_loss", float(val_loss) if val_loss else 0.0)
            if best_path:
                mlflow.log_artifact(best_path)

    except Exception as e:
        logger.warning("mlflow_logging_failed", error=str(e))
        trainer.fit(tft, train_dataloaders=train_dataloader, val_dataloaders=val_dataloader)
        best_path = checkpoint.best_model_path
        val_loss = checkpoint.best_model_score

    result = {
        "basin_id": basin_id,
        "best_checkpoint": best_path,
        "val_loss": float(val_loss) if val_loss else None,
        "epochs_trained": trainer.current_epoch,
        "model_params": sum(p.numel() for p in tft.parameters()),
    }

    logger.info("tft_training_complete", **result)
    return result
