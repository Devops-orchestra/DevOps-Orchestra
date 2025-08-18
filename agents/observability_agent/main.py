from langgraph_flows import get_all_flows
from shared_modules.kafka_event_bus.kafka_consumer import create_consumer
from shared_modules.kafka_event_bus.topics import OBSERVABILITY_ALERT
from shared_modules.utils.logger import logger
from shared_modules.state.devops_state import DevOpsAgentState
import threading


def start_observability_agent(state: DevOpsAgentState):
    logger.info("[Observability Agent] Starting Kafka Listener for OBSERVABILITY_ALERT")

    flows = get_all_flows()
    graph = flows["observability"]

    def kafka_listener():
        consumer = create_consumer(OBSERVABILITY_ALERT)
        for msg in consumer:
            event_data = msg.value
            logger.info(f"[Observability Agent] Received OBSERVABILITY_ALERT for repo: {event_data.get('repo')}")
            graph.invoke({"event_data": event_data, "state": state})

    thread = threading.Thread(target=kafka_listener, daemon=True)
    thread.start()


