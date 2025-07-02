import os
import subprocess
from langgraph.graph import StateGraph

from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.kafka_event_bus.event_schema import BuildReadyEvent
from shared_modules.kafka_event_bus.kafka_producer import publish_event
from agents.build_agent.workflow.nodes import run_build_node

REPO_BASE_PATH = "/tmp/gitops_repos"

def detect_language_framework(repo_path: str) -> str:
    if os.path.exists(os.path.join(repo_path, "package.json")):
        return "nodejs"
    if os.path.exists(os.path.join(repo_path, "requirements.txt")):
        with open(os.path.join(repo_path, "requirements.txt")) as f:
            contents = f.read().lower()
            if "django" in contents:
                return "django"
            elif "flask" in contents:
                return "flask"
        return "python"
    return "unknown"

def generate_dockerfile(repo_path: str, framework: str, has_frontend: bool) -> str:
    if has_frontend and framework == "flask":
        return f"""\
# Stage 1: Build frontend
FROM node:18 as frontend-builder
WORKDIR /app
COPY frontend/ frontend/
RUN cd frontend && npm install && npm run build

# Stage 2: Backend with Flask
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend-builder /app/frontend/build /app/static
EXPOSE 5000
CMD ["python", "main.py"]
"""
    elif framework == "flask":
        return f"""\
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "main.py"]
"""
    elif framework == "django":
        return f"""\
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
"""
    elif framework == "nodejs":
        return f"""\
FROM node:18
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "start"]
"""
    return "# Could not detect framework; please write Dockerfile manually.\n"

def run_build_agent(inputs: dict) -> dict:
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

def get_build_flow() -> StateGraph:
    builder = StateGraph(dict)
    builder.add_node("build", run_build_node)
    builder.set_entry_point("build")
    return builder.compile()
