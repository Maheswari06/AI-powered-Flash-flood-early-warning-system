"""Feature consumer — reads enriched features from TimescaleDB.

Polls the ``feature_store`` hyper-table every 60 seconds per village,
retrieves the latest feature rows, and feeds them into the prediction
pipeline (XGBoost → SHAP → alert classification → publish).
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

_POLL_INTERVAL_SEC = int(os.getenv("FEATURE_POLL_INTERVAL_SEC", "60"))

# ── SQL for pulling latest features ──────────────────────────────────────
_SQL_LATEST_FEATURES = """
SELECT time, village_id, station_id, features, quality
FROM feature_store
WHERE village_id = $1
ORDER BY time DESC
LIMIT 1;
"""

_SQL_ALL_VILLAGES = """
SELECT DISTINCT village_id FROM feature_store;
"""


class FeatureConsumer:
    """Polls TimescaleDB for the latest feature rows and triggers predictions.

    Usage::

        consumer = FeatureConsumer(dsn=TIMESCALE_DSN, on_features=callback)
        await consumer.start()
    """

    def __init__(
        self,
        dsn: str,
        on_features: Callable[[str, Dict[str, float], str], Any],
    ) -> None:
        """
        Args:
            dsn: PostgreSQL/TimescaleDB connection string.
            on_features: Callback(village_id, features_dict, quality)
                         invoked for each village on every poll cycle.
        """
        self._dsn = dsn
        self._on_features = on_features
        self._pool = None
        self._running = False

    async def start(self) -> None:
        """Connect to TimescaleDB and start the polling loop."""
        self._running = True
        await self._connect()
        logger.info(
            "feature_consumer_started",
            dsn=self._dsn.split("@")[-1] if "@" in self._dsn else "***",
            interval_sec=_POLL_INTERVAL_SEC,
        )

        while self._running:
            await self._poll_cycle()
            await asyncio.sleep(_POLL_INTERVAL_SEC)

    async def stop(self) -> None:
        """Stop the polling loop and close the pool."""
        self._running = False
        if self._pool:
            await self._pool.close()
            logger.info("feature_consumer_pool_closed")

    async def _connect(self) -> None:
        """Establish the asyncpg connection pool."""
        try:
            import asyncpg
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
            logger.info("feature_consumer_connected")
        except ImportError:
            logger.warning("asyncpg_not_installed_feature_consumer_disabled")
        except Exception as exc:
            logger.error("feature_consumer_connect_error", error=str(exc))

    async def _poll_cycle(self) -> None:
        """One poll cycle: discover villages → fetch latest features → callback."""
        if self._pool is None:
            return

        try:
            async with self._pool.acquire() as conn:
                # Discover all known villages
                village_rows = await conn.fetch(_SQL_ALL_VILLAGES)
                village_ids = [r["village_id"] for r in village_rows]

            if not village_ids:
                logger.debug("feature_consumer_no_villages")
                return

            logger.info("feature_consumer_poll", n_villages=len(village_ids))

            for vid in village_ids:
                try:
                    async with self._pool.acquire() as conn:
                        row = await conn.fetchrow(_SQL_LATEST_FEATURES, vid)
                    if row is None:
                        continue

                    features = json.loads(row["features"])
                    quality = row["quality"]

                    # Invoke the prediction callback
                    result = self._on_features(vid, features, quality)
                    # If callback is a coroutine, await it
                    if asyncio.iscoroutine(result):
                        await result

                except Exception as exc:
                    logger.error("feature_consumer_village_error", village=vid, error=str(exc))

        except Exception as exc:
            logger.error("feature_consumer_poll_error", error=str(exc))

    @property
    def is_connected(self) -> bool:
        return self._pool is not None
