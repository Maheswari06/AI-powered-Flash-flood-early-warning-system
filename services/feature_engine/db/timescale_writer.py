"""TimescaleDB writer for enriched feature rows.

Uses ``asyncpg`` for async writes to PostgreSQL + TimescaleDB.

Schema::

    CREATE TABLE feature_store (
        time        TIMESTAMPTZ NOT NULL,
        village_id  TEXT NOT NULL,
        station_id  TEXT,
        features    JSONB NOT NULL,
        quality     TEXT DEFAULT 'GOOD'
    );
    SELECT create_hypertable('feature_store', 'time');
"""

from __future__ import annotations

import json
from typing import List, Optional

import structlog

from services.feature_engine.schemas import FeatureRow

logger = structlog.get_logger(__name__)

# ── Attempt to import asyncpg; fall back gracefully in demo mode ──────────
try:
    import asyncpg

    _ASYNCPG_AVAILABLE = True
except ImportError:
    _ASYNCPG_AVAILABLE = False
    logger.warning("asyncpg_not_installed_timescale_writes_disabled")


# SQL statements
_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS feature_store (
    time        TIMESTAMPTZ NOT NULL,
    village_id  TEXT NOT NULL,
    station_id  TEXT,
    features    JSONB NOT NULL,
    quality     TEXT DEFAULT 'GOOD'
);
"""

_CREATE_HYPERTABLE = """
SELECT create_hypertable('feature_store', 'time', if_not_exists => TRUE);
"""

_INSERT_ROW = """
INSERT INTO feature_store (time, village_id, station_id, features, quality)
VALUES ($1, $2, $3, $4::jsonb, $5)
ON CONFLICT DO NOTHING;
"""

_SELECT_LATEST = """
SELECT time, village_id, station_id, features, quality
FROM feature_store
WHERE village_id = $1
ORDER BY time DESC
LIMIT 1;
"""

_SELECT_RANGE = """
SELECT time, village_id, station_id, features, quality
FROM feature_store
WHERE village_id = $1
  AND time >= $2
  AND time <= $3
ORDER BY time ASC;
"""


class TimescaleWriter:
    """Async writer/reader for the TimescaleDB ``feature_store`` hyper-table.

    Usage::

        writer = TimescaleWriter(dsn="postgresql://user:pass@host/db")
        await writer.connect()
        await writer.write(feature_row)
        await writer.close()
    """

    def __init__(self, dsn: str) -> None:
        """
        Args:
            dsn: PostgreSQL connection string
                 e.g. ``postgresql://argus:argus@timescaledb:5432/argus``
        """
        self._dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None  # type: ignore[name-defined]

    # ── lifecycle ──────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Establish a connection pool and ensure the schema exists."""
        if not _ASYNCPG_AVAILABLE:
            logger.warning("timescale_connect_skipped_no_asyncpg")
            return

        try:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=2, max_size=10)
            async with self._pool.acquire() as conn:
                await conn.execute(_CREATE_TABLE)
                try:
                    await conn.execute(_CREATE_HYPERTABLE)
                except Exception:
                    # TimescaleDB extension may not be installed;
                    # plain PG table still works for development
                    logger.warning("timescale_hypertable_creation_skipped")
            logger.info("timescale_connected", dsn=self._dsn.split("@")[-1])
        except Exception as exc:
            logger.error("timescale_connect_failed", error=str(exc))
            self._pool = None

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("timescale_pool_closed")

    # ── write ─────────────────────────────────────────────────────────

    async def write(self, row: FeatureRow) -> bool:
        """Insert a single FeatureRow into TimescaleDB.

        Returns True on success, False on failure or if pool unavailable.
        """
        if self._pool is None:
            logger.debug("timescale_write_skipped_no_pool", village=row.village_id)
            return False

        try:
            features_json = json.dumps(row.features, default=str)
            async with self._pool.acquire() as conn:
                await conn.execute(
                    _INSERT_ROW,
                    row.timestamp,
                    row.village_id,
                    row.station_id,
                    features_json,
                    row.quality.value,
                )
            logger.debug(
                "timescale_row_written",
                village=row.village_id,
                station=row.station_id,
                ts=row.timestamp.isoformat(),
            )
            return True
        except Exception as exc:
            logger.error("timescale_write_error", error=str(exc))
            return False

    async def write_batch(self, rows: List[FeatureRow]) -> int:
        """Insert multiple FeatureRows in a single transaction.

        Returns the number of rows successfully written.
        """
        if self._pool is None or not rows:
            return 0

        try:
            records = [
                (
                    r.timestamp,
                    r.village_id,
                    r.station_id,
                    json.dumps(r.features, default=str),
                    r.quality.value,
                )
                for r in rows
            ]
            async with self._pool.acquire() as conn:
                await conn.executemany(_INSERT_ROW, records)
            logger.info("timescale_batch_written", count=len(records))
            return len(records)
        except Exception as exc:
            logger.error("timescale_batch_error", error=str(exc))
            return 0

    # ── read ──────────────────────────────────────────────────────────

    async def get_latest(self, village_id: str) -> Optional[FeatureRow]:
        """Fetch the most recent feature row for a village."""
        if self._pool is None:
            return None

        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(_SELECT_LATEST, village_id)
            if row is None:
                return None
            return FeatureRow(
                village_id=row["village_id"],
                station_id=row["station_id"],
                timestamp=row["time"],
                features=json.loads(row["features"]),
                quality=row["quality"],
            )
        except Exception as exc:
            logger.error("timescale_read_error", error=str(exc))
            return None

    async def get_range(
        self,
        village_id: str,
        start: str,
        end: str,
    ) -> List[FeatureRow]:
        """Fetch feature rows for a village within a time range."""
        if self._pool is None:
            return []

        try:
            from datetime import datetime

            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)

            async with self._pool.acquire() as conn:
                rows = await conn.fetch(_SELECT_RANGE, village_id, start_dt, end_dt)
            return [
                FeatureRow(
                    village_id=r["village_id"],
                    station_id=r["station_id"],
                    timestamp=r["time"],
                    features=json.loads(r["features"]),
                    quality=r["quality"],
                )
                for r in rows
            ]
        except Exception as exc:
            logger.error("timescale_range_error", error=str(exc))
            return []

    @property
    def is_connected(self) -> bool:
        """True if the connection pool is active."""
        return self._pool is not None
