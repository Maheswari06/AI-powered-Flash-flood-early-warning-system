"""Location extractor and geocoder for CHORUS flood reports.

Extracts location entities from text and resolves them to
(lat, lon, geohash) using multiple strategies in priority order:

1. GPS coordinates if WhatsApp location pin shared
2. Named landmark recognition (bridge names, road numbers)
3. Fuzzy text match against landmark database
4. Approximate location from phone number's district

Uses pygeohash for geohash encoding (5-char ≈ 5km × 5km cells).
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)

# Try to import pygeohash — fall back to simple hash
try:
    import pygeohash as pgh  # type: ignore[import-untyped]
    _GEOHASH_AVAILABLE = True
except ImportError:
    pgh = None
    _GEOHASH_AVAILABLE = False
    logger.warning("pygeohash_not_available", hint="pip install pygeohash")


@dataclass
class LocationResult:
    """Resolved location for a community report."""
    lat: Optional[float] = None
    lon: Optional[float] = None
    geohash: str = ""
    landmark_name: Optional[str] = None
    resolution_method: str = "none"  # gps, landmark, district, default
    confidence: float = 0.0


# ── Default landmark database (Assam + Himachal Pradesh) ─────────────

DEFAULT_LANDMARKS: List[Dict[str, str]] = [
    # Majuli Island, Assam
    {"name": "Majuli bridge", "lat": "26.9500", "lon": "94.1700", "aliases": "majuli bridge,মাজুলী ব্রিজ,মাজুলী সেতু"},
    {"name": "Kamalabari ghat", "lat": "26.9400", "lon": "94.2100", "aliases": "kamalabari,কমলাবাৰী"},
    {"name": "Garamur", "lat": "26.9570", "lon": "94.1530", "aliases": "garamur,গড়মূৰ"},
    {"name": "Jengraimukh", "lat": "26.9800", "lon": "94.0900", "aliases": "jengraimukh,জেংৰাইমুখ"},
    {"name": "Salmora", "lat": "26.9200", "lon": "94.1800", "aliases": "salmora,শালমৰা"},
    # Kullu / Beas basin, Himachal Pradesh
    {"name": "Kullu town", "lat": "31.9579", "lon": "77.1095", "aliases": "kullu,कुल्लू"},
    {"name": "Manali", "lat": "32.2396", "lon": "77.1887", "aliases": "manali,मनाली"},
    {"name": "Beas bridge Kullu", "lat": "31.9600", "lon": "77.1050", "aliases": "beas bridge,ब्यास पुल"},
    {"name": "Bhuntar", "lat": "31.8815", "lon": "77.1582", "aliases": "bhuntar,भुंतर"},
    {"name": "NH-21 Pandoh", "lat": "31.6700", "lon": "77.0600", "aliases": "nh-21,nh21,pandoh,पंडोह"},
    {"name": "NH-715 junction", "lat": "26.9650", "lon": "94.1550", "aliases": "nh-715,nh715"},
    # Brahmaputra basin
    {"name": "Dibrugarh", "lat": "27.4728", "lon": "94.9120", "aliases": "dibrugarh,ডিব্ৰুগড়"},
    {"name": "Tezpur", "lat": "26.6338", "lon": "92.7926", "aliases": "tezpur,তেজপুৰ"},
    {"name": "Guwahati", "lat": "26.1445", "lon": "91.7362", "aliases": "guwahati,গুৱাহাটী"},
]

# Regex patterns for road / landmark mentions
ROAD_PATTERNS = [
    r"\b(NH[-\s]?\d+)\b",         # National Highway
    r"\b(SH[-\s]?\d+)\b",         # State Highway
    r"\b(MDR[-\s]?\d+)\b",        # Major District Road
]

# Default fallback coordinates (centre of Majuli Island)
DEFAULT_LAT = 26.95
DEFAULT_LON = 94.17


def _encode_geohash(lat: float, lon: float, precision: int = 5) -> str:
    """Encode lat/lon to geohash string."""
    if _GEOHASH_AVAILABLE:
        return pgh.encode(lat, lon, precision=precision)
    # Simple fallback: truncated lat/lon string
    return f"{lat:.2f}_{lon:.2f}"


class LocationExtractor:
    """Extracts and geocodes location mentions from flood reports."""

    def __init__(
        self,
        landmark_csv_path: Optional[str] = None,
        geohash_precision: int = 5,
    ):
        self.geohash_precision = geohash_precision
        self._landmarks = self._load_landmarks(landmark_csv_path)
        logger.info("location_extractor_init", landmarks=len(self._landmarks))

    def _load_landmarks(
        self, csv_path: Optional[str]
    ) -> List[Dict[str, str]]:
        """Load landmarks from CSV or use built-in defaults."""
        if csv_path and os.path.exists(csv_path):
            try:
                landmarks = []
                with open(csv_path, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        landmarks.append(row)
                logger.info("landmarks_loaded_from_csv", path=csv_path, n=len(landmarks))
                return landmarks
            except Exception as exc:
                logger.warning("landmark_csv_load_failed", error=str(exc))

        return DEFAULT_LANDMARKS

    def extract(
        self,
        text: str,
        whatsapp_location: Optional[Dict] = None,
        phone_district: Optional[str] = None,
    ) -> LocationResult:
        """Extract location using multiple strategies.

        Priority:
        1. WhatsApp location pin (GPS) — highest confidence
        2. Named landmark / road number in text
        3. Phone number's registered district
        4. Default fallback (Majuli centre)
        """
        # Strategy 1: GPS from WhatsApp location pin
        if whatsapp_location:
            lat = whatsapp_location.get("latitude") or whatsapp_location.get("lat")
            lon = whatsapp_location.get("longitude") or whatsapp_location.get("lon")
            if lat is not None and lon is not None:
                lat, lon = float(lat), float(lon)
                return LocationResult(
                    lat=lat,
                    lon=lon,
                    geohash=_encode_geohash(lat, lon, self.geohash_precision),
                    resolution_method="gps",
                    confidence=0.99,
                )

        # Strategy 2: Landmark / road number in text
        landmark_result = self._match_landmark(text)
        if landmark_result:
            return landmark_result

        # Strategy 3: District from phone number
        if phone_district:
            district_coords = self._district_to_coords(phone_district)
            if district_coords:
                lat, lon = district_coords
                return LocationResult(
                    lat=lat,
                    lon=lon,
                    geohash=_encode_geohash(lat, lon, self.geohash_precision),
                    resolution_method="district",
                    confidence=0.3,
                )

        # Strategy 4: Default fallback
        return LocationResult(
            lat=DEFAULT_LAT,
            lon=DEFAULT_LON,
            geohash=_encode_geohash(DEFAULT_LAT, DEFAULT_LON, self.geohash_precision),
            resolution_method="default",
            confidence=0.1,
        )

    def _match_landmark(self, text: str) -> Optional[LocationResult]:
        """Try to match a landmark or road number in the text."""
        text_lower = text.lower()

        # Check road number patterns first
        for pat in ROAD_PATTERNS:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                road_id = match.group(1).lower().replace(" ", "").replace("-", "")
                for lm in self._landmarks:
                    aliases = lm.get("aliases", "").lower()
                    if road_id in aliases.replace("-", "").replace(" ", ""):
                        lat = float(lm["lat"])
                        lon = float(lm["lon"])
                        return LocationResult(
                            lat=lat,
                            lon=lon,
                            geohash=_encode_geohash(lat, lon, self.geohash_precision),
                            landmark_name=lm["name"],
                            resolution_method="landmark",
                            confidence=0.7,
                        )

        # Fuzzy match landmark names and aliases
        best_match = None
        best_len = 0  # prefer longest match

        for lm in self._landmarks:
            name_lower = lm["name"].lower()
            aliases = lm.get("aliases", "").lower().split(",")
            all_names = [name_lower] + [a.strip() for a in aliases if a.strip()]

            for candidate in all_names:
                if candidate in text_lower and len(candidate) > best_len:
                    best_match = lm
                    best_len = len(candidate)

        if best_match and best_len >= 3:
            lat = float(best_match["lat"])
            lon = float(best_match["lon"])
            return LocationResult(
                lat=lat,
                lon=lon,
                geohash=_encode_geohash(lat, lon, self.geohash_precision),
                landmark_name=best_match["name"],
                resolution_method="landmark",
                confidence=0.6 + min(0.2, best_len * 0.02),
            )

        return None

    def geocode_landmark(self, landmark_name: str) -> Optional[Tuple[float, float]]:
        """Geocode a landmark by name. Returns ``(lat, lon)`` or ``None``."""
        result = self._match_landmark(landmark_name)
        if result and result.lat is not None:
            return (result.lat, result.lon)
        return None

    def _district_to_coords(self, district: str) -> Optional[Tuple[float, float]]:
        """Map a district name to approximate centre coordinates."""
        DISTRICTS = {
            "jorhat": (26.75, 94.22),
            "majuli": (26.95, 94.17),
            "dibrugarh": (27.47, 94.91),
            "tezpur": (26.63, 92.79),
            "guwahati": (26.14, 91.74),
            "kullu": (31.96, 77.11),
            "manali": (32.24, 77.19),
            "mandi": (31.71, 76.93),
        }
        return DISTRICTS.get(district.lower().strip())
