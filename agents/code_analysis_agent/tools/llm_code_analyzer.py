"""
Code analysis agent: run SonarQube for validation and surface suggestions.

Behavior:
- Uses SonarQube (sonar-scanner + REST API) instead of pure LLM for validation.
- Stores issues/suggestions in state.code_analysis.{errors,warnings,logs}.
- Publishes CodeAnalysisEvent with summarized issues.

Required configuration (environment variables):

Self-hosted SonarQube (e.g. docker-compose):
- SONAR_HOST_URL: e.g. http://sonarqube:9000
- SONAR_TOKEN:    user token with analysis permissions
- Optional: SONAR_PROJECT_KEY (defaults to "{repo}_{branch}")

SonarCloud (free cloud; no server to run):
- SONAR_HOST_URL: https://sonarcloud.io
- SONAR_TOKEN:    token from SonarCloud (Project → Administration → Analysis Method)
- SONAR_ORGANIZATION: your SonarCloud organization key
- Optional: SONAR_PROJECT_KEY (must match key created on SonarCloud)
"""

import os
import subprocess
import json
from typing import List, Dict, Any

import requests

from shared_modules.utils.logger import logger
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus.event_schema import CodeAnalysisEvent
from shared_modules.kafka_event_bus.topics import CODE_ANALYSIS

REPO_BASE_PATH = os.getenv("REPO_BASE_PATH", "/tmp/gitops_repos")


def _repo_path_from_state(event: dict, state: DevOpsAgentState) -> str:
    """Use same clone convention as pipeline: REPO_BASE_PATH / repo_branch."""
    repo = event["repo_context"]["repo"]
    branch = event["repo_context"]["branch"] or "main"
    branch_safe = branch.replace("/", "_")
    return os.path.join(REPO_BASE_PATH, f"{repo}_{branch_safe}")


def _run_sonar_scanner(repo_path: str, repo: str, branch: str) -> Dict[str, Any]:
    host = os.getenv("SONAR_HOST_URL", "").strip()
    token = os.getenv("SONAR_TOKEN", "").strip()
    project_key = os.getenv("SONAR_PROJECT_KEY", f"{repo}_{branch.replace('/', '_')}")
    organization = os.getenv("SONAR_ORGANIZATION", "").strip()

    if not host or not token:
        msg = "Sonar not configured (SONAR_HOST_URL/SONAR_TOKEN missing). Use SonarCloud (free) or self-hosted."
        logger.warning(f"[Code Analysis] {msg}")
        return {"status": "failed", "logs": msg, "project_key": project_key}

    cmd = [
        "sonar-scanner",
        f"-Dsonar.projectKey={project_key}",
        f"-Dsonar.sources=.",
        f"-Dsonar.host.url={host}",
        f"-Dsonar.login={token}",
    ]
    if organization:
        cmd.append(f"-Dsonar.organization={organization}")
    logger.info(f"[Code Analysis] Running scan in {repo_path} projectKey={project_key} host={host}")
    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=900,
        )
        logs = (proc.stdout or "") + "\n" + (proc.stderr or "")
        # Exit code 0 = success. Exit code 1 often means quality gate failed or issues found;
        # we still treat as success so we fetch issues and let the user choose continue/stop.
        if proc.returncode == 0:
            status = "success"
        elif "Analyzing on SonarCloud" in logs or "Server id:" in logs:
            status = "success"
        else:
            status = "failed"
        return {"status": status, "logs": logs, "project_key": project_key, "host": host, "token": token}
    except subprocess.TimeoutExpired:
        msg = "SonarQube scan timed out."
        logger.error(f"[Code Analysis] {msg}")
        return {"status": "failed", "logs": msg, "project_key": project_key, "host": host, "token": token}
    except FileNotFoundError:
        msg = "sonar-scanner not found in PATH inside container."
        logger.error(f"[Code Analysis] {msg}")
        return {"status": "failed", "logs": msg, "project_key": project_key, "host": host, "token": token}
    except Exception as e:
        msg = f"SonarQube scan error: {e}"
        logger.error(f"[Code Analysis] {msg}")
        return {"status": "failed", "logs": msg, "project_key": project_key, "host": host, "token": token}


def _fetch_sonar_issues(host: str, token: str, project_key: str, page_size: int = 50) -> List[Dict[str, Any]]:
    """Fetch top issues from SonarQube for this project."""
    try:
        url = f"{host.rstrip('/')}/api/issues/search"
        params = {
            "componentKeys": project_key,
            "ps": str(page_size),
            "s": "SEVERITY",
            "types": "BUG,VULNERABILITY,CODE_SMELL",
        }
        resp = requests.get(url, params=params, auth=(token, ""), timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return data.get("issues", []) or []
    except Exception as e:
        logger.warning(f"[Code Analysis] Failed to fetch SonarQube issues: {e}")
        return []


def _summarize_issues(issues: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    notes: List[str] = []

    for issue in issues:
        severity = (issue.get("severity") or "").upper()
        msg = issue.get("message") or ""
        rule = issue.get("rule") or ""
        comp = issue.get("component") or ""
        line = issue.get("line")
        loc = f"{comp}:{line}" if line else comp
        text = f"[{severity}] {msg} (rule={rule}, at {loc})"
        if severity in ("BLOCKER", "CRITICAL", "MAJOR"):
            errors.append(text)
        elif severity in ("MINOR", "INFO"):
            warnings.append(text)
        else:
            notes.append(text)

    if not notes and (errors or warnings):
        notes.append("SonarQube issues detected. See above errors/warnings.")
    return {"errors": errors, "warnings": warnings, "notes": notes}


def analyze_code_with_llm(event: dict, state: DevOpsAgentState = None):
    """
    Run SonarQube-based code analysis and update shared state.
    Suggestions from SonarQube are stored in state.code_analysis.{errors,warnings,logs}
    and surfaced to the user via Slack (pipeline logs + failure handler).
    """
    repo = event["repo_context"]["repo"]
    branch = event["repo_context"]["branch"] or "main"
    commit_id = event["repo_context"]["commit"]
    repo_path = _repo_path_from_state(event, state)

    logger.info(f"[Code Analysis] Starting SonarQube analysis for repo={repo} branch={branch} path={repo_path}")

    scan_result = _run_sonar_scanner(repo_path, repo, branch)
    status = scan_result.get("status", "failed")
    logs = scan_result.get("logs", "")
    host = scan_result.get("host") or os.getenv("SONAR_HOST_URL", "")
    token = scan_result.get("token") or os.getenv("SONAR_TOKEN", "")
    project_key = scan_result.get("project_key", f"{repo}_{branch.replace('/', '_')}")

    issues: List[Dict[str, Any]] = []
    if status == "success" and host and token:
        issues = _fetch_sonar_issues(host, token, project_key)

    summary = _summarize_issues(issues) if issues else {"errors": [], "warnings": [], "notes": []}

    # Update state (issues are non-blocking; user is asked in Slack whether to continue or stop)
    if state is not None:
        state.code_analysis.errors = summary["errors"]
        state.code_analysis.warnings = summary["warnings"]
        # Scan success = pass for flow; issues are reported to user who chooses continue/stop
        state.code_analysis.passed = status == "success"
        # logs: notes plus a short pointer to SonarQube project
        notes = list(summary["notes"])
        if host:
            notes.append(f"SonarQube project: {host.rstrip('/')}/dashboard?id={project_key}")
        if logs:
            notes.append(f"(scanner logs excerpt)\n{logs[:800]}")
        state.code_analysis.logs = notes

    logger.info(
        f"[Code Analysis] SonarQube status={status}, "
        f"errors={len(summary['errors'])}, warnings={len(summary['warnings'])}"
    )

    # Publish event
    try:
        evt = CodeAnalysisEvent(
            repo=repo,
            passed=state.code_analysis.passed if state is not None else (status == "success"),
            errors=summary["errors"],
            warnings=summary["warnings"],
            notes=state.code_analysis.logs if state is not None else summary["notes"],
        )
        publish_event(CODE_ANALYSIS, evt.model_dump())
        logger.info("[Kafka] CodeAnalysisEvent published (SonarQube-based)")
    except Exception as e:
        logger.error(f"[Kafka] Failed to publish CodeAnalysisEvent: {e}")

    return {
        "status": status,
        "project_key": project_key,
        "issues_count": len(issues),
        "issues": issues,
    }
