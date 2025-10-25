import os
import subprocess
from typing import List, Dict, Any
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.utils.logger import logger
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus import topics
from shared_modules.kafka_event_bus.event_schema import DeploymentEvent, RollbackEvent

REPO_BASE_PATH = "/tmp/gitops_repos"

def get_missing_tools(required_tools: List[str] = None) -> List[str]:
    tools = required_tools or ["terraform"]
    missing: List[str] = []
    for tool in tools:
        try:
            exit_code = subprocess.call(["which", tool], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if exit_code != 0:
                missing.append(tool)
        except Exception:
            missing.append(tool)
    return missing

def _run(cmd: List[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)

def _terraform_outputs(terraform_dir: str) -> Dict[str, Any]:
    try:
        proc = subprocess.run(["terraform", "output", "-json"], cwd=terraform_dir, check=True, capture_output=True, text=True)
        return {"raw": proc.stdout}
    except subprocess.CalledProcessError as e:
        return {"error": e.stderr}

def apply_terraform(terraform_dir: str) -> Dict[str, Any]:
    logs: str = ""
    try:
        init_proc = _run(["terraform", "init"], cwd=terraform_dir)
        logs += init_proc.stdout
        apply_proc = _run(["terraform", "apply", "-auto-approve"], cwd=terraform_dir)
        logs += "\n" + apply_proc.stdout
        outputs = _terraform_outputs(terraform_dir)
        return {"status": "success", "logs": logs, "outputs": outputs}
    except subprocess.CalledProcessError as e:
        logs += "\n" + (e.stdout or "") + "\n" + (e.stderr or "")
        return {"status": "failed", "logs": logs}

def deploy_with_terraform(event: dict, state: DevOpsAgentState) -> Dict[str, Any]:
    """
    Orchestrates terraform deployment, updates state, and emits Kafka events.
    Expects `state.repo_context.repo` and terraform files in infra/ directory.
    """
    repo_name = event.get("repo") or getattr(getattr(state, "repo_context", None), "repo", None) or "unknown"
    config = state.repo_context.config or {}
    infra_cfg = config.get("infrastructure", {})
    path = infra_cfg.get("path", "infra/")
    deployment_cfg = config.get("deployment", {})
    service_name = deployment_cfg.get("service_name", "default-service")
    version = deployment_cfg.get("version", "latest")
    strategy = deployment_cfg.get("strategy", "standard")
    
    terraform_dir = os.path.join(REPO_BASE_PATH, repo_name, path)

    logger.info(f"[Deployment Agent] Starting deployment for repo={repo_name} dir={terraform_dir}")
    missing = get_missing_tools()
    if missing:
        msg = f"Missing required tools: {', '.join(missing)}"
        logger.error(f"[Deployment Agent] {msg}")
        state.deployment.status = "failed"
        state.deployment.logs = msg
        
        # Publish rollback event on failure before any apply
        try:
            rb = RollbackEvent(
                repo=repo_name,
                service=service_name,
                reason="deployment_failed_missing_tools",
                triggered_by="deployment_agent",
                logs=msg,
                rollback_to=None,
            )
            publish_event(topics.ROLLBACK_EVENT, rb.model_dump())
        except Exception as e:
            logger.error(f"[Deployment Agent] Failed to publish rollback event: {e}")
        return {"status": "failed", "logs": msg}

    # Publish deployment triggered (in progress) before applying
    try:
        start_ev = DeploymentEvent(
            repo=repo_name,
            service_name=service_name,
            version=version,
            strategy=strategy,
            status="in_progress",
            logs="Deployment initiated",
        )
        publish_event(topics.DEPLOYMENT_TRIGGERED, start_ev.model_dump())
    except Exception as e:
        logger.error(f"[Deployment Agent] Failed to publish 'in_progress' deployment event: {e}")

    result = apply_terraform(terraform_dir)

    # Update state
    state.deployment.logs = result.get("logs", "")
    state.deployment.status = "success" if result.get("status") == "success" else "failed"

    # Publish success/failure events to appropriate topics
    try:
        if state.deployment.status == "success":
            final_ev = DeploymentEvent(
                repo=repo_name,
                service_name=service_name,
                version=version,
                strategy=strategy,
                status="success",
                logs=state.deployment.logs,
            )
            publish_event(topics.DEPLOYMENT_TRIGGERED, final_ev.model_dump())
        else:
            rb = RollbackEvent(
                repo=repo_name,
                service=service_name,
                reason="deployment_failed",
                triggered_by="deployment_agent",
                logs=state.deployment.logs,
                rollback_to=None,
            )
            publish_event(topics.ROLLBACK_EVENT, rb.model_dump())
    except Exception as e:
        logger.error(f"[Deployment Agent] Failed to publish Kafka event: {e}")

    return {"status": result.get("status"), "logs": state.deployment.logs, "outputs": result.get("outputs")}
