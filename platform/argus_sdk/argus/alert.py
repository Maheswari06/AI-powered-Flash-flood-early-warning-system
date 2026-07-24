"""
ARGUS SDK — Alert Client

Provides programmatic access to the ARGUS Alert Dispatcher API.

Usage:
    from argus import AlertClient

    client = AlertClient("https://argus.my-deployment.org")
    alerts = client.get_active_alerts()
    for alert in alerts:
        print(f"{alert['level']}: {alert['station_name']} — {alert['message']}")
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class AlertClient:
    """
    Client for the ARGUS Alert Dispatcher API.
    Subscribe to alerts, query alert history, and manage alert rules.
    """

    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=30.0,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )

    def get_active_alerts(
        self,
        basin_id: Optional[str] = None,
        level: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get currently active alerts.

        Args:
            basin_id: Optional basin filter
            level: Optional level filter ("WATCH", "WARNING", "CRITICAL")

        Returns:
            List of active alert records
        """
        params = {}
        if basin_id:
            params["basin_id"] = basin_id
        if level:
            params["level"] = level

        r = self._client.get("/api/v1/alerts/active", params=params)
        r.raise_for_status()
        return r.json()

    def get_alert_history(
        self,
        basin_id: str,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Get alert history for a basin.

        Args:
            basin_id: Basin to query
            days: Number of days of history (default: 30)

        Returns:
            List of historical alert records
        """
        r = self._client.get(
            "/api/v1/alerts/history",
            params={"basin_id": basin_id, "days": days},
        )
        r.raise_for_status()
        return r.json()

    def subscribe_webhook(
        self,
        webhook_url: str,
        basin_id: str,
        min_level: str = "WARNING",
    ) -> Dict[str, Any]:
        """
        Register a webhook to receive real-time alert notifications.

        Args:
            webhook_url: URL to POST alerts to
            basin_id: Basin to subscribe to
            min_level: Minimum alert level to trigger ("WATCH", "WARNING", "CRITICAL")

        Returns:
            Subscription confirmation with subscription_id
        """
        r = self._client.post(
            "/api/v1/alerts/subscribe",
            json={
                "webhook_url": webhook_url,
                "basin_id": basin_id,
                "min_level": min_level,
            },
        )
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
