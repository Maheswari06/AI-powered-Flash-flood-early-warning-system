"""Kafka publisher for computed feature vectors.

Publishes FeatureVector JSON to ``features.vector.{station_id}``
so the Prediction service can consume it.
"""

from __future__ import annotations

import structlog

from shared.config import get_settings
from shared.models.feature_engine import FeatureVector

logger = structlog.get_logger(__name__)
settings = get_settings()


class FeaturePublisher:
    """Publishes feature vectors to Kafka."""

    def __init__(self) -> None:
        self._producer = None

    def _ensure_producer(self) -> None:
        """Lazy-initialise the Kafka producer."""
        if self._producer is not None:
            return
        try:
            from shared.kafka_client import KafkaProducerClient
            self._producer = KafkaProducerClient(client_id="feature-engine-publisher")
        except Exception as exc:
            logger.warning("kafka_producer_unavailable", error=str(exc))

    def publish(self, fv: FeatureVector) -> None:
        """Publish a feature vector to Kafka topic ``features.vector.{station_id}``."""
        self._ensure_producer()
        if self._producer is None:
            logger.debug("skip_publish_no_kafka", station=fv.station_id)
            return

        topic = f"features.vector.{fv.station_id}"
        self._producer.produce(
            topic=topic,
            key=fv.station_id,
            value=fv.model_dump(mode="json"),
        )
        logger.info("feature_published", topic=topic, station=fv.station_id)

    def flush(self) -> None:
        """Flush pending messages."""
        if self._producer:
            self._producer.flush()
