from kafka import KafkaConsumer
import json

def create_consumer(topic):
    return KafkaConsumer(
        topic,
        bootstrap_servers='localhost:9092',
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest',
        group_id='devops-orchestra-group',
        enable_auto_commit=True
    )
