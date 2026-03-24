"""
GitOps stages as LangGraph nodes (clone, validate config, repo size, license, git metadata).
Uses shared tool server via shared_modules.pipeline.tool_client.
"""
import os
import shutil

from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.utils.logger import logger
from shared_modules.utils.config_loader import load_yaml
from shared_modules.utils.git_metadata import populate_git_metadata
from shared_modules.pipeline.tool_client import call_tool
from shared_modules.kafka_event_bus.agent_events import publish_pipeline_agent_event
from shared_modules.kafka_event_bus import topics as kafka_topics
from coordinator.slack_logger import log_pipeline_step

REPO_BASE_PATH = os.getenv("REPO_BASE_PATH", "/tmp/gitops_repos")


def _gitops_publish(state: DevOpsAgentState, step: str, status: str, extra: dict | None = None) -> None:
    repo = state.repo_context.repo or "unknown"
    publish_pipeline_agent_event(
        kafka_topics.GITOPS_PIPELINE,
        "gitops_agent",
        step,
        state.pipeline.pipeline_id,
        repo,
        status,
        extra,
    )


def _clone_path(repo_name: str, branch: str) -> str:
    return os.path.join(REPO_BASE_PATH, f"{repo_name}_{branch.replace('/', '_')}")


def run_clone_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    state.current_agent = "gitops_agent"
    repo_url = event.get("repo_url") or ""
    branch = (event.get("branch") or state.repo_context.branch or "main").strip()
    repo_name = state.repo_context.repo or repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    clone_path = _clone_path(repo_name, branch)

    try:
        if os.path.exists(clone_path):
            shutil.rmtree(clone_path)
        result = call_tool(
            "clone_repo",
            {"repo_url": repo_url, "branch": branch, "clone_path": clone_path},
        )
        if result.get("status") != "success":
            raise RuntimeError(result.get("output", {}).get("message", "Clone failed"))
        state.git_meta.local_path = clone_path
        state.git_meta.branch = branch
        state.repo_context.repo = repo_name
        state.repo_context.branch = branch
        state.pipeline.last_failed_step = None
        log_pipeline_step("Clone", "success", f"Cloned {branch} to {clone_path}")
        _gitops_publish(state, "clone", "success", {"path": clone_path})
    except Exception as e:
        logger.error(f"[GitOps] Clone failed: {e}")
        state.pipeline.last_failed_step = "clone"
        _gitops_publish(state, "clone", "failed", {"error": str(e)})
        raise

    return {"event_data": event, "state": state}


def run_validate_config_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    state.current_agent = "gitops_agent"
    clone_path = state.git_meta.local_path
    if not clone_path:
        raise RuntimeError("Clone path not set")
    config_path = os.path.join(clone_path, "devops_orchestra.yaml")

    if state.pipeline.skips.validate_config:
        state.repo_context.config = state.repo_context.config or {}
        log_pipeline_step("Validate config", "skipped", "User skip flag")
        _gitops_publish(state, "validate_config", "skipped", {})
        return {"event_data": event, "state": state}

    if not os.path.isfile(config_path):
        state.pipeline.last_failed_step = "validate_config"
        raise FileNotFoundError("devops_orchestra.yaml not found")

    result = call_tool("config_validator", {"config_path": config_path})
    if result.get("status") != "success":
        state.pipeline.last_failed_step = "validate_config"
        raise RuntimeError(result.get("output", {}).get("message", "Validation failed"))
    state.repo_context.config = load_yaml(config_path)
    state.pipeline.last_failed_step = None
    log_pipeline_step("Validate config", "success", "")
    _gitops_publish(state, "validate_config", "success", {})
    return {"event_data": event, "state": state}


def run_repo_size_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    clone_path = state.git_meta.local_path
    if not clone_path:
        raise RuntimeError("Clone path not set")

    if state.pipeline.skips.repo_size:
        log_pipeline_step("Repo size", "skipped", "User skip flag")
        _gitops_publish(state, "repo_size", "skipped", {})
        return {"event_data": event, "state": state}

    result = call_tool("repo_size", {"repo_path": clone_path})
    if result.get("status") != "success":
        state.pipeline.last_failed_step = "repo_size"
        raise RuntimeError(result.get("output", {}).get("message", "Repo size failed"))
    size_mb = result.get("output", {}).get("repo_size_mb")
    state.repo_context.size_mb = size_mb
    log_pipeline_step("Repo size", "success", f"Repository size: {size_mb} MB")
    _gitops_publish(state, "repo_size", "success", {"size_mb": size_mb})
    return {"event_data": event, "state": state}


def run_license_audit_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    clone_path = state.git_meta.local_path
    if not clone_path:
        raise RuntimeError("Clone path not set")

    if state.pipeline.skips.license_audit:
        log_pipeline_step("License audit", "skipped", "User skip flag")
        _gitops_publish(state, "license_audit", "skipped", {})
        return {"event_data": event, "state": state}

    result = call_tool("license_audit", {"repo_path": clone_path})
    if result.get("status") != "success":
        state.pipeline.last_failed_step = "license_audit"
        raise RuntimeError(result.get("output", {}).get("message", "License audit failed"))
    licenses = result.get("output", {}).get("licenses", [])
    summary = f"Found {len(licenses)} dependency set(s) audited (pip/node/maven)."
    log_pipeline_step("License audit", "success", summary)
    _gitops_publish(state, "license_audit", "success", {"sets": len(licenses)})
    return {"event_data": event, "state": state}


def run_git_metadata_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    clone_path = state.git_meta.local_path
    branch = state.repo_context.branch or "main"
    if not clone_path:
        raise RuntimeError("Clone path not set")
    populate_git_metadata(state, clone_path, branch)
    log_pipeline_step(
        "Git metadata",
        "success",
        (state.git_meta.diff_summary or "No summary")[:900],
    )
    _gitops_publish(
        state,
        "git_metadata",
        "success",
        {"changed_files": len(state.git_meta.changed_files or [])},
    )
    return {"event_data": event, "state": state}
