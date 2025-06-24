import os
from venv import logger
from langgraph.graph import StateGraph
from agents.code_analysis_agent.models.schemas import LLMCodeAnalysisInput
from agents.code_analysis_agent.tools.llm_code_analyzer import analyze_code_with_llm
from shared_modules.state.devops_state import DevOpsAgentState
from agents.code_analysis_agent.tools.llm_utils import parse_llm_summary
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus.event_schema import CodeAnalysisEvent



REPO_BASE_PATH = "/tmp/gitops_repos"

def run_code_analysis(inputs: dict) -> dict:
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

    llm_result = analyze_code_with_llm(input_data)

    if llm_result["results"]:
        analysis_text = llm_result["results"][0]["analysis"]
        parsed = parse_llm_summary(analysis_text)
        state.code_analysis.passed = parsed.passed
        state.code_analysis.errors = parsed.errors
        state.code_analysis.warnings = parsed.warnings

        print(f"\nSummary:")
        print(f" Errors: {len(parsed.errors)}")
        print(f" Warnings: {len(parsed.warnings)}")
        print(f" Notes: {analysis_text.lower().count('note')}")

        if parsed.passed:
            print("\n Passed Checks:")
        if parsed.warnings:
            print("\n Warning:")
            for item in parsed.warnings:
                print(f" - {item}")
        if parsed.errors:
            print("\n Errors:")
            for item in parsed.errors:
                print(f" - {item}")

        code_analysis_event = CodeAnalysisEvent(
            repo=event['repo_context']["repo"],
            passed=parsed.passed,
            errors=parsed.errors,
            warnings=parsed.warnings,
            notes=parsed.notes
        )

        event_data = code_analysis_event.model_dump()
        logger.info("[Kafka] Preparing to send CodeAnalysisEvent to Kafka topic: code_analysis")
        logger.debug(f"[Kafka] Payload: {event_data}")
        
        try:
            publish_event(topic="code_analysis", data=event_data)
            logger.info("[Kafka] CodeAnalysisEvent successfully published to Kafka.")
        except Exception as e:
            logger.error(f"[Kafka] Failed to publish CodeAnalysisEvent: {e}")

    logger.info(f"Final state: {state}")
    return {
        "event_data": event,
        "state": state
    }

def get_code_analysis_flow() -> StateGraph:
    builder = StateGraph(dict)
    builder.add_node("analyze_code", run_code_analysis)
    builder.set_entry_point("analyze_code")
    return builder.compile()
