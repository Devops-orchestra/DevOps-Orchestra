# File: langgraph_flows/shared_nodes.py

import os
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus.event_schema import CodeAnalysisEvent, BuildReadyEvent
from shared_modules.utils.logger import logger
from agents.code_analysis_agent.tools.llm_code_analyzer import analyze_code_with_llm
from agents.code_analysis_agent.models.schemas import LLMCodeAnalysisInput
from agents.code_analysis_agent.tools.llm_utils import parse_llm_summary
from agents.build_agent.llm.prompt_dockerfile import generate_dockerfile_with_llm
import subprocess
from shared_modules.utils.decorators import retry_on_failure

REPO_BASE_PATH = "/tmp/gitops_repos"

def run_code_analysis_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]

    input_data = LLMCodeAnalysisInput(
        repo=event['repo_context']["repo"],
        branch=event['repo_context']["branch"],
        commit_id=event['repo_context']["commit"],
        repo_path=os.path.join(REPO_BASE_PATH, event['repo_context']["repo"]),
        file_limit=10,
        llm_model="llama-3.3-70b-versatile"
    )

    llm_result = analyze_code_with_llm(input_data, state)

    if llm_result["results"]:
        analysis_text = llm_result["results"][0]["analysis"]
        parsed = parse_llm_summary(analysis_text)

        state.code_analysis.passed = parsed.passed
        state.code_analysis.errors = parsed.errors
        state.code_analysis.warnings = parsed.warnings
        state.code_analysis.logs = parsed.notes

        logger.info(f"[Code Analysis] Errors: {len(parsed.errors)}, Warnings: {len(parsed.warnings)}")

        code_analysis_event = CodeAnalysisEvent(
            repo=event['repo_context']["repo"],
            passed=parsed.passed,
            errors=parsed.errors,
            warnings=parsed.warnings,
            notes=parsed.notes
        )

        try:
            publish_event("code_analysis", code_analysis_event.model_dump())
            logger.info("[Kafka] CodeAnalysisEvent published")
        except Exception as e:
            logger.error(f"[Kafka] Failed to publish CodeAnalysisEvent: {e}")

    return {"event_data": event, "state": state}

@retry_on_failure(max_retries=3, agent_name="Build Agent")
def run_build_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]

    repo_name = event.get("repo_context", {}).get("repo") \
        or event.get("payload", {}).get("repository", {}).get("name")

    if not repo_name:
        raise ValueError("Missing repo name in event")

    repo_path = os.path.join(REPO_BASE_PATH, repo_name)
    dockerfile_path = os.path.join(repo_path, "Dockerfile")

    try:
        dockerfile_content = generate_dockerfile_with_llm(state)
        with open(dockerfile_path, "w") as f:
            f.write(dockerfile_content)
        logger.info(f"[Build Agent] Dockerfile written to {dockerfile_path}")
    except Exception as e:
        logger.error(f"[Build Agent] Failed to generate Dockerfile: {e}")
        return {"event_data": event, "state": state}

    image_tag = f"{repo_name.lower()}-image:latest"
    build_cmd = ["docker", "build", "-t", image_tag, repo_path]

    try:
        logger.info(f"[Build Agent] Building image: {image_tag}")
        build_output = subprocess.check_output(build_cmd, stderr=subprocess.STDOUT, text=True)
        logger.info("[Build Agent] Docker build succeeded")
        build_status = "success"
        image_url = image_tag
        build_logs = build_output
    except subprocess.CalledProcessError as e:
        logger.error("[Build Agent] Docker build failed")
        build_status = "failed"
        image_url = None
        build_logs = e.output

    build_event = BuildReadyEvent(
        repo=repo_name,
        image_url=image_url,
        status=build_status,
        logs=build_logs[-1000:]
    )

    try:
        publish_event("build_ready", build_event.model_dump())
        logger.info("[Kafka] BuildReadyEvent published")
    except Exception as e:
        logger.error(f"[Kafka] Failed to publish BuildReadyEvent: {e}")

    return {"event_data": event, "state": state}
