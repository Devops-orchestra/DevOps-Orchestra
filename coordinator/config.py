"""
Coordinator configuration. Loads from environment variables and optional YAML.
"""
import os
from typing import Optional


def _env(key: str, default: Optional[str] = None) -> str:
    v = os.getenv(key, default)
    if v is None and default is None:
        return ""
    return (v or "").strip()


class CoordinatorConfig:
    """Configuration for the Coordinator daemon."""

    # Slack
    SLACK_BOT_TOKEN: str = _env("SLACK_BOT_TOKEN", "")
    SLACK_APP_TOKEN: str = _env("SLACK_APP_TOKEN", "")  # For Socket Mode
    SLACK_COMMAND_CHANNEL_ID: str = _env("SLACK_COMMAND_CHANNEL_ID", "")  # Where users + GitHub events appear
    SLACK_PIPELINE_LOGS_CHANNEL_ID: str = _env("SLACK_PIPELINE_LOGS_CHANNEL_ID", "")  # All pipeline logs
    SLACK_PIPELINE_LOGS_WEBHOOK_URL: str = _env("SLACK_PIPELINE_LOGS_WEBHOOK_URL", "")  # Optional: webhook for logs

    # Jira (for Test agent use-case tool)
    JIRA_BASE_URL: str = _env("JIRA_BASE_URL", "")
    JIRA_API_TOKEN: str = _env("JIRA_API_TOKEN", "")
    JIRA_EMAIL: str = _env("JIRA_EMAIL", "")

    # Repo
    DEFAULT_REPO_URL: str = _env("DEFAULT_REPO_URL", "")
    REPO_BASE_PATH: str = _env("REPO_BASE_PATH", "/tmp/gitops_repos")

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = _env("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

    # LLM (for failure suggestions)
    GROQ_API_KEY: str = _env("GROQ_API_KEY", "")

    @classmethod
    def validate_slack(cls) -> list[str]:
        errors = []
        if not cls.SLACK_BOT_TOKEN:
            errors.append("SLACK_BOT_TOKEN is required")
        if not cls.SLACK_APP_TOKEN:
            errors.append("SLACK_APP_TOKEN is required (Socket Mode)")
        if not cls.SLACK_COMMAND_CHANNEL_ID:
            errors.append("SLACK_COMMAND_CHANNEL_ID is required")
        if not cls.SLACK_PIPELINE_LOGS_CHANNEL_ID and not cls.SLACK_PIPELINE_LOGS_WEBHOOK_URL:
            errors.append("Either SLACK_PIPELINE_LOGS_CHANNEL_ID or SLACK_PIPELINE_LOGS_WEBHOOK_URL is required")
        return errors

    @classmethod
    def validate_jira(cls) -> list[str]:
        errors = []
        if not cls.JIRA_BASE_URL:
            errors.append("JIRA_BASE_URL is required for Jira use-case tool")
        if not cls.JIRA_API_TOKEN:
            errors.append("JIRA_API_TOKEN is required")
        return errors


config = CoordinatorConfig()
