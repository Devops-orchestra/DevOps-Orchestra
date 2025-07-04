from langgraph.graph import StateGraph
from langgraph_flows.shared_nodes import run_code_analysis_node, run_build_node
from shared_modules.state.devops_state import DevOpsAgentState
from agents.slack_agent.notifier import notify_failure_from_state
from shared_modules.utils.logger import logger

MAX_RETRIES = 3

def should_build(inputs: dict) -> str:
    state: DevOpsAgentState = inputs["state"]
    return "build_image" if state.code_analysis.passed else "build_image"

def check_build_status(inputs: dict) -> str:
    state: DevOpsAgentState = inputs["state"]
    if state.build_result.status == "success":
        return "end"
    if state.build_result.retries < MAX_RETRIES:
        logger.warning(f"[Build Agent] Retry {state.build_result.retries}/{MAX_RETRIES}")
        return "build_image"
    return "notify_build_failure"

def send_build_failure_notification(inputs: dict) -> dict:
    return notify_failure_from_state("Build Result", inputs["event_data"], inputs["state"])

def send_code_analysis_failure_notification(inputs: dict) -> dict:
    return notify_failure_from_state("Code Analysis", inputs["event_data"], inputs["state"])

def get_combined_flow() -> StateGraph:
    builder = StateGraph(dict)

    builder.add_node("code_analysis", run_code_analysis_node)
    builder.add_node("build_image", run_build_node)
    builder.add_node("notify_build_failure", send_build_failure_notification)
    builder.add_node("notify_code_analysis_failure", send_code_analysis_failure_notification)
    builder.add_node("end", lambda x: x)

    builder.add_conditional_edges("code_analysis", should_build, {
        "build_image": "build_image",
        "notify_code_analysis_failure": "notify_code_analysis_failure"
    })

    builder.add_conditional_edges("build_image", check_build_status, {
        "build_image": "build_image",
        "notify_build_failure": "notify_build_failure",
        "end": "end"
    })

    builder.set_entry_point("code_analysis")
    return builder.compile()
