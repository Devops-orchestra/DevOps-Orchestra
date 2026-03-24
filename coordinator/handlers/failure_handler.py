"""
On agent failure: get LLM suggestion for resolution and format message for user in Slack.
Uses Groq when GROQ_API_KEY is set; otherwise returns a short static hint to check logs.
"""
import os
from typing import Tuple

from shared_modules.utils.logger import logger
from shared_modules.llm_config.model_wrapper import run_prompt



FAILURE_SUGGESTION_PROMPT = """You are a DevOps assistant. An agent in the pipeline has failed.

Step: {step_name}
Error: {error_message}

Logs (excerpt):
```
{logs_snippet}
```

In 1-3 short sentences, suggest what the user could do to fix the issue (e.g. fix the Dockerfile, check environment variables). Do not repeat the full logs. Be concise.
Then remind: "Reply with *skip* to skip this step and continue to the next stage, *retry* to rerun this step (optionally after fixing), or *resolved* after you have fixed the issue and want to rerun this step."
"""


def get_failure_suggestion(step_name: str, error_message: str, logs_snippet: str = "") -> Tuple[str, str]:
    """
    Call LLM to get a suggested resolution for the failure.
    Returns (llm_suggestion, message_for_user) to post in command channel.
    """
    logs_snippet = (logs_snippet or "")[:1500]
    prompt = FAILURE_SUGGESTION_PROMPT.format(
        step_name=step_name,
        error_message=error_message[:500],
        logs_snippet=logs_snippet or "(no logs)",
    )
    suggestion = ""
    if os.getenv("GROQ_API_KEY"):
        try:
            suggestion = run_prompt(
                prompt,
                model="llama-3.3-70b-versatile",
                temperature=0.3,
                max_tokens=400,
            ).strip()
        except Exception as e:
            logger.warning(f"[FailureHandler] LLM suggestion failed: {e}")
            suggestion = "Could not generate suggestion. Please check the logs and fix the issue."
    else:
        suggestion = "Check the pipeline logs channel for details."

    message_for_user = (
        f":x: *{step_name}* failed.\n\n{suggestion}\n\n"
        "Reply with *skip* to skip this step and continue to the next stage, "
        "*retry* to rerun this step, or *resolved* after you have fixed the issue and want to rerun this step."
    )
    return suggestion, message_for_user
