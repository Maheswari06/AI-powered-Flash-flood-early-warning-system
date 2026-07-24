"""Phase 2 FloodLedger Oracle API routes.

Mounted by ``main.py`` via ``app.include_router(oracle_router)``.
The ``init_router`` function wires up the blockchain client and
intersection detector at startup.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException

from shared.models.phase2 import (
    DemoTriggerRequest,
    DemoTriggerResponse,
    FloodEvent,
    IntersectedAsset,
    PayoutRecord,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/ledger", tags=["flood-ledger-oracle"])

# Wired at startup via init_router()
_blockchain = None
_detector = None


def init_router(blockchain, detector) -> None:  # noqa: ANN001
    """Wire singletons created during lifespan into the router."""
    global _blockchain, _detector
    _blockchain = blockchain
    _detector = detector
    logger.info("oracle_routes_initialised")


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post("/record-event", response_model=FloodEvent)
async def record_event(
    basin_id: str = "brahmaputra_upper",
    severity: str = "SEVERE",
    polygon: Optional[Dict[str, Any]] = None,
):
    """Record a confirmed flood event on the blockchain."""
    if _blockchain is None:
        raise HTTPException(503, "Blockchain client not ready")

    event_id = f"EVT-{uuid.uuid4().hex[:8].upper()}"
    polygon_hash = hashlib.sha256(
        json.dumps(polygon or {}, sort_keys=True).encode()
    ).hexdigest()

    tx_hash = _blockchain.record_flood_event(
        event_id=event_id,
        polygon_hash=polygon_hash,
        severity=severity,
    )

    return FloodEvent(
        event_id=event_id,
        basin_id=basin_id,
        flood_polygon_geojson=polygon,
        flood_polygon_hash=polygon_hash,
        severity=severity,
        satellite_confirmed=True,
        tx_hash=tx_hash,
    )


@router.get("/events")
async def list_events():
    """List all recorded flood events."""
    if _blockchain is None:
        raise HTTPException(503, "Blockchain client not ready")
    return _blockchain.get_events()


@router.get("/assets", response_model=List[IntersectedAsset])
async def list_assets():
    """List all insured assets from the registry."""
    if _detector is None:
        raise HTTPException(503, "Intersection detector not ready")
    return [
        IntersectedAsset(
            asset_id=a["asset_id"],
            name=a["name"],
            lat=a["lat"],
            lon=a["lon"],
            insured_value_inr=a["insured_value_inr"],
            insurer_id=a["insurer_id"],
        )
        for a in _detector.assets
    ]


@router.post("/demo-trigger", response_model=DemoTriggerResponse)
async def demo_trigger(req: DemoTriggerRequest):
    """One-click demo: simulate a flood event → detect assets → trigger payouts."""
    if _blockchain is None or _detector is None:
        raise HTTPException(503, "Oracle not ready")

    event_id = f"EVT-{uuid.uuid4().hex[:8].upper()}"
    polygon_hash = hashlib.sha256(
        f"demo-{event_id}".encode()
    ).hexdigest()

    # Record event on-chain
    tx_hash = _blockchain.record_flood_event(
        event_id=event_id,
        polygon_hash=polygon_hash,
        severity=req.severity,
    )

    event = FloodEvent(
        event_id=event_id,
        basin_id=req.basin_id,
        flood_polygon_hash=polygon_hash,
        severity=req.severity,
        satellite_confirmed=req.satellite_confirmed,
        tx_hash=tx_hash,
    )

    # Detect intersected assets (demo mode → all assets)
    intersected = _detector.detect(flood_polygon_geojson=None)

    # Compute parametric payouts
    payouts = _detector.compute_payouts(event_id, intersected, req.severity)

    # Record payouts on-chain
    for payout in payouts:
        payout.tx_hash = _blockchain.record_payout(
            event_id=event_id,
            asset_id=payout.asset_id,
            amount_inr=payout.amount_inr,
            insurer_id=payout.insurer_id,
        )
        payout.executed = True

    total = sum(p.amount_inr for p in payouts)

    logger.info(
        "demo_trigger_complete",
        event_id=event_id,
        assets=len(intersected),
        total_payout=total,
    )

    return DemoTriggerResponse(
        event=event,
        intersected_assets=intersected,
        payouts=payouts,
        total_payout_inr=total,
    )
