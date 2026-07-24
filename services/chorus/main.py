"""CHORUS — Community Sensing FastAPI service (port 8008).

Turns every citizen with a WhatsApp account into a verified,
AI-weighted sensor. No app install required.

Architecture:
  Twilio webhook → Whisper ASR → IndicBERT classifier → Location extractor
  → Trust engine (consensus protocol) → Kafka publisher → Causal Engine

Endpoints:
  POST /chorus/webhook                → Twilio WhatsApp webhook (main entry)
  POST /api/v1/chorus/demo            → Inject mock report (for demo)
  GET  /api/v1/chorus/signals         → Recent CHORUS signals (for map)
  GET  /api/v1/chorus/consensus       → Active consensus events (3+ reports)
  GET  /api/v1/chorus/stats           → Totals: reports, signals, languages
  GET  /api/v1/chorus/village/{id}    → Aggregated sentiment for a village
  GET  /api/v1/chorus/villages        → All village aggregations
  GET  /health                        → Liveness check

Run: ``uvicorn services.chorus.main:app --reload --port 8008``
"""

from __future__ import annotations

import os
import random
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from shared.config import get_settings
from services.chorus.nlp import analyze_message
from services.chorus.aggregator import ChorusAggregator
from services.chorus.nlp.whisper_transcriber import WhisperTranscriber
from services.chorus.nlp.indic_classifier import IndicFloodClassifier
from services.chorus.nlp.location_extractor import LocationExtractor
from services.chorus.trust.trust_engine import TrustEngine
from services.chorus.publisher.chorus_publisher import ChorusPublisher
from services.chorus.webhook.twilio_handler import router as twilio_router, init_webhook

logger = structlog.get_logger(__name__)
settings = get_settings()

# ── Globals ──────────────────────────────────────────────────────────────
_aggregator: Optional[ChorusAggregator] = None
_publisher: Optional[ChorusPublisher] = None
_trust_engine: Optional[TrustEngine] = None
_classifier: Optional[IndicFloodClassifier] = None
_location_extractor: Optional[LocationExtractor] = None
_transcriber: Optional[WhisperTranscriber] = None

# In-memory recent signals buffer (for /signals endpoint)
_recent_signals: List[Dict] = []
_MAX_SIGNALS = 500


class ReportRequest(BaseModel):
    message: str
    village_id: str
    source: str = "whatsapp"
    language: str = "hi"
    lat: Optional[float] = None
    lon: Optional[float] = None


class DemoReport(BaseModel):
    """Pre-crafted demo report for hackathon judges."""
    message: str = "नदी बहुत तेज़ बह रही है, पानी रास्ते पर आ गया"
    village_id: str = "majuli_01"
    source: str = "whatsapp"
    language: str = "hi"
    lat: Optional[float] = 26.95
    lon: Optional[float] = 94.17
    simulate_consensus: bool = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _aggregator, _publisher, _trust_engine, _classifier
    global _location_extractor, _transcriber

    logger.info("chorus_starting", port=settings.CHORUS_PORT)

    # Initialize all pipeline components
    _aggregator = ChorusAggregator(
        window_minutes=int(os.getenv("CHORUS_CONSENSUS_WINDOW_MINUTES", str(settings.CHORUS_WINDOW_MIN)))
    )

    _classifier = IndicFloodClassifier(
        checkpoint_path=os.getenv("INDIC_BERT_CHECKPOINT")
    )

    _location_extractor = LocationExtractor(
        landmark_csv_path=os.getenv("LANDMARK_DB_PATH"),
        geohash_precision=int(os.getenv("GEOHASH_PRECISION", "5")),
    )

    _transcriber = WhisperTranscriber(
        model_size=os.getenv("WHISPER_MODEL_SIZE", "base")
    )

    _trust_engine = TrustEngine(
        redis_url=os.getenv("REDIS_URL", settings.REDIS_URL),
        consensus_threshold=int(os.getenv("CHORUS_CONSENSUS_THRESHOLD", "3")),
        consensus_window_seconds=int(os.getenv("CHORUS_CONSENSUS_WINDOW_MINUTES", "10")) * 60,
    )

    _publisher = ChorusPublisher(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
    )

    # Wire up the webhook handler with all dependencies
    init_webhook(
        transcriber=_transcriber,
        classifier=_classifier,
        location_extractor=_location_extractor,
        trust_engine=_trust_engine,
        publisher=_publisher,
        aggregator=_aggregator,
    )

    logger.info("chorus_ready", classifier="keyword_fallback" if not _classifier._using_model else "indic_bert")
    yield

    if _publisher:
        _publisher.flush()
    logger.info("chorus_shutdown")


app = FastAPI(
    title="ARGUS CHORUS — Community Sensing",
    version="2.1.0",
    description=(
        "WhatsApp-based community intelligence for flood early warning. "
        "Whisper ASR + IndicBERT classification + geohash consensus protocol."
    ),
    lifespan=lifespan,
)

# Mount the Twilio webhook router
app.include_router(twilio_router)


# ═══════════════════════════════════════════════════════════════════════
#  Health
# ═══════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {
        "service": "chorus",
        "version": "2.1.0",
        "status": "healthy",
        "total_reports": _aggregator.get_report_count() if _aggregator else 0,
        "components": {
            "whisper": _transcriber.is_available if _transcriber else False,
            "indic_bert": _classifier._using_model if _classifier else False,
            "classifier_mode": "model" if (_classifier and _classifier._using_model) else "keyword",
            "kafka_publisher": _publisher._producer is not None if _publisher else False,
            "trust_engine_mode": "redis" if (_trust_engine and _trust_engine._redis_client) else "memory",
        },
    }


# ═══════════════════════════════════════════════════════════════════════
#  Core Endpoints
# ═══════════════════════════════════════════════════════════════════════

@app.post("/api/v1/chorus/report")
async def submit_report(req: ReportRequest):
    """Analyze and store a community report (direct API, no WhatsApp)."""
    if not _aggregator:
        raise HTTPException(503, "Service not ready")

    report = analyze_message(
        message=req.message,
        village_id=req.village_id,
        source=req.source,
        language=req.language,
        lat=req.lat,
        lon=req.lon,
    )

    # Run through trust engine
    geohash = ""
    if _location_extractor:
        loc = _location_extractor.extract(
            req.message,
            whatsapp_location={"lat": req.lat, "lon": req.lon} if req.lat else None,
        )
        geohash = loc.geohash

    trust_weight = 0.2
    consensus = None
    if _trust_engine:
        phone_hash = TrustEngine.hash_phone(f"api_{req.source}_{uuid.uuid4().hex[:8]}")
        trust = _trust_engine.get_trust_score(phone_hash, geohash)
        trust_weight = trust.weight
        consensus = _trust_engine.record_report(phone_hash, geohash, "API_REPORT")

    if report.credibility_score < settings.CHORUS_CREDIBILITY_THRESHOLD:
        return {
            "accepted": False,
            "reason": "Below credibility threshold",
            "score": report.credibility_score,
        }

    _aggregator.add_report(report)

    # Build signal for Kafka
    signal = {
        "report_id": report.report_id,
        "geohash": geohash,
        "lat": req.lat,
        "lon": req.lon,
        "classification": report.keywords[0] if report.keywords else "UNRELATED",
        "confidence": report.credibility_score,
        "trust_weight": trust_weight,
        "original_text": req.message,
        "language_detected": req.language,
        "consensus_count": consensus.count if consensus else 1,
        "is_flood_relevant": report.flood_mentioned,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if _publisher:
        _publisher.publish(signal)
    _recent_signals.append(signal)
    if len(_recent_signals) > _MAX_SIGNALS:
        _recent_signals.pop(0)

    return {
        "accepted": True,
        "report_id": report.report_id,
        "classification": signal["classification"],
        "sentiment": report.sentiment.value,
        "flood_mentioned": report.flood_mentioned,
        "credibility": report.credibility_score,
        "trust_weight": trust_weight,
        "geohash": geohash,
        "consensus_count": signal["consensus_count"],
        "keywords": report.keywords,
    }


@app.get("/api/v1/chorus/signals")
async def get_signals(limit: int = 50):
    """Recent CHORUS signals for dashboard map pins."""
    return _recent_signals[-limit:]


@app.get("/api/v1/chorus/consensus")
async def get_consensus():
    """Active consensus events (3+ reports from same geohash in window)."""
    if not _trust_engine:
        return []

    active = []
    geohashes = set()
    for sig in _recent_signals:
        gh = sig.get("geohash", "")
        if gh:
            geohashes.add(gh)

    for gh in geohashes:
        status = _trust_engine.check_consensus(gh)
        if status.threshold_reached:
            active.append({
                "geohash": gh,
                "count": status.count,
                "reporters": status.reporters,
                "trust_weight": status.trust_weight,
                "window_seconds": status.window_seconds,
            })

    return active


@app.get("/api/v1/chorus/stats")
async def stats():
    if not _aggregator:
        raise HTTPException(503, "Service not ready")
    all_agg = _aggregator.aggregate_all()
    return {
        "total_reports": _aggregator.get_report_count(),
        "total_signals": len(_recent_signals),
        "villages_reporting": len(all_agg),
        "active_consensus": sum(
            1 for sig in _recent_signals
            if sig.get("consensus_count", 0) >= 3
        ),
        "languages_detected": list(set(
            sig.get("language_detected", "unknown")
            for sig in _recent_signals
        )),
        "aggregations": {k: v.model_dump() for k, v in all_agg.items()},
    }


@app.get("/api/v1/chorus/village/{village_id}")
async def village_aggregation(village_id: str):
    if not _aggregator:
        raise HTTPException(503, "Service not ready")
    agg = _aggregator.aggregate(village_id)
    return agg.model_dump()


@app.get("/api/v1/chorus/villages")
async def all_villages():
    if not _aggregator:
        raise HTTPException(503, "Service not ready")
    return {k: v.model_dump() for k, v in _aggregator.aggregate_all().items()}


# ═══════════════════════════════════════════════════════════════════════
#  Demo Endpoint — Critical for Hackathon
# ═══════════════════════════════════════════════════════════════════════

# Pre-canned demo reports
DEMO_REPORTS = [
    DemoReport(
        message="नदी बहुत तेज़ बह रही है, पानी रास्ते पर आ गया",
        village_id="majuli_01",
        language="hi",
        lat=26.95, lon=94.17,
    ),
    DemoReport(
        message="ব্রিজের উপর দিয়ে পানি আসছে",
        village_id="majuli_01",
        language="bn",
        lat=26.95, lon=94.17,
    ),
    DemoReport(
        message="Bachao! Water entering houses in lower colony. Need rescue boats!",
        village_id="majuli_01",
        language="en",
        lat=26.94, lon=94.21,
    ),
    DemoReport(
        message="Dam release se paani 2 meter upar aa gaya. SOS!",
        village_id="kullu_01",
        language="hi",
        lat=31.96, lon=77.11,
    ),
    DemoReport(
        message="Heavy rain for 3 hours non-stop near NH-715 junction. Road submerged.",
        village_id="majuli_01",
        language="en",
        lat=26.965, lon=94.155,
    ),
]


@app.post("/api/v1/chorus/demo")
async def inject_demo_report(report: Optional[DemoReport] = None):
    """Inject a mock CHORUS report without needing WhatsApp.

    Used during demo: team clicks this button on the dashboard and
    the geocoded pin appears on the map with risk score updating
    in real time.

    If no report body provided, cycles through pre-canned reports.
    """
    if not _aggregator:
        raise HTTPException(503, "Service not ready")

    if report is None:
        report = random.choice(DEMO_REPORTS)

    # Simulate the full pipeline
    analyzed = analyze_message(
        message=report.message,
        village_id=report.village_id,
        source=report.source,
        language=report.language,
        lat=report.lat,
        lon=report.lon,
    )

    # Get geohash
    geohash = ""
    if _location_extractor:
        loc = _location_extractor.extract(
            report.message,
            whatsapp_location={"lat": report.lat, "lon": report.lon},
        )
        geohash = loc.geohash

    # Simulate consensus if requested
    trust_weight = 0.2
    consensus_count = 1
    if report.simulate_consensus and _trust_engine:
        for i in range(3):
            _trust_engine.record_report(
                f"demo_reporter_{i}", geohash,
                analyzed.keywords[0] if analyzed.keywords else "DEMO",
            )
        consensus = _trust_engine.check_consensus(geohash)
        if consensus.threshold_reached:
            trust_weight = 0.8
            consensus_count = consensus.count

    _aggregator.add_report(analyzed)

    signal = {
        "report_id": analyzed.report_id,
        "geohash": geohash,
        "lat": report.lat,
        "lon": report.lon,
        "classification": analyzed.keywords[0] if analyzed.keywords else "UNRELATED",
        "confidence": round(analyzed.credibility_score, 3),
        "trust_weight": trust_weight,
        "original_text": report.message,
        "language_detected": report.language,
        "consensus_count": consensus_count,
        "is_flood_relevant": analyzed.flood_mentioned,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if _publisher:
        _publisher.publish(signal)
    _recent_signals.append(signal)
    if len(_recent_signals) > _MAX_SIGNALS:
        _recent_signals.pop(0)

    return {
        "injected": True,
        "report_id": analyzed.report_id,
        "classification": signal["classification"],
        "sentiment": analyzed.sentiment.value,
        "trust_weight": trust_weight,
        "consensus_count": consensus_count,
        "geohash": geohash,
        "flood_mentioned": analyzed.flood_mentioned,
        "signal": signal,
        "aggregation": _aggregator.aggregate(report.village_id).model_dump(),
    }


@app.post("/api/v1/chorus/demo/generate")
async def demo_generate(village_id: str = "majuli_01", count: int = 10):
    """Generate multiple synthetic demo reports for a village."""
    if not _aggregator:
        raise HTTPException(503, "Service not ready")

    demo_messages = [
        "River water level rising fast near the bridge. Very dangerous!",
        "Heavy rain for 3 hours non-stop. Paani bahut badh raha hai.",
        "Baarish ruk gayi hai. Situation seems stable now.",
        "Bachao! Water entering houses in lower colony. Need rescue boats!",
        "Dam release se paani 2 meter upar aa gaya. SOS!",
        "Fields submerged, road to hospital washed away. Emergency!",
        "Sab theek hai, water level normal. No flooding in our area.",
        "Cloudburst reported upstream. Heavy flooding expected in 3 hours.",
        "Landslide near bridge blocked evacuation route. Khatra!",
        "Nadi ka paani 4 feet upar. Madad chahiye urgently!",
        "Water receding slowly. Situation improving compared to yesterday.",
        "Embankment breach near village school. Children stranded!",
        "নদী বহুত তীব্র বৈ আছে, পানী ৰাস্তাত আহি গৈছে",
        "ব্রিজ ডুবে যাচ্ছে, রাস্তা বন্ধ",
    ]

    generated = []
    for i in range(count):
        msg = random.choice(demo_messages)
        report = analyze_message(
            message=msg,
            village_id=village_id,
            source=random.choice(["whatsapp", "field_worker", "voice_call"]),
            language=random.choice(["hi", "en", "as", "bn"]),
        )
        _aggregator.add_report(report)
        generated.append(report.report_id)

    return {
        "generated": len(generated),
        "village_id": village_id,
        "aggregation": _aggregator.aggregate(village_id).model_dump(),
    }


# ═══════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    uvicorn.run(
        "services.chorus.main:app",
        host=settings.SERVICE_HOST,
        port=settings.CHORUS_PORT,
        reload=False,
    )
