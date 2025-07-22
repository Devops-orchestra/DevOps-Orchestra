from langgraph_flows import get_all_flows
from shared_modules.kafka_event_bus.kafka_consumer import create_consumer
from shared_modules.kafka_event_bus.topics import TEST_RESULTS
from shared_modules.utils.logger import logger
from shared_modules.state.devops_state import DevOpsAgentState
import threading

def start_infrastructure_agent(state: DevOpsAgentState):
    logger.info("[Infrastructure Agent] Starting Kafka Listener for TEST_RESULTS")

    flows = get_all_flows()
    graph = flows["infra"]

    def kafka_listener():
        consumer = create_consumer(TEST_RESULTS)
        for msg in consumer:
            event_data = msg.value
            logger.info(f"[Infrastructure Agent] Received TEST_RESULTS event for repo: {event_data.get('repo')}")
            graph.invoke({"event_data": event_data, "state": state})

    thread = threading.Thread(target=kafka_listener, daemon=True)
    thread.start()
