"""
Coordinator daemon: gateway layer + pipeline orchestration.
Listens to Slack command channel; triggers pipeline on user run-request or pull_request.
All pipeline logs go to a separate Slack channel. User input (Jira ticket, retry/resolve) via Slack.
"""
import os
import sys
import threading
import time
from dotenv import load_dotenv

# Ensure project root is on path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

from shared_modules.utils.logger import logger
from coordinator.config import config
from coordinator.gateway.slack_gateway import run_gateway
from coordinator.gateway.trigger_filter import TriggerResult
from coordinator.gateway.intent_parser import ParsedIntent
from coordinator.handlers.pipeline_handler import run_pipeline

load_dotenv(os.path.join(_project_root, ".env"))

# Shared: when we're waiting for a user reply (Jira ticket, retry/resolved)
# key = (channel_id, thread_ts or ""); value = (threading.Event, list of reply text)
pending_replies: dict = {}


def _start_tool_server():
    """Start the GitOps tool server (clone, config_validator, etc.) if not running."""
    try:
        import requests
        r = requests.get("http://localhost:8001/health", timeout=2)
        if r.status_code == 200:
            return
    except Exception:
        pass
    tool_server_script = os.path.join(
        os.path.dirname(__file__), "..", "agents", "gitops_agent", "tools", "tool_server.py"
    )
    if not os.path.isfile(tool_server_script):
        logger.warning("[Coordinator] Tool server script not found; clone/config_validator may fail.")
        return
    import subprocess
    venv_python = sys.executable
    tool_server_cwd = os.path.dirname(tool_server_script)
    subprocess.Popen(
        [venv_python, tool_server_script],
        cwd=tool_server_cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    time.sleep(2)
    logger.info("[Coordinator] Tool server started.")


def on_trigger(trigger_result: TriggerResult, parsed_intent: ParsedIntent, slack_context: dict):
    """Called by gateway when a valid trigger is detected (user run-request or pull_request)."""
    event = slack_context.get("event", {})
    say = slack_context.get("say")
    channel_id = event.get("channel") or ""
    thread_ts = event.get("thread_ts") or event.get("ts") or ""

    repo_url = config.DEFAULT_REPO_URL or parsed_intent.repo or ""
    if not repo_url:
        if say and channel_id:
            say(text=":x: No repo configured. Set DEFAULT_REPO_URL or specify repo.", channel=channel_id, thread_ts=thread_ts)
        return

    branch = parsed_intent.branch or "main"
    jira_ticket = parsed_intent.jira_ticket
    pr_number = parsed_intent.pr_number or trigger_result.pr_number

    def ask_user(question: str) -> str:
        if not say or not channel_id:
            return ""
        say(text=question, channel=channel_id, thread_ts=thread_ts)
        key = (channel_id, thread_ts)
        ev = threading.Event()
        reply_list = []
        pending_replies[key] = (ev, reply_list)
        ev.wait(timeout=300)
        pending_replies.pop(key, None)
        return (reply_list[0] if reply_list else "").strip()

    def run_in_thread():
        try:
            run_pipeline(
                repo_url=repo_url,
                branch=branch,
                jira_ticket=jira_ticket,
                trigger_source=trigger_result.source,
                pr_number=pr_number,
                ask_user=ask_user,
                slack_say=say,
                command_channel=channel_id,
                thread_ts=thread_ts,
            )
        except Exception as e:
            logger.exception(f"[Coordinator] Pipeline failed: {e}")
            if say and channel_id:
                say(text=f":x: Pipeline error: {e}", channel=channel_id, thread_ts=thread_ts)

    t = threading.Thread(target=run_in_thread, daemon=False)
    t.start()
    if say and channel_id:
        say(text=f":rocket: Pipeline started for branch `{branch}`. Logs will appear in the pipeline logs channel.", channel=channel_id, thread_ts=thread_ts)


def main():
    """Run the coordinator daemon (blocking)."""
    logger.info("[Coordinator] Starting daemon.")

    errors = config.validate_slack()
    if errors:
        for e in errors:
            logger.error(f"[Coordinator] Config: {e}")
        raise SystemExit(1)

    _start_tool_server()

    command_channel_id = config.SLACK_COMMAND_CHANNEL_ID
    default_repo = config.DEFAULT_REPO_URL
    default_branch = "main"

    run_gateway(
        command_channel_id=command_channel_id,
        on_trigger=on_trigger,
        default_repo=default_repo,
        default_branch=default_branch,
        pending_replies=pending_replies,
    )


if __name__ == "__main__":
    main()
