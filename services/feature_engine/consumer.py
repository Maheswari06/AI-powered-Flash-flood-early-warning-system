"""Kafka consumers for the Feature Engine.

Subscribes to ingestion topics and feeds raw readings into the FeatureStore.
Periodically triggers feature computation for all known stations.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import structlog

from shared.config import get_settings
from shared.models.ingestion import GaugeReading, WeatherData
from shared.models.cv_gauging import VirtualGaugeReading

from services.feature_engine.store import FeatureStore
from services.feature_engine.temporal import compute_temporal_features
from services.feature_engine.spatial import compute_spatial_features
from services.feature_engine.builder import build_feature_vector
from services.feature_engine.publisher import FeaturePublisher

logger = structlog.get_logger(__name__)
settings = get_settings()

# Topics to consume
GAUGE_TOPIC = "gauge.realtime.*"
WEATHER_TOPIC = "weather.api.imd"
CV_TOPIC = "virtual.gauge.*"

# Feature recomputation interval (seconds)
RECOMPUTE_INTERVAL_S = 60


async def _consume_kafka(store: FeatureStore) -> None:
    """Run blocking Kafka consumer in a thread (non-async confluent-kafka)."""
    try:
        from confluent_kafka import Consumer

        consumer = Consumer(
            {
                "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
                "group.id": f"{settings.KAFKA_GROUP_PREFIX}.feature-engine",
                "auto.offset.reset": "latest",
                "enable.auto.commit": True,
            }
        )
        consumer.subscribe([
            "gauge.realtime",
            "weather.api.imd",
            "virtual.gauge",
        ])
        logger.info("feature_engine_consumer_started")

        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                await asyncio.sleep(0.01)
                continue
            if msg.error():
                logger.error("kafka_error", error=str(msg.error()))
                continue

            topic = msg.topic()
            try:
                payload = json.loads(msg.value().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.error("bad_message", topic=topic)
                continue

            if topic.startswith("gauge.realtime"):
                store.add_gauge(GaugeReading(**payload))
            elif topic.startswith("weather.api"):
                store.add_weather(WeatherData(**payload))
            elif topic.startswith("virtual.gauge"):
                store.add_cv(VirtualGaugeReading(**payload))

    except ImportError:
        logger.warning("confluent_kafka_not_installed_running_demo_mode")
    except Exception as exc:
        logger.exception("consumer_crash", error=str(exc))


async def _recompute_loop(store: FeatureStore, publisher: FeaturePublisher) -> None:
    """Periodically recompute feature vectors for all stations."""
    while True:
        await asyncio.sleep(RECOMPUTE_INTERVAL_S)
        now = datetime.now(timezone.utc)
        station_ids = store.get_all_station_ids()
        logger.info("recompute_features", num_stations=len(station_ids))

        for sid in station_ids:
            try:
                # Gather raw buffers
                gauge_readings = store.get_gauge_readings(sid)
                node = store.topology.get(sid, {})
                lat = node.get("lat", 0.0) if isinstance(node, dict) else 0.0
                lon = node.get("lon", 0.0) if isinstance(node, dict) else 0.0
                weather_readings = store.get_weather_near(lat, lon)
                cv_readings = store.get_cv_readings(sid)  # camera mapped to station

                # Compute temporal
                temporal = compute_temporal_features(
                    station_id=sid,
                    now=now,
                    gauge_readings=gauge_readings,
                    weather_readings=weather_readings,
                    cv_readings=cv_readings,
                )

                # Compute spatial
                spatial = compute_spatial_features(
                    station_id=sid,
                    now=now,
                    topology=store.topology,
                    gauge_buffers={k: list(v) for k, v in store.gauge_buffer.items()},
                    weather_buffers={k: list(v) for k, v in store.weather_buffer.items()},
                )

                # Latest CV reading
                latest_cv = cv_readings[-1] if cv_readings else None

                # Build full vector
                fv = build_feature_vector(sid, now, temporal, spatial, latest_cv)
                store.set_latest(sid, fv)

                # Publish to Kafka
                publisher.publish(fv)

            except Exception as exc:
                logger.exception("feature_compute_error", station=sid, error=str(exc))


async def start_consumers(store: FeatureStore, publisher: FeaturePublisher) -> None:
    """Launch Kafka consumer + periodic recomputation as concurrent tasks."""
    await asyncio.gather(
        _consume_kafka(store),
        _recompute_loop(store, publisher),
    )
