"""
kafka_producer.py

Kafka producer utility for publishing events to Kafka topics using JSON serialization.
Producer is created lazily on first use. If Kafka is unavailable, publish_event no-ops
so the coordinator pipeline can run without Kafka.
"""
import json
import os
import time
import atexit
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

from shared_modules.utils.logger import logger

# Lazy producer: None until first successful create_producer(); stays None if Kafka disabled/unavailable
producer = None

def _bootstrap_servers():
    return (os.getenv("KAFKA_BOOTSTRAP_SERVERS") or "kafka:9092").strip()


def create_producer():
    """Create Kafka producer; returns None if Kafka disabled or unavailable (no exception)."""
    global producer
    if producer is not None:
        return producer
    servers = _bootstrap_servers()
    if not servers or servers.lower() in ("", "disabled", "none"):
        logger.info("[Kafka Producer] Kafka disabled (KAFKA_BOOTSTRAP_SERVERS empty or 'disabled')")
        return None
    for attempt in range(3):  # Fewer retries so coordinator path doesn't block long
        try:
            logger.info(f"[Kafka Producer] Attempt {attempt + 1} to connect to Kafka...")
            p = KafkaProducer(
                bootstrap_servers=servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=3,
            )
            producer = p
            return producer
        except NoBrokersAvailable:
            logger.warning("Kafka not available. Retrying in 2 seconds...")
            time.sleep(2)
    logger.warning("[Kafka Producer] Kafka unavailable after retries; events will not be published.")
    return None


def publish_event(topic: str, data: dict):
    """
    Publishes a JSON-serializable event to the specified Kafka topic.
    If Kafka is disabled or unavailable, logs at debug and returns without error.
    """
    global producer
    if producer is None:
        producer = create_producer()
    if producer is None:
        logger.debug(f"[Kafka Producer] Skipping publish to '{topic}' (Kafka unavailable)")
        return
    try:
        logger.info(f"[Kafka Producer] Publishing to topic '{topic}': {data}")
        future = producer.send(topic, value=data)
        record_metadata = future.get(timeout=10)
        logger.info(
            f"[Kafka Producer] Message delivered to {record_metadata.topic}:"
            f"{record_metadata.partition}@{record_metadata.offset}"
        )
    except Exception as e:
        logger.error(f"[Kafka Producer] Failed to publish to topic '{topic}': {e}")


def _close_producer():
    global producer
    if producer is not None:
        try:
            producer.close()
        except Exception:
            pass


atexit.register(_close_producer)
