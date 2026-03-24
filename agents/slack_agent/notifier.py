"""
Build failure notification from pipeline state and send to pipeline logs channel.
"""
from agents.slack_agent.main import notify_failure
from shared_modules.state.devops_state import DevOpsAgentState


# Map failure step names to state attribute names
_STATE_ATTR = {"build_result": "build_result", "code_analysis": "code_analysis", "test_results": "test_results", "infrastructure": "infra", "deployment": "deployment"}


def notify_failure_from_state(agent: str, event_data: dict, state: DevOpsAgentState) -> dict:
    """Extract repo and logs from state and send failure to pipeline logs channel."""
    repo = (event_data.get("repo_context") or {}).get("repo", "unknown-repo")
    agent_key = agent.lower().replace(" ", "_")
    state_attr = _STATE_ATTR.get(agent_key, agent_key)
    logs = "No logs available."
    if hasattr(state, state_attr):
        obj = getattr(state, state_attr)
        logs = getattr(obj, "logs", None) or getattr(obj, "errors", None) or str(obj)
    if isinstance(logs, (list,)):
        logs = "\n".join(str(x) for x in logs)
    notify_failure(agent=agent, repo=repo, reason=logs or "No logs available.")
    return {"event_data": event_data, "state": state}
