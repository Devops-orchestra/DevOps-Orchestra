"""
Send failure and status messages to the pipeline logs channel only.
Uses SLACK_PIPELINE_LOGS_CHANNEL_ID (and SLACK_BOT_TOKEN) or SLACK_PIPELINE_LOGS_WEBHOOK_URL
via coordinator.slack_logger.
"""
from coordinator.slack_logger import send_pipeline_log


def notify_failure(agent: str, repo: str, reason: str):
    """Send a failure notification to the pipeline logs channel."""
    message = f":x: *{agent} Failure* in repository *{repo}*\n\n*Reason:* ```{(reason or '')[:2000]}```"
    send_pipeline_log(message)
