from langgraph_flows import get_all_flows
from shared_modules.kafka_event_bus.kafka_consumer import create_consumer
from shared_modules.kafka_event_bus.topics import DEPLOYMENT_TRIGGERED
from shared_modules.utils.logger import logger
from shared_modules.state.devops_state import DevOpsAgentState
import threading


def start_observability_agent(state: DevOpsAgentState):
    logger.info("[Observability Agent] Starting Kafka Listener for DEPLOYMENT_TRIGGERED")

    flows = get_all_flows()
    graph = flows["observability"]

    def kafka_listener():
        consumer = create_consumer(DEPLOYMENT_TRIGGERED)
        for msg in consumer:
            event_data = msg.value
            logger.info(f"[Observability Agent] Received DEPLOYMENT_TRIGGERED event for repo: {event_data.get('repo')}")
            graph.invoke({"event_data": event_data, "state": state})

    thread = threading.Thread(target=kafka_listener, daemon=True)
    thread.start()
