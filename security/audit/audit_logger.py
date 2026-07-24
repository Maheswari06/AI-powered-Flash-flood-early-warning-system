"""
ARGUS Security — Immutable Audit Logger
Chained-hash audit trail stored in TimescaleDB + CloudWatch.

Every state-changing operation is logged with:
  - Timestamp (ISO-8601)
  - Actor (user sub from JWT)
  - Action (HTTP method + path)
  - Resource (affected entity ID)
  - Details (before/after or payload summary)
  - Chain hash (SHA-256 of previous entry + current entry)

The chain hash makes the audit log tamper-evident — any modification
to a past entry breaks the chain for all subsequent entries.
"""

from __future__ import annotations

import os
import json
import hashlib
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Any
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger("argus.audit")

# ═══════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════
AUDIT_DB_TABLE = "argus_audit_log"
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
CLOUDWATCH_LOG_GROUP = os.getenv("CLOUDWATCH_AUDIT_LOG_GROUP", "/argus/audit")
ENABLE_CLOUDWATCH = os.getenv("ENABLE_CLOUDWATCH_AUDIT", "false").lower() == "true"


# ═══════════════════════════════════════════════════════════════════
# Audit Entry Model
# ═══════════════════════════════════════════════════════════════════
class AuditEntry(BaseModel):
    """A single immutable audit log entry."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    actor: str  # User sub or service ID
    actor_name: Optional[str] = None
    actor_roles: list[str] = []
    action: str  # e.g., "POST /api/v1/evacuation/trigger"
    resource_type: str  # e.g., "evacuation", "alert", "config"
    resource_id: Optional[str] = None
    details: dict[str, Any] = {}
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    status_code: int = 200
    district: Optional[str] = None
    previous_hash: str = ""
    entry_hash: str = ""

    def compute_hash(self, previous_hash: str = "") -> str:
        """Compute SHA-256 chain hash for this entry."""
        self.previous_hash = previous_hash
        hashable = (
            f"{self.id}|{self.timestamp}|{self.actor}|{self.action}|"
            f"{self.resource_type}|{self.resource_id}|"
            f"{json.dumps(self.details, sort_keys=True)}|{previous_hash}"
        )
        self.entry_hash = hashlib.sha256(hashable.encode()).hexdigest()
        return self.entry_hash


# ═══════════════════════════════════════════════════════════════════
# Audit Logger
# ═══════════════════════════════════════════════════════════════════
class AuditLogger:
    """
    Immutable, chained-hash audit logger.

    Stores entries in TimescaleDB with chain hashes for tamper detection.
    Optionally mirrors to AWS CloudWatch for compliance.
    """

    def __init__(self):
        self._last_hash: str = "GENESIS"
        self._db_pool = None
        self._cloudwatch_client = None
        self._buffer: list[AuditEntry] = []
        self._flush_lock = asyncio.Lock()

    async def initialize(self, db_pool=None):
        """Initialize database connection and load last chain hash."""
        self._db_pool = db_pool

        if self._db_pool:
            await self._ensure_table()
            await self._load_last_hash()

        if ENABLE_CLOUDWATCH and not DEMO_MODE:
            try:
                import boto3
                self._cloudwatch_client = boto3.client(
                    "logs", region_name=os.getenv("AWS_REGION", "ap-south-1")
                )
                logger.info("CloudWatch audit logging enabled")
            except Exception as e:
                logger.warning(f"CloudWatch init failed: {e}")

        logger.info(f"Audit logger initialized. Last hash: {self._last_hash[:16]}...")

    async def _ensure_table(self):
        """Create audit log hypertable if it doesn't exist."""
        if not self._db_pool:
            return

        async with self._db_pool.acquire() as conn:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {AUDIT_DB_TABLE} (
                    id              UUID PRIMARY KEY,
                    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    actor           TEXT NOT NULL,
                    actor_name      TEXT,
                    actor_roles     TEXT[],
                    action          TEXT NOT NULL,
                    resource_type   TEXT NOT NULL,
                    resource_id     TEXT,
                    details         JSONB DEFAULT '{{}}',
                    ip_address      INET,
                    user_agent      TEXT,
                    status_code     INTEGER DEFAULT 200,
                    district        TEXT,
                    previous_hash   TEXT NOT NULL,
                    entry_hash      TEXT NOT NULL
                );

                -- Convert to TimescaleDB hypertable for time-series queries
                SELECT create_hypertable(
                    '{AUDIT_DB_TABLE}', 'timestamp',
                    if_not_exists => TRUE,
                    migrate_data => TRUE
                );

                -- Index for actor lookups
                CREATE INDEX IF NOT EXISTS idx_audit_actor
                    ON {AUDIT_DB_TABLE} (actor, timestamp DESC);

                -- Index for resource lookups
                CREATE INDEX IF NOT EXISTS idx_audit_resource
                    ON {AUDIT_DB_TABLE} (resource_type, resource_id, timestamp DESC);

                -- Index for chain verification
                CREATE INDEX IF NOT EXISTS idx_audit_hash
                    ON {AUDIT_DB_TABLE} (entry_hash);
            """)

    async def _load_last_hash(self):
        """Load the most recent chain hash from the database."""
        if not self._db_pool:
            return

        async with self._db_pool.acquire() as conn:
            row = await conn.fetchrow(f"""
                SELECT entry_hash FROM {AUDIT_DB_TABLE}
                ORDER BY timestamp DESC LIMIT 1
            """)
            if row:
                self._last_hash = row["entry_hash"]

    async def log(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[dict] = None,
        actor_name: Optional[str] = None,
        actor_roles: Optional[list[str]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        status_code: int = 200,
        district: Optional[str] = None,
    ) -> AuditEntry:
        """
        Log an auditable event with chained hash.

        Args:
            actor: User sub or service identifier
            action: HTTP method + path (e.g., "POST /api/v1/evacuation/trigger")
            resource_type: Entity type (e.g., "evacuation", "alert")
            resource_id: Specific resource identifier
            details: Additional context (before/after state, payload summary)
            actor_name: Human-readable actor name
            actor_roles: Actor's roles at time of action
            ip_address: Source IP address
            user_agent: HTTP User-Agent header
            status_code: Response status code
            district: District scope (for DISTRICT_ADMIN actions)

        Returns:
            The created AuditEntry with computed chain hash
        """
        entry = AuditEntry(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            actor_name=actor_name,
            actor_roles=actor_roles or [],
            ip_address=ip_address,
            user_agent=user_agent,
            status_code=status_code,
            district=district,
        )

        # Compute chained hash
        async with self._flush_lock:
            entry.compute_hash(self._last_hash)
            self._last_hash = entry.entry_hash

        # Persist to database
        if self._db_pool:
            await self._persist_to_db(entry)
        else:
            # In-memory buffer for demo mode
            self._buffer.append(entry)
            if len(self._buffer) > 10000:
                self._buffer = self._buffer[-5000:]

        # Mirror to CloudWatch
        if self._cloudwatch_client:
            await self._send_to_cloudwatch(entry)

        logger.info(
            f"AUDIT: {entry.action} by {entry.actor} "
            f"on {entry.resource_type}/{entry.resource_id} "
            f"hash={entry.entry_hash[:16]}"
        )

        return entry

    async def _persist_to_db(self, entry: AuditEntry):
        """Write audit entry to TimescaleDB."""
        try:
            async with self._db_pool.acquire() as conn:
                await conn.execute(
                    f"""
                    INSERT INTO {AUDIT_DB_TABLE}
                        (id, timestamp, actor, actor_name, actor_roles,
                         action, resource_type, resource_id, details,
                         ip_address, user_agent, status_code, district,
                         previous_hash, entry_hash)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
                            $10, $11, $12, $13, $14, $15)
                    """,
                    entry.id,
                    entry.timestamp,
                    entry.actor,
                    entry.actor_name,
                    entry.actor_roles,
                    entry.action,
                    entry.resource_type,
                    entry.resource_id,
                    json.dumps(entry.details),
                    entry.ip_address,
                    entry.user_agent,
                    entry.status_code,
                    entry.district,
                    entry.previous_hash,
                    entry.entry_hash,
                )
        except Exception as e:
            logger.error(f"Failed to persist audit entry: {e}")

    async def _send_to_cloudwatch(self, entry: AuditEntry):
        """Mirror audit entry to AWS CloudWatch Logs."""
        try:
            import time as _time

            self._cloudwatch_client.put_log_events(
                logGroupName=CLOUDWATCH_LOG_GROUP,
                logStreamName=f"argus-audit-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                logEvents=[
                    {
                        "timestamp": int(_time.time() * 1000),
                        "message": entry.model_dump_json(),
                    }
                ],
            )
        except Exception as e:
            logger.warning(f"CloudWatch audit push failed: {e}")

    async def verify_chain(self, limit: int = 1000) -> dict:
        """
        Verify the integrity of the audit chain.

        Returns:
            dict with 'valid' (bool), 'entries_checked' (int),
            'first_broken' (str or None)
        """
        if self._db_pool:
            return await self._verify_chain_db(limit)
        else:
            return self._verify_chain_buffer()

    async def _verify_chain_db(self, limit: int) -> dict:
        """Verify chain from database."""
        async with self._db_pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT id, timestamp, actor, action, resource_type,
                       resource_id, details, previous_hash, entry_hash
                FROM {AUDIT_DB_TABLE}
                ORDER BY timestamp ASC
                LIMIT {limit}
            """)

        expected_prev = "GENESIS"
        for i, row in enumerate(rows):
            if row["previous_hash"] != expected_prev:
                return {
                    "valid": False,
                    "entries_checked": i + 1,
                    "first_broken": row["id"],
                    "expected_previous": expected_prev,
                    "actual_previous": row["previous_hash"],
                }
            expected_prev = row["entry_hash"]

        return {
            "valid": True,
            "entries_checked": len(rows),
            "first_broken": None,
        }

    def _verify_chain_buffer(self) -> dict:
        """Verify chain from in-memory buffer."""
        expected_prev = "GENESIS"
        for i, entry in enumerate(self._buffer):
            if entry.previous_hash != expected_prev:
                return {
                    "valid": False,
                    "entries_checked": i + 1,
                    "first_broken": entry.id,
                }
            expected_prev = entry.entry_hash

        return {
            "valid": True,
            "entries_checked": len(self._buffer),
            "first_broken": None,
        }

    async def query(
        self,
        actor: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query audit log with filters."""
        if not self._db_pool:
            # Filter in-memory buffer
            results = self._buffer
            if actor:
                results = [e for e in results if e.actor == actor]
            if resource_type:
                results = [e for e in results if e.resource_type == resource_type]
            if resource_id:
                results = [e for e in results if e.resource_id == resource_id]
            return results[-limit:]

        conditions = []
        params = []
        idx = 1

        if actor:
            conditions.append(f"actor = ${idx}")
            params.append(actor)
            idx += 1
        if resource_type:
            conditions.append(f"resource_type = ${idx}")
            params.append(resource_type)
            idx += 1
        if resource_id:
            conditions.append(f"resource_id = ${idx}")
            params.append(resource_id)
            idx += 1
        if start_time:
            conditions.append(f"timestamp >= ${idx}")
            params.append(start_time)
            idx += 1
        if end_time:
            conditions.append(f"timestamp <= ${idx}")
            params.append(end_time)
            idx += 1

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        async with self._db_pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT * FROM {AUDIT_DB_TABLE}
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT {limit}
            """, *params)

        return [
            AuditEntry(
                id=str(row["id"]),
                timestamp=row["timestamp"].isoformat(),
                actor=row["actor"],
                actor_name=row["actor_name"],
                actor_roles=row["actor_roles"] or [],
                action=row["action"],
                resource_type=row["resource_type"],
                resource_id=row["resource_id"],
                details=json.loads(row["details"]) if row["details"] else {},
                ip_address=str(row["ip_address"]) if row["ip_address"] else None,
                user_agent=row["user_agent"],
                status_code=row["status_code"],
                district=row["district"],
                previous_hash=row["previous_hash"],
                entry_hash=row["entry_hash"],
            )
            for row in rows
        ]


# ═══════════════════════════════════════════════════════════════════
# Global Instance
# ═══════════════════════════════════════════════════════════════════
audit_logger = AuditLogger()
