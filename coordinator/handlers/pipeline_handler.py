"""
Run the full pipeline via a single LangGraph graph for GitOps + agents (clone → … → test).
Infra generation / deploy stay here because they require Slack plan approval (human-in-the-loop).
Kafka: gitops and agent nodes publish per-step events; state remains the source of truth.
"""
import os
import uuid
from typing import Callable, Optional

from shared_modules.state.devops_state import DevOpsAgentState, StatusEnum, PipelineSkips
from coordinator.slack_logger import (
    log_pipeline_trigger,
    log_pipeline_step,
    log_pipeline_completion,
    log_pipeline_error,
    log_infra_plan,
)
from coordinator.handlers.failure_handler import get_failure_suggestion
from langgraph_flows.pipeline_graph import get_full_pipeline_flow
from langgraph_flows.infra_deploy_graph import get_infra_prepare_graph, get_post_approval_deploy_graph
from agents.rollback_agent.tools.terraform_rollback import rollback_and_publish
from shared_modules.kafka_event_bus.agent_events import publish_pipeline_agent_event
from shared_modules.kafka_event_bus import topics as kafka_topics

REPO_BASE_PATH = os.getenv("REPO_BASE_PATH", "/tmp/gitops_repos")


def _kafka_infra(state: DevOpsAgentState, repo_name: str, status: str, extra: dict) -> None:
    publish_pipeline_agent_event(
        kafka_topics.IAC_READY,
        "iac_agent",
        "infrastructure",
        state.pipeline.pipeline_id,
        repo_name,
        status,
        extra,
    )


def _eval_agent_steps(state: DevOpsAgentState) -> tuple[bool, bool, bool]:
    code_ok = bool(state.code_analysis.passed)
    br = str(state.build_result.status).lower()
    build_ok = br == "success" or state.build_result.status == StatusEnum.SUCCESS
    tr = str(state.test_results.status).lower()
    test_ok = tr == "success" or state.test_results.status == StatusEnum.SUCCESS
    return code_ok, build_ok, test_ok


def _reset_skips_and_retries(state: DevOpsAgentState) -> None:
    state.pipeline.skips = PipelineSkips()
    state.pipeline.last_failed_step = None
    state.build_result.retries = 0
    state.test_results.retries = 0


def _apply_skip_for_failed_agents(state: DevOpsAgentState, code_ok: bool, build_ok: bool, test_ok: bool) -> None:
    if not code_ok:
        state.pipeline.skips.code_analysis = True
    if not build_ok:
        state.pipeline.skips.build = True
    if not test_ok:
        state.pipeline.skips.test = True


def _apply_gitops_skip(state: DevOpsAgentState, step: str) -> None:
    if step == "validate_config":
        state.pipeline.skips.validate_config = True
        state.repo_context.config = state.repo_context.config or {}
    elif step == "repo_size":
        state.pipeline.skips.repo_size = True
    elif step == "license_audit":
        state.pipeline.skips.license_audit = True


def run_pipeline(
    repo_url: str,
    branch: str,
    jira_ticket: Optional[str],
    trigger_source: str,
    pr_number: Optional[str],
    ask_user: Callable[[str], str],
    slack_say: Optional[Callable] = None,
    command_channel: Optional[str] = None,
    thread_ts: Optional[str] = None,
) -> bool:
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    clone_path = os.path.join(REPO_BASE_PATH, f"{repo_name}_{branch.replace('/', '_')}")

    log_pipeline_trigger(repo=repo_name, branch=branch, trigger_source=trigger_source, pr_number=pr_number)

    state = DevOpsAgentState()
    state.pipeline.pipeline_id = str(uuid.uuid4())
    state.pipeline.trigger_type = trigger_source or "unknown"
    state.repo_context.repo = repo_name
    state.repo_context.branch = branch
    state.repo_context.commit = "unknown"

    event_data = {
        "repo_context": state.repo_context.model_dump(),
        "repo": repo_name,
        "pipeline_id": state.pipeline.pipeline_id,
        "repo_url": repo_url,
        "branch": branch,
    }

    if not jira_ticket:
        reply = ask_user("Please provide the Jira ticket number for this run (e.g. `PROJ-123`).")
        jira_ticket = (reply or "").strip() or None
        if not jira_ticket:
            log_pipeline_error("Pipeline", "No Jira ticket provided; skipping test use case.")
            jira_ticket = None

    event_data["jira_ticket"] = jira_ticket
    flow = get_full_pipeline_flow()

    # --- LangGraph: GitOps + agents (single graph, consistent routing & retries) ---
    while True:
        try:
            flow.invoke({"event_data": event_data, "state": state})
        except FileNotFoundError as e:
            log_pipeline_error("Validate config", str(e))
            if "devops_orchestra" not in str(e).lower():
                raise
            reply = ask_user(
                ":x: `devops_orchestra.yaml` not found in repo. Reply *skip* to continue without it, or *retry* after adding the file."
            )
            if "skip" in reply.lower():
                log_pipeline_step("Validate config", "skipped", "User chose to skip")
                state.pipeline.skips.validate_config = True
                state.repo_context.config = {}
                continue
            continue
        except Exception as e:
            step = state.pipeline.last_failed_step or "Pipeline"
            log_pipeline_error(step, str(e))
            if step == "clone":
                _, msg = get_failure_suggestion("Clone", str(e), "")
                reply = ask_user(msg)
                if "skip" in reply.lower():
                    log_pipeline_step("Clone", "skipped", "User chose to skip")
                    return False
                _reset_skips_and_retries(state)
                continue
            _, msg = get_failure_suggestion(step, str(e), "")
            reply = ask_user(msg)
            if "skip" in reply.lower():
                log_pipeline_step(step, "skipped", "User chose to skip")
                _apply_gitops_skip(state, step)
                continue
            if "retry" in reply.lower() or "resolved" in reply.lower():
                _reset_skips_and_retries(state)
                continue
            continue

        code_ok, build_ok, test_ok = _eval_agent_steps(state)
        if code_ok and build_ok and test_ok:
            log_pipeline_step(
                "Pipeline graph",
                "success",
                f"Code analysis: passed={code_ok}; Build: {state.build_result.status}; Test: {state.test_results.status}",
            )
            sonar_errors = getattr(state.code_analysis, "errors", []) or []
            sonar_warnings = getattr(state.code_analysis, "warnings", []) or []
            if sonar_errors or sonar_warnings:
                err_preview = "\n".join(sonar_errors[:8]) if sonar_errors else ""
                warn_preview = "\n".join(sonar_warnings[:8]) if sonar_warnings else ""
                summary = f"*Issues reported by Sonar:* {len(sonar_errors)} error(s), {len(sonar_warnings)} warning(s)."
                if err_preview:
                    summary += f"\n*Errors:*\n```{err_preview[:1200]}```"
                if warn_preview:
                    summary += f"\n*Warnings:*\n```{warn_preview[:1200]}```"
                log_pipeline_step("Sonar", "issues found", summary[:2500])
                reply = ask_user(
                    "Sonar identified the issues above. Would you like to *continue* to infra/deploy or *stop* execution? "
                    "Reply *continue* to proceed, *stop* to abort the pipeline."
                )
                if reply and "stop" in reply.lower().strip():
                    log_pipeline_step("Pipeline", "stopped", "User chose to stop after Sonar issues.")
                    log_pipeline_completion(False, "Stopped by user after Sonar issues.")
                    return False
            break

        failed_parts = []
        if not code_ok:
            failed_parts.append("code analysis")
        if not build_ok:
            failed_parts.append("build")
        if not test_ok:
            failed_parts.append("test")
        error_summary = "Agent flow failed: " + ", ".join(failed_parts)
        logs_parts = []
        if not code_ok and state.code_analysis.logs:
            logs_parts.append(f"Code analysis: {str(state.code_analysis.logs)[:400]}")
        if not build_ok and state.build_result.logs:
            logs_parts.append(f"Build: {(state.build_result.logs or '')[:400]}")
        if not test_ok and state.test_results.logs:
            logs_parts.append(f"Test: {str(state.test_results.logs)[:400]}")
        logs_snippet = "\n".join(logs_parts) or error_summary

        log_pipeline_error("Agent flow", error_summary, logs_snippet[:1500])
        _, msg = get_failure_suggestion("Agent flow", error_summary, logs_snippet)
        reply = ask_user(msg)
        if "skip" in reply.lower():
            log_pipeline_step("Agent flow", "skipped", "User chose to skip failed step(s) and continue")
            _apply_skip_for_failed_agents(state, code_ok, build_ok, test_ok)
            flow.invoke({"event_data": event_data, "state": state})
            code_ok, build_ok, test_ok = _eval_agent_steps(state)
            if code_ok and build_ok and test_ok:
                log_pipeline_step(
                    "Pipeline graph",
                    "success",
                    "Skipped failed stages; downstream steps completed.",
                )
            break
        if "retry" in reply.lower() or "resolved" in reply.lower():
            _reset_skips_and_retries(state)
            continue

    # --- Infra prepare (LangGraph) → Slack approval → deploy (second LangGraph) ---
    infra_prepare = get_infra_prepare_graph()
    deploy_flow = get_post_approval_deploy_graph()

    while True:
        try:
            infra_prepare.invoke({"event_data": event_data, "state": state})
        except Exception as e:
            log_pipeline_error("Infrastructure", str(e))
            _, msg = get_failure_suggestion("Infrastructure", str(e), "")
            reply = ask_user(msg)
            if "skip" in reply.lower():
                log_pipeline_step("Infrastructure", "skipped", "User chose to skip and continue")
                break
            continue

        if state.infra.status == StatusEnum.IN_PROGRESS:
            log_infra_plan(repo_name, state.infra.infra_tool or "terraform", state.infra.plan_output or "")
            reply = ask_user(
                "Infrastructure plan was sent to the pipeline logs channel. "
                "Reply *yes* or *apply* to have the deployment agent create resources, or *skip* to continue without applying."
            )
            if reply and reply.lower().strip() in ("yes", "apply"):
                state.infra.plan_accepted = True
                log_pipeline_step("Infrastructure", "success", "User accepted plan; deployment agent will apply.")
            else:
                state.infra.plan_accepted = False
                log_pipeline_step("Infrastructure", "skipped", "User chose not to apply; plan saved.")
            _kafka_infra(state, repo_name, "plan_ready", {"plan_accepted": bool(state.infra.plan_accepted)})
            break

        if state.infra.status == StatusEnum.SUCCESS:
            log_pipeline_step("Infrastructure", "success", (state.infra.logs or "")[:500])
            _kafka_infra(state, repo_name, "success", {})
            break

        log_pipeline_step("Infrastructure", "failed", (state.infra.logs or "")[:500])
        _, msg = get_failure_suggestion("Infrastructure", state.infra.logs or "Infra failed", state.infra.logs or "")
        reply = ask_user(msg)
        if "skip" in reply.lower():
            log_pipeline_step("Infrastructure", "skipped", "User chose to skip and continue")
            break
        continue

    while True:
        try:
            deploy_flow.invoke({"event_data": event_data, "state": state})
            log_pipeline_step("Deployment", state.deployment.status, (state.deployment.logs or "")[:500])
            ds = state.deployment.status
            if ds == StatusEnum.SUCCESS or str(ds).lower() == "success":
                publish_pipeline_agent_event(
                    kafka_topics.DEPLOYMENT_TRIGGERED,
                    "deployment_agent",
                    "deploy",
                    state.pipeline.pipeline_id,
                    repo_name,
                    "success",
                    {"logs_excerpt": (state.deployment.logs or "")[:500]},
                )
                break
            # deploy graph already ran rollback node when deploy failed
            _, msg = get_failure_suggestion("Deployment", state.deployment.logs or "Deploy failed", state.deployment.logs or "")
            reply = ask_user(msg)
            if "skip" in reply.lower():
                log_pipeline_step("Deployment", "skipped", "User chose to skip and continue")
                break
            continue
        except Exception as e:
            log_pipeline_error("Deployment", str(e))
            try:
                rollback_and_publish(event_data, state)
            except Exception:
                pass
            log_pipeline_step("Rollback", "run", "Deployment failed; rollback executed.")
            _, msg = get_failure_suggestion("Deployment", str(e), "")
            reply = ask_user(msg)
            if "skip" in reply.lower():
                log_pipeline_step("Deployment", "skipped", "User chose to skip and continue")
                break
            continue

    log_pipeline_completion(True, f"Repo: {repo_name} Branch: {branch}")
    return True
