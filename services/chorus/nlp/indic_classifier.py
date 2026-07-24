"""IndicBERT flood event classifier (12 classes).

Supports fine-tuned checkpoint OR zero-shot keyword fallback.
The fallback is critical for hackathon reliability — it works
without any trained model.

Classes:
  FLOOD_PRECURSOR, ACTIVE_FLOOD, INFRASTRUCTURE_FAILURE,
  PEOPLE_STRANDED, FALSE_ALARM, ROAD_BLOCKED, DAMAGE_REPORT,
  RESOURCE_REQUEST, OFFICIAL_UPDATE, WEATHER_OBSERVATION,
  ANIMAL_MOVEMENT, UNRELATED
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)

# Try to import transformers — fall back to keyword-only mode
try:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification  # type: ignore
    import torch
    _TRANSFORMERS_AVAILABLE = True
except ImportError:
    _TRANSFORMERS_AVAILABLE = False
    logger.warning("transformers_not_available", hint="pip install transformers torch")


# ── Class taxonomy ──────────────────────────────────────────────────────
CLASSES = [
    "FLOOD_PRECURSOR",
    "ACTIVE_FLOOD",
    "INFRASTRUCTURE_FAILURE",
    "PEOPLE_STRANDED",
    "FALSE_ALARM",
    "ROAD_BLOCKED",
    "DAMAGE_REPORT",
    "RESOURCE_REQUEST",
    "OFFICIAL_UPDATE",
    "WEATHER_OBSERVATION",
    "ANIMAL_MOVEMENT",
    "UNRELATED",
]

FLOOD_RELEVANT: Set[str] = {
    "FLOOD_PRECURSOR",
    "ACTIVE_FLOOD",
    "INFRASTRUCTURE_FAILURE",
    "PEOPLE_STRANDED",
    "ROAD_BLOCKED",
}

# ── Keyword dictionaries for zero-shot fallback ─────────────────────────
KEYWORDS: Dict[str, List[str]] = {
    "FLOOD_PRECURSOR": [
        # Hindi
        "नदी", "पानी", "बाढ़", "बह रही", "तेज़", "उफान", "जलस्तर", "बढ़",
        # Assamese
        "ন'দী", "পানী", "বান",
        # Bengali
        "পানি", "বন্যা", "নদী",
        # English
        "river", "flood", "rising", "water level", "surge", "overflow",
        "precursor", "unusual flow", "river sounds",
    ],
    "ACTIVE_FLOOD": [
        "डूब", "घुस", "जलमग्न", "सड़क पर पानी",
        "submerged", "inundated", "water on road", "homes flooded",
        "entering houses", "bridge submerged", "waterlogged",
        "পানি আসছে", "ডুবে যাচ্ছে",
    ],
    "INFRASTRUCTURE_FAILURE": [
        "पुल", "सड़क", "टूट", "दरार", "drain", "नाला",
        "bridge", "road", "damaged", "collapsed", "blocked drain",
        "overflowing drain", "embankment breach",
        "ব্রিজ", "রাস্তা", "ভেঙে",
    ],
    "PEOPLE_STRANDED": [
        "बचाओ", "फँस", "मदद", "rescue", "trapped", "stranded",
        "cut off", "marooned", "bachao", "fasa", "madad",
        "আটকা", "উদ্ধার",
    ],
    "FALSE_ALARM": [
        "normal", "safe", "ok", "ठीक", "सब ठीक", "no flood",
        "false alarm", "situation controlled", "receding",
    ],
    "ROAD_BLOCKED": [
        "road blocked", "रास्ता बंद", "route closed", "inaccessible",
        "debris", "landslide blocked",
    ],
    "DAMAGE_REPORT": [
        "damage", "destroyed", "loss", "नुकसान", "तबाही", "ক্ষতি",
    ],
    "RESOURCE_REQUEST": [
        "need food", "medical", "boats", "relief", "राहत", "खाना", "दवाई",
    ],
    "OFFICIAL_UPDATE": [
        "government", "official", "NDRF", "SDRF", "CWC", "IMD",
        "advisory", "bulletin", "सरकारी",
    ],
    "WEATHER_OBSERVATION": [
        "rain", "baarish", "barsat", "cloudburst", "heavy rain",
        "बारिश", "मूसलाधार", "बादल फटा",
        "বৃষ্টি",
    ],
    "ANIMAL_MOVEMENT": [
        "animals", "birds", "snakes", "unusual behavior",
        "जानवर", "साँप", "পশু",
    ],
    "UNRELATED": [],
}


@dataclass
class ClassificationResult:
    """Output of the IndicBERT classifier."""
    label: str = "UNRELATED"
    confidence: float = 0.0
    all_scores: Dict[str, float] = field(default_factory=dict)
    is_flood_relevant: bool = False
    method: str = "keyword"  # "keyword" or "model"


class IndicFloodClassifier:
    """12-class flood event classifier.

    Uses ``ai4bharat/indic-bert`` when a fine-tuned checkpoint is
    available. Otherwise falls back to keyword matching, which is
    the primary mode for the hackathon demo.
    """

    MODEL_NAME = "ai4bharat/indic-bert"

    def __init__(self, checkpoint_path: Optional[str] = None):
        self._model = None
        self._tokenizer = None
        self._using_model = False

        if checkpoint_path and _TRANSFORMERS_AVAILABLE:
            try:
                self._tokenizer = AutoTokenizer.from_pretrained(checkpoint_path)
                self._model = AutoModelForSequenceClassification.from_pretrained(
                    checkpoint_path, num_labels=len(CLASSES)
                )
                self._model.eval()
                self._using_model = True
                logger.info("indic_bert_loaded", checkpoint=checkpoint_path)
            except Exception as exc:
                logger.warning("indic_bert_load_failed", error=str(exc))
                logger.info("using_keyword_fallback")
        else:
            logger.info("using_keyword_fallback")

    def classify(self, text: str) -> ClassificationResult:
        """Classify a community report text.

        Tries the fine-tuned model first, falls back to keyword matching.
        """
        if self._using_model:
            return self._classify_with_model(text)
        return self._classify_with_keywords(text)

    def _classify_with_model(self, text: str) -> ClassificationResult:
        """Classify using the fine-tuned IndicBERT model."""
        import torch

        inputs = self._tokenizer(
            text, return_tensors="pt", truncation=True, max_length=256, padding=True
        )
        with torch.no_grad():
            logits = self._model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0]

        all_scores = {CLASSES[i]: round(probs[i].item(), 4) for i in range(len(CLASSES))}
        best_idx = probs.argmax().item()
        best_label = CLASSES[best_idx]
        best_conf = probs[best_idx].item()

        return ClassificationResult(
            label=best_label,
            confidence=round(best_conf, 4),
            all_scores=all_scores,
            is_flood_relevant=best_label in FLOOD_RELEVANT,
            method="model",
        )

    def _classify_with_keywords(self, text: str) -> ClassificationResult:
        """Keyword-based zero-shot fallback classifier.

        Scores each class by counting keyword matches, then picks
        the highest scoring class. Critical for hackathon demo
        where no fine-tuned model is available.
        """
        text_lower = text.lower()
        scores: Dict[str, float] = {}

        for cls, keywords in KEYWORDS.items():
            if not keywords:
                scores[cls] = 0.0
                continue
            matches = sum(1 for kw in keywords if kw.lower() in text_lower)
            # Normalize by keyword list length to avoid bias toward large lists
            scores[cls] = matches / len(keywords) if keywords else 0.0

        # Apply bonus for longer matches and multi-keyword hits
        for cls in scores:
            raw_matches = sum(1 for kw in KEYWORDS.get(cls, []) if kw.lower() in text_lower)
            if raw_matches >= 3:
                scores[cls] *= 1.5  # boost for strong evidence
            if raw_matches >= 5:
                scores[cls] *= 1.3  # extra boost

        best_label = max(scores, key=scores.get)  # type: ignore[arg-type]
        best_score = scores[best_label]

        # If no keywords matched at all, classify as UNRELATED
        if best_score == 0.0:
            best_label = "UNRELATED"

        # Convert raw score to a pseudo-confidence (0-1)
        confidence = min(1.0, best_score * 3.0)  # scale up for readability

        # Normalize all scores to a pseudo-probability distribution
        total = sum(scores.values()) or 1.0
        all_scores = {cls: round(s / total, 4) for cls, s in scores.items()}

        return ClassificationResult(
            label=best_label,
            confidence=round(confidence, 4),
            all_scores=all_scores,
            is_flood_relevant=best_label in FLOOD_RELEVANT,
            method="keyword",
        )
