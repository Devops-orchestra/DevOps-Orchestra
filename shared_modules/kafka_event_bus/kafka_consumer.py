from kafka import KafkaConsumer
import json
from shared.utils.logger import logger

def create_consumer(topic):
    logger.info(f"[Kafka Consumer] Subscribed to topic '{topic}'")
    return KafkaConsumer(
        topic,
        bootstrap_servers='localhost:9092',
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest',
        group_id='devops-orchestra-group',
        enable_auto_commit=True
    )
