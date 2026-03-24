"""
kafka_consumer.py

Provides a utility to create a Kafka consumer subscribed to a specific topic
with JSON deserialization. Consumers created via create_consumer are closed
gracefully on process exit (similar to kafka_producer).
"""

import atexit
import json
from kafka import KafkaConsumer

from shared_modules.utils.logger import logger

# Track consumers so we can close them on exit
_consumers = set()


def create_consumer(topic: str) -> KafkaConsumer:
    """
    Creates a Kafka consumer subscribed to a specified topic with JSON deserialization.
    The consumer is registered for graceful close on process exit.

    Args:
        topic (str): The Kafka topic to subscribe to.

    Returns:
        KafkaConsumer: A configured KafkaConsumer instance.
    """
    logger.info(f"[Kafka Consumer] Subscribing to topic '{topic}'")

    consumer = KafkaConsumer(
        topic,
        bootstrap_servers='kafka:9092',
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest',
        group_id='devops-orchestra-group',
        enable_auto_commit=True,
    )
    _consumers.add(consumer)
    return consumer


def _close_consumers():
    """Close all consumers created via create_consumer."""
    global _consumers
    for consumer in _consumers:
        try:
            consumer.close()
        except Exception:
            pass
    _consumers.clear()

atexit.register(_close_consumers)