import functools
from shared_modules.utils.logger import logger
from agents.slack_agent.main import notify_failure

def retry_on_failure(max_retries=3, agent_name="Unknown Agent"):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(inputs: dict):
            state = inputs.get("state")
            event = inputs.get("event_data")
            repo = event.get("repo_context", {}).get("repo", "unknown-repo")
            
            if not hasattr(state, agent_name.lower().replace(" ", "_")):
                logger.warning(f"[{agent_name}] No state found for retry tracking.")
                return func(inputs)

            agent_state = getattr(state, agent_name.lower().replace(" ", "_"))
            agent_state.retries += 1

            try:
                result = func(inputs)
                return result
            except Exception as e:
                logger.error(f"[{agent_name}] Attempt {agent_state.retries} failed: {e}")
                if agent_state.retries >= max_retries:
                    notify_failure(agent=agent_name, repo=repo, reason=str(e))
                    logger.error(f"[{agent_name}] Max retries reached. Notifying via Slack.")
                raise
        return wrapper
    return decorator
