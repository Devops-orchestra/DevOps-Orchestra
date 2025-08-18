import os
from typing import Dict, Any, List
from shared_modules.state.devops_state import DevOpsAgentState
import boto3
from botocore.config import Config
from shared_modules.utils.logger import logger
from agents.slack_agent.notifier import notify_failure_from_state


def _get_boto_logs_client() -> Any:
    region = os.getenv("AWS_REGION", "us-east-1")
    return boto3.client("logs", config=Config(region_name=region))


def fetch_cloudwatch_errors(log_group_name: str, filter_pattern: str = "?ERROR ?Exception ?Traceback") -> List[str]:
    client = _get_boto_logs_client()
    messages: List[str] = []
    try:
        paginator = client.get_paginator("filter_log_events")
        for page in paginator.paginate(logGroupName=log_group_name, filterPattern=filter_pattern, limit=100):
            for event in page.get("events", []):
                msg = event.get("message")
                if msg:
                    messages.append(msg)
    except Exception as e:
        logger.error(f"[Observability Agent] Failed to fetch CloudWatch logs: {e}")
    return messages


def check_system_logs(paths: List[str] = None) -> List[str]:
    candidates = paths or ["/var/log/syslog", "/var/log/messages"]
    findings: List[str] = []
    for p in candidates:
        try:
            if os.path.exists(p):
                with open(p, "r", errors="ignore") as f:
                    for line in f:
                        if any(keyword in line for keyword in ["ERROR", "Exception", "Traceback", "CRITICAL"]):
                            findings.append(line.strip())
        except Exception as e:
            logger.warning(f"[Observability Agent] Could not read {p}: {e}")
    return findings


def run_observability_checks(event: dict, state: DevOpsAgentState = None) -> Dict[str, Any]:
    """
    Core logic: reads CloudWatch logs and local system logs for errors.
    Updates state.observability and sends Slack notification if issues found.
    """
    repo_name = event['repo_context']["repo"]
    log_group = event.get("cloudwatch_log_group") or os.getenv("CLOUDWATCH_LOG_GROUP", f"/aws/{repo_name}")

    cloudwatch_errors = fetch_cloudwatch_errors(log_group)
    system_errors = check_system_logs()

    issues: List[str] = []
    if cloudwatch_errors:
        issues.append(f"CloudWatch errors detected: {len(cloudwatch_errors)}")
    if system_errors:
        issues.append(f"System log errors detected: {len(system_errors)}")

    state.observability.alerts = issues
    if issues:
        # Aggregate a short reason for Slack
        state.observability.rollback_triggered = True
        notify_failure_from_state("Observability", {"repo_context": {"repo": repo_name}}, state)

    return {
        "event_data": event,
        "state": state,
        "cloudwatch_errors": cloudwatch_errors[:10],
        "system_errors": system_errors[:10],
    }


