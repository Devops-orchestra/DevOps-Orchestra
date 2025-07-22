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

    # --- Step 0: Read build tool from config ---
    config = state.repo_context.config or {}
    build_cfg = config.get("build", {})
    build_tool = build_cfg.get("tool", "docker").lower()
    logger.info(f"[Build Agent] Build tool from config: {build_tool}")

    image_url = None
    build_success = False
    build_logs = ""

    try:
        if build_tool == "docker":
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
                    build_success = True
                    build_logs = build_output[-1000:]
                except subprocess.CalledProcessError as e:
                    logger.error("[Build Agent] Docker build failed.")
                    state.build_result.status = "failed"
                    state.build_result.logs = e.output[-1000:]
                    image_url = None
                    build_logs = e.output[-1000:]
                    return {"event_data": event, "state": state}
            else:
                logger.info("[Build Agent] Detected docker-compose.yml – skipping Docker build.")
                state.build_result.status = "success"
                state.build_result.logs = "docker-compose.yml generated. Manual orchestration required."
                state.build_result.retries = 0
                image_url = None
                build_success = True
                build_logs = "docker-compose.yml generated. Manual orchestration required."

        elif build_tool == "maven":
            build_cmd = ["mvn", "package"]
            try:
                logger.info(f"[Build Agent] Running Maven build for {repo_name}")
                build_output = subprocess.check_output(build_cmd, cwd=repo_path, stderr=subprocess.STDOUT, text=True)
                logger.info("[Build Agent] Maven build succeeded.")
                state.build_result.status = "success"
                state.build_result.logs = build_output[-1000:]
                state.build_result.retries = 0
                build_success = True
                build_logs = build_output[-1000:]
            except subprocess.CalledProcessError as e:
                logger.error("[Build Agent] Maven build failed.")
                state.build_result.status = "failed"
                state.build_result.logs = e.output[-1000:]
                build_logs = e.output[-1000:]
                return {"event_data": event, "state": state}

        elif build_tool == "gradle":
            build_cmd = ["./gradlew", "build"]
            try:
                logger.info(f"[Build Agent] Running Gradle build for {repo_name}")
                build_output = subprocess.check_output(build_cmd, cwd=repo_path, stderr=subprocess.STDOUT, text=True)
                logger.info("[Build Agent] Gradle build succeeded.")
                state.build_result.status = "success"
                state.build_result.logs = build_output[-1000:]
                state.build_result.retries = 0
                build_success = True
                build_logs = build_output[-1000:]
            except subprocess.CalledProcessError as e:
                logger.error("[Build Agent] Gradle build failed.")
                state.build_result.status = "failed"
                state.build_result.logs = e.output[-1000:]
                build_logs = e.output[-1000:]
                return {"event_data": event, "state": state}

        elif build_tool == "npm":
            build_cmd = ["npm", "run", "build"]
            try:
                logger.info(f"[Build Agent] Running npm build for {repo_name}")
                build_output = subprocess.check_output(build_cmd, cwd=repo_path, stderr=subprocess.STDOUT, text=True)
                logger.info("[Build Agent] npm build succeeded.")
                state.build_result.status = "success"
                state.build_result.logs = build_output[-1000:]
                state.build_result.retries = 0
                build_success = True
                build_logs = build_output[-1000:]
            except subprocess.CalledProcessError as e:
                logger.error("[Build Agent] npm build failed.")
                state.build_result.status = "failed"
                state.build_result.logs = e.output[-1000:]
                build_logs = e.output[-1000:]
                return {"event_data": event, "state": state}

        elif build_tool == "poetry":
            build_cmd = ["poetry", "build"]
            try:
                logger.info(f"[Build Agent] Running poetry build for {repo_name}")
                build_output = subprocess.check_output(build_cmd, cwd=repo_path, stderr=subprocess.STDOUT, text=True)
                logger.info("[Build Agent] Poetry build succeeded.")
                state.build_result.status = "success"
                state.build_result.logs = build_output[-1000:]
                state.build_result.retries = 0
                build_success = True
                build_logs = build_output[-1000:]
            except subprocess.CalledProcessError as e:
                logger.error("[Build Agent] Poetry build failed.")
                state.build_result.status = "failed"
                state.build_result.logs = e.output[-1000:]
                build_logs = e.output[-1000:]
                return {"event_data": event, "state": state}

        else:
            logger.error(f"[Build Agent] Unsupported build tool: {build_tool}")
            state.build_result.status = "failed"
            state.build_result.logs = f"Unsupported build tool: {build_tool}"
            build_logs = f"Unsupported build tool: {build_tool}"
            return {"event_data": event, "state": state}

    except Exception as e:
        logger.error(f"[Build Agent] Exception during build: {e}")
        state.build_result.status = "failed"
        state.build_result.logs = str(e)
        build_logs = str(e)
        return {"event_data": event, "state": state}

    # --- Step 3: Publish BuildReadyEvent ---
    build_event = BuildReadyEvent(
        repo=repo_name,
        image_url=image_url,
        status=state.build_result.status,
        logs=build_logs
    )

    try:
        publish_event("build_ready", build_event.model_dump())
        logger.info("[Kafka] BuildReadyEvent published.")
    except Exception as e:
        logger.error(f"[Kafka] Failed to publish BuildReadyEvent: {e}")

