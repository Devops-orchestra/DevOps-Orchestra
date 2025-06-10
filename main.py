# File: main.py
import shutil
import threading
import os
from flask import Flask, request, jsonify
from agents.gitops_agent.main import run_gitops_agent
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.kafka_event_bus.topic_manager import create_topics
from shared_modules.utils.logger import logger
from shared_modules.utils.file_utils import handle_remove_readonly
from pyngrok import ngrok

app = Flask(__name__)

# Initialize global state
state = DevOpsAgentState()

def cleanup_old_repos():
    base_dir = "/tmp/gitops_repos"
    if os.path.exists(base_dir):
        logger.info("Cleaning Old Repository")
        shutil.rmtree(base_dir, onerror=handle_remove_readonly)
    os.makedirs(base_dir, exist_ok=True)

@app.route("/webhook", methods=["POST"])
def github_webhook():
    logger.info("Github Event triggered")
    event_type = request.headers.get("X-GitHub-Event")

    # Try to parse JSON first; fallback to form data
    if request.is_json:
        payload = request.get_json()
    else:
        try:
            payload = request.form.to_dict()
        except Exception as e:
            logger.error(f"Failed to parse request payload: {e}")
            return jsonify({"error": "Unsupported Media Type"}), 415

    if not payload:
        logger.error("Empty or malformed payload")
        return jsonify({"error": "Empty or malformed payload"}), 400

    logger.info(f"Received GitHub event: {event_type}")
    
    thread = threading.Thread(target=run_gitops_agent, args=(event_type, payload, state))
    thread.start()
    return jsonify({"message": "GitOps Agent triggered"}), 200

def launch_ngrok():
    url = ngrok.connect(5001)
    logger.info(f"GitOps Agent Webhook URL (ngrok): {url}")

def launch_gitops_agent():
    cleanup_old_repos()
    create_topics()
    launch_ngrok()
    app.run(port=5001)

if __name__ == "__main__":
    launch_gitops_agent()
