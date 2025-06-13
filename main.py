# File: main.py
import shutil
import threading
import os
import time
from flask import Flask, request, jsonify
from agents.gitops_agent.main import run_gitops_agent
from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.kafka_event_bus.topic_manager import create_topics
from shared_modules.utils.logger import logger
from shared_modules.utils.file_utils import handle_remove_readonly
from pyngrok import ngrok
from kafka.admin import KafkaAdminClient
from kafka.errors import KafkaError

app = Flask(__name__)

# Initialize global state
state = DevOpsAgentState()

def cleanup_old_repos():
    base_dir = "/tmp/gitops_repos"

    if os.path.exists(base_dir):
        logger.info("Cleaning Old Repository")
        for filename in os.listdir(base_dir):
            file_path = os.path.join(base_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path, onerror=handle_remove_readonly)
            except Exception as e:
                logger.error(f"Failed to delete {file_path}. Reason: {e}")
    else:
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

def wait_for_kafka(bootstrap_servers="kafka:9092", timeout=120, interval=5):
    """Wait until Kafka is ready to accept connections."""
    start_time = time.time()
    attempt = 1
    while time.time() - start_time < timeout:
        try:
            logger.info(f"[Kafka Wait] Attempt {attempt} to connect to Kafka...")
            admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers)
            admin.list_topics()  # This will fail if Kafka isn't ready
            logger.info("[Kafka Wait] Kafka is available.")
            return
        except KafkaError as e:
            logger.warning(f"[Kafka Wait] Kafka not ready (attempt {attempt}): {e.__class__.__name__}")
            time.sleep(interval)
            attempt += 1
    raise RuntimeError("Kafka did not become ready.")

def launch_ngrok():
    authtoken = os.getenv("NGROK_AUTHTOKEN")
    if authtoken:
        ngrok.set_auth_token(authtoken)  
    else:
        print("NGROK_AUTHTOKEN not found in environment")
    url = ngrok.connect(5001)
    logger.info(f"GitOps Agent Webhook URL (ngrok): {url}")

def launch_gitops_agent():
    cleanup_old_repos()
    wait_for_kafka()
    create_topics()
    launch_ngrok()
    app.run(host='0.0.0.0', port=5001)

if __name__ == "__main__":
    launch_gitops_agent()
