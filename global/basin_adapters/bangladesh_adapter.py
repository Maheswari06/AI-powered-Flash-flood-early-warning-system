"""
ARGUS Phase 6 — Bangladesh Flood Adapter

Adapts ARGUS for Bangladesh deployment — the highest-impact
international deployment due to:
  - Brahmaputra (Jamuna) arrives 48 hours after Assam peaks
  - 160M people, 80% flood-exposed
  - BWDB + FFWC existing infrastructure to integrate with

Key differences from India:
  - Data: BWDB (Bangladesh Water Development Board) API
  - Language: Bengali (bn) primary — IndicTTS + bangla-tts
  - Admin units: Division → District → Upazila → Union
  - Alert system: SPARRSO satellite + FFWC operational warnings
  - Mobile: bKash payment integration for FloodLedger payouts
  - Shelters: Union-level cyclone shelters (dual-use for flash floods)
  - Cross-border: Models Brahmaputra + Meghna + Ganges from India
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Basin Configuration
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class BasinConfig:
    """Configuration for a specific basin deployment."""
    basin_id: str
    display_name: str
    state: str
    country: str
    bbox: tuple
    flash_flood_threshold_hours: int
    monsoon_months: List[int]
    language_codes: List[str]
    admin_unit_hierarchy: List[str]
    payment_provider: str
    shelter_registry_api: str
    upstream_warning_source: str
    upstream_lag_hours: int


@dataclass
class AlertEvent:
    """Standardized ARGUS alert event."""
    alert_id: str
    alert_level: str          # WATCH / WARNING / CRITICAL
    station_name: str
    predicted_level_m: float
    danger_level_m: float
    predicted_flood_time: datetime
    confidence: float
    basin_id: str
    lat: float
    lon: float


class FFWCAlertLevel(str, Enum):
    """Bangladesh FFWC alert level mapping."""
    NORMAL = "NORMAL"
    ALERT = "ALERT"
    WARNING = "WARNING"
    DANGER = "DANGER"
    SEVERE_DANGER = "SEVERE_DANGER"


# ══════════════════════════════════════════════════════════════════════════
# Bangladesh Adapter
# ══════════════════════════════════════════════════════════════════════════

class BangladeshFloodAdapter:
    """
    Adapts ARGUS for Bangladesh deployment.

    Integrates with:
      - BWDB (Bangladesh Water Development Board) for gauge data
      - FFWC (Flood Forecasting and Warning Centre) for alert routing
      - SPARRSO (Space Research and Remote Sensing Organization) for satellite
      - bKash mobile money for FloodLedger parametric insurance payouts

    The key value proposition for Bangladesh:
      ARGUS Assam provides a 48-hour upstream signal for the Brahmaputra
      (known as Jamuna in Bangladesh). BWDB currently has ~12-hour lead time.
      ARGUS extends this to 48+ hours.
    """

    BWDB_BASE = "https://www.hydrology.bwdb.gov.bd/api"
    SPARRSO = "https://sparrso.gov.bd/api/flood"
    FFWC_BASE = "https://www.ffwc.gov.bd/api"
    BKASH_API = "https://tokenized.pay.bka.sh/v1.2.0-beta"

    # River name mapping (same river, different names per country)
    RIVER_NAME_MAP = {
        "Brahmaputra": "Jamuna",     # Brahmaputra = Jamuna in Bangladesh
        "Ganges": "Padma",            # Ganges = Padma after Farakka
        "Meghna": "Meghna",           # Same name
        "Teesta": "Teesta",           # Same name
        "Kosi": "Ganges-Padma",       # Kosi joins Ganges which becomes Padma
    }

    # Bangladesh admin division hierarchy
    DIVISIONS = [
        "Dhaka", "Chittagong", "Rajshahi", "Khulna",
        "Barisal", "Sylhet", "Rangpur", "Mymensingh"
    ]

    def __init__(self, upstream_argus_url: str = "http://argus-assam:8000"):
        self.upstream_argus_url = upstream_argus_url
        self.logger = logger.bind(adapter="bangladesh")

    # ── Basin Config ─────────────────────────────────────────────────────

    def get_basin_config(self) -> BasinConfig:
        """Returns basin configuration for Bangladesh Brahmaputra (Jamuna)."""
        return BasinConfig(
            basin_id="brahmaputra_bangladesh",
            display_name="Brahmaputra (Jamuna) — Bangladesh",
            state="Dhaka Division",
            country="Bangladesh",
            bbox=(88.0, 22.0, 92.7, 26.0),
            flash_flood_threshold_hours=6,
            monsoon_months=[6, 7, 8, 9, 10],
            language_codes=["bn", "en"],
            admin_unit_hierarchy=["division", "district", "upazila", "union"],
            payment_provider="bkash",
            shelter_registry_api=f"{self.BWDB_BASE}/shelters",
            upstream_warning_source="argus_assam",
            upstream_lag_hours=48,
        )

    # ── Data Ingestion ───────────────────────────────────────────────────

    async def get_gauge_readings(self) -> List[dict]:
        """
        Pulls current water level data from BWDB.
        Free API — requires registration at hydrology.bwdb.gov.bd.
        Falls back to FFWC if BWDB is unavailable.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(f"{self.BWDB_BASE}/current_water_level")
                r.raise_for_status()
            readings = [
                self._normalize_bwdb(station)
                for station in r.json().get("stations", [])
            ]
            self.logger.info("bwdb_readings_fetched", count=len(readings))
            return readings
        except Exception as e:
            self.logger.warning("bwdb_unavailable", error=str(e))
            return await self._fallback_ffwc_readings()

    async def _fallback_ffwc_readings(self) -> List[dict]:
        """Fallback: pull simplified readings from FFWC."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(f"{self.FFWC_BASE}/water_level/current")
                r.raise_for_status()
            return [self._normalize_ffwc(s) for s in r.json().get("data", [])]
        except Exception:
            self.logger.error("ffwc_also_unavailable")
            return []

    async def get_upstream_signal_from_assam(self) -> Optional[dict]:
        """
        Pull the 48-hour upstream flood signal from ARGUS Assam deployment.
        This is the primary value of cross-border integration —
        Dhaka gets 48 more hours of warning.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(
                    f"{self.upstream_argus_url}/api/v1/prediction/latest",
                    params={"station": "BR_ASSAM_DHUBRI"},
                )
                r.raise_for_status()
            signal = r.json()
            self.logger.info(
                "upstream_signal_received",
                station="BR_ASSAM_DHUBRI",
                predicted_level=signal.get("predicted_level_m"),
                lead_time_hours=48,
            )
            return signal
        except Exception as e:
            self.logger.warning(
                "upstream_signal_unavailable",
                error=str(e),
                fallback="PINN_interpolation",
            )
            return None

    # ── Alert Translation ────────────────────────────────────────────────

    async def translate_alert_for_bangladesh(
        self,
        argus_alert: AlertEvent,
    ) -> dict:
        """
        Translates ARGUS alert format to Bangladesh FFWC standard format.
        Required for SPARRSO and FFWC system integration.

        Handles:
          - River name translation (Brahmaputra → Jamuna)
          - Alert level mapping to FFWC 5-tier system
          - Bengali language alert text generation
          - bKash payout trigger if FloodLedger is active
        """
        ffwc_level = self._map_to_ffwc_level(argus_alert.alert_level)
        river_name = self.RIVER_NAME_MAP.get(
            argus_alert.station_name.split("_")[0],
            "Jamuna"
        )

        alert_dict = {
            "alertId": argus_alert.alert_id,
            "alertLevel": ffwc_level.value,
            "riverName": river_name,
            "stationName": argus_alert.station_name,
            "predictedLevel": argus_alert.predicted_level_m,
            "dangerLevel": argus_alert.danger_level_m,
            "forecastTime": argus_alert.predicted_flood_time.isoformat(),
            "issuedBy": "ARGUS AI System",
            "confidencePercent": int(argus_alert.confidence * 100),
            "upstreamSource": "Assam ARGUS Node — 48hr upstream signal",
            "language": "bn",
            "bengaliMessage": self._generate_bengali_alert(
                ffwc_level, river_name, argus_alert
            ),
            "shelterAdvice": self._get_nearest_shelter_advice(argus_alert),
            "bkashPayoutEligible": (
                ffwc_level in (FFWCAlertLevel.DANGER, FFWCAlertLevel.SEVERE_DANGER)
            ),
        }

        self.logger.info(
            "alert_translated_for_bangladesh",
            alert_id=argus_alert.alert_id,
            ffwc_level=ffwc_level.value,
            river=river_name,
        )

        return alert_dict

    def _map_to_ffwc_level(self, argus_level: str) -> FFWCAlertLevel:
        """Map ARGUS 3-tier to FFWC 5-tier alert level."""
        mapping = {
            "WATCH": FFWCAlertLevel.ALERT,
            "WARNING": FFWCAlertLevel.WARNING,
            "CRITICAL": FFWCAlertLevel.DANGER,
        }
        return mapping.get(argus_level, FFWCAlertLevel.ALERT)

    def _generate_bengali_alert(
        self,
        level: FFWCAlertLevel,
        river_name: str,
        alert: AlertEvent,
    ) -> str:
        """Generate alert message in Bengali (transliterated for SMS/IVR)."""
        level_bn = {
            FFWCAlertLevel.NORMAL: "স্বাভাবিক",
            FFWCAlertLevel.ALERT: "সতর্কতা",
            FFWCAlertLevel.WARNING: "সতর্কবার্তা",
            FFWCAlertLevel.DANGER: "বিপদ",
            FFWCAlertLevel.SEVERE_DANGER: "চরম বিপদ",
        }

        hours_to_flood = int(
            (alert.predicted_flood_time - datetime.utcnow()).total_seconds() / 3600
        )

        return (
            f"⚠️ {level_bn.get(level, 'সতর্কতা')} — {river_name} নদী\n"
            f"পূর্বাভাস: {hours_to_flood} ঘণ্টার মধ্যে বন্যা\n"
            f"জলস্তর: {alert.predicted_level_m:.1f}m (বিপদসীমা: {alert.danger_level_m:.1f}m)\n"
            f"আত্মবিশ্বাস: {int(alert.confidence * 100)}%\n"
            f"নিকটতম আশ্রয়কেন্দ্রে যান।"
        )

    def _get_nearest_shelter_advice(self, alert: AlertEvent) -> dict:
        """Placeholder for nearest cyclone shelter lookup."""
        return {
            "instruction": "Move to nearest Union-level cyclone shelter",
            "lookup_api": f"{self.BWDB_BASE}/shelters?lat={alert.lat}&lon={alert.lon}",
        }

    # ── Data Normalization ───────────────────────────────────────────────

    def _normalize_bwdb(self, station: dict) -> dict:
        """Normalize BWDB station reading to ARGUS standard format."""
        return {
            "station_id": station.get("station_id", ""),
            "station_name": station.get("station_name", ""),
            "river": station.get("river_name", ""),
            "level_m": float(station.get("water_level", 0)),
            "danger_level_m": float(station.get("danger_level", 0)),
            "timestamp": station.get("observed_at", datetime.utcnow().isoformat()),
            "source": "BWDB",
            "country": "Bangladesh",
            "lat": float(station.get("latitude", 0)),
            "lon": float(station.get("longitude", 0)),
        }

    def _normalize_ffwc(self, station: dict) -> dict:
        """Normalize FFWC station reading to ARGUS standard format."""
        return {
            "station_id": station.get("id", ""),
            "station_name": station.get("name", ""),
            "river": station.get("river", ""),
            "level_m": float(station.get("level", 0)),
            "danger_level_m": float(station.get("danger_level", 0)),
            "timestamp": station.get("timestamp", datetime.utcnow().isoformat()),
            "source": "FFWC",
            "country": "Bangladesh",
            "lat": float(station.get("lat", 0)),
            "lon": float(station.get("lon", 0)),
        }

    # ── bKash Integration ────────────────────────────────────────────────

    async def trigger_bkash_payout(
        self,
        phone_number: str,
        amount_bdt: float,
        flood_event_id: str,
    ) -> dict:
        """
        Trigger bKash mobile money payout for FloodLedger parametric insurance.
        Bangladesh uses bKash (not UPI) — 70M+ active users.

        This is an automated payout triggered when:
          1. ARGUS issues a DANGER-level alert
          2. Satellite confirms inundation > threshold
          3. Smart contract on FloodLedger validates claim
        """
        payload = {
            "mode": "0011",   # bKash disbursement mode
            "payerReference": f"ARGUS-FLOOD-{flood_event_id}",
            "callbackURL": "https://argus.foundation/api/bkash/callback",
            "amount": str(amount_bdt),
            "currency": "BDT",
            "intent": "sale",
            "merchantInvoiceNumber": f"FL-{flood_event_id}",
        }

        self.logger.info(
            "bkash_payout_initiated",
            phone=phone_number[-4:],   # Log last 4 only
            amount_bdt=amount_bdt,
            flood_event=flood_event_id,
        )

        # In production: POST to bKash tokenized API
        # For now: return mock response
        return {
            "status": "INITIATED",
            "paymentID": f"bkash_{flood_event_id}",
            "amount": amount_bdt,
            "currency": "BDT",
            "provider": "bKash",
        }
