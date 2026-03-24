"""
Second-stage LangGraph: infra generation (plan) then, after Slack approval, deploy + rollback.

Coordinator flow: invoke get_infra_prepare_graph() → human approves plan → invoke get_post_approval_deploy_graph().
"""
from langgraph.graph import StateGraph

from shared_modules.state.devops_state import DevOpsAgentState, StatusEnum
from shared_modules.utils.logger import logger
from agents.infrastructure_agent.tools.llm_infra_generator import generate_infrastructure_with_llm
from langgraph_flows.deployment_flow import get_deployment_flow


def run_infra_generate_node(inputs: dict) -> dict:
    """Run LLM infra generation + terraform plan (no apply)."""
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    state.current_agent = "infrastructure_agent"
    try:
        r = generate_infrastructure_with_llm(event, state)
        status = r.get("status")
        state.infra.logs = r.get("logs", "")
        state.infra.infra_path = r.get("infra_path") or ""
        state.infra.infra_tool = (r.get("tool") or "terraform").strip().lower()
        state.infra.plan_output = (r.get("plan_output") or "")[:120_000]

        if status == "plan_ready":
            state.infra.status = StatusEnum.IN_PROGRESS
        elif status == "success":
            state.infra.status = StatusEnum.SUCCESS
        else:
            state.infra.status = StatusEnum.FAILED
    except Exception as e:
        logger.error(f"[Infra Graph] generate failed: {e}")
        state.infra.status = StatusEnum.FAILED
        state.infra.logs = str(e)
        state.infra.plan_output = None
    return {"event_data": event, "state": state}


def get_infra_prepare_graph():
    """Single-node graph: generate IaC + plan (no apply)."""
    builder = StateGraph(dict)
    builder.add_node("infra_generate", run_infra_generate_node)
    builder.add_node("end", lambda x: x)
    builder.add_edge("infra_generate", "end")
    builder.set_entry_point("infra_generate")
    return builder.compile()


def get_post_approval_deploy_graph():
    """
    Deploy (+ rollback on failure). Same as deployment_flow.get_deployment_flow();
    use after user accepts infra plan (or to run app deploy when plan was skipped).
    """
    return get_deployment_flow()
