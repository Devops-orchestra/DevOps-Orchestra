from agents.slack_agent.main import notify_failure
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.utils.logger import logger

def notify_failure_from_state(agent: str, event_data: dict, state: DevOpsAgentState) -> dict:
    repo = event_data.get("repo_context", {}).get("repo", "unknown-repo")
    agent_key = agent.lower().replace(" ", "_")
    logs = getattr(state, agent_key).logs if hasattr(state, agent_key) else "No logs available."

    # Read chatops config from state
    config = getattr(state.repo_context, "config", {}) or {}
    chatops_cfg = config.get("chatops", {})
    enabled = chatops_cfg.get("enabled", False)
    platform = chatops_cfg.get("platform", "slack").lower()

    if not enabled:
        logger.info(f"[Slack Agent] ChatOps notifications are disabled in config. Not sending message for {agent}.")
        return {
            "event_data": event_data,
            "state": state
        }
    if platform != "slack":
        logger.warning(f"[Slack Agent] ChatOps platform '{platform}' is not supported. Only 'slack' is supported.")
        return {
            "event_data": event_data,
            "state": state
        }

    notify_failure(agent=agent, repo=repo, reason=logs)
    logger.info(f"[Slack] Failure notification sent for {agent} in repo: {repo}")
    return {
        "event_data": event_data,
        "state": state
    }
