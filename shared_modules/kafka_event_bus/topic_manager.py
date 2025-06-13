"""
kafka_topic_setup.py

Creates required Kafka topics for the DevOps orchestration pipeline using KafkaAdminClient.

Topics are only created if they do not already exist.
"""

from kafka.admin import KafkaAdminClient, NewTopic
from shared_modules.kafka_event_bus import topics
from shared_modules.utils.logger import logger
from kafka.errors import NoBrokersAvailable, NodeNotReadyError
import time

KAFKA_BOOTSTRAP_SERVERS = 'kafka:9092'

def create_topics():
    """
    Creates required Kafka topics if they do not already exist.
    """
    admin_client = None

    for attempt in range(10):
        try:
            logger.info(f"[Kafka Admin] Attempt {attempt + 1} to connect to Kafka...")
            admin_client = KafkaAdminClient(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                client_id='devops-orchestra-admin'
            )
            existing = admin_client.list_topics()  # This can raise NodeNotReadyError

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

            topics_to_create = [t for t in new_topics if t.name not in existing]

            if topics_to_create:
                admin_client.create_topics(new_topics=topics_to_create)
                logger.info(f"[Kafka Admin] Created Kafka topics: {[t.name for t in topics_to_create]}")
            else:
                logger.info("[Kafka Admin] All required Kafka topics already exist.")

            admin_client.close()
            break  # success
        except (NoBrokersAvailable, NodeNotReadyError) as e:
            logger.warning(f"[Kafka Admin] Kafka not ready yet ({e}). Retrying in 3 seconds...")
            time.sleep(3)
        except Exception as e:
            logger.error(f"[Kafka Admin] Unexpected error: {e}")
            break