from kafka import KafkaProducer
import json
from shared.utils.logger import logger

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

def publish_event(topic, data):
    logger.info(f"[Kafka Producer] Publishing to topic '{topic}': {data}")
    producer.send(topic, value=data)
    producer.flush()