"""
Run the full pipeline: clone → validate → repo size → license audit → [LangGraph DAG: code analysis → build → test] → infra → deploy.
Agent steps (code analysis, build, test) run via LangGraph pipeline_agent flow; infra/deploy run in pipeline with ask_user.
Logs to pipeline logs channel; on failure asks user (skip/retry/resolved).
"""
import os
import sys
import shutil
import httpx
from typing import Callable, Optional, Any
from shared_modules.utils.config_loader import load_yaml
from shared_modules.state.devops_state import DevOpsAgentState, StatusEnum
from shared_modules.utils.logger import logger
from agents.code_analysis_agent.tools.llm_code_analyzer import analyze_code_with_llm
from coordinator.slack_logger import (
    log_pipeline_trigger,
    log_pipeline_step,
    log_pipeline_completion,
    log_pipeline_error,
    log_infra_plan,
)
from coordinator.handlers.failure_handler import get_failure_suggestion
from langgraph_flows import get_all_flows
from agents.infrastructure_agent.tools.llm_infra_generator import generate_infrastructure_with_llm

# Add project root for imports
REPO_BASE_PATH = os.getenv("REPO_BASE_PATH", "/tmp/gitops_repos")
TOOL_SERVER_URL = os.getenv("TOOL_SERVER_URL", "http://localhost:8001/invoke")


def _call_tool(tool_name: str, input_payload: dict) -> dict:
    try:
        r = httpx.post(TOOL_SERVER_URL, json={"tool_name": tool_name, "input": input_payload}, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"status": "error", "output": {"message": str(e)}}


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
    """
    Run full pipeline. ask_user(question) blocks and returns user reply.
    Returns True if pipeline completed successfully.
    """
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    clone_path = os.path.join(REPO_BASE_PATH, f"{repo_name}_{branch.replace('/', '_')}")

    log_pipeline_trigger(repo=repo_name, branch=branch, trigger_source=trigger_source, pr_number=pr_number)

    state = DevOpsAgentState()
    state.repo_context.repo = repo_name
    state.repo_context.branch = branch
    state.repo_context.commit = "unknown"
    event_data = {"repo_context": state.repo_context.model_dump(), "repo": repo_name}

    # ask_user(question): coordinator posts question to command channel and blocks until user reply; returns reply text.
    # Resolve Jira ticket if missing
    if not jira_ticket:
        reply = ask_user("Please provide the Jira ticket number for this run (e.g. `PROJ-123`).")
        jira_ticket = (reply or "").strip() or None
        if not jira_ticket:
            log_pipeline_error("Pipeline", "No Jira ticket provided; skipping test use case.")
            jira_ticket = None

    # 1. Clone
    while True:
        try:
            if os.path.exists(clone_path):
                shutil.rmtree(clone_path)
            result = _call_tool("clone_repo", {"repo_url": repo_url, "branch": branch, "clone_path": clone_path})
            if result.get("status") != "success":
                raise RuntimeError(result.get("output", {}).get("message", "Clone failed"))
            log_pipeline_step("Clone", "success", f"Cloned {branch} to {clone_path}")
            break
        except Exception as e:
            log_pipeline_error("Clone", str(e))
            _, msg = get_failure_suggestion("Clone", str(e), "")
            reply = ask_user(msg)
            if "skip" in reply.lower():
                log_pipeline_step("Clone", "skipped", "User chose to skip")
                return False  # Cannot continue pipeline without clone
            # retry or resolved: loop again

    # 2. Validate devops_orchestra.yaml
    config_path = os.path.join(clone_path, "devops_orchestra.yaml")
    while True:
        if not os.path.isfile(config_path):
            log_pipeline_error("Validate config", "devops_orchestra.yaml not found")
            reply = ask_user(":x: `devops_orchestra.yaml` not found in repo. Reply *skip* to continue without it, or *retry* after adding the file.")
            if "skip" in reply.lower():
                log_pipeline_step("Validate config", "skipped", "User chose to skip")
                state.repo_context.config = {}
                break
            continue
        result = _call_tool("config_validator", {"config_path": config_path})
        if result.get("status") != "success":
            log_pipeline_error("Validate config", result.get("output", {}).get("message", "Validation failed"))
            _, msg = get_failure_suggestion("Validate config", result.get("output", {}).get("message", "Validation failed"), "")
            reply = ask_user(msg)
            if "skip" in reply.lower():
                log_pipeline_step("Validate config", "skipped", "User chose to skip")
                state.repo_context.config = {}
                break
            continue
        log_pipeline_step("Validate config", "success")
        state.repo_context.config = load_yaml(config_path)
        break

    # 3. Repo size
    while True:
        try:
            result = _call_tool("repo_size", {"repo_path": clone_path})
            if result.get("status") != "success":
                raise RuntimeError(result.get("output", {}).get("message", "Repo size failed"))
            size_mb = result.get("output", {}).get("repo_size_mb")
            state.repo_context.size_mb = size_mb
            log_pipeline_step("Repo size", "success", f"Repository size: {size_mb} MB")
            break
        except Exception as e:
            log_pipeline_error("Repo size", str(e))
            _, msg = get_failure_suggestion("Repo size", str(e), "")
            reply = ask_user(msg)
            if "skip" in reply.lower():
                log_pipeline_step("Repo size", "skipped", "User chose to skip")
                break
            # retry or resolved: loop again

    # 4. License audit
    while True:
        try:
            result = _call_tool("license_audit", {"repo_path": clone_path})
            if result.get("status") != "success":
                raise RuntimeError(result.get("output", {}).get("message", "License audit failed"))
            licenses = result.get("output", {}).get("licenses", [])
            summary = f"Found {len(licenses)} dependency set(s) audited (pip/node/maven)."
            log_pipeline_step("License audit", "success", summary)
            break
        except Exception as e:
            log_pipeline_error("License audit", str(e))
            _, msg = get_failure_suggestion("License audit", str(e), "")
            reply = ask_user(msg)
            if "skip" in reply.lower():
                log_pipeline_step("License audit", "skipped", "User chose to skip")
                break
            # retry or resolved: loop again

    # 5. Agent flow (LangGraph DAG: code_analysis → build → test)
    while True:
        try:
            event_data["jira_ticket"] = jira_ticket
            flow = get_all_flows()["pipeline_agent"]
            flow.invoke({"event_data": event_data, "state": state})

            # Check if any step failed after retries (same skip/retry/resolve as other steps)
            code_ok = state.code_analysis.passed
            build_ok = getattr(state.build_result, "status", None) == StatusEnum.SUCCESS or state.build_result.status == "success"
            test_ok = getattr(state.test_results, "status", None) == StatusEnum.SUCCESS or state.test_results.status == "success"

            if code_ok and build_ok and test_ok:
                log_pipeline_step(
                    "Agent flow (code analysis, build, test)",
                    "success",
                    f"Code analysis: passed; Build: {state.build_result.status}; Test: {state.test_results.status}",
                )
                # Sonar found issues (non-blocking): notify user and ask continue or stop
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

            # One or more steps failed after retries — ask user like other steps
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
                log_pipeline_step("Agent flow", "skipped", "User chose to skip and continue")
                break
            # retry or resolved: loop again
        except Exception as e:
            log_pipeline_error("Agent flow", str(e))
            _, msg = get_failure_suggestion("Agent flow", str(e), "")
            reply = ask_user(msg)
            if "skip" in reply.lower():
                log_pipeline_step("Agent flow", "skipped", "User chose to skip and continue")
                break
            # retry or resolved: loop again

    # 6. Infra (generate code + init + plan only; no apply — deployment agent applies after user accepts)
    while True:
        try:
            r = generate_infrastructure_with_llm(event_data, state)
            status = r.get("status")
            state.infra.logs = r.get("logs", "")

            if status == "plan_ready":
                # Send plan and code to Slack for user review
                log_infra_plan(repo_name, r.get("tool", "terraform"), r.get("plan_output") or "")
                reply = ask_user(
                    "Infrastructure plan was sent to the pipeline logs channel. "
                    "Reply *yes* or *apply* to have the deployment agent create resources, or *skip* to continue without applying."
                )
                if reply and reply.lower().strip() in ("yes", "apply"):
                    state.infra.plan_accepted = True
                    state.infra.infra_path = r.get("infra_path", "")
                    state.infra.infra_tool = r.get("tool", "terraform")
                    state.infra.status = StatusEnum.SUCCESS
                    log_pipeline_step("Infrastructure", "success", "User accepted plan; deployment agent will apply.")
                else:
                    log_pipeline_step("Infrastructure", "skipped", "User chose not to apply; plan saved.")
                break

            if status == "success":
                log_pipeline_step("Infrastructure", "success", (state.infra.logs or "")[:500])
                break

            log_pipeline_step("Infrastructure", "failed", (state.infra.logs or "")[:500])
            _, msg = get_failure_suggestion("Infrastructure", state.infra.logs or "Infra failed", state.infra.logs or "")
            reply = ask_user(msg)
            if "skip" in reply.lower():
                log_pipeline_step("Infrastructure", "skipped", "User chose to skip and continue")
                break
        except Exception as e:
            log_pipeline_error("Infrastructure", str(e))
            _, msg = get_failure_suggestion("Infrastructure", str(e), "")
            reply = ask_user(msg)
            if "skip" in reply.lower():
                log_pipeline_step("Infrastructure", "skipped", "User chose to skip and continue")
                break

    # 7. Deploy
    while True:
        try:
            from agents.deployment_agent.tools.terraform_deployer import deploy_with_terraform
            deploy_with_terraform(event_data, state)
            log_pipeline_step("Deployment", state.deployment.status, (state.deployment.logs or "")[:500])
            if state.deployment.status == "success":
                break
            from agents.rollback_agent.tools.terraform_rollback import rollback_and_publish
            rollback_and_publish(event_data, state)
            log_pipeline_step("Rollback", "run", "Deployment failed; rollback executed.")
            _, msg = get_failure_suggestion("Deployment", state.deployment.logs or "Deploy failed", state.deployment.logs or "")
            reply = ask_user(msg)
            if "skip" in reply.lower():
                log_pipeline_step("Deployment", "skipped", "User chose to skip and continue")
                break
        except Exception as e:
            log_pipeline_error("Deployment", str(e))
            try:
                from agents.rollback_agent.tools.terraform_rollback import rollback_and_publish
                rollback_and_publish(event_data, state)
            except Exception:
                pass
            log_pipeline_step("Rollback", "run", "Deployment failed; rollback executed.")
            _, msg = get_failure_suggestion("Deployment", str(e), "")
            reply = ask_user(msg)
            if "skip" in reply.lower():
                log_pipeline_step("Deployment", "skipped", "User chose to skip and continue")
                break

    log_pipeline_completion(True, f"Repo: {repo_name} Branch: {branch}")
    return True
