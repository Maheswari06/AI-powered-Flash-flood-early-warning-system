"""Prediction publisher — writes to Kafka and Redis.

Publishes prediction results to two destinations:

1. Kafka topic ``predictions.fast.{village_id}``
   — consumed by the Alert Dispatcher service.

2. Redis key ``prediction:{village_id}``
   — low-latency cache for dashboard API reads.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)


class PredictionPublisher:
    """Dual-destination publisher: Kafka + Redis.

    Usage::

        pub = PredictionPublisher()
        pub.publish(village_id, prediction_dict)
    """

    def __init__(self) -> None:
        self._kafka_producer = None
        self._redis_client = None
        self._redis_ttl = int(os.getenv("PREDICTION_REDIS_TTL", "300"))

    # ── lazy init ─────────────────────────────────────────────────────

    def _ensure_kafka(self) -> None:
        """Lazy-init Kafka producer."""
        if self._kafka_producer is not None:
            return
        try:
            from shared.kafka_client import KafkaProducerClient
            self._kafka_producer = KafkaProducerClient(client_id="prediction-publisher")
            logger.info("prediction_kafka_producer_ready")
        except Exception as exc:
            logger.warning("prediction_kafka_unavailable", error=str(exc))

    def _ensure_redis(self) -> None:
        """Lazy-init Redis client."""
        if self._redis_client is not None:
            return
        try:
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            self._redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
            # Test connection
            self._redis_client.ping()
            logger.info("prediction_redis_ready", url=redis_url.split("@")[-1])
        except ImportError:
            logger.warning("redis_not_installed_publisher_kafka_only")
        except Exception as exc:
            logger.warning("redis_unavailable", error=str(exc))
            self._redis_client = None

    # ── publish ───────────────────────────────────────────────────────

    def publish(self, village_id: str, prediction: Dict[str, Any]) -> None:
        """Publish a prediction to Kafka and Redis.

        Args:
            village_id:  Target village identifier.
            prediction:  Serialisable prediction dict.
        """
        self._publish_kafka(village_id, prediction)
        self._publish_redis(village_id, prediction)

    def _publish_kafka(self, village_id: str, prediction: Dict[str, Any]) -> None:
        """Publish to Kafka topic ``predictions.fast.{village_id}``."""
        self._ensure_kafka()
        if self._kafka_producer is None:
            return
        try:
            topic = f"predictions.fast.{village_id}"
            self._kafka_producer.produce(
                topic=topic,
                key=village_id,
                value=prediction,
            )
            logger.debug("prediction_published_kafka", topic=topic, village=village_id)
        except Exception as exc:
            logger.error("prediction_kafka_publish_error", error=str(exc))

    def _publish_redis(self, village_id: str, prediction: Dict[str, Any]) -> None:
        """Cache prediction in Redis with TTL."""
        self._ensure_redis()
        if self._redis_client is None:
            return
        try:
            key = f"prediction:{village_id}"
            self._redis_client.setex(
                key,
                self._redis_ttl,
                json.dumps(prediction, default=str),
            )
            logger.debug("prediction_published_redis", key=key, village=village_id)
        except Exception as exc:
            logger.error("prediction_redis_publish_error", error=str(exc))

    def publish_all(self, predictions: Dict[str, Dict[str, Any]]) -> None:
        """Batch publish predictions for multiple villages.

        Args:
            predictions: {village_id: prediction_dict}
        """
        for vid, pred in predictions.items():
            self.publish(vid, pred)

    def flush(self) -> None:
        """Flush Kafka producer buffers."""
        if self._kafka_producer:
            self._kafka_producer.flush()
