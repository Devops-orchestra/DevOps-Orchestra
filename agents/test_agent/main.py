from langgraph_flows import get_all_flows
from shared_modules.kafka_event_bus.kafka_consumer import create_consumer
from shared_modules.kafka_event_bus.topics import BUILD_READY
from shared_modules.utils.logger import logger
from shared_modules.state.devops_state import DevOpsAgentState
import threading

def start_test_agent(state: DevOpsAgentState):
    logger.info("[Test Agent] Starting Kafka Listener for BUILD_READY")

    flows = get_all_flows()
    graph = flows["test"]

    def kafka_listener():
        consumer = create_consumer(BUILD_READY)
        for msg in consumer:
            event_data = msg.value
            logger.info(f"[Test Agent] Received BUILD_READY event for repo: {event_data['repo']}")
            graph.invoke({"event_data": event_data, "state": state})

    thread = threading.Thread(target=kafka_listener, daemon=True)
    thread.start()
