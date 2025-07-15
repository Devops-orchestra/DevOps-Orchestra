import os
import subprocess
from agents.build_agent.llm.prompt_dockerfile import generate_dockerfile_with_llm
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus.event_schema import BuildReadyEvent
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.utils.logger import logger

REPO_BASE_PATH = "/tmp/gitops_repos"

def build_and_push_image(event: dict, state: DevOpsAgentState):
    repo_name = event.get("repo_context", {}).get("repo") \
        or event.get("payload", {}).get("repository", {}).get("name")

    if not repo_name:
        raise ValueError("Missing repo name in event")

    repo_path = os.path.join(REPO_BASE_PATH, repo_name)
    dockerfile_path = os.path.join(repo_path, "Dockerfile")
    compose_path = os.path.join(repo_path, "docker-compose.yml")

    dockerfile_type = None

    # --- Step 1: Check if config files exist ---
    if not os.path.exists(dockerfile_path) and not os.path.exists(compose_path):
        logger.info(f"[Build Agent] No Dockerfile or docker-compose.yml found. Generating via LLM for {repo_name}.")
        try:
            response = generate_dockerfile_with_llm(state)
            lower = response.strip().lower()

            if lower.startswith("version:") or "services:" in lower:
                dockerfile_type = "compose"
                with open(compose_path, "w") as f:
                    f.write(response)
                logger.info(f"[Build Agent] docker-compose.yml written to {compose_path}")
            else:
                dockerfile_type = "dockerfile"
                with open(dockerfile_path, "w") as f:
                    f.write(response)
                logger.info(f"[Build Agent] Dockerfile written to {dockerfile_path}")
        except Exception as e:
            logger.error(f"[Build Agent] Failed to generate container config: {e}")
            state.build_result.status = "failed"
            state.build_result.logs = str(e)
            return {"event_data": event, "state": state}
    else:
        dockerfile_type = "compose" if os.path.exists(compose_path) else "dockerfile"

    # --- Step 2: Build Docker image if Dockerfile present ---
    if dockerfile_type == "dockerfile":
        image_tag = f"{repo_name.lower()}-image:latest"
        build_cmd = ["docker", "build", "-t", image_tag, repo_path]

        try:
            logger.info(f"[Build Agent] Building Docker image: {image_tag}")
            build_output = subprocess.check_output(build_cmd, stderr=subprocess.STDOUT, text=True)
            logger.info("[Build Agent] Docker build succeeded.")
            state.build_result.status = "success"
            state.build_result.logs = build_output[-1000:]
            state.build_result.retries = 0
            image_url = image_tag
        except subprocess.CalledProcessError as e:
            logger.error("[Build Agent] Docker build failed.")
            state.build_result.status = "failed"
            state.build_result.logs = e.output[-1000:]
            image_url = None
            return {"event_data": event, "state": state}
    else:
        logger.info("[Build Agent] Detected docker-compose.yml – skipping Docker build.")
        state.build_result.status = "success"
        state.build_result.logs = "docker-compose.yml generated. Manual orchestration required."
        state.build_result.retries = 0
        image_url = None

    # --- Step 3: Publish BuildReadyEvent ---
    build_event = BuildReadyEvent(
        repo=repo_name,
        image_url=image_url,
        status=state.build_result.status,
        logs=state.build_result.logs
    )

    try:
        publish_event("build_ready", build_event.model_dump())
        logger.info("[Kafka] BuildReadyEvent published.")
    except Exception as e:
        logger.error(f"[Kafka] Failed to publish BuildReadyEvent: {e}")

