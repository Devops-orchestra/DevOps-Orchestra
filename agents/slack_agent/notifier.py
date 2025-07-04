from agents.slack_agent.main import notify_failure
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.utils.logger import logger

def notify_failure_from_state(agent: str, event_data: dict, state: DevOpsAgentState) -> dict:
    repo = event_data.get("repo_context", {}).get("repo", "unknown-repo")
    agent_key = agent.lower().replace(" ", "_")
    logs = getattr(state, agent_key).logs if hasattr(state, agent_key) else "No logs available."

    notify_failure(agent=agent, repo=repo, reason=logs)
    logger.info(f"[Slack] Failure notification sent for {agent} in repo: {repo}")
    return {
        "event_data": event_data,
        "state": state
    }
