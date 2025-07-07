import functools
import time
from shared_modules.utils.logger import logger
from agents.slack_agent.main import notify_failure

def retry_on_failure(max_retries=3, agent_name="Unknown Agent", state_field="Unknown", retry_delay=0):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(inputs: dict):
            state = inputs.get("state")
            event = inputs.get("event_data")
            repo = event.get("repo_context", {}).get("repo", "unknown-repo")

            if not hasattr(state, state_field):
                logger.warning(f"[{agent_name}] No '{state_field}' found in state for retry tracking.")
                return func(inputs)

            state_obj = getattr(state, state_field)
            retries = getattr(state_obj, "retries", 0)

            while retries < max_retries:
                try:
                    return func(inputs)
                except Exception as e:
                    retries += 1
                    state_obj.retries = retries
                    logger.error(f"[{agent_name}] Attempt {retries} failed: {e}")

                    if retries >= max_retries:
                        notify_failure(agent=agent_name, repo=repo, reason=str(e))
                        logger.error(f"[{agent_name}] Max retries reached. Notifying via Slack.")
                        raise

                    if retry_delay > 0:
                        time.sleep(retry_delay)

            logger.error(f"[{agent_name}] Exiting retry loop after {retries} attempts without success.")
            raise RuntimeError(f"{agent_name} failed after {max_retries} retries")

        return wrapper
    return decorator
