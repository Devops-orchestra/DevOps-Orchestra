"""
Single LangGraph definition for GitOps pre-steps + agents (index → code analysis → build → test).
Infra/deploy stay in coordinator until plan-approval UX is modeled as graph interrupts.
"""
from langgraph.graph import StateGraph

from langgraph_flows.gitops_nodes import (
    run_clone_node,
    run_validate_config_node,
    run_repo_size_node,
    run_license_audit_node,
    run_git_metadata_node,
)
from langgraph_flows.shared_nodes import (
    run_index_repo_node,
    run_code_analysis_node,
    run_build_node,
    run_tests_node,
)
from shared_modules.state.devops_state import DevOpsAgentState, StatusEnum
from shared_modules.utils.logger import logger

MAX_RETRIES = 3


def route_after_index(inputs: dict) -> str:
    """Skip code analysis stage when user set pipeline.skips.code_analysis."""
    state: DevOpsAgentState = inputs["state"]
    if state.pipeline.skips.code_analysis:
        return "build_image"
    return "code_analysis"


def should_build_after_analysis(inputs: dict) -> str:
    state: DevOpsAgentState = inputs["state"]
    if state.pipeline.skips.code_analysis:
        return "build_image"
    return "build_image" if state.code_analysis.passed else "end"


def check_build_status(inputs: dict) -> str:
    state: DevOpsAgentState = inputs["state"]
    if state.pipeline.skips.build:
        return "test_code"
    br = str(state.build_result.status).lower()
    if br == "success":
        return "test_code"
    state.build_result.retries += 1
    if state.build_result.retries < MAX_RETRIES:
        logger.warning(f"[Build Agent] Retry {state.build_result.retries}/{MAX_RETRIES}")
        return "build_image"
    return "end"


def check_test_status_then_end(inputs: dict) -> str:
    state: DevOpsAgentState = inputs["state"]
    if state.pipeline.skips.test:
        return "end"
    tr = str(state.test_results.status).lower()
    if tr == "success" or state.test_results.status == StatusEnum.SUCCESS:
        return "end"
    state.test_results.retries += 1
    if state.test_results.retries < MAX_RETRIES:
        logger.warning(f"[Test Agent] Retry {state.test_results.retries}/{MAX_RETRIES}")
        return "test_code"
    return "end"


def get_full_pipeline_flow():
    """
    GitOps: clone → validate → repo_size → license → git_metadata
    Agents: index_repo → code_analysis → build → test → end
    """
    builder = StateGraph(dict)

    builder.add_node("clone", run_clone_node)
    builder.add_node("validate_config", run_validate_config_node)
    builder.add_node("repo_size", run_repo_size_node)
    builder.add_node("license_audit", run_license_audit_node)
    builder.add_node("git_metadata", run_git_metadata_node)
    builder.add_node("index_repo", run_index_repo_node)
    builder.add_node("code_analysis", run_code_analysis_node)
    builder.add_node("build_image", run_build_node)
    builder.add_node("test_code", run_tests_node)
    builder.add_node("end", lambda x: x)

    builder.add_edge("clone", "validate_config")
    builder.add_edge("validate_config", "repo_size")
    builder.add_edge("repo_size", "license_audit")
    builder.add_edge("license_audit", "git_metadata")
    builder.add_edge("git_metadata", "index_repo")

    builder.add_conditional_edges("index_repo", route_after_index, {
        "code_analysis": "code_analysis",
        "build_image": "build_image",
    })

    builder.add_conditional_edges("code_analysis", should_build_after_analysis, {
        "build_image": "build_image",
        "end": "end",
    })

    builder.add_conditional_edges("build_image", check_build_status, {
        "build_image": "build_image",
        "test_code": "test_code",
        "end": "end",
    })

    builder.add_conditional_edges("test_code", check_test_status_then_end, {
        "test_code": "test_code",
        "end": "end",
    })

    builder.set_entry_point("clone")
    return builder.compile()


def get_pipeline_agent_flow():
    """Backward-compatible alias: same as get_full_pipeline_flow."""
    return get_full_pipeline_flow()
