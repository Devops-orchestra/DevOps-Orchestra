# File: unified_orchestrator.py

import os
import shutil
import threading
import time
import json
from flask import Flask, request, jsonify
from kafka.admin import KafkaAdminClient
from kafka.errors import KafkaError
from pyngrok import ngrok

from shared_modules.utils.logger import logger
from shared_modules.utils.file_utils import handle_remove_readonly
from shared_modules.kafka_event_bus.topic_manager import create_topics

from agents.gitops_agent.main import run_gitops_agent
from shared_modules.state.devops_state import DevOpsAgentState

from agents.code_analysis_agent.main import start_code_analysis_agent

from agents.build_agent.main import run_build_agent

from agents.build_agent.main import start_build_agent

# Flask App
app = Flask(__name__)
state = DevOpsAgentState()

REPO_PATH = "/tmp/gitops_repos"

# --- GitOps Cleanup ---
def cleanup_old_repos():
    if os.path.exists(REPO_PATH):
        logger.info("Cleaning Old Repository")
        for filename in os.listdir(REPO_PATH):
            file_path = os.path.join(REPO_PATH, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path, onerror=handle_remove_readonly)
            except Exception as e:
                logger.error(f"Failed to delete {file_path}. Reason: {e}")
    else:
        os.makedirs(REPO_PATH, exist_ok=True)

# --- Kafka Wait ---
def wait_for_kafka(bootstrap_servers="kafka:9092", timeout=120, interval=5):
    start_time = time.time()
    attempt = 1
    while time.time() - start_time < timeout:
        try:
            logger.info(f"[Kafka Wait] Attempt {attempt} to connect to Kafka...")
            admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers)
            admin.list_topics()
            logger.info("[Kafka Wait] Kafka is available.")
            return
        except KafkaError as e:
            logger.warning(f"[Kafka Wait] Kafka not ready (attempt {attempt}): {e.__class__.__name__}")
            time.sleep(interval)
            attempt += 1
    raise RuntimeError("Kafka did not become ready.")

# --- Ngrok Launch ---
def launch_ngrok():
    authtoken = os.getenv("NGROK_AUTHTOKEN")
    if authtoken:
        ngrok.set_auth_token(authtoken)
    else:
        logger.warning("NGROK_AUTHTOKEN not found")
    url = ngrok.connect(5001)
    logger.info(f"GitOps Agent Webhook URL (ngrok): {url}")

# --- GitHub Webhook Endpoint ---
@app.route("/webhook", methods=["POST"])
def github_webhook():
    logger.info("GitHub Event triggered")
    event_type = request.headers.get("X-GitHub-Event")
    payload = request.get_json() or request.form.to_dict()

    state.last_event = {
        "event_type": event_type,
        "payload": payload
    }

    if not payload:
        logger.error("Empty or malformed payload")
        return jsonify({"error": "Empty or malformed payload"}), 400

    def handle_agents():
        run_gitops_agent(event_type, payload, state)

    thread = threading.Thread(target=handle_agents)
    thread.start()

    return jsonify({"message": "GitOps & Build Agent triggered"}), 200


# --- Unified Launch ---
def launch_orchestrator():
    cleanup_old_repos()
    wait_for_kafka()
    create_topics()
    launch_ngrok()
    start_code_analysis_agent(state)
    start_build_agent(state)
    app.run(host="0.0.0.0", port=5001)

if __name__ == "__main__":
    launch_orchestrator()
