"""
Send pipeline logs, errors, and results to the separate pipeline logs Slack channel.
Uses either SLACK_PIPELINE_LOGS_WEBHOOK_URL (incoming webhook) or Slack Web API (chat.postMessage)
with SLACK_PIPELINE_LOGS_CHANNEL_ID and SLACK_BOT_TOKEN.
"""
import os
import requests
from typing import Optional

from shared_modules.utils.logger import logger

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
except ImportError:
    WebClient = None
    SlackApiError = Exception


def _webhook_url() -> Optional[str]:
    return (os.getenv("SLACK_PIPELINE_LOGS_WEBHOOK_URL") or "").strip() or None


def _channel_id() -> Optional[str]:
    return (os.getenv("SLACK_PIPELINE_LOGS_CHANNEL_ID") or "").strip() or None


def _bot_token() -> Optional[str]:
    return (os.getenv("SLACK_BOT_TOKEN") or "").strip() or None


def send_pipeline_log(message: str, blocks: Optional[list] = None) -> bool:
    """
    Send a log message to the pipeline logs channel.
    Prefer webhook if set; otherwise use Web API with bot token and channel ID.
    """
    webhook = _webhook_url()
    if webhook:
        try:
            payload = {"text": message}
            if blocks:
                payload["blocks"] = blocks
            resp = requests.post(webhook, json=payload, timeout=10)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"[PipelineLogs] Webhook send failed: {e}")
            return False

    channel = _channel_id()
    token = _bot_token()
    if channel and token and WebClient is not None:
        try:
            client = WebClient(token=token)
            kwargs = {"channel": channel, "text": message}
            if blocks:
                kwargs["blocks"] = blocks
            client.chat_postMessage(**kwargs)
            return True
        except SlackApiError as e:
            logger.error(f"[PipelineLogs] Slack API error: {e.response.get('error', e)}")
            return False
        except Exception as e:
            logger.error(f"[PipelineLogs] Send failed: {e}")
            return False

    logger.warning("[PipelineLogs] No webhook or channel/token configured; log not sent.")
    return False


def log_pipeline_trigger(repo: str, branch: str, trigger_source: str, pr_number: Optional[str] = None):
    """Log that the pipeline was triggered."""
    text = f":rocket: *Pipeline triggered*\n• Repo: `{repo}`\n• Branch: `{branch}`\n• Source: {trigger_source}"
    if pr_number:
        text += f"\n• PR: #{pr_number}"
    send_pipeline_log(text)


def log_pipeline_step(step_name: str, status: str, details: str = ""):
    """Log a pipeline step result (success/failed/skipped)."""
    if status == "success":
        icon = ":white_check_mark:"
    elif status == "skipped":
        icon = ":fast_forward:"
    else:
        icon = ":x:"
    text = f"{icon} *{step_name}* — {status}"
    if details:
        text += f"\n```{details[:2000]}```"  # Limit length
    send_pipeline_log(text)


def log_pipeline_completion(success: bool, summary: str = ""):
    """Log pipeline completion."""
    icon = ":tada:" if success else ":warning:"
    text = f"{icon} *Pipeline completed* — {'Success' if success else 'Failed'}"
    if summary:
        text += f"\n{summary}"
    send_pipeline_log(text)


def log_pipeline_error(step_name: str, error_message: str, logs_snippet: str = ""):
    """Log an error to the pipeline logs channel."""
    text = f":x: *{step_name}* — Error\n{error_message}"
    if logs_snippet:
        text += f"\n```{logs_snippet[:1500]}```"
    send_pipeline_log(text)


def log_infra_plan(repo_name: str, tool: str, plan_output: str, max_chars: int = 3500):
    """
    Send infrastructure plan/code to the pipeline logs channel for user review.
    Infra agent generates code + plan only; user approves via reply; deployment agent applies.
    """
    plan_preview = (plan_output or "").strip()
    if len(plan_preview) > max_chars:
        plan_preview = plan_preview[:max_chars] + "\n...(truncated)"
    text = (
        f":clipboard: *Infrastructure plan* — `{repo_name}` ({tool})\n"
        "Review the plan below. Reply *yes* or *apply* to create resources; *skip* to continue without applying.\n"
        f"```\n{plan_preview}\n```"
    )
    send_pipeline_log(text)
