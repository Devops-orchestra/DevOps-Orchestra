import os
import subprocess
from agents.build_agent.llm.prompt_dockerfile import generate_dockerfile_with_llm
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus.event_schema import BuildReadyEvent
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.utils.logger import logger

REPO_BASE_PATH = "/tmp/gitops_repos"

def build_and_push_image(event: dict, state: DevOpsAgentState):
    repo_name = event.get("repo_context", {}).get("repo")
    if not repo_name:
        raise ValueError("[Build Agent] Missing repo name in event")

    repo_path = os.path.join(REPO_BASE_PATH, repo_name)
    dockerfile_path = os.path.join(repo_path, "Dockerfile")
    compose_path = os.path.join(repo_path, "docker-compose.yml")

    # Step 1: Check for existing files or generate using LLM
    dockerfile_type = None

    if not os.path.exists(dockerfile_path) and not os.path.exists(compose_path):
        logger.info(f"[Build Agent] No Dockerfile or docker-compose.yml found. Generating via LLM for {repo_name}.")
        try:
            response = generate_dockerfile_with_llm(state)
            if response.strip().lower().startswith("dockerfile"):
                dockerfile_type = "dockerfile"
                content = response.partition("\n")[2]
                with open(dockerfile_path, "w") as f:
                    f.write(content)
                logger.info(f"[Build Agent] Dockerfile generated at {dockerfile_path}")
            elif response.strip().lower().startswith("docker-compose.yml"):
                dockerfile_type = "compose"
                content = response.partition("\n")[2]
                with open(compose_path, "w") as f:
                    f.write(content)
                logger.info(f"[Build Agent] docker-compose.yml generated at {compose_path}")
            else:
                raise ValueError("LLM did not return a recognized Docker config type.")
        except Exception as e:
            logger.error(f"[Build Agent] Failed to generate container config: {e}")
            state.build.status = "failed"
            state.build.logs = str(e)
            return
    else:
        dockerfile_type = "compose" if os.path.exists(compose_path) else "dockerfile"

    # Step 2: Handle Dockerfile build
    if dockerfile_type == "dockerfile":
        image_tag = f"{repo_name.lower()}-image:latest"
        build_cmd = ["docker", "build", "-t", image_tag, repo_path]

        try:
            logger.info(f"[Build Agent] Building Docker image: {image_tag}")
            build_output = subprocess.check_output(build_cmd, stderr=subprocess.STDOUT, text=True)
            logger.info("[Build Agent] Docker build succeeded.")
            state.build.status = "success"
            state.build.logs = build_output[-1000:]
            state.build.retries = 0
            image_url = image_tag
        except subprocess.CalledProcessError as e:
            logger.error("[Build Agent] Docker build failed.")
            state.build.status = "failed"
            state.build.logs = e.output[-1000:]
            state.build.retries += 1
            image_url = None
    else:
        # For docker-compose.yml – no image build, just notify
        logger.info("[Build Agent] docker-compose.yml detected – skipping build.")
        state.build.status = "success"
        state.build.logs = "docker-compose.yml generated. Manual orchestration required."
        state.build.retries = 0
        image_url = None

    # Step 3: Publish build status
    event = BuildReadyEvent(
        repo=repo_name,
        image_url=image_url,
        status=state.build.status,
        logs=state.build.logs
    )

    try:
        publish_event("build_ready", event.model_dump())
        logger.info("[Kafka] BuildReadyEvent published to Kafka.")
    except Exception as e:
        logger.error(f"[Kafka] Failed to publish BuildReadyEvent: {e}")
