import os
import subprocess
from typing import Dict, Any
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.utils.logger import logger
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus import topics
from shared_modules.kafka_event_bus.event_schema import RollbackEvent

REPO_BASE_PATH = "/tmp/gitops_repos"

def destroy_terraform(terraform_dir: str) -> Dict[str, Any]:
    logs = ""
    try:
        proc = subprocess.run(["terraform", "destroy", "-auto-approve"], cwd=terraform_dir, check=True, capture_output=True, text=True)
        logs += proc.stdout
        return {"status": "success", "logs": logs}
    except subprocess.CalledProcessError as e:
        logs += (e.stdout or "") + "\n" + (e.stderr or "")
        return {"status": "failed", "logs": logs}

def rollback_and_publish(event: dict, state: DevOpsAgentState) -> Dict[str, Any]:
    repo_name = event.get("repo") or getattr(getattr(state, "repo_context", None), "repo", None) or "unknown"
    config = state.repo_context.config or {}
    infra_cfg = config.get("infrastructure", {})
    path = infra_cfg.get("path", "infra/")
    deployment_cfg = config.get("deployment", {})
    service_name = deployment_cfg.get("service_name", "default-service")
    
    terraform_dir = os.path.join(REPO_BASE_PATH, repo_name, path)

    logger.info(f"[Rollback Agent] Destroying resources for repo={repo_name} dir={terraform_dir}")
    result = destroy_terraform(terraform_dir)

    # Update deployment state with rollback logs
    state.deployment.logs = (state.deployment.logs or "") + "\n[Rollback Agent]\n" + result.get("logs", "")

    # Publish rollback completion event
    try:
        rb = RollbackEvent(
            repo=repo_name,
            service=service_name,
            reason=event.get("reason", "deployment_failure"),
            triggered_by=event.get("triggered_by", "deployment_agent"),
            logs=result.get("logs"),
            rollback_to=event.get("rollback_to")
        )
        publish_event(topics.ROLLBACK_EVENT, rb.model_dump())
    except Exception as e:
        logger.error(f"[Rollback Agent] Failed to publish Kafka event: {e}")

    return result
