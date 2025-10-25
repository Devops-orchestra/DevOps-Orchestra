from shared_modules.kafka_event_bus.kafka_consumer import create_consumer
from shared_modules.kafka_event_bus.topics import ROLLBACK_EVENT
from shared_modules.utils.logger import logger
from shared_modules.state.devops_state import DevOpsAgentState
from agents.rollback_agent.tools.terraform_rollback import rollback_and_publish
import threading


def start_rollback_agent(state: DevOpsAgentState):
    logger.info("[Rollback Agent] Starting Kafka Listener for ROLLBACK_EVENT")

    def kafka_listener():
        consumer = create_consumer(ROLLBACK_EVENT)
        for msg in consumer:
            event_data = msg.value
            logger.info(f"[Rollback Agent] Received ROLLBACK_EVENT for repo: {event_data.get('repo')}")
            rollback_and_publish(event_data, state)

    thread = threading.Thread(target=kafka_listener, daemon=True)
    thread.start()
