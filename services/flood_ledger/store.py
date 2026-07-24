"""SQLite persistence layer for FloodLedger.

Stores blocks and entries so the chain survives service restarts.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Optional

import structlog

from shared.models.phase2 import LedgerEntry
from services.flood_ledger.chain import Block, FloodLedger

logger = structlog.get_logger(__name__)


class LedgerStore:
    """SQLite-backed persistence for the FloodLedger."""

    def __init__(self, db_path: str = "./data/flood_ledger.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()
        logger.info("ledger_store_ready", path=db_path)

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS blocks (
                block_number INTEGER PRIMARY KEY,
                timestamp    TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                nonce        INTEGER NOT NULL,
                hash         TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS entries (
                entry_id     TEXT PRIMARY KEY,
                block_number INTEGER NOT NULL,
                village_id   TEXT NOT NULL,
                event_type   TEXT NOT NULL,
                payload      TEXT NOT NULL,
                data_hash    TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                timestamp    TEXT NOT NULL,
                verified     INTEGER DEFAULT 0,
                FOREIGN KEY (block_number) REFERENCES blocks(block_number)
            );
            CREATE INDEX IF NOT EXISTS idx_entries_village ON entries(village_id);
            CREATE INDEX IF NOT EXISTS idx_entries_type ON entries(event_type);
        """)
        self._conn.commit()

    def save_block(self, block: Block) -> None:
        """Persist a mined block and its entries."""
        self._conn.execute(
            "INSERT OR REPLACE INTO blocks VALUES (?, ?, ?, ?, ?)",
            (
                block.block_number,
                block.timestamp,
                block.previous_hash,
                block.nonce,
                block.hash,
            ),
        )
        for entry in block.entries:
            self._conn.execute(
                "INSERT OR REPLACE INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.entry_id,
                    entry.block_number,
                    entry.village_id,
                    entry.event_type,
                    json.dumps(entry.payload, default=str),
                    entry.data_hash,
                    entry.previous_hash,
                    entry.timestamp.isoformat() if hasattr(entry.timestamp, "isoformat") else str(entry.timestamp),
                    1 if entry.verified else 0,
                ),
            )
        self._conn.commit()

    def load_chain(self, ledger: FloodLedger) -> int:
        """Load persisted chain into a FloodLedger instance. Returns block count loaded."""
        cursor = self._conn.execute(
            "SELECT block_number, timestamp, previous_hash, nonce, hash FROM blocks ORDER BY block_number"
        )
        rows = cursor.fetchall()
        if not rows:
            return 0

        loaded = 0
        for row in rows:
            bn, ts, prev_hash, nonce, hash_ = row
            if bn == 0:
                # Update genesis if it exists
                if ledger.chain and ledger.chain[0].block_number == 0:
                    ledger.chain[0].hash = hash_
                continue
            # Load entries for this block
            ecursor = self._conn.execute(
                "SELECT entry_id, block_number, village_id, event_type, payload, data_hash, previous_hash, timestamp, verified "
                "FROM entries WHERE block_number = ?",
                (bn,),
            )
            entries = []
            for er in ecursor.fetchall():
                entries.append(
                    LedgerEntry(
                        entry_id=er[0],
                        block_number=er[1],
                        village_id=er[2],
                        event_type=er[3],
                        payload=json.loads(er[4]),
                        data_hash=er[5],
                        previous_hash=er[6],
                        timestamp=er[7],
                        verified=bool(er[8]),
                    )
                )
            block = Block(
                block_number=bn,
                entries=entries,
                previous_hash=prev_hash,
                nonce=nonce,
                hash_=hash_,
            )
            block.timestamp = ts
            ledger.chain.append(block)
            loaded += 1

        logger.info("chain_loaded", blocks=loaded)
        return loaded

    def get_stats(self) -> dict:
        """Return DB stats."""
        blocks = self._conn.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]
        entries = self._conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        villages = self._conn.execute("SELECT COUNT(DISTINCT village_id) FROM entries").fetchone()[0]
        return {"blocks": blocks, "entries": entries, "villages_tracked": villages}

    def close(self) -> None:
        self._conn.close()
