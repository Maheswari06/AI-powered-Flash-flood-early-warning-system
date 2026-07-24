"""ORACLE v2 FastAPI service — on-device flood prediction (port 8017).

Exposes the MobileFloodFormer inference pipeline as a REST API
for ACN (Autonomous Community Nodes) and the API Gateway.

Endpoints:
  POST /api/v1/oracle/predict        → Single village prediction
  POST /api/v1/oracle/predict/batch   → Batch prediction
  GET  /api/v1/oracle/model/info      → Model metadata + constraints
  GET  /api/v1/oracle/explain/{id}    → Attention explanation for last prediction
  POST /api/v1/oracle/quantize        → Trigger quantization pipeline
  GET  /health                        → Liveness check

Run: ``uvicorn services.oracle_v2.main:app --reload --port 8017``
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import structlog
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from services.oracle_v2.mobile_flood_former import (
    AlertLevel,
    MobileFloodFormer,
    OracleV2InferencePipeline,
    OracleV2Quantizer,
    create_oracle_v2,
)

logger = structlog.get_logger(__name__)


# ── Request / Response Schemas ───────────────────────────────────────────

class PredictionRequest(BaseModel):
    """Single village prediction request."""
    village_id: str = Field(..., description="Unique village identifier")
    sensor_data: list[list[float]] = Field(
        ...,
        description="24×6 array: [water_level, rainfall, soil_moisture, "
                    "rate_change, hour, is_monsoon] per hour",
        min_length=24, max_length=24,
    )

class BatchPredictionRequest(BaseModel):
    """Multi-village batch prediction."""
    predictions: list[PredictionRequest]

class PredictionResponse(BaseModel):
    """Prediction result."""
    village_id: str
    risk_score: float
    alert_level: str
    alert_probs: list[float]
    inference_ms: float
    meets_latency_target: bool
    attention_weights: list[float]
    explanation: Optional[dict] = None
    timestamp: str
    model_version: str = "oracle_v2_mobilefloodformer"

class ModelInfoResponse(BaseModel):
    """Model metadata."""
    model_name: str = "MobileFloodFormer"
    version: str = "2.0.0"
    parameters: int
    model_size_kb: float
    max_input_shape: str = "(batch, 24, 6)"
    target_latency_ms: float = 80.0
    target_size_kb: float = 500.0
    quantized: bool
    architecture: dict

class QuantizeRequest(BaseModel):
    """Request to quantize model for RPi deployment."""
    village_id: str
    n_calibration_samples: int = Field(default=200, ge=50, le=5000)
    output_format: str = Field(default="torchscript", pattern="^(torchscript|onnx)$")


# ── App State ────────────────────────────────────────────────────────────

_model: Optional[MobileFloodFormer] = None
_pipeline: Optional[OracleV2InferencePipeline] = None
_quantized: bool = False
_last_results: dict[str, PredictionResponse] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise model on startup."""
    global _model, _pipeline

    logger.info("oracle_v2_starting")

    _model, _pipeline = create_oracle_v2()
    warmup_ms = _pipeline.warmup(n_runs=10)

    logger.info(
        "oracle_v2_ready",
        params=_model.count_parameters(),
        size_kb=f"{_model.model_size_bytes() / 1024:.1f}",
        warmup_median_ms=f"{warmup_ms:.1f}",
    )
    yield
    logger.info("oracle_v2_shutdown")


app = FastAPI(
    title="ARGUS ORACLE v2",
    description="On-device MobileFloodFormer inference service",
    version="2.0.0",
    lifespan=lifespan,
)


# ── Endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "service": "oracle_v2",
        "status": "healthy" if _model is not None else "initializing",
        "model_loaded": _model is not None,
        "quantized": _quantized,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/v1/oracle/predict", response_model=PredictionResponse)
async def predict(req: PredictionRequest):
    """Run single village prediction through MobileFloodFormer."""
    if _pipeline is None:
        raise HTTPException(503, "Model not loaded yet")

    try:
        tensor = torch.tensor(req.sensor_data, dtype=torch.float32)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"Invalid sensor data: {e}")

    if tensor.shape != (24, 6):
        raise HTTPException(
            400,
            f"Expected sensor_data shape (24, 6), got {tuple(tensor.shape)}",
        )

    result = _pipeline.predict(tensor)
    explanation = _pipeline.get_attention_explanation(result)

    response = PredictionResponse(
        village_id=req.village_id,
        risk_score=result.risk_score,
        alert_level=result.alert_level.name,
        alert_probs=result.alert_probs,
        inference_ms=result.inference_ms,
        meets_latency_target=result.meets_latency_target,
        attention_weights=result.attention_weights,
        explanation=explanation,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    _last_results[req.village_id] = response
    return response


@app.post("/api/v1/oracle/predict/batch")
async def predict_batch(req: BatchPredictionRequest):
    """Batch prediction for multiple villages."""
    if _pipeline is None:
        raise HTTPException(503, "Model not loaded yet")

    tensors = []
    for pred_req in req.predictions:
        try:
            t = torch.tensor(pred_req.sensor_data, dtype=torch.float32)
            if t.shape != (24, 6):
                raise ValueError(f"Bad shape {t.shape}")
            tensors.append(t)
        except (ValueError, TypeError) as e:
            raise HTTPException(
                400,
                f"Invalid sensor data for {pred_req.village_id}: {e}",
            )

    batch = torch.stack(tensors)
    results = _pipeline.predict_batch(batch)

    responses = []
    for pred_req, result in zip(req.predictions, results):
        explanation = _pipeline.get_attention_explanation(result)
        resp = PredictionResponse(
            village_id=pred_req.village_id,
            risk_score=result.risk_score,
            alert_level=result.alert_level.name,
            alert_probs=result.alert_probs,
            inference_ms=result.inference_ms,
            meets_latency_target=result.meets_latency_target,
            attention_weights=result.attention_weights,
            explanation=explanation,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        _last_results[pred_req.village_id] = resp
        responses.append(resp)

    return {"predictions": responses, "total_villages": len(responses)}


@app.get("/api/v1/oracle/model/info", response_model=ModelInfoResponse)
async def model_info():
    """Return MobileFloodFormer architecture and constraint info."""
    if _model is None:
        raise HTTPException(503, "Model not loaded yet")

    return ModelInfoResponse(
        parameters=_model.count_parameters(),
        model_size_kb=round(_model.model_size_bytes() / 1024, 1),
        quantized=_quantized,
        architecture={
            "type": "MicroTransformer",
            "d_model": _model.d_model,
            "n_heads": 4,
            "n_layers": 2,
            "d_ff": 64,
            "seq_len": _model.seq_len,
            "n_features": _model.n_features,
            "pooling": "attention_weighted",
            "output_heads": ["risk_score (sigmoid)", "alert_level (4-class softmax)"],
            "comparison_to_bert": {
                "bert_params": "110M",
                "oracle_v2_params": f"{_model.count_parameters():,}",
                "reduction_factor": f"{110_000_000 / _model.count_parameters():.0f}x",
            },
        },
    )


@app.get("/api/v1/oracle/explain/{village_id}")
async def explain(village_id: str):
    """Get attention-based explanation for the last prediction."""
    if village_id not in _last_results:
        raise HTTPException(404, f"No prediction found for village: {village_id}")

    return _last_results[village_id].explanation


@app.post("/api/v1/oracle/quantize")
async def quantize(req: QuantizeRequest):
    """Trigger model quantization for RPi deployment."""
    global _quantized

    if _model is None:
        raise HTTPException(503, "Model not loaded yet")

    # Generate synthetic calibration data (in production, use real village data)
    calibration = torch.randn(req.n_calibration_samples, 24, 6)

    quantizer = OracleV2Quantizer()
    quantized_model, report = quantizer.quantize_for_rpi(_model, calibration)

    if req.output_format == "onnx":
        path = quantizer.export_to_onnx(
            _model, f"/tmp/oracle_v2/{req.village_id}", req.village_id
        )
    else:
        path = quantizer.save_for_rpi(
            quantized_model, f"/tmp/oracle_v2/{req.village_id}", req.village_id
        )

    _quantized = True

    return {
        "village_id": req.village_id,
        "format": req.output_format,
        "output_path": path,
        "original_size_kb": report.original_size_kb,
        "quantized_size_kb": report.quantized_size_kb,
        "compression_ratio": f"{report.compression_ratio:.1f}x",
        "meets_500kb": report.meets_500kb_constraint,
        "calibration_samples": report.calibration_samples,
    }


# ── Entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "services.oracle_v2.main:app",
        host="0.0.0.0",
        port=8017,
        reload=True,
    )
