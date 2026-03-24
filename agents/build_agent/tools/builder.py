"""
Build agent: run Maven, Gradle, npm, Poetry, or Docker build.
Discovers build files (pom.xml, package.json, Dockerfile, etc.) anywhere under repo;
runs each build in the directory where the build file is present.
If no container config exists, generates Dockerfile/docker-compose via LLM.
"""
import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from agents.build_agent.llm.prompt_dockerfile import generate_dockerfile_with_llm
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus.event_schema import BuildReadyEvent
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.utils.logger import logger

REPO_BASE_PATH = os.getenv("REPO_BASE_PATH", "/tmp/gitops_repos")

SKIP_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "env", ".env", "dist", "build", "target"}


def _repo_path_from_state(event: dict, state: DevOpsAgentState) -> str:
    """Resolve repo clone path (must match pipeline clone_path)."""
    repo_name = event.get("repo_context", {}).get("repo") or event.get("repo") or event.get("payload", {}).get("repository", {}).get("name")
    if not repo_name:
        raise ValueError("Missing repo name in event")
    branch = (state.repo_context.branch or "main").replace("/", "_")
    return os.path.join(REPO_BASE_PATH, f"{repo_name}_{branch}")


def _find_first_file(repo_path: str, names: list) -> Optional[Path]:
    """Return path to first file with one of the given names under repo_path, or None."""
    repo = Path(repo_path)
    if not repo.is_dir():
        return None
    for root, dirs, files in os.walk(repo_path, topdown=True):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            if name in files:
                return Path(root) / name
    return None


def _find_docker_context(repo_path: str) -> Tuple[Optional[str], Optional[str]]:
    """Find first Dockerfile or docker-compose.yml; return (path_to_file, parent_dir)."""
    dockerfile = _find_first_file(repo_path, ["Dockerfile"])
    compose = _find_first_file(repo_path, ["docker-compose.yml", "docker-compose.yaml"])
    if dockerfile:
        return str(dockerfile), str(dockerfile.parent)
    if compose:
        return str(compose), str(compose.parent)
    return None, None


def _detect_build_tool_and_cwd(repo_path: str, config: dict) -> Tuple[str, str]:
    """
    Detect build tool from repo contents; config can override with build.tool.
    Returns (tool, cwd) where cwd is the directory to run the build in.
    """
    build_cfg = config.get("build", {})
    explicit_tool = (build_cfg.get("tool") or "").strip().lower()
    if explicit_tool and explicit_tool not in ("auto", "docker"):
        # Config says maven/gradle/npm/poetry; find the file and cwd
        if explicit_tool == "maven":
            p = _find_first_file(repo_path, ["pom.xml"])
            if p:
                return "maven", str(p.parent)
        elif explicit_tool == "gradle":
            p = _find_first_file(repo_path, ["build.gradle", "build.gradle.kts"])
            if p:
                return "gradle", str(p.parent)
        elif explicit_tool == "npm":
            p = _find_first_file(repo_path, ["package.json"])
            if p:
                return "npm", str(p.parent)
        elif explicit_tool == "poetry":
            p = _find_first_file(repo_path, ["pyproject.toml"])
            if p:
                return "poetry", str(p.parent)
        # fallback to auto

    # Auto-detect: priority pom.xml > gradle > package.json > pyproject.toml > docker
    p = _find_first_file(repo_path, ["pom.xml"])
    if p:
        return "maven", str(p.parent)
    p = _find_first_file(repo_path, ["build.gradle", "build.gradle.kts"])
    if p:
        return "gradle", str(p.parent)
    p = _find_first_file(repo_path, ["package.json"])
    if p:
        return "npm", str(p.parent)
    p = _find_first_file(repo_path, ["pyproject.toml"])
    if p:
        return "poetry", str(p.parent)
    # Docker (or generate): use repo root as cwd for context
    return "docker", repo_path


def build_and_push_image(event: dict, state: DevOpsAgentState):
    repo_name = event.get("repo_context", {}).get("repo") or event.get("repo") or event.get("payload", {}).get("repository", {}).get("name")
    if not repo_name:
        raise ValueError("Missing repo name in event")

    repo_path = _repo_path_from_state(event, state)
    if not os.path.isdir(repo_path):
        state.build_result.status = "failed"
        state.build_result.logs = f"Repo path not found: {repo_path}"
        return {"event_data": event, "state": state}

    config = state.repo_context.config or {}
    build_tool, cwd = _detect_build_tool_and_cwd(repo_path, config)
    logger.info(f"[Build Agent] Detected build tool: {build_tool}, cwd: {cwd}")

    image_url = None
    build_logs = ""

    try:
        if build_tool == "docker":
            docker_path, context_dir = _find_docker_context(repo_path)
            if not docker_path:
                logger.info("[Build Agent] No Dockerfile or docker-compose found. Generating via LLM.")
                try:
                    response = generate_dockerfile_with_llm(state)
                    lower = response.strip().lower()
                    write_dir = repo_path
                    if lower.startswith("version:") or "services:" in lower:
                        compose_path = os.path.join(write_dir, "docker-compose.yml")
                        with open(compose_path, "w") as f:
                            f.write(response)
                        logger.info(f"[Build Agent] docker-compose.yml written to {compose_path}")
                        state.build_result.status = "success"
                        state.build_result.logs = "docker-compose.yml generated. Manual orchestration required."
                        state.build_result.retries = 0
                        image_url = None
                        build_logs = state.build_result.logs
                    else:
                        dockerfile_path = os.path.join(write_dir, "Dockerfile")
                        with open(dockerfile_path, "w") as f:
                            f.write(response)
                        logger.info(f"[Build Agent] Dockerfile written to {dockerfile_path}")
                        context_dir = write_dir
                        image_tag = f"{repo_name.lower()}-image:latest"
                        build_cmd = ["docker", "build", "-t", image_tag, context_dir]
                        build_output = subprocess.check_output(build_cmd, stderr=subprocess.STDOUT, text=True)
                        state.build_result.status = "success"
                        state.build_result.logs = build_output[-1000:]
                        state.build_result.retries = 0
                        image_url = image_tag
                        build_logs = build_output[-1000:]
                except Exception as e:
                    logger.error(f"[Build Agent] Failed to generate/build: {e}")
                    state.build_result.status = "failed"
                    state.build_result.logs = str(e)
                    return {"event_data": event, "state": state}
            else:
                if docker_path.endswith(".yml") or docker_path.endswith(".yaml"):
                    logger.info("[Build Agent] Using docker-compose; skipping image build.")
                    state.build_result.status = "success"
                    state.build_result.logs = "docker-compose found. Manual orchestration required."
                    state.build_result.retries = 0
                    image_url = None
                    build_logs = state.build_result.logs
                else:
                    image_tag = f"{repo_name.lower()}-image:latest"
                    build_cmd = ["docker", "build", "-t", image_tag, context_dir]
                    try:
                        build_output = subprocess.check_output(build_cmd, stderr=subprocess.STDOUT, text=True)
                        state.build_result.status = "success"
                        state.build_result.logs = build_output[-1000:]
                        state.build_result.retries = 0
                        image_url = image_tag
                        build_logs = build_output[-1000:]
                    except subprocess.CalledProcessError as e:
                        state.build_result.status = "failed"
                        state.build_result.logs = e.output[-1000:]
                        return {"event_data": event, "state": state}

        elif build_tool == "maven":
            build_cmd = ["mvn", "package"]
            try:
                build_output = subprocess.check_output(build_cmd, cwd=cwd, stderr=subprocess.STDOUT, text=True)
                state.build_result.status = "success"
                state.build_result.logs = build_output[-1000:]
                state.build_result.retries = 0
                build_logs = build_output[-1000:]
            except subprocess.CalledProcessError as e:
                state.build_result.status = "failed"
                state.build_result.logs = e.output[-1000:]
                return {"event_data": event, "state": state}

        elif build_tool == "gradle":
            build_cmd = ["./gradlew", "build"] if os.name != "nt" else ["gradlew.bat", "build"]
            try:
                build_output = subprocess.check_output(build_cmd, cwd=cwd, stderr=subprocess.STDOUT, text=True)
                state.build_result.status = "success"
                state.build_result.logs = build_output[-1000:]
                state.build_result.retries = 0
                build_logs = build_output[-1000:]
            except subprocess.CalledProcessError as e:
                state.build_result.status = "failed"
                state.build_result.logs = e.output[-1000:]
                return {"event_data": event, "state": state}

        elif build_tool == "npm":
            build_cmd = ["npm", "run", "build"]
            try:
                build_output = subprocess.check_output(build_cmd, cwd=cwd, stderr=subprocess.STDOUT, text=True)
                state.build_result.status = "success"
                state.build_result.logs = build_output[-1000:]
                state.build_result.retries = 0
                build_logs = build_output[-1000:]
            except subprocess.CalledProcessError as e:
                state.build_result.status = "failed"
                state.build_result.logs = e.output[-1000:]
                return {"event_data": event, "state": state}

        elif build_tool == "poetry":
            build_cmd = ["poetry", "build"]
            try:
                build_output = subprocess.check_output(build_cmd, cwd=cwd, stderr=subprocess.STDOUT, text=True)
                state.build_result.status = "success"
                state.build_result.logs = build_output[-1000:]
                state.build_result.retries = 0
                build_logs = build_output[-1000:]
            except subprocess.CalledProcessError as e:
                state.build_result.status = "failed"
                state.build_result.logs = e.output[-1000:]
                return {"event_data": event, "state": state}

        else:
            state.build_result.status = "failed"
            state.build_result.logs = f"Unsupported build tool: {build_tool}"
            build_logs = state.build_result.logs
            return {"event_data": event, "state": state}

    except Exception as e:
        logger.error(f"[Build Agent] Exception: {e}")
        state.build_result.status = "failed"
        state.build_result.logs = str(e)
        build_logs = str(e)
        return {"event_data": event, "state": state}

    build_event = BuildReadyEvent(
        repo=repo_name,
        image_url=image_url,
        status=state.build_result.status,
        logs=build_logs,
    )
    try:
        publish_event("build_ready", build_event.model_dump())
        logger.info("[Kafka] BuildReadyEvent published.")
    except Exception as e:
        logger.error(f"[Kafka] Failed to publish BuildReadyEvent: {e}")
