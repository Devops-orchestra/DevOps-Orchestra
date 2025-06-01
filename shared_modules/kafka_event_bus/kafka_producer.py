from kafka import KafkaProducer
import json

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

def publish_event(topic, data):
    print(f"[Kafka] Publishing to {topic}: {data}")
    producer.send(topic, value=data)
    producer.flush()
