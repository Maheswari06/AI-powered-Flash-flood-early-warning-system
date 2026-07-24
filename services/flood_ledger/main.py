"""FloodLedger — FastAPI service (port 8007).

Blockchain-anchored parametric insurance oracle.
Auto-triggers payouts when confirmed flood polygon intersects insured assets.

Exposes:
  POST /api/v1/ledger/record           → add an entry (legacy blockchain)
  GET  /api/v1/ledger/chain            → full chain
  GET  /api/v1/ledger/chain/summary    → chain summary stats
  GET  /api/v1/ledger/block/{number}   → specific block
  GET  /api/v1/ledger/village/{id}     → entries for a village
  GET  /api/v1/ledger/verify           → integrity check
  POST /api/v1/ledger/record-event     → record confirmed flood event (Phase 2)
  GET  /api/v1/ledger/events           → list flood events (Phase 2)
  GET  /api/v1/ledger/assets           → insured asset locations (Phase 2)
  POST /api/v1/ledger/demo-trigger     → one-click demo button (Phase 2)
  GET  /health                         → liveness
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Dict

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared.config import get_settings
from services.flood_ledger.chain import FloodLedger
from services.flood_ledger.store import LedgerStore
from services.flood_ledger.blockchain.hardhat_client import HardhatClient
from services.flood_ledger.oracle.intersection_detector import IntersectionDetector
from services.flood_ledger.api.routes import router as oracle_router, init_router

logger = structlog.get_logger(__name__)
settings = get_settings()

FLOOD_LEDGER_PORT = int(os.getenv("FLOOD_LEDGER_PORT", "8007"))
HARDHAT_RPC_URL = os.getenv("HARDHAT_RPC_URL", "http://localhost:8545")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "")
ASSET_REGISTRY_PATH = os.getenv("ASSET_REGISTRY_PATH", "./data/insured_assets.csv")

# ── Globals ──────────────────────────────────────────────────────────────
_ledger: FloodLedger | None = None
_store: LedgerStore | None = None
_blockchain: HardhatClient | None = None
_detector: IntersectionDetector | None = None


class RecordRequest(BaseModel):
    village_id: str
    event_type: str = "prediction"
    payload: Dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ledger, _store, _blockchain, _detector
    logger.info("flood_ledger_starting", port=FLOOD_LEDGER_PORT)

    # Legacy blockchain
    _ledger = FloodLedger(difficulty=settings.LEDGER_DIFFICULTY)
    _store = LedgerStore(db_path=settings.LEDGER_DB_PATH)
    loaded = _store.load_chain(_ledger)

    # Phase 2: Hardhat blockchain client + intersection detector
    _blockchain = HardhatClient(
        rpc_url=HARDHAT_RPC_URL,
        contract_address=CONTRACT_ADDRESS or None,
    )
    _detector = IntersectionDetector(asset_registry_path=ASSET_REGISTRY_PATH)

    # Wire Phase 2 Oracle routes
    init_router(_blockchain, _detector)

    logger.info(
        "flood_ledger_ready",
        chain_length=len(_ledger.chain),
        loaded=loaded,
        blockchain_connected=_blockchain.is_connected,
        assets_registered=len(_detector.assets),
    )
    yield

    for block in _ledger.chain:
        _store.save_block(block)
    _store.close()
    logger.info("flood_ledger_shutdown")


app = FastAPI(
    title="ARGUS FloodLedger Oracle",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount Phase 2 Oracle routes ──────────────────────────────────────────
app.include_router(oracle_router)


# ═══════════════════════════════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    stats = _store.get_stats() if _store else {}
    return {
        "service": "flood_ledger",
        "version": "2.0.0",
        "status": "healthy",
        "chain_length": len(_ledger.chain) if _ledger else 0,
        **stats,
    }


@app.post("/api/v1/ledger/record")
async def record(req: RecordRequest):
    """Add a new entry to the ledger (auto-mines a block)."""
    if not _ledger or not _store:
        raise HTTPException(503, "Ledger not ready")
    entry = _ledger.add_entry(
        village_id=req.village_id,
        event_type=req.event_type,
        payload=req.payload,
        auto_mine=True,
    )
    # Persist the new block
    _store.save_block(_ledger.chain[-1])
    return {
        "entry_id": entry.entry_id,
        "block_number": _ledger.chain[-1].block_number,
        "hash": _ledger.chain[-1].hash,
        "data_hash": entry.data_hash,
    }


@app.get("/api/v1/ledger/chain")
async def get_chain():
    """Return the full chain."""
    if not _ledger:
        raise HTTPException(503, "Ledger not ready")
    return _ledger.get_full_chain()


@app.get("/api/v1/ledger/chain/summary")
async def chain_summary():
    if not _ledger:
        raise HTTPException(503, "Ledger not ready")
    return _ledger.get_chain_summary().model_dump()


@app.get("/api/v1/ledger/block/{block_number}")
async def get_block(block_number: int):
    if not _ledger:
        raise HTTPException(503, "Ledger not ready")
    block = _ledger.get_block(block_number)
    if block is None:
        raise HTTPException(404, f"Block {block_number} not found")
    return block


@app.get("/api/v1/ledger/village/{village_id}")
async def village_entries(village_id: str):
    if not _ledger:
        raise HTTPException(503, "Ledger not ready")
    entries = _ledger.get_entries_for_village(village_id)
    return [e.model_dump() for e in entries]


@app.get("/api/v1/ledger/verify")
async def verify():
    """Verify chain integrity."""
    if not _ledger:
        raise HTTPException(503, "Ledger not ready")
    valid = _ledger.verify_chain()
    return {
        "integrity": valid,
        "chain_length": len(_ledger.chain),
        "last_hash": _ledger.chain[-1].hash if _ledger.chain else "",
    }


# ═══════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(
        "services.flood_ledger.main:app",
        host="0.0.0.0",
        port=FLOOD_LEDGER_PORT,
        reload=False,
    )
