"""Kafka consumer for gauge topics.

Subscribes to ``gauge.realtime.*`` and ``virtual.gauge.*`` topics,
runs each reading through the Kalman filter for quality assurance,
and stores the filtered reading in the in-memory FeatureStore.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import structlog

from shared.config import get_settings
from shared.models.ingestion import GaugeReading
from shared.models.cv_gauging import VirtualGaugeReading
from services.feature_engine.kalman_filter import KalmanFilterBank
from services.feature_engine.store import FeatureStore
from services.feature_engine.schemas import KalmanOutput

logger = structlog.get_logger(__name__)
settings = get_settings()


class GaugeConsumer:
    """Consumes gauge and virtual-gauge messages from Kafka.

    Each real gauge reading is passed through the Kalman filter
    before being stored. Virtual gauge (CV) readings are stored
    directly.
    """

    def __init__(
        self,
        store: FeatureStore,
        kalman_bank: KalmanFilterBank,
    ) -> None:
        self._store = store
        self._kalman = kalman_bank
        self._running = False

    async def start(self) -> None:
        """Start the blocking Kafka consume loop in a thread."""
        self._running = True
        logger.info("gauge_consumer_starting")
        try:
            await asyncio.get_event_loop().run_in_executor(None, self._consume_loop)
        except asyncio.CancelledError:
            self._running = False
            logger.info("gauge_consumer_cancelled")

    def stop(self) -> None:
        """Signal the consume loop to stop."""
        self._running = False

    def _consume_loop(self) -> None:
        """Blocking Kafka consume loop (runs in a thread)."""
        try:
            from confluent_kafka import Consumer
        except ImportError:
            logger.warning("confluent_kafka_not_installed_gauge_consumer_demo_mode")
            return

        consumer = Consumer({
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": f"{settings.KAFKA_GROUP_PREFIX}.feature-engine.gauge",
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
        })
        consumer.subscribe([
            "gauge.realtime",
            "virtual.gauge",
        ])
        logger.info("gauge_consumer_subscribed", topics=["gauge.realtime", "virtual.gauge"])

        try:
            while self._running:
                msg = consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    logger.error("gauge_kafka_error", error=str(msg.error()))
                    continue

                topic = msg.topic()
                try:
                    payload = json.loads(msg.value().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    logger.error("gauge_bad_message", topic=topic)
                    continue

                self._handle_message(topic, payload)
        finally:
            consumer.close()
            logger.info("gauge_consumer_closed")

    def _handle_message(self, topic: str, payload: dict) -> None:
        """Route a decoded message to the appropriate handler."""
        if topic.startswith("gauge.realtime"):
            self._handle_gauge(payload)
        elif topic.startswith("virtual.gauge"):
            self._handle_virtual_gauge(payload)
        else:
            logger.warning("gauge_consumer_unknown_topic", topic=topic)

    def _handle_gauge(self, payload: dict) -> None:
        """Process a real gauge reading through the Kalman filter."""
        try:
            reading = GaugeReading(**payload)
        except Exception as exc:
            logger.error("gauge_parse_error", error=str(exc))
            return

        # Run through Kalman filter for quality assurance
        kf_output: KalmanOutput = self._kalman.update(
            station_id=reading.station_id,
            timestamp=reading.timestamp,
            raw_level=reading.level_m,
        )

        # Update the reading with filtered value if anomaly detected
        if kf_output.quality_flag.value == "KALMAN_IMPUTED":
            reading = GaugeReading(
                station_id=reading.station_id,
                timestamp=reading.timestamp,
                level_m=kf_output.filtered_value,
                flow_cumecs=reading.flow_cumecs,
                quality_flag="ESTIMATED",
            )
            logger.info(
                "gauge_kalman_imputed",
                station=reading.station_id,
                raw=kf_output.raw_value,
                filtered=kf_output.filtered_value,
            )

        self._store.add_gauge(reading)
        logger.debug(
            "gauge_reading_stored",
            station=reading.station_id,
            level=reading.level_m,
            quality=kf_output.quality_flag.value,
        )

    def _handle_virtual_gauge(self, payload: dict) -> None:
        """Process a CV virtual gauge reading (no Kalman filter applied)."""
        try:
            reading = VirtualGaugeReading(**payload)
            self._store.add_cv(reading)
            logger.debug(
                "cv_reading_stored",
                camera=reading.camera_id,
                depth=reading.depth_m,
            )
        except Exception as exc:
            logger.error("cv_parse_error", error=str(exc))

    @property
    def kalman_bank(self) -> KalmanFilterBank:
        """Expose the Kalman filter bank for monitoring endpoints."""
        return self._kalman
