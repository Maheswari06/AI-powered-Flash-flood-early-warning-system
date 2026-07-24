"""Kafka consumer for weather topics.

Subscribes to ``weather.api.*`` topics and stores weather
observations in the in-memory FeatureStore.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import structlog

from shared.config import get_settings
from shared.models.ingestion import WeatherData
from services.feature_engine.store import FeatureStore

logger = structlog.get_logger(__name__)
settings = get_settings()


class WeatherConsumer:
    """Consumes weather observations from Kafka.

    Weather data is stored keyed by grid cell (lat/lon) in the
    FeatureStore for spatial feature computation.
    """

    def __init__(self, store: FeatureStore) -> None:
        self._store = store
        self._running = False

    async def start(self) -> None:
        """Start the blocking Kafka consume loop in a thread."""
        self._running = True
        logger.info("weather_consumer_starting")
        try:
            await asyncio.get_event_loop().run_in_executor(None, self._consume_loop)
        except asyncio.CancelledError:
            self._running = False
            logger.info("weather_consumer_cancelled")

    def stop(self) -> None:
        """Signal the consume loop to stop."""
        self._running = False

    def _consume_loop(self) -> None:
        """Blocking Kafka consume loop (runs in a thread)."""
        try:
            from confluent_kafka import Consumer
        except ImportError:
            logger.warning("confluent_kafka_not_installed_weather_consumer_demo_mode")
            return

        consumer = Consumer({
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": f"{settings.KAFKA_GROUP_PREFIX}.feature-engine.weather",
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
        })
        consumer.subscribe(["weather.api.imd"])
        logger.info("weather_consumer_subscribed", topics=["weather.api.imd"])

        try:
            while self._running:
                msg = consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    logger.error("weather_kafka_error", error=str(msg.error()))
                    continue

                try:
                    payload = json.loads(msg.value().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    logger.error("weather_bad_message")
                    continue

                self._handle_weather(payload)
        finally:
            consumer.close()
            logger.info("weather_consumer_closed")

    def _handle_weather(self, payload: dict) -> None:
        """Parse and store a weather observation."""
        try:
            reading = WeatherData(**payload)
            self._store.add_weather(reading)
            logger.debug(
                "weather_reading_stored",
                lat=reading.lat,
                lon=reading.lon,
                rainfall=reading.rainfall_mm_hr,
            )
        except Exception as exc:
            logger.error("weather_parse_error", error=str(exc))
