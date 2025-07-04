import os
import requests
from shared_modules.utils.logger import logger

def notify_failure(agent: str, repo: str, reason: str):
    slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not slack_webhook_url:
        logger.warning("[Slack] SLACK_WEBHOOK_URL not set. Notification skipped.")
        return

    message = {
        "text": f":x: *{agent} Failure* in repository *{repo}*\n\n*Reason:* ```{reason}```"
    }

    try:
        response = requests.post(slack_webhook_url, json=message)
        response.raise_for_status()
        logger.info(f"[Slack] Notification sent for {agent} failure in repo: {repo}")
    except Exception as e:
        logger.error(f"[Slack] Failed to send notification: {e}")