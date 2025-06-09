import subprocess
import time
import os
import platform
import requests
import socket
from agents.gitops_agent.event_handler import handle_github_event
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.utils.logger import logger

TOOL_SERVER_PORT = 8001

def start_tool_server():
    """
    Start the shared FastAPI server that serves all tools.
    Runs as a subprocess in the background.
    """
    logger.info("Launching Tool Server...")
    tool_server_script = os.path.join(os.getcwd(), "agents","gitops_agent","tools", "tool_server.py")
    venv_python = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")

    # Check if already running on the port
    try:
        sock = socket.create_connection(("localhost", TOOL_SERVER_PORT), timeout=2)
        logger.info(f"Tool server already running on port {TOOL_SERVER_PORT}")
        sock.close()
        return
    except (ConnectionRefusedError, OSError):
        pass

    if platform.system() == "Windows":
        venv_python = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
        subprocess.Popen(
            [venv_python, tool_server_script],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        venv_python = os.path.join(os.getcwd(), ".venv", "bin", "python")
        subprocess.Popen(
            [venv_python, tool_server_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid
        )
    time.sleep(2)  # Give time for server to boot up
    logger.info("Tool Server started.")


def wait_for_tool_server(timeout=10):
    url = f"http://localhost:{TOOL_SERVER_PORT}/health"
    for _ in range(timeout):
        try:
            r = requests.get(url, timeout=1)
            if r.status_code == 200:
                logger.info("Tool server is healthy.")
                return True
        except requests.exceptions.RequestException:
            time.sleep(1)
    raise Exception("Tool server health check failed.")


def run_gitops_agent(event_type: str, payload: dict, state: DevOpsAgentState) -> DevOpsAgentState:
    """
    Entrypoint for GitOps agent in LangGraph pipeline.
    """
    logger.info("Running GitOps Agent")

    # Step 1: Start tool server if not running
    start_tool_server()
    wait_for_tool_server()

    # Step 2: Run the event handler
    updated_state = handle_github_event(
        event_type=event_type,
        payload=payload,
        state=state
    )

    logger.info(f"GitOps Agent completed with status: {updated_state.status}")
    return updated_state
