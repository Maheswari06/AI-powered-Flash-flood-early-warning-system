"""Alert publisher — sends AlertPayload to Kafka for the Alert Dispatcher.

Publishes to ``alerts.dispatch`` topic with a cooldown to
prevent duplicate alerts for the same station.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

import structlog

from shared.config import get_settings
from shared.models.prediction import AlertPayload

logger = structlog.get_logger(__name__)
settings = get_settings()


class AlertPublisher:
    """Publishes alerts to Kafka with per-station cooldown."""

    def __init__(self) -> None:
        self._producer = None
        self._last_alert: Dict[str, datetime] = {}

    def _ensure_producer(self) -> None:
        """Lazy-init the Kafka producer."""
        if self._producer is not None:
            return
        try:
            from shared.kafka_client import KafkaProducerClient
            self._producer = KafkaProducerClient(client_id="prediction-alert-publisher")
        except Exception as exc:
            logger.warning("kafka_alert_producer_unavailable", error=str(exc))

    def _should_send(self, station_id: str) -> bool:
        """Check cooldown — don't spam alerts for the same station."""
        now = datetime.now(timezone.utc)
        last = self._last_alert.get(station_id)
        if last is None:
            return True
        elapsed = (now - last).total_seconds()
        return elapsed >= settings.ALERT_COOLDOWN_S

    def publish(self, alert: AlertPayload) -> None:
        """Publish an alert to Kafka if cooldown has elapsed."""
        if not self._should_send(alert.station_id):
            logger.info(
                "alert_suppressed_cooldown",
                station=alert.station_id,
                cooldown_s=settings.ALERT_COOLDOWN_S,
            )
            return

        self._ensure_producer()
        if self._producer is None:
            logger.warning("alert_not_published_no_kafka", alert_id=alert.alert_id)
            return

        self._producer.produce(
            topic=settings.ALERT_KAFKA_TOPIC,
            key=alert.station_id,
            value=alert.model_dump(mode="json"),
        )
        self._last_alert[alert.station_id] = datetime.now(timezone.utc)
        logger.info("alert_published", alert_id=alert.alert_id, station=alert.station_id)

    def flush(self) -> None:
        """Flush buffered messages."""
        if self._producer:
            self._producer.flush()
