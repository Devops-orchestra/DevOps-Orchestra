from langgraph.graph import StateGraph
<<<<<<< Updated upstream
from langgraph_flows.shared_nodes import run_code_analysis_node, run_build_node, run_tests_node, run_infra_node
=======
from langgraph_flows.shared_nodes import run_code_analysis_node, run_build_node, run_tests_node, run_infra_node, run_deploy_node, run_rollback_node, run_observability_node
>>>>>>> Stashed changes
from shared_modules.state.devops_state import DevOpsAgentState
from agents.slack_agent.notifier import notify_failure_from_state
from shared_modules.utils.logger import logger

MAX_RETRIES = 3

def should_build(inputs: dict) -> str:
    state: DevOpsAgentState = inputs["state"]
    return "build_image" if state.code_analysis.passed else "notify_code_analysis_failure"

def check_build_status(inputs: dict) -> str:
    state: DevOpsAgentState = inputs["state"]
    if state.build_result.status == "success":
        return "test_code"  
    state.build_result.retries += 1
    if state.build_result.retries < MAX_RETRIES:
        logger.warning(f"[Build Agent] Retry {state.build_result.retries}/{MAX_RETRIES}")
        return "build_image"
    return "notify_build_failure"

def check_test_status(inputs: dict) -> str:
    state: DevOpsAgentState = inputs["state"]
    if state.test_results.status == "success":
        return "provision_infra"
    state.test_results.retries += 1
    if state.test_results.retries < MAX_RETRIES:
        logger.warning(f"[Test Agent] Retry {state.test_results.retries}/{MAX_RETRIES}")
        return "test_code"
    return "notify_test_failure"

def check_infrastructure_status(inputs: dict) -> str:
    state: DevOpsAgentState = inputs["state"]
    if state.infra.status == "success":
        return "end"
    else:
        return "notify_infra_failure"

<<<<<<< Updated upstream
=======
def check_deploy_status(inputs: dict) -> str:
    state: DevOpsAgentState = inputs["state"]
    if state.deployment.status == "success":
        return "observability"
    return "notify_deploy_failure"

>>>>>>> Stashed changes
def send_build_failure_notification(inputs: dict) -> dict:
    return notify_failure_from_state("Build Result", inputs["event_data"], inputs["state"])

def send_code_analysis_failure_notification(inputs: dict) -> dict:
    return notify_failure_from_state("Code Analysis", inputs["event_data"], inputs["state"])

def send_test_failure_notification(inputs: dict) -> dict:
    return notify_failure_from_state("Test Results", inputs["event_data"], inputs["state"])

def send_infrastructure_code_failure_notification(inputs: dict) -> dict:
    return notify_failure_from_state("Infrastructure", inputs["event_data"], inputs["state"])


def get_combined_flow() -> StateGraph:
    builder = StateGraph(dict)

    builder.add_node("code_analysis", run_code_analysis_node)
    builder.add_node("build_image", run_build_node)
    builder.add_node("test_code", run_tests_node)
    builder.add_node("provision_infra", run_infra_node)
<<<<<<< Updated upstream
=======
    builder.add_node("deploy", run_deploy_node)
    builder.add_node("rollback", run_rollback_node)
    builder.add_node("observability", run_observability_node)
>>>>>>> Stashed changes
    builder.add_node("notify_build_failure", send_build_failure_notification)
    builder.add_node("notify_code_analysis_failure", send_code_analysis_failure_notification)
    builder.add_node("notify_test_failure", send_test_failure_notification)
    builder.add_node("notify_infra_failure", send_infrastructure_code_failure_notification)
    builder.add_node("end", lambda x: x)

    builder.add_conditional_edges("code_analysis", should_build, {
        "build_image": "build_image",
        "notify_code_analysis_failure": "notify_code_analysis_failure"
    })

    builder.add_conditional_edges("build_image", check_build_status, {
        "build_image": "build_image",
        "test_code": "test_code",
        "notify_build_failure": "notify_build_failure",
        "end": "end"
    })

    builder.add_conditional_edges("test_code", check_test_status, {
        "test_code": "test_code", 
        "provision_infra": "provision_infra",
        "notify_test_failure": "notify_test_failure",
        "end": "end"
    })

    builder.add_conditional_edges("provision_infra", check_infrastructure_status, {
<<<<<<< Updated upstream
        "end": "end",
        "notify_infra_failure": "notify_infra_failure"
=======
        "deploy": "deploy",
        "notify_infra_failure": "notify_infra_failure"
    })

    builder.add_conditional_edges("deploy", check_deploy_status, {
        "observability": "observability",
        "notify_deploy_failure": "notify_deploy_failure",
    })

    builder.add_conditional_edges("notify_deploy_failure", after_deploy_failure_notified, {
        "rollback": "rollback",
>>>>>>> Stashed changes
    })

    builder.set_entry_point("code_analysis")
    return builder.compile()
