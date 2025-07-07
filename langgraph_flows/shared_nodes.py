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
from shared_modules.kafka_event_bus.event_schema import TestResultsEvent
from agents.test_agent.tools.llm_test_generator import generate_tests_with_llm, run_tests_for_language


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

@retry_on_failure(max_retries=3, agent_name="Build Agent", state_field="build_result")
def run_build_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]

    build_and_push_image(event, state)
    if state.build_result.status == "failed":
        logger.error(f"[Build Agent] Build failed: {state.build_result.logs}")
        raise RuntimeError(f"Build failed: {state.build_result.logs}")
    
    return {"event_data": event, "state": state}



@retry_on_failure(max_retries=3, agent_name="Test Agent", state_field="test_results")
def run_tests_node(inputs: dict) -> dict:
    state: DevOpsAgentState = inputs["state"]
    event = inputs["event_data"]

    repo_name = event.get("repo") or event.get("repo_context", {}).get("repo")
    repo_path = os.path.join(REPO_BASE_PATH, repo_name)

    try:
        test_code = generate_tests_with_llm(repo_path, state)
        result = run_tests_for_language(repo_path, test_code)

        failed_count = 0 if result.passed else (result.total - result.passed)
        if failed_count < 0:
            failed_count = 1

        state.test_results.status = "success" if result.passed else "failed"
        state.test_results.logs = result.logs
        state.test_results.total = result.total
        state.test_results.passed = result.passed
        state.test_results.failed = failed_count
        state.test_results.coverage = result.coverage if hasattr(result, 'coverage') else None

        test_event = TestResultsEvent(
            repo=repo_name,
            total_tests=result.total,
            passed=result.passed,
            failed=failed_count,
            coverage=result.coverage,
            logs=result.logs
        )

        if not result.passed:
            logger.error(f"[Test Agent] Tests failed: {failed_count} out of {result.total}")
            raise RuntimeError(f"Tests failed: {failed_count} failed out of {result.total}. See logs for details.")
        
        publish_event("test_complete", test_event.model_dump())
        logger.info("[Kafka] TestResultsEvent published")

        
    except Exception as e:
        logger.error(f"[Test Agent] Test execution failed: {e}")
        state.test_results.status = "failed"
        state.test_results.logs = str(e)
        # Re-raise to trigger retry and Slack notification
        raise

    return {"event_data": event, "state": state}
