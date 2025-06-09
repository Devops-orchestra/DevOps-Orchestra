import os
import shutil
import httpx

from shared_modules.kafka_event_bus.kafka_producer import publish_event
from shared_modules.kafka_event_bus.topics import CODE_PUSH
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.utils.logger import logger

from agents.gitops_agent.config_parser import parse_orchestra_config

REPO_BASE_DIR = "/tmp/gitops_repos"
TOOL_SERVER_URL = "http://localhost:8001/invoke"  


def call_tool_server(tool_name: str, input_payload: dict) -> dict:
    """
    Invokes a tool on the MCP-compatible tool server.

    Args:
        tool_name (str): Name of the tool to invoke.
        input_payload (dict): Input arguments for the tool.

    Returns:
        dict: Standardized response with 'status' and 'output'.
    """
    try:
        response = httpx.post(
            TOOL_SERVER_URL,
            json={
                "tool_name": tool_name,
                "input": input_payload
            },
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error calling tool server ({tool_name}): {e}")
        return {"status": "error", "output": {"message": str(e)}}


def handle_github_event(event_type: str, payload: dict, state: DevOpsAgentState) -> DevOpsAgentState:
    repo_url = payload['repository']['clone_url']
    repo_name = payload['repository']['name']
    branch = payload['ref'].split('/')[-1]
    commit = payload.get('after', 'unknown')
    clone_path = os.path.join(REPO_BASE_DIR, repo_name)

    # Step 1: Clean old repo
    if os.path.exists(clone_path):
        logger.info(f"Cleaning existing repo at {clone_path}")
        shutil.rmtree(clone_path)

    # Step 2: Clone the repository via tool server
    logger.info(f"Cloning repo {repo_url} (branch: {branch}) to {clone_path}")
    clone_result = call_tool_server("clone_repo", {
        "repo_url": repo_url,
        "branch": branch,
        "clone_path": clone_path
    })
    if clone_result["status"] != "success":
        logger.error(f"Repo clone failed: {clone_result['output']['message']}")
        state.status = "failed"
        return state

    # Step 3: License audit
    logger.info("Running license compliance check...")
    license_result = call_tool_server("license_audit", {
        "repo_path": clone_path
    })
    if license_result["status"] != "success":
        logger.error(f"License audit failed: {license_result['output']['message']}")
        state.status = "failed"
        return state

    # Step 4: YAML config validation
    config_path = os.path.join(clone_path, "devops_orchestra.yaml")
    logger.info(f"Validating config at {config_path}")
    config_result = call_tool_server("config_validator", {
        "config_path": config_path
    })
    if config_result["status"] != "success":
        logger.error(f"YAML validation failed: {config_result['output']['message']}")
        state.status = "failed"
        return state

    # Step 5: Repo size check
    logger.info("Calculating repo size...")
    size_result = call_tool_server("repo_size", {
        "repo_path": clone_path
    })
    if size_result["status"] != "success":
        logger.error(f"Repo size check failed: {size_result['output']['message']}")
        state.status = "failed"
        return state

    # Step 6: Parse YAML config
    config = parse_orchestra_config(config_path)

    # Step 7: Update shared state
    state.repo_context.repo = repo_name
    state.repo_context.branch = branch
    state.repo_context.commit = commit
    state.repo_context.config = config
    state.repo_context.size_mb = size_result['output']['size_mb']

    state.status = "success"
    logger.info(f"GitOps Agent successfully completed for repo: {repo_name}")

    # Step 8: Emit Kafka event
    publish_event(CODE_PUSH, state.model_dump())
    return state
