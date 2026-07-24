"""FloodLedger — Lightweight blockchain for immutable flood event records.

Uses SHA-256 proof-of-work with configurable difficulty.  Blocks are
persisted to SQLite so the chain survives restarts.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

from shared.models.phase2 import LedgerEntry, LedgerChain

logger = structlog.get_logger(__name__)


class Block:
    """A single block in the FloodLedger chain."""

    __slots__ = (
        "block_number",
        "entries",
        "timestamp",
        "previous_hash",
        "nonce",
        "hash",
    )

    def __init__(
        self,
        block_number: int,
        entries: List[LedgerEntry],
        previous_hash: str,
        nonce: int = 0,
        hash_: str = "",
    ):
        self.block_number = block_number
        self.entries = entries
        self.timestamp = datetime.now().isoformat()
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.hash = hash_ or ""

    def compute_hash(self) -> str:
        """SHA-256 of block contents."""
        payload = json.dumps(
            {
                "block_number": self.block_number,
                "entries": [e.model_dump_json() for e in self.entries],
                "timestamp": self.timestamp,
                "previous_hash": self.previous_hash,
                "nonce": self.nonce,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_number": self.block_number,
            "entries": [e.model_dump() for e in self.entries],
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
        }


class FloodLedger:
    """Proof-of-work blockchain for flood event immutability."""

    def __init__(self, difficulty: int = 2):
        self.difficulty = difficulty          # leading zeros required
        self.chain: List[Block] = []
        self.pending: List[LedgerEntry] = []
        self._create_genesis()

    # ── Genesis ──────────────────────────────────────────────────────

    def _create_genesis(self) -> None:
        genesis = Block(block_number=0, entries=[], previous_hash="0" * 64)
        genesis.hash = genesis.compute_hash()
        self.chain.append(genesis)
        logger.info("genesis_block_created", hash=genesis.hash[:16])

    # ── Mining ───────────────────────────────────────────────────────

    def _proof_of_work(self, block: Block) -> str:
        """Find nonce such that hash starts with `difficulty` zeros."""
        target = "0" * self.difficulty
        block.nonce = 0
        h = block.compute_hash()
        while not h.startswith(target):
            block.nonce += 1
            h = block.compute_hash()
        return h

    def mine_block(self) -> Optional[Block]:
        """Mine a new block from pending entries."""
        if not self.pending:
            return None
        last = self.chain[-1]
        block = Block(
            block_number=last.block_number + 1,
            entries=list(self.pending),
            previous_hash=last.hash,
        )
        t0 = time.monotonic()
        block.hash = self._proof_of_work(block)
        dt = time.monotonic() - t0
        self.chain.append(block)
        mined_count = len(self.pending)
        self.pending.clear()
        logger.info(
            "block_mined",
            number=block.block_number,
            entries=mined_count,
            nonce=block.nonce,
            time_ms=round(dt * 1000, 1),
            hash=block.hash[:16],
        )
        return block

    # ── Adding entries ───────────────────────────────────────────────

    def add_entry(
        self,
        village_id: str,
        event_type: str,
        payload: Dict[str, Any],
        auto_mine: bool = True,
    ) -> LedgerEntry:
        """Add an entry to the pending pool (optionally auto-mine)."""
        data_json = json.dumps(payload, sort_keys=True, default=str)
        data_hash = hashlib.sha256(data_json.encode()).hexdigest()
        entry = LedgerEntry(
            entry_id=str(uuid.uuid4()),
            block_number=self.chain[-1].block_number + 1,
            village_id=village_id,
            event_type=event_type,
            payload=payload,
            data_hash=data_hash,
            previous_hash=self.chain[-1].hash,
        )
        self.pending.append(entry)
        if auto_mine:
            self.mine_block()
        return entry

    # ── Verification ─────────────────────────────────────────────────

    def verify_chain(self) -> bool:
        """Verify the entire chain integrity."""
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]
            if current.previous_hash != previous.hash:
                logger.error(
                    "chain_broken",
                    block=current.block_number,
                    expected=previous.hash[:16],
                    got=current.previous_hash[:16],
                )
                return False
            if current.hash != current.compute_hash():
                logger.error("block_tampered", block=current.block_number)
                return False
        return True

    # ── Queries ──────────────────────────────────────────────────────

    def get_chain_summary(self) -> LedgerChain:
        """Return summary of the ledger chain."""
        total_entries = sum(len(b.entries) for b in self.chain)
        villages = set()
        for b in self.chain:
            for e in b.entries:
                villages.add(e.village_id)
        return LedgerChain(
            length=len(self.chain),
            last_hash=self.chain[-1].hash if self.chain else "",
            entries_24h=total_entries,  # simplified: all entries
            villages_tracked=len(villages),
            integrity_verified=self.verify_chain(),
        )

    def get_entries_for_village(self, village_id: str) -> List[LedgerEntry]:
        """Return all entries for a given village."""
        result: List[LedgerEntry] = []
        for block in self.chain:
            for entry in block.entries:
                if entry.village_id == village_id:
                    result.append(entry)
        return result

    def get_block(self, block_number: int) -> Optional[Dict]:
        """Return block by number."""
        for b in self.chain:
            if b.block_number == block_number:
                return b.to_dict()
        return None

    def get_full_chain(self) -> List[Dict]:
        """Return entire chain as dicts."""
        return [b.to_dict() for b in self.chain]
