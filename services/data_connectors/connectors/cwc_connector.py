"""CWC (Central Water Commission) WRIS Data Connector.

Connects to India Water Resources Information System (WRIS) API
for real-time and historical gauge readings.

Requires: WRIS_TOKEN environment variable.
Registration: https://indiawris.gov.in
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Fallback Readings ────────────────────────────────────────────────────
# Used when WRIS API is unreachable (network issues, API downtime).
# Values are realistic gauge readings from known stations.

BASIN_FALLBACK_READINGS: Dict[str, List[Dict[str, Any]]] = {
    "brahmaputra_upper": [
        {
            "station_id": "CWC_DIBRUGARH_01",
            "station_name": "Dibrugarh",
            "lat": 27.4728,
            "lon": 94.9120,
            "level_m": 4.8,
            "flow_cumecs": 8500.0,
            "danger_level_m": 7.0,
            "warning_level_m": 6.0,
            "timestamp": "2024-07-15T06:00:00+05:30",
            "quality_flag": "SYNTHETIC",
            "source": "FALLBACK",
        },
        {
            "station_id": "CWC_NEAMATI_01",
            "station_name": "Neamati (Jorhat)",
            "lat": 26.8200,
            "lon": 94.2100,
            "level_m": 5.3,
            "flow_cumecs": 12000.0,
            "danger_level_m": 7.0,
            "warning_level_m": 6.0,
            "timestamp": "2024-07-15T06:00:00+05:30",
            "quality_flag": "SYNTHETIC",
            "source": "FALLBACK",
        },
        {
            "station_id": "CWC_TEZPUR_01",
            "station_name": "Tezpur",
            "lat": 26.6338,
            "lon": 92.7926,
            "level_m": 6.2,
            "flow_cumecs": 15000.0,
            "danger_level_m": 7.0,
            "warning_level_m": 6.0,
            "timestamp": "2024-07-15T06:00:00+05:30",
            "quality_flag": "SYNTHETIC",
            "source": "FALLBACK",
        },
        {
            "station_id": "CWC_GUWAHATI_01",
            "station_name": "Guwahati (Pandu)",
            "lat": 26.1445,
            "lon": 91.6657,
            "level_m": 3.5,
            "flow_cumecs": 7200.0,
            "danger_level_m": 7.0,
            "warning_level_m": 6.0,
            "timestamp": "2024-07-15T06:00:00+05:30",
            "quality_flag": "SYNTHETIC",
            "source": "FALLBACK",
        },
    ],
    "beas_himachal": [
        {
            "station_id": "CWC_KULLU_01",
            "station_name": "Kullu",
            "lat": 31.9579,
            "lon": 77.1095,
            "level_m": 2.1,
            "flow_cumecs": 450.0,
            "danger_level_m": 5.0,
            "warning_level_m": 4.0,
            "timestamp": "2024-07-15T06:00:00+05:30",
            "quality_flag": "SYNTHETIC",
            "source": "FALLBACK",
        },
        {
            "station_id": "CWC_MANALI_01",
            "station_name": "Manali",
            "lat": 32.2432,
            "lon": 77.1892,
            "level_m": 1.2,
            "flow_cumecs": 180.0,
            "danger_level_m": 5.0,
            "warning_level_m": 4.0,
            "timestamp": "2024-07-15T06:00:00+05:30",
            "quality_flag": "SYNTHETIC",
            "source": "FALLBACK",
        },
        {
            "station_id": "CWC_PANDOH_01",
            "station_name": "Pandoh Dam",
            "lat": 31.6689,
            "lon": 77.0561,
            "level_m": 3.8,
            "flow_cumecs": 920.0,
            "danger_level_m": 5.0,
            "warning_level_m": 4.0,
            "timestamp": "2024-07-15T06:00:00+05:30",
            "quality_flag": "SYNTHETIC",
            "source": "FALLBACK",
        },
    ],
}


# ── CWC Connector ────────────────────────────────────────────────────────

class CWCConnector:
    """Central Water Commission WRIS API connector.

    Fetches real-time gauge data from India's WRIS platform.
    Falls back to BASIN_FALLBACK_READINGS when API is unreachable.

    Live switch (Gap 9): Set WRIS_TOKEN env var to enable real CWC data.
    Without a token, connector operates in fallback/demo mode automatically.
    """

    BASE_URL = "https://indiawris.gov.in/api/v1"

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("WRIS_TOKEN", "")
        self.demo_mode = not bool(self.token)
        if self.demo_mode:
            logger.warning(
                "CWC DEMO MODE: WRIS_TOKEN not set — using synthetic gauge readings. "
                "Set WRIS_TOKEN for real CWC WRIS data. "
                "Register at https://indiawris.gov.in to get an API token."
            )
        else:
            logger.info("CWC WRIS LIVE MODE — fetching real river gauge data")

    def fetch_realtime(self, basin_id: str) -> List[Dict[str, Any]]:
        """Fetch real-time gauge readings for a basin.

        Returns list of normalized reading dicts.
        Falls back to BASIN_FALLBACK_READINGS on API failure.
        """
        if not self.token:
            return self._get_fallback(basin_id)

        try:
            import httpx
            resp = httpx.get(
                f"{self.BASE_URL}/stations/realtime",
                params={"basin": basin_id},
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10.0,
            )
            resp.raise_for_status()
            raw = resp.json().get("data", [])
            return [self._normalize(r) for r in raw]
        except Exception as e:
            logger.warning("CWC API failed for %s: %s", basin_id, str(e)[:100])
            return self._get_fallback(basin_id)

    def _get_fallback(self, basin_id: str) -> List[Dict[str, Any]]:
        """Return fallback readings for a basin."""
        readings = BASIN_FALLBACK_READINGS.get(basin_id, [])
        if not readings:
            logger.warning("No fallback readings for basin: %s", basin_id)
        return readings

    def _normalize(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a raw WRIS API response to ARGUS schema."""
        return {
            "station_id": raw.get("station_code", "unknown"),
            "station_name": raw.get("station_name", "unknown"),
            "lat": float(raw.get("latitude", 0)),
            "lon": float(raw.get("longitude", 0)),
            "level_m": float(raw.get("current_level", 0)),
            "flow_cumecs": float(raw.get("discharge_cumecs", 0)),
            "danger_level_m": float(raw.get("danger_level", 0)),
            "warning_level_m": float(raw.get("warning_level", 0)),
            "timestamp": raw.get("observation_time", datetime.utcnow().isoformat()),
            "quality_flag": "LIVE",
            "source": "CWC_WRIS",
        }

    def test_connection(self) -> Dict[str, Any]:
        """Test connectivity to WRIS API."""
        if not self.token:
            return {"status": "no_token", "message": "WRIS_TOKEN not configured — demo mode active"}
        try:
            import httpx
            resp = httpx.get(
                f"{self.BASE_URL}/health",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=5.0,
            )
            return {
                "status": "ok" if resp.status_code == 200 else "error",
                "http_code": resp.status_code,
                "latency_ms": int(resp.elapsed.total_seconds() * 1000),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)[:100]}

    def get_mode(self) -> Dict[str, Any]:
        """Return current CWC connector mode for dashboard transparency."""
        return {
            "mode": "FALLBACK" if self.demo_mode else "LIVE",
            "data_source": "BASIN_FALLBACK_READINGS (synthetic)" if self.demo_mode else "CWC WRIS API",
            "live_switch": "Set WRIS_TOKEN env var to enable real data",
            "token_configured": not self.demo_mode,
        }
