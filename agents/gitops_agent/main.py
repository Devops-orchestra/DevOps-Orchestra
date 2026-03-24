"""
GitOps agent: tool server lifecycle helpers.
The pipeline is triggered only via Slack (user message or GitHub events in Slack channel).
Clone, validate, license audit, etc. are run by the coordinator via the tool server.
"""
import os
import platform
import socket
import subprocess
import sys
import time

import psutil
import requests

from shared_modules.utils.logger import logger

TOOL_SERVER_PORT = 8001


def kill_process_on_port(port: int):
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr.port == port:
                try:
                    proc = psutil.Process(conn.pid)
                    logger.info(f"Killing process {conn.pid} using port {port}")
                    proc.kill()
                    return
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    logger.error(f"Could not kill process {conn.pid}: {e}")
    except psutil.AccessDenied:
        logger.warning("Access denied: Unable to scan for processes on port due to OS restrictions.")
    except Exception as e:
        logger.error(f"Unexpected error while scanning for open ports: {e}")


def start_tool_server():
    """Start the FastAPI tool server (clone, config_validator, license_audit, repo_size)."""
    logger.info("Launching Tool Server...")
    tool_server_script = os.path.join(os.getcwd(), "agents", "gitops_agent", "tools", "tool_server.py")
    venv_python = sys.executable
    try:
        with socket.create_connection(("localhost", TOOL_SERVER_PORT), timeout=2):
            logger.info(f"Tool server already running on port {TOOL_SERVER_PORT}, restarting it.")
            kill_process_on_port(TOOL_SERVER_PORT)
    except (ConnectionRefusedError, OSError):
        logger.info("Tool server is not running. Starting it now...")

    if platform.system() == "Windows":
        subprocess.Popen(
            [venv_python, tool_server_script],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    else:
        subprocess.Popen(
            [venv_python, tool_server_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    time.sleep(2)
    logger.info("Tool Server started.")


def wait_for_tool_server(timeout=10):
    """Block until the tool server health check succeeds."""
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
