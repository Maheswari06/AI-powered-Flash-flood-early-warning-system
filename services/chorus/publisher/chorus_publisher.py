"""CHORUS Kafka publisher — publishes processed signals for the Causal Engine.

Kafka topic: ``chorus.signal.{geohash_5}``

Each signal is a self-contained evidence node for the causal DAG:
  - Classification + confidence (from IndicBERT)
  - Trust weight (from consensus engine)
  - Geo-coordinates + geohash
  - Anonymized text (no phone number ever transmitted)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)

# Try confluent-kafka
try:
    from confluent_kafka import Producer  # type: ignore[import-untyped]
    _KAFKA_AVAILABLE = True
except ImportError:
    Producer = None
    _KAFKA_AVAILABLE = False
    logger.warning("confluent_kafka_not_available")


class ChorusPublisher:
    """Publishes CHORUS signals to Kafka for consumption by the Causal Engine.

    Falls back to a local in-memory buffer when Kafka is unavailable
    (for hackathon testing without docker infra).
    """

    def __init__(self, bootstrap_servers: str = "localhost:9092"):
        self._producer = None
        self._buffer: list = []

        if _KAFKA_AVAILABLE:
            try:
                self._producer = Producer({
                    "bootstrap.servers": bootstrap_servers,
                    "client.id": "chorus-publisher",
                    "acks": "all",
                })
                logger.info("chorus_kafka_producer_connected", servers=bootstrap_servers)
            except Exception as exc:
                logger.warning("chorus_kafka_connect_failed", error=str(exc))

    def publish(self, signal: Dict[str, Any]) -> None:
        """Publish a CHORUS signal to Kafka.

        Topic is ``chorus.signal.{geohash}`` so the Causal Engine
        can subscribe to geohash-specific partitions.
        """
        geohash = signal.get("geohash", "unknown")
        topic = f"chorus.signal.{geohash}"

        # Add timestamp if not present
        if "timestamp" not in signal:
            signal["timestamp"] = datetime.now(timezone.utc).isoformat()

        payload = json.dumps(signal, default=str).encode("utf-8")

        if self._producer:
            try:
                self._producer.produce(
                    topic=topic,
                    value=payload,
                    key=signal.get("report_id", "").encode("utf-8"),
                    callback=self._delivery_callback,
                )
                self._producer.poll(0)  # trigger callbacks
            except Exception as exc:
                logger.error("chorus_kafka_publish_failed", error=str(exc))
                self._buffer.append(signal)
        else:
            self._buffer.append(signal)

        logger.debug(
            "chorus_signal_published",
            topic=topic,
            report_id=signal.get("report_id"),
            classification=signal.get("classification"),
        )

    def flush(self, timeout: float = 5.0) -> None:
        """Flush pending Kafka messages."""
        if self._producer:
            self._producer.flush(timeout)

    def get_buffer(self) -> list:
        """Return buffered signals (when Kafka is unavailable)."""
        return list(self._buffer)

    def clear_buffer(self) -> None:
        self._buffer.clear()

    @staticmethod
    def _delivery_callback(err, msg):
        if err:
            logger.error("kafka_delivery_failed", error=str(err))
        else:
            logger.debug("kafka_delivered", topic=msg.topic(), partition=msg.partition())
