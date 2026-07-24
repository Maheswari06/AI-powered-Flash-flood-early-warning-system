"""CHORUS NLP — Unified message analysis pipeline.

Combines IndicBERT classification, keyword sentiment, location
extraction, and water-level detection into a single ``analyze_message``
call that returns a ``CommunityReport``.

This module is the backward-compatible entry point used by main.py.
The heavy NLP components live in ``services/chorus/nlp/``.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import structlog

from shared.models.phase2 import CommunityReport, SentimentLevel

logger = structlog.get_logger(__name__)

# ── Import sub-modules (fail gracefully) ─────────────────────────────
try:
    from services.chorus.nlp.indic_classifier import IndicFloodClassifier, FLOOD_RELEVANT
except ImportError:
    IndicFloodClassifier = None  # type: ignore[assignment,misc]
    FLOOD_RELEVANT = set()

try:
    from services.chorus.nlp.location_extractor import LocationExtractor
except ImportError:
    LocationExtractor = None  # type: ignore[assignment,misc]

# Singleton instances (lazy-init on first use)
_classifier: Optional[IndicFloodClassifier] = None  # type: ignore[assignment]
_location_extractor: Optional[LocationExtractor] = None  # type: ignore[assignment]


def _get_classifier():
    global _classifier
    if _classifier is None and IndicFloodClassifier is not None:
        _classifier = IndicFloodClassifier()
    return _classifier


def _get_location_extractor():
    global _location_extractor
    if _location_extractor is None and LocationExtractor is not None:
        _location_extractor = LocationExtractor()
    return _location_extractor


# ── Flood keyword dictionaries (kept for backward compat) ───────────
FLOOD_KEYWORDS_EN = {
    "flood", "flooding", "water level", "rising water", "overflow",
    "submerged", "inundated", "waterlogged", "embankment", "breach",
    "dam release", "cloudburst", "landslide", "evacuation", "rescue",
    "marooned", "stranded", "washed away", "danger", "emergency",
    "river bank", "overflowing", "heavy rain", "downpour",
}

FLOOD_KEYWORDS_HI = {
    "baadh", "baarish", "paani", "nadi", "ubhar",
    "doob", "behna", "toofan", "barsat", "khatra",
    "bachao", "madad", "tabaahi", "jal", "pralay",
    "seelab", "daldal", "bhaari", "dhara", "kinara",
}

PANIC_KEYWORDS = {
    "help", "emergency", "sos", "bachao", "madad",
    "danger", "dying", "trapped", "rescue", "urgent",
    "khatra", "maut", "fasa", "doob raha",
}

CALM_KEYWORDS = {
    "normal", "safe", "ok", "fine", "sab theek",
    "stable", "receding", "improving", "controlled",
}


def _extract_keywords(text: str) -> List[str]:
    """Extract flood-related keywords from text."""
    text_lower = text.lower()
    found = []
    for kw in FLOOD_KEYWORDS_EN | FLOOD_KEYWORDS_HI:
        if kw in text_lower:
            found.append(kw)
    return found


def _score_sentiment(text: str, keywords: List[str], classification_label: Optional[str] = None) -> SentimentLevel:
    """Rule-based sentiment classification, boosted by IndicBERT label."""
    text_lower = text.lower()
    panic_count = sum(1 for kw in PANIC_KEYWORDS if kw in text_lower)
    calm_count = sum(1 for kw in CALM_KEYWORDS if kw in text_lower)
    flood_intensity = len(keywords)

    # Boost from IndicBERT classification
    if classification_label in ("ACTIVE_FLOOD", "PEOPLE_STRANDED"):
        panic_count += 2
    elif classification_label in ("FLOOD_PRECURSOR", "INFRASTRUCTURE_FAILURE"):
        flood_intensity += 2

    if panic_count >= 2 or (panic_count >= 1 and flood_intensity >= 3):
        return SentimentLevel.PANIC
    if flood_intensity >= 3 or panic_count >= 1:
        return SentimentLevel.ANXIOUS
    if flood_intensity >= 1:
        return SentimentLevel.CONCERNED
    if calm_count >= 1:
        return SentimentLevel.CALM
    return SentimentLevel.CALM


def _extract_water_level(text: str) -> Optional[float]:
    """Try to extract a numeric water level from text."""
    patterns = [
        r"(\d+(?:\.\d+)?)\s*(?:meter|metre|m|feet|ft)",
        r"water\s*(?:level|height)?\s*(?:is|at|around|about)?\s*(\d+(?:\.\d+)?)",
        r"paani\s*(\d+(?:\.\d+)?)",
    ]
    for pat in patterns:
        match = re.search(pat, text.lower())
        if match:
            val = float(match.group(1))
            if "feet" in text.lower() or "ft" in text.lower():
                val *= 0.3048
            return round(val, 2)
    return None


def _assess_credibility(
    text: str,
    keywords: List[str],
    source: str,
    has_location: bool,
    classification_confidence: float = 0.0,
) -> float:
    """Heuristic credibility score, boosted by classifier confidence."""
    score = 0.3
    if len(text) > 50:
        score += 0.1
    if len(text) > 150:
        score += 0.1
    score += min(0.2, len(keywords) * 0.05)
    if source in ("field_worker", "government"):
        score += 0.2
    if has_location:
        score += 0.1
    # Boost from classifier confidence
    score += classification_confidence * 0.1
    return min(1.0, round(score, 2))


def analyze_message(
    message: str,
    village_id: str,
    source: str = "whatsapp",
    language: str = "hi",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> CommunityReport:
    """Analyze a single community message and return a structured report.

    Runs the full pipeline: IndicBERT -> keywords -> sentiment ->
    location -> credibility -> CommunityReport.
    """
    # Run IndicBERT classifier
    classifier = _get_classifier()
    classification = classifier.classify(message) if classifier else None
    class_label = classification.label if classification else None
    class_confidence = classification.confidence if classification else 0.0
    is_flood = classification.is_flood_relevant if classification else False

    # Keyword extraction
    keywords = _extract_keywords(message)
    if classification and classification.label != "UNRELATED":
        keywords.append(classification.label)

    # Location extraction
    loc_extractor = _get_location_extractor()
    if loc_extractor and lat is None:
        loc_result = loc_extractor.extract(message)
        if loc_result.lat is not None and loc_result.confidence > 0.2:
            lat = loc_result.lat
            lon = loc_result.lon

    sentiment = _score_sentiment(message, keywords, class_label)
    water_level = _extract_water_level(message)
    flood_mentioned = len(keywords) > 0 or is_flood
    credibility = _assess_credibility(
        message, keywords, source,
        has_location=(lat is not None),
        classification_confidence=class_confidence,
    )

    report = CommunityReport(
        report_id=str(uuid.uuid4()),
        village_id=village_id,
        source=source,
        message=message,
        language=language,
        sentiment=sentiment,
        keywords=keywords,
        flood_mentioned=flood_mentioned,
        water_level_reported=water_level,
        location_lat=lat,
        location_lon=lon,
        credibility_score=credibility,
    )
    logger.info(
        "message_analyzed",
        village=village_id,
        sentiment=sentiment.value,
        keywords=len(keywords),
        flood=flood_mentioned,
        credibility=credibility,
    )
    return report
