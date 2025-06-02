from kafka.admin import KafkaAdminClient, NewTopic
from shared.event_bus import topics
from shared.utils.logger import logger

KAFKA_BOOTSTRAP_SERVERS = 'localhost:9092'

def create_topics():
    admin_client = KafkaAdminClient(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        client_id='devops-orchestra-admin'
    )

    topic_list = [
        topics.CODE_PUSH,
        topics.CODE_ANALYSIS,
        topics.TEST_RESULTS,
        topics.BUILD_READY,
        topics.IAC_READY,
        topics.DEPLOYMENT_TRIGGERED,
        topics.OBSERVABILITY_ALERT,
        topics.ROLLBACK_EVENT
    ]

    new_topics = [
        NewTopic(name=topic, num_partitions=1, replication_factor=1)
        for topic in topic_list
    ]

    try:
        existing = admin_client.list_topics()
        topics_to_create = [t for t in new_topics if t.name not in existing]
        if topics_to_create:
            admin_client.create_topics(new_topics=topics_to_create)
            logger.info(f"Created Kafka topics: {[t.name for t in topics_to_create]}")
        else:
            logger.info("All Kafka topics already exist.")
    except Exception as e:
        logger.error(f"Error creating Kafka topics: {e}")
