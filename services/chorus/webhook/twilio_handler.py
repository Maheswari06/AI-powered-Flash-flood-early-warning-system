"""Twilio webhook handler for incoming WhatsApp messages.

Responds to Twilio immediately (< 5 s timeout), then processes
the message in a background task so the pipeline doesn't block.

Handles:
  - Plain text messages → NLP classifier
  - Voice notes → Whisper ASR → NLP classifier
  - Location pins → GPS coordinates
"""

from __future__ import annotations

import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, Request, Response

from services.chorus.nlp.whisper_transcriber import WhisperTranscriber
from services.chorus.nlp.indic_classifier import IndicFloodClassifier
from services.chorus.nlp.location_extractor import LocationExtractor
from services.chorus.trust.trust_engine import TrustEngine

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["chorus-webhook"])

# These are injected at startup from main.py
_transcriber: Optional[WhisperTranscriber] = None
_classifier: Optional[IndicFloodClassifier] = None
_location_extractor: Optional[LocationExtractor] = None
_trust_engine: Optional[TrustEngine] = None
_publisher = None   # ChorusPublisher, set from main
_aggregator = None  # ChorusAggregator, set from main


def init_webhook(
    transcriber: WhisperTranscriber,
    classifier: IndicFloodClassifier,
    location_extractor: LocationExtractor,
    trust_engine: TrustEngine,
    publisher,
    aggregator,
):
    """Inject dependencies into the webhook handler."""
    global _transcriber, _classifier, _location_extractor, _trust_engine
    global _publisher, _aggregator
    _transcriber = transcriber
    _classifier = classifier
    _location_extractor = location_extractor
    _trust_engine = trust_engine
    _publisher = publisher
    _aggregator = aggregator


@router.post("/chorus/webhook")
async def handle_whatsapp_message(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Twilio WhatsApp webhook entry point.

    Twilio sends a POST with form data for each incoming message.
    Must respond in < 5 seconds (Twilio timeout).
    Heavy NLP processing goes to a background task.
    """
    form_data = await request.form()

    from_number = form_data.get("From", "")          # "whatsapp:+91XXXXXXXXXX"
    body = form_data.get("Body", "")                 # text message
    media_url = form_data.get("MediaUrl0")           # voice note URL
    media_type = form_data.get("MediaContentType0")  # audio/ogg etc.
    latitude = form_data.get("Latitude")
    longitude = form_data.get("Longitude")
    num_media = int(form_data.get("NumMedia", "0"))

    logger.info(
        "twilio_webhook_received",
        has_body=bool(body),
        has_media=num_media > 0,
        has_location=latitude is not None,
    )

    # Queue heavy processing in background
    background_tasks.add_task(
        process_chorus_report,
        from_number=from_number,
        body=body,
        media_url=media_url,
        media_type=media_type,
        latitude=float(latitude) if latitude else None,
        longitude=float(longitude) if longitude else None,
    )

    # Respond immediately to Twilio with TwiML acknowledgment
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        "<Message>🌊 ARGUS has received your flood report. Stay safe. "
        "कृपया सुरक्षित रहें।</Message>"
        "</Response>"
    )
    return Response(content=twiml, media_type="application/xml")


async def process_chorus_report(
    from_number: str,
    body: str,
    media_url: Optional[str],
    media_type: Optional[str],
    latitude: Optional[float],
    longitude: Optional[float],
):
    """Full NLP pipeline — runs in background after Twilio ack."""
    try:
        report_id = str(uuid.uuid4())
        phone_hash = TrustEngine.hash_phone(from_number) if from_number else "unknown"

        # Step 1: Transcribe voice note if present
        text = body or ""
        language_detected = "unknown"
        if media_url and _transcriber and _transcriber.is_available:
            if media_type and "audio" in media_type:
                transcription = _transcriber.transcribe_url(media_url)
                if transcription.text:
                    text = transcription.text
                    language_detected = transcription.language_detected

        if not text:
            logger.debug("chorus_empty_message", phone_hash=phone_hash)
            return

        # Step 2: Classify the message
        classification = _classifier.classify(text) if _classifier else None
        label = classification.label if classification else "UNRELATED"
        confidence = classification.confidence if classification else 0.0

        # Step 3: Extract location
        whatsapp_loc = None
        if latitude is not None and longitude is not None:
            whatsapp_loc = {"lat": latitude, "lon": longitude}

        location = _location_extractor.extract(
            text, whatsapp_location=whatsapp_loc
        ) if _location_extractor else None

        geohash = location.geohash if location else ""
        lat = location.lat if location else latitude
        lon = location.lon if location else longitude

        # Step 4: Compute trust score
        trust = _trust_engine.get_trust_score(phone_hash, geohash) if _trust_engine else None
        trust_weight = trust.weight if trust else 0.2

        # Step 5: Record report for consensus tracking
        consensus = None
        if _trust_engine and geohash:
            consensus = _trust_engine.record_report(phone_hash, geohash, label)
            if consensus.threshold_reached:
                trust_weight = 0.8
                logger.info(
                    "consensus_reached",
                    geohash=geohash,
                    count=consensus.count,
                )

        # Step 6: Build signal and publish to Kafka
        signal = {
            "report_id": report_id,
            "geohash": geohash,
            "lat": lat,
            "lon": lon,
            "classification": label,
            "confidence": round(confidence, 3),
            "trust_weight": trust_weight,
            "original_text": text,  # anonymized — no phone number
            "language_detected": language_detected,
            "consensus_count": consensus.count if consensus else 1,
            "landmark": location.landmark_name if location else None,
            "is_flood_relevant": classification.is_flood_relevant if classification else False,
        }

        if _publisher:
            _publisher.publish(signal)

        # Step 7: Also add to aggregator for REST queries
        if _aggregator:
            from shared.models.phase2 import CommunityReport, SentimentLevel
            from services.chorus.nlp import indic_classifier

            # Map classification to sentiment
            sentiment_map = {
                "ACTIVE_FLOOD": SentimentLevel.PANIC,
                "PEOPLE_STRANDED": SentimentLevel.PANIC,
                "FLOOD_PRECURSOR": SentimentLevel.ANXIOUS,
                "INFRASTRUCTURE_FAILURE": SentimentLevel.ANXIOUS,
                "ROAD_BLOCKED": SentimentLevel.CONCERNED,
                "DAMAGE_REPORT": SentimentLevel.CONCERNED,
                "RESOURCE_REQUEST": SentimentLevel.ANXIOUS,
                "WEATHER_OBSERVATION": SentimentLevel.CONCERNED,
                "FALSE_ALARM": SentimentLevel.CALM,
                "OFFICIAL_UPDATE": SentimentLevel.CONCERNED,
            }
            sentiment = sentiment_map.get(label, SentimentLevel.CALM)

            report = CommunityReport(
                report_id=report_id,
                village_id=geohash or "unknown",
                source="whatsapp",
                message=text,
                language=language_detected,
                sentiment=sentiment,
                keywords=[label],
                flood_mentioned=classification.is_flood_relevant if classification else False,
                location_lat=lat,
                location_lon=lon,
                credibility_score=trust_weight,
            )
            _aggregator.add_report(report)

        logger.info(
            "chorus_report_processed",
            report_id=report_id,
            classification=label,
            confidence=round(confidence, 3),
            trust=trust_weight,
            geohash=geohash,
            consensus=consensus.count if consensus else 0,
        )
    except Exception as exc:
        logger.exception("chorus_processing_error", error=str(exc))
