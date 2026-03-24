"""
Emit per-step pipeline events so agents and other services can observe progress
via Kafka while still using DevOpsAgentState as the source of truth.
"""
from typing import Any, Dict, Optional

from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.utils.logger import logger


def publish_pipeline_agent_event(
    topic: str,
    agent: str,
    step: str,
    pipeline_id: str,
    repo: str,
    status: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    payload: Dict[str, Any] = {
        "agent": agent,
        "step": step,
        "pipeline_id": pipeline_id,
        "repo": repo,
        "status": status,
    }
    if extra:
        payload["meta"] = extra
    try:
        publish_event(topic, payload)
    except Exception as e:
        logger.debug(f"[Kafka] publish_pipeline_agent_event skipped: {e}")
