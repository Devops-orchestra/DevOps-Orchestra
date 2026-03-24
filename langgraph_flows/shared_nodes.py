"""LangGraph node implementations shared across pipelines (index, build, test, deploy).
Each node updates DevOpsAgentState and publishes Kafka step events.
"""
import os
from shared_modules.state.devops_state import DevOpsAgentState, StatusEnum
from shared_modules.utils.logger import logger
from coordinator.slack_logger import log_pipeline_step, send_pipeline_log
from agents.indexing_agent.tools.repo_indexer import build_repo_index
from agents.code_analysis_agent.tools.llm_code_analyzer import analyze_code_with_llm
from agents.build_agent.tools.builder import build_and_push_image
from agents.test_agent.tools.llm_test_generator import (
    MAX_RETRY_CODE_CHARS,
    MAX_RETRY_LOG_CHARS,
    generate_tests_with_llm,
    run_tests_for_language,
)
from agents.infrastructure_agent.tools.llm_infra_generator import generate_infrastructure_with_llm
from agents.deployment_agent.tools.terraform_deployer import deploy_with_terraform
from agents.rollback_agent.tools.terraform_rollback import rollback_and_publish
from agents.observability_agent.tools.monitor import monitor_and_alert
from shared_modules.kafka_event_bus.agent_events import publish_pipeline_agent_event
from shared_modules.kafka_event_bus import topics as kafka_topics

REPO_BASE_PATH = os.getenv("REPO_BASE_PATH", "/tmp/gitops_repos")


def _kafka_agent(
    topic: str,
    agent: str,
    state: DevOpsAgentState,
    step: str,
    status: str,
    extra: dict | None = None,
) -> None:
    repo = state.repo_context.repo or "unknown"
    publish_pipeline_agent_event(
        topic,
        agent,
        step,
        state.pipeline.pipeline_id,
        repo,
        status,
        extra,
    )


def _slack_agent_started(label: str) -> None:
    """Pipeline logs channel: agent step started (transition)."""
    send_pipeline_log(f":arrow_forward: *{label}* — started")


def _slack_agent_finished(step_name: str, ok: bool, details: str) -> None:
    """Pipeline logs channel: agent step outcome."""
    status = "success" if ok else "failed"
    log_pipeline_step(step_name, status, (details or "")[:1900])


def _clone_path_from_state(event_data: dict, state) -> str:
    """Same convention as pipeline: REPO_BASE_PATH / repo_name_branch."""
    if getattr(state, "git_meta", None) and state.git_meta.local_path:
        p = state.git_meta.local_path
        if os.path.isdir(p):
            return p
    repo_name = event_data.get("repo") or (event_data.get("repo_context") or {}).get("repo") or "repo"
    branch = (getattr(getattr(state, "repo_context", None), "branch", None) or "main").replace("/", "_")
    return os.path.join(REPO_BASE_PATH, f"{repo_name}_{branch}")


def run_index_repo_node(inputs: dict) -> dict:
    """
    Index cloned repository (AST, call hints, optional Chroma) after GitOps, before code analysis.
    Failures are logged on state.index but do not abort the graph.
    """
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    state.current_agent = "indexing_agent"
    repo_path = _clone_path_from_state(event, state)
    _slack_agent_started("Indexing")
    try:
        build_repo_index(repo_path, state)
    except Exception as e:
        logger.error(f"[Indexing Agent] Exception: {e}")
        state.index.status = StatusEnum.FAILED
        state.index.logs.append(str(e))
    idx_ok = state.index.status == StatusEnum.SUCCESS
    detail_parts = [
        f"path: `{repo_path}`",
        f"files: {state.index.file_count}, symbols: {state.index.symbol_count}",
        f"vector: {state.index.embedding_backend or 'none'}",
    ]
    if state.index.logs:
        detail_parts.append("; ".join(state.index.logs[-3:]))
    _slack_agent_finished("Indexing", idx_ok, "\n".join(detail_parts))
    _kafka_agent(
        kafka_topics.GITOPS_PIPELINE,
        "indexing_agent",
        state,
        "index_repo",
        "success" if idx_ok else "failed",
        {"symbols": state.index.symbol_count, "files": state.index.file_count},
    )
    return {"event_data": event, "state": state}


def run_code_analysis_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    if state.pipeline.skips.code_analysis:
        state.code_analysis.passed = True
        prev = list(state.code_analysis.logs or [])
        prev.append("Skipped by user (pipeline flag).")
        state.code_analysis.logs = prev
        _slack_agent_finished("Code analysis", True, "Skipped by user")
        _kafka_agent(kafka_topics.CODE_ANALYSIS, "code_analysis_agent", state, "sonar", "skipped", {})
        return {"event_data": event, "state": state}
    _slack_agent_started("Code analysis")
    try:
        analyze_code_with_llm(event, state)
    except Exception as e:
        logger.error(f"[Code Analysis Agent] Exception during Analysis: {e}")
        state.code_analysis.passed = False
        state.code_analysis.logs = [str(e)]
    ca_ok = bool(state.code_analysis.passed)
    n_err = len(state.code_analysis.errors or [])
    n_warn = len(state.code_analysis.warnings or [])
    details = f"Sonar/analysis: passed={ca_ok}, errors={n_err}, warnings={n_warn}"
    if state.code_analysis.logs:
        details += "\n" + "\n".join(str(x) for x in state.code_analysis.logs[-2:])
    _slack_agent_finished("Code analysis", ca_ok, details)
    _kafka_agent(
        kafka_topics.CODE_ANALYSIS,
        "code_analysis_agent",
        state,
        "sonar",
        "success" if ca_ok else "failed",
        {"errors": n_err, "warnings": n_warn},
    )
    return {"event_data": event, "state": state}

def run_build_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    if state.pipeline.skips.build:
        state.build_result.status = "success"
        state.build_result.logs = "Skipped by user (pipeline flag)."
        _slack_agent_finished("Build", True, "Skipped by user")
        _kafka_agent(kafka_topics.BUILD_READY, "build_agent", state, "docker_build", "skipped", {})
        return {"event_data": event, "state": state}
    _slack_agent_started("Build")
    try:
        build_and_push_image(event, state)
    except Exception as e:
        logger.error(f"[Build Agent] Exception during build: {e}")
        state.build_result.status = "failed"
        state.build_result.logs = str(e)
    br = str(state.build_result.status).lower()
    build_ok = br in ("success", StatusEnum.SUCCESS.value)
    img = state.build_result.image_url or "n/a"
    tail = (state.build_result.logs or "")[-800:] if state.build_result.logs else ""
    details = f"image: `{img}`\n{tail}" if tail else f"image: `{img}`"
    _slack_agent_finished("Build", build_ok, details)
    _kafka_agent(
        kafka_topics.BUILD_READY,
        "build_agent",
        state,
        "docker_build",
        "success" if build_ok else "failed",
        {"image": img},
    )
    return {"event_data": event, "state": state}



def run_tests_node(inputs: dict) -> dict:
    state: DevOpsAgentState = inputs["state"]
    event = inputs["event_data"]
    repo_path = _clone_path_from_state(event, state)
    jira_ticket = event.get("jira_ticket")

    if state.pipeline.skips.test:
        state.test_results.status = StatusEnum.SUCCESS
        state.test_results.logs = ["Skipped by user (pipeline flag)."]
        state.test_results.total = 0
        state.test_results.passed = 0
        state.test_results.failed = 0
        _slack_agent_finished("Test", True, "Skipped by user")
        _kafka_agent(kafka_topics.TEST_RESULTS, "test_agent", state, "pytest", "skipped", {})
        return {"event_data": event, "state": state}

    _slack_agent_started("Test")
    test_code = ""
    result = None
    try:
        test_code = generate_tests_with_llm(repo_path, state, jira_ticket=jira_ticket)
        result = run_tests_for_language(repo_path, test_code, state)

        failed_count = result.total - result.passed
        state.test_results.status = "success" if result.passed else "failed"
        state.test_results.logs = result.logs
        state.test_results.total = result.total
        state.test_results.passed = result.passed
        state.test_results.failed = failed_count
        state.test_results.coverage = result.coverage

    except Exception as e:
        logger.error(f"[Test Agent] Test execution failed: {e}")
        state.test_results.status = "failed"
        state.test_results.logs = str(e)

    tr = str(state.test_results.status).lower()
    test_ok = tr in ("success", StatusEnum.SUCCESS.value)

    if test_ok:
        state.test_results.last_generated_code = None
        state.test_results.last_run_failure_logs = None
    else:
        if test_code:
            state.test_results.last_generated_code = test_code[:MAX_RETRY_CODE_CHARS]
        logs_for_retry = ""
        if result is not None and getattr(result, "logs", None):
            logs_for_retry = str(result.logs)
        elif state.test_results.logs:
            if isinstance(state.test_results.logs, list):
                logs_for_retry = "\n".join(str(x) for x in state.test_results.logs)
            else:
                logs_for_retry = str(state.test_results.logs)
        state.test_results.last_run_failure_logs = logs_for_retry[:MAX_RETRY_LOG_CHARS]
    log_tail = ""
    if state.test_results.logs:
        if isinstance(state.test_results.logs, list):
            log_tail = "\n".join(str(x) for x in state.test_results.logs[-5:])
        else:
            log_tail = str(state.test_results.logs)[-1200:]
    details = f"path: `{repo_path}`\npassed {state.test_results.passed}/{state.test_results.total} tests"
    if log_tail:
        details += f"\n{log_tail}"
    _slack_agent_finished("Test", test_ok, details)
    _kafka_agent(
        kafka_topics.TEST_RESULTS,
        "test_agent",
        state,
        "pytest",
        "success" if test_ok else "failed",
        {"passed": state.test_results.passed, "total": state.test_results.total},
    )

    return {"event_data": event, "state": state}

def run_infra_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    _slack_agent_started("Infrastructure")
    try:
        result = generate_infrastructure_with_llm(event, state)
        state.infra.status = "success" if result.get("status") == "success" else "failed"
        state.infra.resources = result.get("resources")
        state.infra.outputs = result.get("outputs")
        state.infra.logs = result.get("logs", "")
    except Exception as e:
        logger.error(f"[Infra Agent] Exception during infra provisioning: {e}")
        state.infra.status = "failed"
        state.infra.outputs = {}
        state.infra.logs = str(e)
    inf_ok = state.infra.status == StatusEnum.SUCCESS or str(state.infra.status).lower() == "success"
    _slack_agent_finished("Infrastructure", inf_ok, (state.infra.logs or "")[:1900])
    return {"event_data": event, "state": state}

def run_deploy_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    _slack_agent_started("Deployment")
    try:
        result = deploy_with_terraform(event, state)
        if result.get("status") != "success":
            logger.error("[Deployment Agent] Deployment failed; will allow flow to branch to rollback.")
    except Exception as e:
        logger.error(f"[Deployment Agent] Exception during deployment: {e}")
        state.deployment.status = "failed"
        state.deployment.logs = str(e)
    dep_ok = state.deployment.status == StatusEnum.SUCCESS or str(state.deployment.status).lower() == "success"
    _slack_agent_finished("Deployment", dep_ok, (state.deployment.logs or "")[:1900])
    return {"event_data": event, "state": state}

def run_rollback_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    try:
        rollback_and_publish(event, state)
    except Exception as e:
        logger.error(f"[Rollback Agent] Exception during rollback: {e}")
    return {"event_data": event, "state": state}

def run_observability_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    try:
        result = monitor_and_alert(event, state)
        if result.get("status") == "success":
            logger.info(f"[Observability Agent] Monitoring completed. Alerts: {result.get('alerts_count', 0)}")
        else:
            logger.error(f"[Observability Agent] Monitoring failed: {result.get('error')}")
    except Exception as e:
        logger.error(f"[Observability Agent] Exception during monitoring: {e}")
    return {"event_data": event, "state": state}
