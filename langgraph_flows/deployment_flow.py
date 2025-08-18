from langgraph.graph import StateGraph
from langgraph_flows.shared_nodes import run_deploy_node, run_rollback_node


def get_deployment_flow() -> StateGraph:
    builder = StateGraph(dict)

    builder.add_node("deploy", run_deploy_node)
    builder.add_node("rollback", run_rollback_node)
    builder.add_node("end", lambda x: x)

    def check_deploy_status(inputs: dict) -> str:
        state = inputs["state"]
        if state.deployment.status == "success":
            return "end"
        return "rollback"

    builder.add_conditional_edges("deploy", check_deploy_status, {
        "end": "end",
        "rollback": "rollback",
    })

    builder.set_entry_point("deploy")
    return builder.compile()

