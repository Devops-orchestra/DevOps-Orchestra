# File: langgraph_flows/shared_nodes.py

import os
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus.event_schema import CodeAnalysisEvent
from shared_modules.utils.logger import logger
from agents.code_analysis_agent.tools.llm_code_analyzer import analyze_code_with_llm
from agents.code_analysis_agent.models.schemas import LLMCodeAnalysisInput
from agents.code_analysis_agent.tools.llm_utils import parse_llm_summary
from agents.build_agent.tools.docker_builder import build_and_push_image
from shared_modules.utils.decorators import retry_on_failure

REPO_BASE_PATH = "/tmp/gitops_repos"

def run_code_analysis_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]

    input_data = LLMCodeAnalysisInput(
        repo=event['repo_context']["repo"],
        branch=event['repo_context']["branch"],
        commit_id=event['repo_context']["commit"],
        repo_path=os.path.join(REPO_BASE_PATH, event['repo_context']["repo"]),
        file_limit=10,
        llm_model="llama-3.3-70b-versatile"
    )

    llm_result = analyze_code_with_llm(input_data, state)

    if llm_result["results"]:
        analysis_text = llm_result["results"][0]["analysis"]
        parsed = parse_llm_summary(analysis_text)

        state.code_analysis.passed = parsed.passed
        state.code_analysis.errors = parsed.errors
        state.code_analysis.warnings = parsed.warnings
        state.code_analysis.logs = parsed.notes

        logger.info(f"[Code Analysis] Errors: {len(parsed.errors)}, Warnings: {len(parsed.warnings)}")

        code_analysis_event = CodeAnalysisEvent(
            repo=event['repo_context']["repo"],
            passed=parsed.passed,
            errors=parsed.errors,
            warnings=parsed.warnings,
            notes=parsed.notes
        )

        try:
            publish_event("code_analysis", code_analysis_event.model_dump())
            logger.info("[Kafka] CodeAnalysisEvent published")
        except Exception as e:
            logger.error(f"[Kafka] Failed to publish CodeAnalysisEvent: {e}")

    return {"event_data": event, "state": state}

@retry_on_failure(max_retries=3, agent_name="Build Agent")
def run_build_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]

    build_and_push_image(event, state)
    return {"event_data": event, "state": state}
