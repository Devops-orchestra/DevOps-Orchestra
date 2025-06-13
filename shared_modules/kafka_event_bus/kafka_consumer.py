"""
kafka_consumer.py

Provides a utility to create a Kafka consumer subscribed to a specific topic
with JSON deserialization.
"""

from kafka import KafkaConsumer
import json
from shared_modules.utils.logger import logger

def create_consumer(topic: str) -> KafkaConsumer:
    """
    Creates a Kafka consumer subscribed to a specified topic with JSON deserialization.

    Args:
        topic (str): The Kafka topic to subscribe to.

    Returns:
        KafkaConsumer: A configured KafkaConsumer instance.
    """
    logger.info(f"[Kafka Consumer] Subscribing to topic '{topic}'")

    return KafkaConsumer(
        topic,
        bootstrap_servers='kafka:9092',
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest',     # Start from beginning if no offset is found
        group_id='devops-orchestra-group',
        enable_auto_commit=True           # Automatically commit offset periodically
    )
