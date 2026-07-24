"""Federated Learning Server — FastAPI service (port 8009).

Enables cross-border, cross-state model improvement without sharing
raw sensor data. Each "node" shares only model gradient updates.

Architecture:
  Central ARGUS Federated Server (port 8009)
    ├── Node A: Assam (simulated locally)
    ├── Node B: Himachal Pradesh (simulated locally)
    └── Node C: Bangladesh (simulated — demonstrates cross-border)

Supports:
  - FedAvg / FedProx aggregation strategies
  - Differential Privacy (Gaussian DP-SGD with calibrated noise)
  - Flower gRPC server (when flwr available, port 8080)
  - REST API for dashboard monitoring + demo triggers

Endpoints:
  POST /api/v1/federated/start-round       → Trigger a federation round (demo)
  GET  /api/v1/federated/status            → Current round, nodes, accuracy
  GET  /api/v1/federated/nodes             → List of nodes with last update
  GET  /api/v1/federated/accuracy-history  → Per-round accuracy for chart
  GET  /api/v1/fl/model                    → Download global model weights
  POST /api/v1/fl/update                   → Submit local update
  POST /api/v1/fl/round                    → Trigger aggregation
  GET  /api/v1/fl/status                   → Convergence info
  GET  /api/v1/fl/history                  → Round history
  POST /api/v1/fl/demo/round              → Simulate complete round
  GET  /health                             → Liveness

Run: ``uvicorn services.federated_server.main:app --reload --port 8009``
"""

from __future__ import annotations

import base64
import io
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.config import get_settings
from services.federated_server.aggregator import (
    FederatedAggregator,
    create_synthetic_global_model,
    simulate_client_update,
)
from services.federated_server.clients import (
    FloodMLP,
    generate_synthetic_data,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

# Try to import Flower for gRPC server
try:
    import flwr as fl  # type: ignore[import-untyped]
    _FLOWER_AVAILABLE = True
except ImportError:
    fl = None
    _FLOWER_AVAILABLE = False

# ── Globals ──────────────────────────────────────────────────────────────
_aggregator: Optional[FederatedAggregator] = None
_pending_updates: List = []
_node_registry: Dict[str, Dict[str, Any]] = {}
_accuracy_history: List[Dict] = []
_flower_thread: Optional[threading.Thread] = None

SIMULATED_NODES = ["assam", "himachal", "bangladesh"]


class ClientUpdate(BaseModel):
    node_id: str
    n_samples: int = 100
    local_loss: float = 0.0
    local_accuracy: float = 0.0
    weights: Dict[str, str] = {}  # key -> base64-encoded ndarray


class DemoRoundRequest(BaseModel):
    n_clients: int = 3
    samples_per_client: int = 500
    training_epochs: int = 5
    nodes: List[str] = ["assam", "himachal", "bangladesh"]


def _encode_weights(weights: Dict[str, np.ndarray]) -> Dict[str, str]:
    """Encode numpy arrays to base64 for JSON transport."""
    encoded = {}
    for key, arr in weights.items():
        buf = io.BytesIO()
        np.save(buf, arr)
        encoded[key] = base64.b64encode(buf.getvalue()).decode()
    return encoded


def _decode_weights(encoded: Dict[str, str]) -> Dict[str, np.ndarray]:
    """Decode base64 strings back to numpy arrays."""
    decoded = {}
    for key, b64 in encoded.items():
        buf = io.BytesIO(base64.b64decode(b64))
        decoded[key] = np.load(buf)
    return decoded


def _start_flower_server():
    """Start Flower gRPC server in a background thread (if available)."""
    if not _FLOWER_AVAILABLE:
        logger.info("flower_not_available_skipping_grpc")
        return

    try:
        from flwr.server.strategy import FedAvg

        strategy = FedAvg(
            fraction_fit=1.0,
            min_fit_clients=2,
            min_available_clients=2,
        )

        logger.info("flower_server_starting", address="0.0.0.0:8080")
        fl.server.start_server(
            server_address="0.0.0.0:8080",
            config=fl.server.ServerConfig(num_rounds=settings.FL_ROUNDS),
            strategy=strategy,
        )
    except Exception as exc:
        logger.error("flower_server_failed", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _aggregator, _flower_thread

    logger.info("fl_server_starting", port=settings.FL_SERVER_PORT)

    # Init global model
    global_weights = create_synthetic_global_model()
    _aggregator = FederatedAggregator(
        global_weights=global_weights,
        method=settings.FL_AGGREGATION,
        dp_epsilon=settings.FL_DP_EPSILON,
        dp_delta=settings.FL_DP_DELTA,
    )

    # Initialize node registry
    for node in SIMULATED_NODES:
        _node_registry[node] = {
            "node_id": node,
            "status": "registered",
            "last_update": None,
            "total_samples_contributed": 0,
            "rounds_participated": 0,
            "last_accuracy": None,
        }

    # Start Flower gRPC server in background (optional)
    if _FLOWER_AVAILABLE:
        _flower_thread = threading.Thread(target=_start_flower_server, daemon=True)
        _flower_thread.start()

    logger.info(
        "fl_server_ready",
        method=settings.FL_AGGREGATION,
        dp_epsilon=settings.FL_DP_EPSILON,
        flower=_FLOWER_AVAILABLE,
        nodes=SIMULATED_NODES,
    )
    yield
    logger.info("fl_server_shutdown")


app = FastAPI(
    title="ARGUS Federated Learning Server",
    version="2.1.0",
    description=(
        "Cross-border federated learning with differential privacy. "
        "FedAvg/FedProx + DP-SGD + Flower gRPC + simulated multi-region nodes."
    ),
    lifespan=lifespan,
)


# ═══════════════════════════════════════════════════════════════════════
#  Health
# ═══════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {
        "service": "federated_server",
        "version": "2.1.0",
        "status": "healthy",
        "current_round": _aggregator.round_id if _aggregator else 0,
        "pending_updates": len(_pending_updates),
        "registered_nodes": len(_node_registry),
        "flower_available": _FLOWER_AVAILABLE,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Primary API (Dhana's dashboard contract)
# ═══════════════════════════════════════════════════════════════════════

@app.post("/api/v1/federated/start-round")
async def start_round_demo(req: Optional[DemoRoundRequest] = None):
    """Trigger a federation round with simulated nodes.

    This is the primary demo button: runs full local training on
    each simulated node, aggregates with DP, returns results.
    """
    if not _aggregator:
        raise HTTPException(503, "Server not ready")

    if req is None:
        req = DemoRoundRequest()

    results_per_node = {}
    all_deltas = []
    now = datetime.now(timezone.utc)

    for node_id in req.nodes[:req.n_clients]:
        # Generate node-specific data
        X, y = generate_synthetic_data(node_id, req.samples_per_client)

        # Create local model, set global weights, train
        model = FloodMLP()
        global_params = [_aggregator.global_weights[k] for k in sorted(_aggregator.global_weights.keys())]
        model.set_weights([w.copy() for w in global_params])

        loss = model.train(X, y, epochs=req.training_epochs)
        _, accuracy = model.evaluate(X, y)

        # Compute deltas
        updated = model.get_weights()
        deltas = {}
        for i, k in enumerate(sorted(_aggregator.global_weights.keys())):
            deltas[k] = updated[i] - global_params[i]

        all_deltas.append((deltas, req.samples_per_client))

        # Update node registry
        if node_id in _node_registry:
            _node_registry[node_id].update({
                "status": "active",
                "last_update": now.isoformat(),
                "total_samples_contributed": _node_registry[node_id].get("total_samples_contributed", 0) + req.samples_per_client,
                "rounds_participated": _node_registry[node_id].get("rounds_participated", 0) + 1,
                "last_accuracy": round(accuracy, 4),
                "last_loss": round(loss, 4),
            })

        results_per_node[node_id] = {
            "loss": round(loss, 4),
            "accuracy": round(accuracy, 4),
            "samples": req.samples_per_client,
            "gradient_norm": round(float(np.sqrt(sum(np.sum(d**2) for d in deltas.values()))), 4),
        }

    # Aggregate with DP
    _aggregator.aggregate(all_deltas)

    # Evaluate global model on all nodes
    global_accs = {}
    global_params = [_aggregator.global_weights[k] for k in sorted(_aggregator.global_weights.keys())]
    for node_id in req.nodes[:req.n_clients]:
        model = FloodMLP()
        model.set_weights([w.copy() for w in global_params])
        X, y = generate_synthetic_data(node_id, req.samples_per_client)
        _, acc = model.evaluate(X, y)
        global_accs[node_id] = round(acc, 4)

    mean_acc = round(float(np.mean(list(global_accs.values()))), 4)

    # Record in history
    _accuracy_history.append({
        "round": _aggregator.round_id,
        "mean_accuracy": mean_acc,
        "per_node_accuracy": global_accs,
        "privacy_budget_spent": round(_aggregator._privacy_budget_spent, 4),
        "timestamp": now.isoformat(),
        "nodes_participated": list(results_per_node.keys()),
    })

    return {
        "round": _aggregator.round_id,
        "mean_accuracy": mean_acc,
        "per_node": results_per_node,
        "global_accuracy": global_accs,
        "convergence": _aggregator.get_convergence_metrics(),
    }


@app.get("/api/v1/federated/status")
async def federated_status():
    if not _aggregator:
        raise HTTPException(503, "Server not ready")
    return {
        **_aggregator.get_convergence_metrics(),
        "registered_nodes": len(_node_registry),
        "pending_updates": len(_pending_updates),
        "flower_active": _FLOWER_AVAILABLE,
        "latest_accuracy": _accuracy_history[-1]["mean_accuracy"] if _accuracy_history else None,
    }


@app.get("/api/v1/federated/nodes")
async def federated_nodes():
    return list(_node_registry.values())


@app.get("/api/v1/federated/accuracy-history")
async def federated_accuracy_history():
    return _accuracy_history


# ═══════════════════════════════════════════════════════════════════════
#  Low-level FL API (backward compat + edge node integration)
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/v1/fl/model")
async def get_model():
    """Download the current global model weights."""
    if not _aggregator:
        raise HTTPException(503, "Server not ready")
    encoded = _encode_weights(_aggregator.get_global_weights())
    return {
        "round": _aggregator.round_id,
        "version": f"v{_aggregator.round_id}",
        "layers": list(encoded.keys()),
        "weights": encoded,
    }


@app.post("/api/v1/fl/update")
async def submit_update(update: ClientUpdate):
    """Submit a local model update from an edge node."""
    if not _aggregator:
        raise HTTPException(503, "Server not ready")

    if update.weights:
        delta = _decode_weights(update.weights)
    else:
        delta, _ = simulate_client_update(
            _aggregator.get_global_weights(),
            n_samples=update.n_samples,
        )

    _pending_updates.append((delta, update.n_samples))

    # Update node registry
    now = datetime.now(timezone.utc)
    if update.node_id not in _node_registry:
        _node_registry[update.node_id] = {
            "node_id": update.node_id,
            "status": "registered",
            "last_update": now.isoformat(),
            "total_samples_contributed": update.n_samples,
            "rounds_participated": 0,
        }
    else:
        _node_registry[update.node_id]["last_update"] = now.isoformat()
        _node_registry[update.node_id]["total_samples_contributed"] = (
            _node_registry[update.node_id].get("total_samples_contributed", 0) + update.n_samples
        )

    logger.info(
        "client_update_received",
        node=update.node_id,
        samples=update.n_samples,
        pending=len(_pending_updates),
    )
    return {
        "accepted": True,
        "node_id": update.node_id,
        "pending_updates": len(_pending_updates),
        "min_for_round": settings.FL_MIN_CLIENTS,
    }


@app.post("/api/v1/fl/round")
async def trigger_round():
    """Trigger a federated aggregation round from pending updates."""
    if not _aggregator:
        raise HTTPException(503, "Server not ready")
    if len(_pending_updates) < settings.FL_MIN_CLIENTS:
        return {
            "triggered": False,
            "reason": f"Need at least {settings.FL_MIN_CLIENTS} updates, have {len(_pending_updates)}",
        }
    _aggregator.aggregate(_pending_updates)
    _pending_updates.clear()
    round_info = _aggregator.get_round_info()
    return {
        "triggered": True,
        "round": round_info.model_dump() if round_info else {},
    }


@app.get("/api/v1/fl/status")
async def fl_status():
    if not _aggregator:
        raise HTTPException(503, "Server not ready")
    return _aggregator.get_convergence_metrics()


@app.get("/api/v1/fl/history")
async def fl_history():
    if not _aggregator:
        raise HTTPException(503, "Server not ready")
    return [r.model_dump() for r in _aggregator.history]


@app.post("/api/v1/fl/demo/round")
async def demo_round(n_clients: int = 3, samples_per_client: int = 200):
    """Simulate a complete federated round (simple version)."""
    if not _aggregator:
        raise HTTPException(503, "Server not ready")

    updates = []
    for i in range(n_clients):
        delta, n = simulate_client_update(
            _aggregator.get_global_weights(),
            n_samples=samples_per_client,
            noise_scale=0.005,
        )
        updates.append((delta, n))

    _aggregator.aggregate(updates)
    return {
        "round": _aggregator.round_id,
        "clients": n_clients,
        "samples_per_client": samples_per_client,
        "convergence": _aggregator.get_convergence_metrics(),
    }


# ═══════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(
        "services.federated_server.main:app",
        host=settings.SERVICE_HOST,
        port=settings.FL_SERVER_PORT,
        reload=False,
    )
