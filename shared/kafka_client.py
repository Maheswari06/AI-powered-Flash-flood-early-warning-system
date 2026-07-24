"""Reusable Kafka producer / consumer helpers for all ARGUS services.

Wraps ``confluent-kafka`` so individual services don't need to
duplicate connection logic.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, Optional

import structlog

from shared.config import get_settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Producer
# ---------------------------------------------------------------------------


class KafkaProducerClient:
    """Thin wrapper around confluent_kafka.Producer with JSON serialisation."""

    def __init__(self, client_id: str = "argus-producer") -> None:
        from confluent_kafka import Producer  # lazy import

        settings = get_settings()
        self._producer = Producer(
            {
                "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "client.id": client_id,
                "acks": "all",
                "retries": 5,
                "linger.ms": 10,
            }
        )
        logger.info("kafka_producer_init", bootstrap=settings.KAFKA_BOOTSTRAP_SERVERS)

    # ── delivery callback ────────────────────────────────────
    @staticmethod
    def _delivery_report(err: Any, msg: Any) -> None:
        """Called once per produced message to indicate delivery result."""
        if err is not None:
            logger.error("kafka_delivery_failed", error=str(err))
        else:
            logger.debug(
                "kafka_delivered",
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset(),
            )

    # ── public API ───────────────────────────────────────────
    def produce(self, topic: str, value: Dict[str, Any], key: Optional[str] = None) -> None:
        """Serialise *value* as JSON and produce to *topic*."""
        self._producer.produce(
            topic=topic,
            key=key.encode("utf-8") if key else None,
            value=json.dumps(value, default=str).encode("utf-8"),
            callback=self._delivery_report,
        )
        self._producer.poll(0)

    def flush(self, timeout: float = 5.0) -> None:
        """Block until all buffered messages are delivered."""
        self._producer.flush(timeout)


# ---------------------------------------------------------------------------
# Consumer
# ---------------------------------------------------------------------------


class KafkaConsumerClient:
    """Thin wrapper around confluent_kafka.Consumer with JSON deserialisation."""

    def __init__(
        self,
        group_id: str,
        topics: list[str],
        auto_offset_reset: str = "latest",
    ) -> None:
        from confluent_kafka import Consumer  # lazy import

        settings = get_settings()
        self._consumer = Consumer(
            {
                "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "group.id": f"{settings.KAFKA_GROUP_PREFIX}.{group_id}",
                "auto.offset.reset": auto_offset_reset,
                "enable.auto.commit": True,
            }
        )
        self._consumer.subscribe(topics)
        logger.info(
            "kafka_consumer_init",
            group=group_id,
            topics=topics,
            bootstrap=settings.KAFKA_BOOTSTRAP_SERVERS,
        )

    def consume_loop(
        self,
        handler: Callable[[str, Dict[str, Any]], None],
        poll_timeout: float = 1.0,
    ) -> None:
        """Blocking consume loop — calls *handler(topic, payload)* for each message."""
        try:
            while True:
                msg = self._consumer.poll(poll_timeout)
                if msg is None:
                    continue
                if msg.error():
                    logger.error("kafka_consume_error", error=str(msg.error()))
                    continue
                try:
                    payload = json.loads(msg.value().decode("utf-8"))
                    handler(msg.topic(), payload)
                except json.JSONDecodeError:
                    logger.error("kafka_json_decode_error", raw=msg.value())
        except KeyboardInterrupt:
            logger.info("kafka_consumer_shutdown")
        finally:
            self._consumer.close()

    def close(self) -> None:
        """Cleanly close the consumer."""
        self._consumer.close()
