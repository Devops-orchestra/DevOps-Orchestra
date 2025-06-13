"""
kafka_producer.py

Kafka producer utility for publishing events to Kafka topics using JSON serialization.
"""
from kafka import KafkaProducer
import json
from shared_modules.utils.logger import logger
import atexit
from kafka.errors import NoBrokersAvailable
import time

def create_producer():
    for attempt in range(10):  # Try up to 10 times
        try:
            logger.info(f"[Kafka Producer] Attempt {attempt+1} to connect to Kafka...")
            return KafkaProducer(
                bootstrap_servers='kafka:9092',
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',
                retries=3
            )
        except NoBrokersAvailable:
            logger.warning("Kafka not available yet. Retrying in 3 seconds...")
            time.sleep(3)
    raise Exception("Kafka not available after multiple retries.")

producer = create_producer()

def publish_event(topic: str, data: dict):
    """
    Publishes a JSON-serializable event to the specified Kafka topic.

    Args:
        topic (str): The Kafka topic to publish to.
        data (dict): The event payload to send.

    Raises:
        Exception: Logs any exception that occurs during send.
    """
    try:
        logger.info(f"[Kafka Producer] Publishing to topic '{topic}': {data}")
        future = producer.send(topic, value=data)
        record_metadata = future.get(timeout=10)  # Block until message is acknowledged
        logger.info(
            f"[Kafka Producer] Message delivered to {record_metadata.topic}:"
            f"{record_metadata.partition}@{record_metadata.offset}"
        )
    except Exception as e:
        logger.error(f"[Kafka Producer] Failed to publish to topic '{topic}': {e}")

# Ensure producer is closed gracefully on shutdown
atexit.register(producer.close)
