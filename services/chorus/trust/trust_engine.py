"""Trust engine for CHORUS community reporters.

Manages per-reporter trust scores and implements the
multi-report consensus protocol:

  - 1 report from anonymous number   → weight 0.2
  - Repeat reporter (>3 valid)       → weight 0.4
  - Community verified (consensus)   → weight 0.6
  - 3+ independent reports, same     → weight 0.8
    geohash within 10 min
  - Government-verified number       → weight 0.95

Uses Redis for state (TTL-based sliding windows).
Falls back to in-memory dict when Redis is unavailable.
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)

# Try to import redis
try:
    import redis as _redis  # type: ignore[import-untyped]
    _REDIS_AVAILABLE = True
except ImportError:
    _redis = None
    _REDIS_AVAILABLE = False


@dataclass
class TrustScore:
    """Trust evaluation for a reporter."""
    phone_hash: str
    level: str = "ANONYMOUS"
    weight: float = 0.2
    report_count: int = 0
    is_government: bool = False


@dataclass
class ConsensusStatus:
    """Consensus state for a geohash cell."""
    geohash: str
    count: int = 0
    threshold_reached: bool = False
    trust_weight: float = 0.2
    reporters: int = 0
    window_seconds: int = 600


TRUST_LEVELS = {
    "ANONYMOUS": 0.2,
    "REPEAT_REPORTER": 0.4,
    "COMMUNITY_VERIFIED": 0.6,
    "CONSENSUS": 0.8,
    "GOVERNMENT": 0.95,
}


class TrustEngine:
    """Manages reporter trust and consensus detection.

    Uses Redis with TTL windows when available.
    Falls back to in-memory storage for hackathon demo.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        consensus_threshold: int = 3,
        consensus_window_seconds: int = 600,
        government_numbers: Optional[Set[str]] = None,
    ):
        self.consensus_threshold = consensus_threshold
        self.consensus_window = consensus_window_seconds
        self.government_numbers = government_numbers or set()
        self._redis_client = None

        if redis_url and _REDIS_AVAILABLE:
            try:
                self._redis_client = _redis.from_url(redis_url)
                self._redis_client.ping()
                logger.info("trust_engine_redis_connected")
            except Exception as exc:
                logger.warning("trust_engine_redis_failed", error=str(exc))
                self._redis_client = None

        # In-memory fallback storage
        self._reporter_counts: Dict[str, int] = defaultdict(int)
        self._geohash_reports: Dict[str, List[float]] = defaultdict(list)
        self._geohash_reporters: Dict[str, Set[str]] = defaultdict(set)

        mode = "redis" if self._redis_client else "memory"
        logger.info("trust_engine_init", mode=mode, threshold=consensus_threshold)

    @staticmethod
    def hash_phone(phone_number: str) -> str:
        """Hash a phone number for privacy-preserving storage."""
        return hashlib.sha256(phone_number.encode()).hexdigest()[:16]

    def get_trust_score(self, phone_hash: str, geohash: str) -> TrustScore:
        """Compute trust score for a reporter at a location."""
        # Check government list
        if phone_hash in self.government_numbers:
            return TrustScore(
                phone_hash=phone_hash,
                level="GOVERNMENT",
                weight=TRUST_LEVELS["GOVERNMENT"],
                is_government=True,
            )

        # Get reporter history
        report_count = self._get_reporter_count(phone_hash)
        consensus = self.check_consensus(geohash)

        if consensus.threshold_reached:
            return TrustScore(
                phone_hash=phone_hash,
                level="CONSENSUS",
                weight=TRUST_LEVELS["CONSENSUS"],
                report_count=report_count,
            )
        if report_count >= 3:
            return TrustScore(
                phone_hash=phone_hash,
                level="REPEAT_REPORTER",
                weight=TRUST_LEVELS["REPEAT_REPORTER"],
                report_count=report_count,
            )
        return TrustScore(
            phone_hash=phone_hash,
            level="ANONYMOUS",
            weight=TRUST_LEVELS["ANONYMOUS"],
            report_count=report_count,
        )

    def record_report(
        self,
        phone_hash: str,
        geohash: str,
        classification: str,
    ) -> ConsensusStatus:
        """Record a report and update trust/consensus state.

        Returns the current consensus status for the geohash.
        """
        now = time.time()

        if self._redis_client:
            return self._record_redis(phone_hash, geohash, classification, now)
        return self._record_memory(phone_hash, geohash, classification, now)

    def check_consensus(self, geohash: str) -> ConsensusStatus:
        """Check if consensus threshold has been reached for a geohash."""
        if self._redis_client:
            return self._check_consensus_redis(geohash)
        return self._check_consensus_memory(geohash)

    def request_verification(
        self, geohash: str, n_verifiers: int = 5
    ) -> Dict:
        """Request verification from nearby users (stub for WhatsApp).

        In production, this would send WhatsApp messages to known
        reporters near this geohash asking for confirmation.
        """
        return {
            "geohash": geohash,
            "verification_requested": True,
            "n_verifiers": n_verifiers,
            "message": (
                "⚠️ We received flood reports near you. "
                "Is there water on the road? Reply YES or NO"
            ),
            "status": "simulated",
        }

    # ── Redis implementation ─────────────────────────────────────────

    def _record_redis(
        self, phone_hash: str, geohash: str, classification: str, now: float
    ) -> ConsensusStatus:
        pipe = self._redis_client.pipeline()
        # Increment reporter's lifetime report count (TTL 24h)
        reporter_key = f"chorus:reporter:{phone_hash}"
        pipe.incr(reporter_key)
        pipe.expire(reporter_key, 86400)

        # Add to geohash consensus window (sorted set, score = timestamp)
        consensus_key = f"chorus:consensus:{geohash}"
        pipe.zadd(consensus_key, {f"{phone_hash}:{now}": now})
        # Remove entries older than window
        cutoff = now - self.consensus_window
        pipe.zremrangebyscore(consensus_key, "-inf", cutoff)
        pipe.expire(consensus_key, self.consensus_window + 60)

        # Track unique reporters per geohash
        reporters_key = f"chorus:reporters:{geohash}"
        pipe.sadd(reporters_key, phone_hash)
        pipe.expire(reporters_key, self.consensus_window + 60)

        results = pipe.execute()

        count = self._redis_client.zcard(consensus_key)
        reporters = self._redis_client.scard(reporters_key)

        return ConsensusStatus(
            geohash=geohash,
            count=int(count),
            threshold_reached=int(count) >= self.consensus_threshold,
            trust_weight=TRUST_LEVELS["CONSENSUS"] if int(count) >= self.consensus_threshold else TRUST_LEVELS["ANONYMOUS"],
            reporters=int(reporters),
            window_seconds=self.consensus_window,
        )

    def _check_consensus_redis(self, geohash: str) -> ConsensusStatus:
        consensus_key = f"chorus:consensus:{geohash}"
        reporters_key = f"chorus:reporters:{geohash}"
        now = time.time()
        # Clean old entries
        self._redis_client.zremrangebyscore(consensus_key, "-inf", now - self.consensus_window)
        count = self._redis_client.zcard(consensus_key)
        reporters = self._redis_client.scard(reporters_key) or 0
        return ConsensusStatus(
            geohash=geohash,
            count=int(count),
            threshold_reached=int(count) >= self.consensus_threshold,
            trust_weight=TRUST_LEVELS["CONSENSUS"] if int(count) >= self.consensus_threshold else TRUST_LEVELS["ANONYMOUS"],
            reporters=int(reporters),
            window_seconds=self.consensus_window,
        )

    def _get_reporter_count(self, phone_hash: str) -> int:
        if self._redis_client:
            val = self._redis_client.get(f"chorus:reporter:{phone_hash}")
            return int(val) if val else 0
        return self._reporter_counts.get(phone_hash, 0)

    # ── In-memory fallback ───────────────────────────────────────────

    def _record_memory(
        self, phone_hash: str, geohash: str, classification: str, now: float
    ) -> ConsensusStatus:
        # Increment reporter count
        self._reporter_counts[phone_hash] += 1

        # Add timestamp to geohash window
        self._geohash_reports[geohash].append(now)
        self._geohash_reporters[geohash].add(phone_hash)

        # Prune old entries
        cutoff = now - self.consensus_window
        self._geohash_reports[geohash] = [
            t for t in self._geohash_reports[geohash] if t > cutoff
        ]

        count = len(self._geohash_reports[geohash])
        return ConsensusStatus(
            geohash=geohash,
            count=count,
            threshold_reached=count >= self.consensus_threshold,
            trust_weight=TRUST_LEVELS["CONSENSUS"] if count >= self.consensus_threshold else TRUST_LEVELS["ANONYMOUS"],
            reporters=len(self._geohash_reporters[geohash]),
            window_seconds=self.consensus_window,
        )

    def _check_consensus_memory(self, geohash: str) -> ConsensusStatus:
        now = time.time()
        cutoff = now - self.consensus_window
        self._geohash_reports[geohash] = [
            t for t in self._geohash_reports.get(geohash, []) if t > cutoff
        ]
        count = len(self._geohash_reports[geohash])
        reporters = len(self._geohash_reporters.get(geohash, set()))
        return ConsensusStatus(
            geohash=geohash,
            count=count,
            threshold_reached=count >= self.consensus_threshold,
            trust_weight=TRUST_LEVELS["CONSENSUS"] if count >= self.consensus_threshold else TRUST_LEVELS["ANONYMOUS"],
            reporters=reporters,
            window_seconds=self.consensus_window,
        )
