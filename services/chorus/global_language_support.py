"""CHORUS Global Language Support — Phase 6 multi-language expansion.

Adds Vietnamese, Khmer, Portuguese (Mozambique), and Nepali to the
CHORUS voice-driven community sensing pipeline.

Architecture:
  Whisper ASR (auto-detects language) → Language-specific BERT classifier
  → Keyword fallback for unsupported languages
  → Language-specific TTS for alert responses
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


# ── Classification Result ────────────────────────────────────────────────

class FloodLabel(str, Enum):
    """CHORUS flood classification labels."""
    FLOOD_PRECURSOR = "FLOOD_PRECURSOR"
    FLOOD_ACTIVE = "FLOOD_ACTIVE"
    FLOOD_AFTERMATH = "FLOOD_AFTERMATH"
    INFRASTRUCTURE_DAMAGE = "INFRASTRUCTURE_DAMAGE"
    EVACUATION_REQUEST = "EVACUATION_REQUEST"
    RESOURCE_REQUEST = "RESOURCE_REQUEST"
    UNRELATED = "UNRELATED"


@dataclass
class ClassificationResult:
    """Result from CHORUS text classification."""
    label: FloodLabel
    confidence: float
    method: str                  # "bert", "zero_shot_keyword", "multilingual"
    language: str = "unknown"
    raw_text: Optional[str] = None
    translated_text: Optional[str] = None


# ── Language Configs ─────────────────────────────────────────────────────

GLOBAL_LANGUAGE_CONFIG = {
    # ── South Asia (Phase 5 — already working) ───────────────────────
    "hi": {
        "name": "Hindi",
        "asr": "whisper",
        "tts": "indic_tts",
        "classifier_model": "ai4bharat/indic-bert",
        "flood_keywords": ["बाढ़", "पानी", "नदी", "बारिश", "तबाही", "जलस्तर"],
        "alert_templates": {
            "WARNING": "⚠️ बाढ़ चेतावनी: {village} में {hours} घंटे में बाढ़ का खतरा। कृपया तैयार रहें।",
            "EMERGENCY": "🚨 आपातकालीन: {village} में तुरंत निकासी। ऊँची जगह पर जाएँ।",
        },
        "active": True,
    },
    "bn": {
        "name": "Bengali",
        "asr": "whisper",
        "tts": "indic_tts",
        "classifier_model": "ai4bharat/indic-bert",
        "flood_keywords": ["বন্যা", "জল", "নদী", "বৃষ্টি", "জলস্তর", "ডুবে যাওয়া"],
        "alert_templates": {
            "WARNING": "⚠️ বন্যা সতর্কতা: {village}-এ {hours} ঘন্টার মধ্যে বন্যার ঝুঁকি। প্রস্তুত থাকুন।",
            "EMERGENCY": "🚨 জরুরি: {village}-এ এখনই সরে যান। উঁচু জায়গায় যান।",
        },
        "active": True,
    },
    "as": {
        "name": "Assamese",
        "asr": "whisper",
        "tts": "indic_tts",
        "classifier_model": "ai4bharat/indic-bert",
        "flood_keywords": ["বান", "পানী", "নৈ", "বৰষুণ", "জলপৃষ্ঠ"],
        "alert_templates": {
            "WARNING": "⚠️ বান সতৰ্কতা: {village}ত {hours} ঘণ্টাৰ ভিতৰত বানৰ আশংকা।",
            "EMERGENCY": "🚨 জৰুৰী: {village}ৰ পৰা এতিয়াই আঁতৰি যাওক।",
        },
        "active": True,
    },

    # ── Phase 6 New Languages ────────────────────────────────────────
    "vi": {
        "name": "Vietnamese",
        "asr": "whisper",
        "tts": "openai_tts",
        "classifier_model": "joeddav/xlm-roberta-large-xnli",
        "flood_keywords": [
            "lũ lụt", "ngập", "nước dâng", "vỡ đê", "mưa lớn",
            "sạt lở", "triều cường", "xả lũ", "sông dâng", "ngập úng",
        ],
        "alert_templates": {
            "WARNING": "⚠️ Cảnh báo lũ lụt: {village} có nguy cơ ngập trong {hours} giờ tới. Hãy chuẩn bị sơ tán.",
            "EMERGENCY": "🚨 KHẨN CẤP: Sơ tán {village} ngay lập tức. Di chuyển đến vùng cao.",
        },
        "active": True,
    },
    "km": {
        "name": "Khmer",
        "asr": "whisper",
        "tts": "openai_tts",
        "classifier_model": "google/muril-base-cased",
        "flood_keywords": [
            "ទឹកជំនន់", "ទឹកឡើង", "ខ្ពស់", "ភ្លៀង", "ទំនប់",
            "ជំនន់", "ព្រែក", "ស្ទឹង",
        ],
        "alert_templates": {
            "WARNING": "⚠️ ការព្រមានទឹកជំនន់: {village} មានគ្រោះថ្នាក់ក្នុងរយៈពេល {hours} ម៉ោង។",
            "EMERGENCY": "🚨 បន្ទាន់: ជម្លៀស {village} ភ្លាមៗ។ ទៅកន្លែងខ្ពស់។",
        },
        "active": True,
    },
    "pt": {
        "name": "Portuguese",
        "asr": "whisper",
        "tts": "openai_tts",
        "classifier_model": "neuralmind/bert-base-portuguese-cased",
        "flood_keywords": [
            "cheia", "inundação", "água subindo", "rio transbordou",
            "chuva forte", "deslizamento", "alagamento", "enchente",
        ],
        "alert_templates": {
            "WARNING": "⚠️ Alerta de cheia: {village} em risco de inundação nas próximas {hours} horas. Prepare-se para evacuar.",
            "EMERGENCY": "🚨 EMERGÊNCIA: Evacue {village} imediatamente. Vá para terreno elevado.",
        },
        "active": True,
    },
    "ne": {
        "name": "Nepali",
        "asr": "whisper",
        "tts": "indic_tts",
        "classifier_model": "ai4bharat/indic-bert",
        "flood_keywords": [
            "बाढी", "पानी बढ्यो", "नदी उर्लियो", "वर्षा", "पहिरो",
            "डुबान", "जलस्तर", "भेल",
        ],
        "alert_templates": {
            "WARNING": "⚠️ बाढी चेतावनी: {village} मा {hours} घण्टा भित्र बाढीको जोखिम छ। तयार रहनुहोस्।",
            "EMERGENCY": "🚨 आपतकालीन: {village} बाट तुरुन्तै सर्नुहोस्। माथिल्लो ठाउँमा जानुहोस्।",
        },
        "active": True,
    },
    "my": {
        "name": "Burmese",
        "asr": "whisper",
        "tts": "openai_tts",
        "classifier_model": "google/muril-base-cased",
        "flood_keywords": [
            "ရေကြီး", "ရေလွှမ်း", "မိုးကြီး", "မြစ်ရေ",
        ],
        "alert_templates": {
            "WARNING": "⚠️ ရေကြီးသတိပေးချက်: {village} တွင် {hours} နာရီအတွင်း ရေကြီးနိုင်ခြေရှိသည်။",
            "EMERGENCY": "🚨 အရေးပေါ်: {village} မှ ချက်ချင်းရွှေ့ပြောင်းပါ။",
        },
        "active": False,   # Pending ASR quality validation
    },
}


# ── Universal Flood Keywords (zero-shot fallback) ────────────────────────

UNIVERSAL_FLOOD_KEYWORDS = {
    # These work across languages via Whisper translation mode
    "flood", "water", "river", "rising", "overflow", "danger",
    "inundation", "submerged", "evacuation", "heavy rain",
    "dam", "embankment", "breach", "landslide", "rescue",
}


# ── Classifier ───────────────────────────────────────────────────────────

class GlobalCHORUSClassifier:
    """
    Multi-language CHORUS classifier using language detection + routing.

    Flow:
    1. Whisper ASR auto-detects language from audio
    2. Route to language-specific BERT model if available
    3. Fall back to zero-shot keyword matching for unsupported languages

    This means CHORUS can process reports in ANY language —
    just with higher accuracy for supported ones.
    """

    def __init__(self):
        self._loaded_models: dict[str, object] = {}
        logger.info(
            "chorus_classifier_init",
            supported_languages=len([
                c for c in GLOBAL_LANGUAGE_CONFIG.values() if c["active"]
            ]),
            total_languages=len(GLOBAL_LANGUAGE_CONFIG),
        )

    def classify(
        self,
        text: str,
        detected_language: str,
    ) -> ClassificationResult:
        """
        Classify a CHORUS report into flood-related categories.

        Args:
            text: Transcribed text from Whisper ASR
            detected_language: ISO 639-1 language code from Whisper

        Returns:
            ClassificationResult with label, confidence, method
        """
        config = GLOBAL_LANGUAGE_CONFIG.get(detected_language)

        if not config or not config["active"]:
            logger.info(
                "chorus_using_zero_shot",
                language=detected_language,
                reason="unsupported_or_inactive",
            )
            result = self._zero_shot_classify(text)
            result.language = detected_language
            return result

        # Use language-specific keyword + BERT classification
        result = self._keyword_classify(text, config)
        if result.confidence >= 0.6:
            result.language = detected_language
            return result

        # Attempt BERT classification for higher accuracy
        bert_result = self._bert_classify(text, config)
        if bert_result.confidence > result.confidence:
            bert_result.language = detected_language
            return bert_result

        result.language = detected_language
        return result

    def _keyword_classify(
        self,
        text: str,
        config: dict,
    ) -> ClassificationResult:
        """
        Keyword-based classification using language-specific flood terms.
        Fast, no model loading required — good for edge / offline.
        """
        text_lower = text.lower()
        keywords = config.get("flood_keywords", [])

        hit_count = sum(1 for kw in keywords if kw.lower() in text_lower)
        confidence = min(0.95, hit_count * 0.18)

        # Classify severity by keyword density
        if hit_count >= 4:
            label = FloodLabel.FLOOD_ACTIVE
        elif hit_count >= 2:
            label = FloodLabel.FLOOD_PRECURSOR
        elif hit_count >= 1:
            label = FloodLabel.FLOOD_PRECURSOR
        else:
            label = FloodLabel.UNRELATED

        # Check for evacuation-specific keywords
        evac_keywords = ["evacuation", "evacuate", "rescue", "help", "trapped",
                         "sơ tán", "निकासी", "উদ্ধার", "বানত", "cứu"]
        if any(kw in text_lower for kw in evac_keywords):
            label = FloodLabel.EVACUATION_REQUEST
            confidence = max(confidence, 0.75)

        return ClassificationResult(
            label=label,
            confidence=round(confidence, 3),
            method="keyword",
            raw_text=text,
        )

    def _bert_classify(
        self,
        text: str,
        config: dict,
    ) -> ClassificationResult:
        """
        Zero-shot NLI classification using xlm-roberta-large-xnli.

        Uses HuggingFace zero-shot-classification pipeline with
        multilingual NLI model — works across all CHORUS languages
        without per-language fine-tuning.
        """
        model_name = config.get(
            "classifier_model", "joeddav/xlm-roberta-large-xnli"
        )

        # Lazy-load and cache the pipeline
        if model_name not in self._loaded_models:
            try:
                from transformers import pipeline as hf_pipeline

                self._loaded_models[model_name] = hf_pipeline(
                    "zero-shot-classification",
                    model=model_name,
                    device=-1,  # CPU for edge / RPi deployment
                )
                logger.info("nli_model_loaded", model=model_name)
            except Exception as exc:
                logger.warning(
                    "nli_model_load_failed",
                    model=model_name,
                    error=str(exc),
                )
                # Fall back to keyword classification
                return self._keyword_classify(text, config)

        classifier = self._loaded_models[model_name]

        # Candidate labels match FloodLabel enum values
        candidate_labels = [
            "active flooding",
            "flood warning or precursor",
            "evacuation request",
            "infrastructure damage",
            "resource or rescue request",
            "unrelated to flooding",
        ]
        label_map = {
            "active flooding": FloodLabel.FLOOD_ACTIVE,
            "flood warning or precursor": FloodLabel.FLOOD_PRECURSOR,
            "evacuation request": FloodLabel.EVACUATION_REQUEST,
            "infrastructure damage": FloodLabel.INFRASTRUCTURE_DAMAGE,
            "resource or rescue request": FloodLabel.RESOURCE_REQUEST,
            "unrelated to flooding": FloodLabel.UNRELATED,
        }

        try:
            result = classifier(
                text,
                candidate_labels,
                hypothesis_template="This text is about {}.",
                multi_label=False,
            )
            top_label = result["labels"][0]
            top_score = result["scores"][0]

            flood_label = label_map.get(top_label, FloodLabel.UNRELATED)

            logger.info(
                "nli_classification",
                model=model_name,
                label=flood_label.value,
                confidence=round(top_score, 3),
                top_3=list(zip(result["labels"][:3], [
                    round(s, 3) for s in result["scores"][:3]
                ])),
            )

            return ClassificationResult(
                label=flood_label,
                confidence=round(top_score, 3),
                method="zero_shot_nli",
                raw_text=text,
            )
        except Exception as exc:
            logger.warning(
                "nli_inference_failed",
                error=str(exc),
            )
            return self._keyword_classify(text, config)

    def _zero_shot_classify(self, text: str) -> ClassificationResult:
        """
        Keyword-based zero-shot fallback for any language.

        Uses Whisper's translation mode to get English text,
        then matches against universal flood keyword list.
        Works for any of Whisper's 97 supported languages.
        """
        text_lower = text.lower()
        hit_count = sum(1 for kw in UNIVERSAL_FLOOD_KEYWORDS if kw in text_lower)
        confidence = min(0.9, hit_count * 0.15)

        label = (
            FloodLabel.FLOOD_PRECURSOR if confidence > 0.3
            else FloodLabel.UNRELATED
        )

        return ClassificationResult(
            label=label,
            confidence=round(confidence, 3),
            method="zero_shot_keyword",
            raw_text=text,
        )

    def get_alert_text(
        self,
        language: str,
        level: str,
        village: str,
        hours: int = 0,
    ) -> str:
        """
        Generate localised alert text for a given language.

        Args:
            language: ISO 639-1 code
            level: "WARNING" or "EMERGENCY"
            village: Village or ward name
            hours: Hours until expected flood
        """
        config = GLOBAL_LANGUAGE_CONFIG.get(language)
        if not config:
            # English fallback
            if level == "EMERGENCY":
                return f"EMERGENCY: Evacuate {village} immediately. Move to high ground."
            return f"Flood warning: {village} at risk in {hours} hours. Prepare to evacuate."

        templates = config.get("alert_templates", {})
        template = templates.get(level, templates.get("WARNING", ""))

        if not template:
            return f"Flood alert for {village}"

        return template.format(village=village, hours=hours)

    def get_supported_languages(self) -> list[dict]:
        """Return list of all supported languages with status."""
        return [
            {
                "code": code,
                "name": config["name"],
                "active": config["active"],
                "asr": config["asr"],
                "tts": config["tts"],
                "classifier": config.get("classifier_model", "keyword_only"),
                "n_keywords": len(config.get("flood_keywords", [])),
            }
            for code, config in GLOBAL_LANGUAGE_CONFIG.items()
        ]
