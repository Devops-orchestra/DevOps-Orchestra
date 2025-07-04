# File: agents/langgraph_combined/main.py

import threading
from langgraph_flows import get_all_flows
from shared_modules.kafka_event_bus.kafka_consumer import create_consumer
from shared_modules.kafka_event_bus.topics import CODE_PUSH
from shared_modules.utils.logger import logger
from shared_modules.state.devops_state import DevOpsAgentState

def start_combined_agent(state: DevOpsAgentState):
    logger.info("[Combined Agent] Starting LangGraph Combined Flow + Kafka Listener")

    flows = get_all_flows()
    combined_flow = flows["combined"]

    def kafka_listener():
        consumer = create_consumer(CODE_PUSH)
        for msg in consumer:
            event_data = msg.value
            logger.info(f"[Combined Agent] Received CODE_PUSH for repo: {event_data['repo_context']['repo']}")
            combined_flow.invoke({"event_data": event_data, "state": state})

    thread = threading.Thread(target=kafka_listener, daemon=True)
    thread.start()
