"""CHORUS Aggregator — Aggregates community reports per village.

Maintains a sliding window of reports and computes community-level
sentiment signals that can boost/lower the flood risk score.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List

import structlog

from shared.models.phase2 import (
    ChorusAggregation,
    CommunityReport,
    SentimentLevel,
)

logger = structlog.get_logger(__name__)


class ChorusAggregator:
    """Windowed aggregation of community intelligence per village."""

    def __init__(self, window_minutes: int = 60):
        self.window_minutes = window_minutes
        self._reports: Dict[str, List[CommunityReport]] = defaultdict(list)

    def add_report(self, report: CommunityReport) -> None:
        """Add a report to the village's window."""
        self._reports[report.village_id].append(report)
        self._prune(report.village_id)

    def _prune(self, village_id: str) -> None:
        """Remove reports outside the window."""
        cutoff = datetime.now() - timedelta(minutes=self.window_minutes)
        self._reports[village_id] = [
            r for r in self._reports[village_id]
            if r.timestamp >= cutoff
        ]

    def aggregate(self, village_id: str) -> ChorusAggregation:
        """Compute aggregated sentiment for a village."""
        self._prune(village_id)
        reports = self._reports.get(village_id, [])

        if not reports:
            return ChorusAggregation(
                village_id=village_id,
                window_minutes=self.window_minutes,
            )

        # Count sentiments
        sentiment_counts: Dict[SentimentLevel, int] = defaultdict(int)
        total_credibility = 0.0
        flood_mentions = 0
        all_keywords: List[str] = []

        for r in reports:
            sentiment_counts[r.sentiment] += 1
            total_credibility += r.credibility_score
            if r.flood_mentioned:
                flood_mentions += 1
            all_keywords.extend(r.keywords)

        n = len(reports)
        dominant = max(sentiment_counts, key=sentiment_counts.get)
        panic_ratio = sentiment_counts.get(SentimentLevel.PANIC, 0) / n
        flood_rate = flood_mentions / n
        avg_cred = total_credibility / n

        # Community risk boost: panic + flood mentions = higher risk signal
        #   max boost = 0.30
        boost = min(0.30, panic_ratio * 0.20 + flood_rate * 0.10)

        # Top keywords by frequency
        kw_freq: Dict[str, int] = defaultdict(int)
        for kw in all_keywords:
            kw_freq[kw] += 1
        top_kw = sorted(kw_freq, key=kw_freq.get, reverse=True)[:5]

        agg = ChorusAggregation(
            village_id=village_id,
            report_count=n,
            dominant_sentiment=dominant,
            panic_ratio=round(panic_ratio, 3),
            avg_credibility=round(avg_cred, 3),
            flood_mention_rate=round(flood_rate, 3),
            community_risk_boost=round(boost, 3),
            top_keywords=top_kw,
            window_minutes=self.window_minutes,
        )

        logger.info(
            "chorus_aggregated",
            village=village_id,
            reports=n,
            sentiment=dominant.value,
            panic_ratio=round(panic_ratio, 3),
            risk_boost=round(boost, 3),
        )
        return agg

    def aggregate_all(self) -> Dict[str, ChorusAggregation]:
        """Aggregate all villages."""
        result = {}
        for village_id in list(self._reports.keys()):
            result[village_id] = self.aggregate(village_id)
        return result

    def get_report_count(self) -> int:
        """Total reports across all villages."""
        return sum(len(v) for v in self._reports.values())
