"""
ARGUS SDK — Prediction Client

Provides programmatic access to ARGUS flood prediction API.

Usage:
    from argus import PredictionClient

    client = PredictionClient("https://argus.my-deployment.org")
    prediction = client.get_latest("station_001")
    print(f"Flood probability: {prediction['probability']}")
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class PredictionClient:
    """
    Client for the ARGUS Prediction API.
    Wraps the REST API with typed methods and error handling.
    """

    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=30.0,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )

    def get_latest(self, station_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get the latest flood prediction.

        Args:
            station_id: Optional station filter. If None, returns all stations.

        Returns:
            Dict with prediction data including probability, lead_time_minutes,
            risk_level, shap_explanations, etc.
        """
        params = {}
        if station_id:
            params["station"] = station_id

        r = self._client.get("/api/v1/prediction/latest", params=params)
        r.raise_for_status()
        return r.json()

    def get_history(
        self,
        station_id: str,
        hours: int = 24,
    ) -> List[Dict[str, Any]]:
        """
        Get prediction history for a station.

        Args:
            station_id: Station to query
            hours: Number of hours of history (default: 24)

        Returns:
            List of prediction records
        """
        r = self._client.get(
            "/api/v1/prediction/history",
            params={"station": station_id, "hours": hours},
        )
        r.raise_for_status()
        return r.json()

    def get_risk_map(
        self,
        bbox: Optional[tuple] = None,
    ) -> Dict[str, Any]:
        """
        Get spatial risk map (GeoJSON FeatureCollection).

        Args:
            bbox: Optional bounding box (west, south, east, north)

        Returns:
            GeoJSON FeatureCollection with risk-scored features
        """
        params = {}
        if bbox:
            params["bbox"] = ",".join(str(x) for x in bbox)

        r = self._client.get("/api/v1/prediction/risk_map", params=params)
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
