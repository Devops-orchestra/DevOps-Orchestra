from langgraph_flows import get_all_flows
from shared_modules.utils.logger import logger
from shared_modules.kafka_event_bus.kafka_consumer import create_consumer
from shared_modules.kafka_event_bus.topics import CODE_PUSH
import threading

def start_code_analysis_agent():
    logger.info("[Code Analysis Agent] Starting MCP Tool and Kafka Listener")
    
    flows = get_all_flows()
    graph = flows["code_analysis"] 

    def kafka_listener():
        consumer = create_consumer(CODE_PUSH)
        for msg in consumer:
            event_data = msg.value
            logger.info(f"[LangGraph] Received CODE_PUSH event for repo: {event_data['repo_context']['repo']}")
            graph.invoke(event_data)

    thread = threading.Thread(target=kafka_listener)
    thread.start()
