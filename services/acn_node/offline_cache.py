"""Offline reading cache backed by SQLite.

Stores the last *N* sensor readings + ORACLE predictions so the ACN
can operate fully disconnected. Also provides the "last known good"
reading when the physical sensor is unreachable.

Database: ``./data/acn_{node_id}.sqlite``
Table:    ``readings`` — timestamp, features JSON, risk_score, synced flag
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class OfflineCache:
    """SQLite-backed ring buffer for offline ACN readings.

    Parameters
    ----------
    node_id : str
        Used to derive the database filename.
    db_dir : str
        Directory for the SQLite file.
    max_readings : int
        Maximum number of readings to retain (oldest pruned first).
    """

    def __init__(
        self,
        node_id: str = "unknown",
        db_dir: str = "./data",
        max_readings: int = 500,
    ) -> None:
        self._node_id = node_id
        self._max = max_readings

        db_path = Path(db_dir)
        db_path.mkdir(parents=True, exist_ok=True)
        self._db_file = str(db_path / f"acn_{node_id}.sqlite")

        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # ── Lifecycle ────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Create table if not exists."""
        self._conn = sqlite3.connect(self._db_file, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS readings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                features    TEXT    NOT NULL,
                risk_score  REAL,
                alert_level TEXT,
                synced      INTEGER DEFAULT 0
            );
            """
        )
        # Index for fast "latest" and "unsynced" queries
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ts ON readings(timestamp DESC);"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_synced ON readings(synced) WHERE synced = 0;"
        )
        self._conn.commit()
        logger.info("offline_cache_ready", node=self._node_id, db=self._db_file)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Write ────────────────────────────────────────────────────────────

    def store_reading(
        self,
        features: Dict[str, float],
        risk_score: Optional[float] = None,
        alert_level: Optional[str] = None,
    ) -> int:
        """Persist a sensor reading + prediction.

        Returns the inserted row id.
        """
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO readings (timestamp, features, risk_score, alert_level)
            VALUES (?, ?, ?, ?)
            """,
            (now, json.dumps(features), risk_score, alert_level),
        )
        self._conn.commit()
        row_id = cur.lastrowid

        # Prune old readings beyond max
        self._prune()

        logger.debug(
            "reading_cached",
            node=self._node_id,
            row_id=row_id,
            risk_score=risk_score,
        )
        return row_id

    def _prune(self) -> None:
        """Delete oldest readings exceeding the ring buffer limit."""
        count = self._conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
        if count > self._max:
            excess = count - self._max
            self._conn.execute(
                """
                DELETE FROM readings
                WHERE id IN (
                    SELECT id FROM readings ORDER BY id ASC LIMIT ?
                )
                """,
                (excess,),
            )
            self._conn.commit()
            logger.debug("cache_pruned", node=self._node_id, removed=excess)

    # ── Read ─────────────────────────────────────────────────────────────

    def get_latest(self) -> Optional[Dict[str, Any]]:
        """Return the most recent cached reading, or None."""
        row = self._conn.execute(
            "SELECT timestamp, features, risk_score, alert_level FROM readings "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return {
            "timestamp": row[0],
            "features": json.loads(row[1]),
            "risk_score": row[2],
            "alert_level": row[3],
        }

    def get_last_n(self, n: int = 10) -> List[Dict[str, Any]]:
        """Return the last *n* readings (newest first)."""
        rows = self._conn.execute(
            "SELECT timestamp, features, risk_score, alert_level FROM readings "
            "ORDER BY id DESC LIMIT ?",
            (n,),
        ).fetchall()
        return [
            {
                "timestamp": r[0],
                "features": json.loads(r[1]),
                "risk_score": r[2],
                "alert_level": r[3],
            }
            for r in rows
        ]

    def get_unsynced(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return readings not yet synced to the cloud."""
        rows = self._conn.execute(
            "SELECT id, timestamp, features, risk_score, alert_level FROM readings "
            "WHERE synced = 0 ORDER BY id ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "timestamp": r[1],
                "features": json.loads(r[2]),
                "risk_score": r[3],
                "alert_level": r[4],
            }
            for r in rows
        ]

    def mark_synced(self, row_ids: List[int]) -> None:
        """Mark readings as successfully synced."""
        if not row_ids:
            return
        placeholders = ",".join("?" for _ in row_ids)
        self._conn.execute(
            f"UPDATE readings SET synced = 1 WHERE id IN ({placeholders})",
            row_ids,
        )
        self._conn.commit()
        logger.debug("readings_marked_synced", node=self._node_id, count=len(row_ids))

    # ── Stats ────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        total = self._conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
        unsynced = self._conn.execute(
            "SELECT COUNT(*) FROM readings WHERE synced = 0"
        ).fetchone()[0]
        return {
            "node_id": self._node_id,
            "total_readings": total,
            "unsynced": unsynced,
            "max_capacity": self._max,
            "db_file": self._db_file,
        }
