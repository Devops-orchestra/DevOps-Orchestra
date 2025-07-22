import os
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.utils.logger import logger
from agents.code_analysis_agent.tools.llm_code_analyzer import analyze_code_with_llm
from agents.build_agent.tools.builder import build_and_push_image
from agents.test_agent.tools.llm_test_generator import generate_tests_with_llm, run_tests_for_language
from agents.infrastructure_agent.tools.llm_infra_generator import generate_infrastructure_with_llm


REPO_BASE_PATH = "/tmp/gitops_repos"

def run_code_analysis_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    try:
        analyze_code_with_llm(event, state)
    except Exception as e:
        logger.error(f"[Code Analysis Agent] Exception during Analysis: {e}")
        state.code_analysis.passed = False
        state.code_analysis.logs = str(e)
    return {"event_data": event, "state": state}

def run_build_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    try:
        build_and_push_image(event, state)
    except Exception as e:
        logger.error(f"[Build Agent] Exception during build: {e}")
        state.build_result.status = "failed"
        state.build_result.logs = str(e)
    return {"event_data": event, "state": state}



def run_tests_node(inputs: dict) -> dict:
    state: DevOpsAgentState = inputs["state"]
    event = inputs["event_data"]
    repo_name = event.get("repo") or event.get("repo_context", {}).get("repo")
    repo_path = os.path.join(REPO_BASE_PATH, repo_name)

    try:
        test_code = generate_tests_with_llm(repo_path, state)
        result = run_tests_for_language(repo_path, test_code, state)

        failed_count = result.total - result.passed
        state.test_results.status = "success" if result.passed else "failed"
        state.test_results.logs = result.logs
        state.test_results.total = result.total
        state.test_results.passed = result.passed
        state.test_results.failed = failed_count
        state.test_results.coverage = result.coverage

    except Exception as e:
        logger.error(f"[Test Agent] Test execution failed: {e}")
        state.test_results.status = "failed"
        state.test_results.logs = str(e)

    return {"event_data": event, "state": state}

def run_infra_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    try:
        result = generate_infrastructure_with_llm(event, state)
        state.infra.status = "success" if result.get("status") == "success" else "failed"
        state.infra.resources = result.get("resources")
        state.infra.outputs = result.get("outputs")
        state.infra.logs = result.get("logs", "")
    except Exception as e:
        logger.error(f"[Infra Agent] Exception during infra provisioning: {e}")
        state.infra.status = "failed"
        state.infra.outputs = {}
        state.infra.logs = str(e)
    return {"event_data": event, "state": state}
