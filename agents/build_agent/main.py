from langgraph_flows import get_all_flows
from shared_modules.utils.logger import logger
from shared_modules.kafka_event_bus.kafka_consumer import create_consumer
from shared_modules.kafka_event_bus.topics import BUILD_TRIGGER
from shared_modules.state.devops_state import DevOpsAgentState
import threading

def start_build_agent(state: DevOpsAgentState):
    logger.info("[Build Agent] Starting LangGraph workflow and Kafka listener")

    flows = get_all_flows()
    graph = flows["build"]

    def kafka_listener():
        consumer = create_consumer(BUILD_TRIGGER)
        for msg in consumer:
            event_data = msg.value
            logger.info(f"[LangGraph] Received BUILD_TRIGGER event for repo: {event_data['repo_context']['repo']}")
            graph.invoke({"event_data": event_data, "state": state})

    thread = threading.Thread(target=kafka_listener)
    thread.start()
