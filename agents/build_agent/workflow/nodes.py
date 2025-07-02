import os
import subprocess
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.kafka_event_bus.event_schema import BuildReadyEvent
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from agents.build_agent.utils import detect_language_framework, generate_dockerfile

REPO_BASE_PATH = "/tmp/gitops_repos"

def run_build_node(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]

    print("[Build Agent] Triggered for event:")
    print(event)

    repo_name = event.get("repo_context", {}).get("repo") \
        or event.get("payload", {}).get("repository", {}).get("name")

    if not repo_name:
        raise ValueError("Missing repo name in event")

    repo_path = os.path.join(REPO_BASE_PATH, repo_name)
    dockerfile_path = os.path.join(repo_path, "Dockerfile")

    has_frontend = os.path.isdir(os.path.join(repo_path, "frontend"))
    framework = detect_language_framework(repo_path)

    print(f"[Build Agent] Detected framework: {framework}")
    print(f"[Build Agent] Frontend folder present: {has_frontend}")

    dockerfile_content = generate_dockerfile(repo_path, framework, has_frontend)

    with open(dockerfile_path, "w") as f:
        f.write(dockerfile_content)

    print(f"[Build Agent] Dockerfile written to {dockerfile_path}")

    image_tag = f"{repo_name.lower()}-image:latest"
    build_cmd = ["docker", "build", "-t", image_tag, repo_path]

    try:
        print(f"[Build Agent] Building Docker image: {image_tag}")
        build_output = subprocess.check_output(build_cmd, stderr=subprocess.STDOUT, text=True)
        print("[Build Agent] Docker build succeeded.")
        build_status = "success"
        image_url = image_tag
        build_logs = build_output
    except subprocess.CalledProcessError as e:
        print("[Build Agent] Docker build failed.")
        build_status = "failed"
        image_url = None
        build_logs = e.output

    build_event = BuildReadyEvent(
        repo=repo_name,
        image_url=image_url,
        status=build_status,
        logs=build_logs[-1000:]
    )
    publish_event(topic="build_ready", data=build_event.model_dump())

    return {
        "event_data": event,
        "state": state
    }
