"""
Deployment agent: deploy infrastructure/application for any stack (AWS, GCP, Azure).
Uses the same path as the infra agent (repo clone + branch + infra path).
Supports Terraform (all clouds), and records provider for events.
"""
import os
import subprocess
import json
from typing import List, Dict, Any, Optional, Tuple

from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.utils.logger import logger
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus import topics
from shared_modules.kafka_event_bus.event_schema import DeploymentEvent, RollbackEvent, IaCReadyEvent
from shared_modules.state.devops_state import StatusEnum

REPO_BASE_PATH = os.getenv("REPO_BASE_PATH", "/tmp/gitops_repos")

SUPPORTED_PROVIDERS = ("aws", "gcp", "azure")


def _deploy_base_path(event: dict, state: DevOpsAgentState) -> str:
    """Return infra/deploy directory path (same repo clone as pipeline and infra agent)."""
    repo_name = event.get("repo") or (event.get("repo_context") or {}).get("repo") or "unknown"
    branch = (getattr(getattr(state, "repo_context", None), "branch", None) or "main")
    branch = branch.replace("/", "_")
    config = getattr(getattr(state, "repo_context", None), "config", None) or {}
    path = (config.get("infrastructure") or {}).get("path", "infra")
    path = path.rstrip("/")
    return os.path.join(REPO_BASE_PATH, f"{repo_name}_{branch}", path)


def _get_provider_and_tool(state: DevOpsAgentState) -> Tuple[str, str]:
    """Return (provider, tool) from config. provider: aws|gcp|azure, tool: terraform|cloudformation|arm|gcp."""
    config = state.repo_context.config or {}
    deployment_cfg = config.get("deployment", {})
    infra_cfg = config.get("infrastructure", {})
    provider = (deployment_cfg.get("provider") or infra_cfg.get("provider") or "aws").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        provider = "aws"
    tool = (infra_cfg.get("tool") or "terraform").strip().lower()
    return provider, tool


def get_missing_tools(required_tools: Optional[List[str]] = None) -> List[str]:
    tools = required_tools or ["terraform"]
    missing: List[str] = []
    for tool in tools:
        try:
            exit_code = subprocess.call(
                ["which", tool], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if exit_code != 0:
                missing.append(tool)
        except Exception:
            missing.append(tool)
    return missing


def _run(cmd: List[str], cwd: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True, timeout=timeout)


def _terraform_outputs(terraform_dir: str) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            ["terraform", "output", "-json"],
            cwd=terraform_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        data = json.loads(proc.stdout)
        return {k: v.get("value") for k, v in data.items()} if isinstance(data, dict) else {"raw": proc.stdout}
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        return {"error": str(e)}


def _deploy_terraform(deploy_dir: str, provider: str) -> Dict[str, Any]:
    """Run terraform init + apply. Works for AWS, GCP, Azure (provider is in .tf files)."""
    logs = ""
    try:
        init_proc = _run(["terraform", "init", "-input=false", "-no-color"], deploy_dir, timeout=120)
        logs += (init_proc.stdout or "") + (init_proc.stderr or "")
        apply_proc = _run(
            ["terraform", "apply", "-auto-approve", "-input=false", "-no-color"],
            deploy_dir,
            timeout=600,
        )
        logs += "\n" + (apply_proc.stdout or "") + (apply_proc.stderr or "")
        outputs = _terraform_outputs(deploy_dir)
        return {"status": "success", "logs": logs, "outputs": outputs}
    except subprocess.CalledProcessError as e:
        logs += "\n" + (e.stdout or "") + "\n" + (e.stderr or "")
        return {"status": "failed", "logs": logs}
    except subprocess.TimeoutExpired:
        return {"status": "failed", "logs": logs + "\nDeployment timed out."}


def _deploy_cloudformation(deploy_dir: str, repo_name: str) -> Dict[str, Any]:
    """Deploy via AWS CloudFormation (stack already created in infra step; optional update)."""
    cf_file = os.path.join(deploy_dir, "cloudformation.yaml")
    if not os.path.isfile(cf_file):
        return {"status": "failed", "logs": f"Missing {cf_file}"}
    try:
        proc = subprocess.run(
            [
                "aws", "cloudformation", "deploy",
                "--template-file", cf_file,
                "--stack-name", f"{repo_name}-stack",
                "--capabilities", "CAPABILITY_NAMED_IAM",
                "--no-fail-on-empty-changeset",
            ],
            cwd=deploy_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        logs = (proc.stdout or "") + (proc.stderr or "")
        return {"status": "success" if proc.returncode == 0 else "failed", "logs": logs}
    except subprocess.TimeoutExpired:
        return {"status": "failed", "logs": "CloudFormation deploy timed out."}


def _deploy_arm(deploy_dir: str, repo_name: str) -> Dict[str, Any]:
    """Deploy via Azure ARM template."""
    template_file = os.path.join(deploy_dir, "template.json")
    if not os.path.isfile(template_file):
        return {"status": "failed", "logs": f"Missing {template_file}"}
    try:
        proc = subprocess.run(
            [
                "az", "deployment", "group", "create",
                "--resource-group", f"{repo_name}-rg",
                "--template-file", template_file,
            ],
            cwd=deploy_dir,
            capture_output=True,
            text=True,
            timeout=600,
        )
        logs = (proc.stdout or "") + (proc.stderr or "")
        return {"status": "success" if proc.returncode == 0 else "failed", "logs": logs}
    except subprocess.TimeoutExpired:
        return {"status": "failed", "logs": "ARM deployment timed out."}


def _deploy_gcp_dm(deploy_dir: str, repo_name: str) -> Dict[str, Any]:
    """Deploy via Google Cloud Deployment Manager."""
    dep_file = os.path.join(deploy_dir, "deployment.yaml")
    if not os.path.isfile(dep_file):
        return {"status": "failed", "logs": f"Missing {dep_file}"}
    try:
        proc = subprocess.run(
            [
                "gcloud", "deployment-manager", "deployments", "update",
                f"{repo_name}-dm",
                "--config", dep_file,
            ],
            cwd=deploy_dir,
            capture_output=True,
            text=True,
            timeout=600,
        )
        logs = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            create_proc = subprocess.run(
                [
                    "gcloud", "deployment-manager", "deployments", "create",
                    f"{repo_name}-dm",
                    "--config", dep_file,
                ],
                cwd=deploy_dir,
                capture_output=True,
                text=True,
                timeout=600,
            )
            logs += "\n" + (create_proc.stdout or "") + (create_proc.stderr or "")
            return {"status": "success" if create_proc.returncode == 0 else "failed", "logs": logs}
        return {"status": "success", "logs": logs}
    except subprocess.TimeoutExpired:
        return {"status": "failed", "logs": "GCP deployment timed out."}


def _clone_path(event: dict, state: DevOpsAgentState) -> str:
    """Return repo clone path (for Lambda packaging etc.)."""
    repo_name = event.get("repo") or (event.get("repo_context") or {}).get("repo") or "unknown"
    branch = (getattr(getattr(state, "repo_context", None), "branch", None) or "main").replace("/", "_")
    return os.path.join(REPO_BASE_PATH, f"{repo_name}_{branch}")


def _package_and_deploy_lambda(clone_path: str, state: DevOpsAgentState, outputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Package application code and deploy to AWS Lambda (after infra apply).
    Config: deployment.target = 'lambda', deployment.lambda_function_name or from Terraform output.
    """
    config = state.repo_context.config or {}
    deployment_cfg = config.get("deployment", {})
    if deployment_cfg.get("target", "").lower() != "lambda" and deployment_cfg.get("type", "").lower() != "lambda":
        return {"status": "skipped", "logs": "Not a Lambda deployment"}
    function_name = deployment_cfg.get("lambda_function_name") or (outputs or {}).get("function_name") or (outputs or {}).get("lambda_function_name")
    if not function_name:
        return {"status": "failed", "logs": "Lambda function name not in config or Terraform outputs"}
    region = (config.get("deployment") or {}).get("region") or (config.get("infrastructure") or {}).get("region") or "us-east-1"
    if not os.path.isdir(clone_path):
        return {"status": "failed", "logs": f"Clone path not found: {clone_path}"}
    import zipfile
    import tempfile
    zip_path = os.path.join(tempfile.gettempdir(), "lambda_deploy.zip")
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(clone_path):
                skip = any(x in root for x in [".git", "node_modules", "__pycache__", ".venv", "venv"])
                if skip:
                    continue
                for f in files:
                    if f.endswith(".zip"):
                        continue
                    path = os.path.join(root, f)
                    zf.write(path, os.path.relpath(path, clone_path))
        proc = subprocess.run(
            ["aws", "lambda", "update-function-code", "--function-name", str(function_name), "--zip-file", f"fileb://{zip_path}", "--region", region],
            capture_output=True,
            text=True,
            timeout=120,
        )
        logs = (proc.stdout or "") + (proc.stderr or "")
        return {"status": "success" if proc.returncode == 0 else "failed", "logs": logs}
    except Exception as e:
        return {"status": "failed", "logs": str(e)}
    finally:
        if os.path.isfile(zip_path):
            try:
                os.remove(zip_path)
            except Exception:
                pass


def deploy_with_terraform(event: dict, state: DevOpsAgentState) -> Dict[str, Any]:
    """
    Deploy for any stack (AWS, GCP, Azure). When user accepted the infra plan (plan_accepted),
    applies infra here (terraform apply / CloudFormation / ARM / GCP). For Lambda, packages
    code and updates the function. Otherwise uses same path as infra agent.
    """
    repo_name = event.get("repo") or (event.get("repo_context") or {}).get("repo") or "unknown"
    config = state.repo_context.config or {}
    deployment_cfg = config.get("deployment", {})
    service_name = deployment_cfg.get("service_name", "default-service")
    version = deployment_cfg.get("version", "latest")
    strategy = deployment_cfg.get("strategy", "standard")

    provider, tool = _get_provider_and_tool(state)
    # If user accepted the infra plan, apply from the path the infra agent wrote to
    plan_accepted = getattr(state.infra, "plan_accepted", False)
    infra_path = getattr(state.infra, "infra_path", None) or ""
    infra_tool = getattr(state.infra, "infra_tool", None)
    if plan_accepted and infra_path and os.path.isdir(infra_path):
        deploy_dir = infra_path
        tool = (infra_tool or tool).strip().lower()
    else:
        deploy_dir = _deploy_base_path(event, state)

    logger.info(f"[Deployment Agent] Deploying repo={repo_name} provider={provider} tool={tool} dir={deploy_dir} (plan_accepted={plan_accepted})")

    # Infra apply only when user accepted the plan; otherwise only Lambda/app deploy if configured
    if not plan_accepted:
        result = {"status": "success", "logs": "User did not accept infra plan; skipping infra apply. Application deploy (e.g. Lambda) may run below."}
    elif not os.path.isdir(deploy_dir):
        msg = f"Deploy directory not found: {deploy_dir}"
        logger.error(f"[Deployment Agent] {msg}")
        state.deployment.status = StatusEnum.FAILED
        state.deployment.logs = msg
        try:
            publish_event(
                topics.ROLLBACK_EVENT,
                RollbackEvent(
                    repo=repo_name,
                    service=service_name,
                    reason="deployment_failed_no_dir",
                    triggered_by="deployment_agent",
                    logs=msg,
                    rollback_to=None,
                ).model_dump(),
            )
        except Exception as e:
            logger.error(f"[Deployment Agent] Failed to publish rollback event: {e}")
        return {"status": "failed", "logs": msg}
    else:
        missing = get_missing_tools()
        if tool == "terraform" and missing:
            msg = f"Missing required tools: {', '.join(missing)}"
            logger.error(f"[Deployment Agent] {msg}")
            state.deployment.status = StatusEnum.FAILED
            state.deployment.logs = msg
            try:
                publish_event(
                    topics.ROLLBACK_EVENT,
                    RollbackEvent(
                        repo=repo_name,
                        service=service_name,
                        reason="deployment_failed_missing_tools",
                        triggered_by="deployment_agent",
                        logs=msg,
                        rollback_to=None,
                    ).model_dump(),
                )
            except Exception as e:
                logger.error(f"[Deployment Agent] Failed to publish rollback event: {e}")
            return {"status": "failed", "logs": msg}

        try:
            publish_event(
                topics.DEPLOYMENT_TRIGGERED,
                DeploymentEvent(
                    repo=repo_name,
                    service_name=service_name,
                    version=version,
                    strategy=strategy,
                    status=StatusEnum.IN_PROGRESS,
                    logs=f"Deployment initiated (provider={provider}, tool={tool})",
                ).model_dump(),
            )
        except Exception as e:
            logger.error(f"[Deployment Agent] Failed to publish in_progress event: {e}")

        if tool == "terraform":
            result = _deploy_terraform(deploy_dir, provider)
        elif tool == "cloudformation":
            result = _deploy_cloudformation(deploy_dir, repo_name)
        elif tool == "arm":
            result = _deploy_arm(deploy_dir, repo_name)
        elif tool == "gcp":
            result = _deploy_gcp_dm(deploy_dir, repo_name)
        else:
            result = {"status": "failed", "logs": f"Unsupported deployment tool: {tool}"}

    state.deployment.logs = result.get("logs", "")
    state.deployment.status = StatusEnum.SUCCESS if result.get("status") == "success" else StatusEnum.FAILED

    # After applying infra (user had accepted plan), publish IAC_READY and clear plan_accepted
    if plan_accepted and state.deployment.status == StatusEnum.SUCCESS:
        state.infra.plan_accepted = False
        state.infra.outputs = result.get("outputs") or {}
        state.infra.status = StatusEnum.SUCCESS
        try:
            from shared_modules.kafka_event_bus.topics import IAC_READY
            out = result.get("outputs") or {}
            publish_event(
                IAC_READY,
                IaCReadyEvent(
                    repo=repo_name,
                    resources=[tool],
                    status=StatusEnum.SUCCESS,
                    logs=(state.deployment.logs or "")[-2000:],
                    outputs={k: str(v) for k, v in out.items()},
                    agent="deployment_agent",
                ).model_dump(),
            )
        except Exception as e:
            logger.warning(f"[Deployment Agent] Publish IAC_READY: {e}")

    # Lambda: package and push code when target is Lambda (e.g. after infra apply)
    if state.deployment.status == StatusEnum.SUCCESS and provider == "aws":
        lambda_result = _package_and_deploy_lambda(_clone_path(event, state), state, result.get("outputs"))
        if lambda_result.get("status") == "success":
            state.deployment.logs = (state.deployment.logs or "") + "\nLambda update: " + (lambda_result.get("logs") or "")
        elif lambda_result.get("status") == "failed":
            state.deployment.logs = (state.deployment.logs or "") + "\nLambda update failed: " + (lambda_result.get("logs") or "")

    try:
        if state.deployment.status == StatusEnum.SUCCESS:
            publish_event(
                topics.DEPLOYMENT_TRIGGERED,
                DeploymentEvent(
                    repo=repo_name,
                    service_name=service_name,
                    version=version,
                    strategy=strategy,
                    status=StatusEnum.SUCCESS,
                    logs=state.deployment.logs[-2000:] if state.deployment.logs else "",
                ).model_dump(),
            )
        else:
            publish_event(
                topics.ROLLBACK_EVENT,
                RollbackEvent(
                    repo=repo_name,
                    service=service_name,
                    reason="deployment_failed",
                    triggered_by="deployment_agent",
                    logs=state.deployment.logs or "",
                    rollback_to=None,
                ).model_dump(),
            )
    except Exception as e:
        logger.error(f"[Deployment Agent] Failed to publish Kafka event: {e}")

    return {
        "status": result.get("status"),
        "logs": state.deployment.logs,
        "outputs": result.get("outputs"),
        "provider": provider,
        "tool": tool,
    }
