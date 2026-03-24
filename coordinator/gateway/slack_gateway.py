"""
Slack gateway: listens to the command channel, runs trigger filter, dispatches to pipeline handler.
Uses Slack Bolt with Socket Mode (no public URL required).
"""
import os
import threading
from typing import Callable, Any, Optional

from shared_modules.utils.logger import logger

from coordinator.gateway.trigger_filter import filter_trigger, TriggerResult
from coordinator.gateway.intent_parser import parse_user_run_intent, parse_pr_event_for_branch, ParsedIntent
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

def _get_message_text(event: dict) -> str:
    """Extract text from Slack message event (including possible bot message)."""
    text = (event.get("text") or "").strip()
    if text:
        return text
    blocks = event.get("blocks") or []
    for b in blocks:
        if b.get("type") == "section" and "text" in b:
            t = b["text"]
            if isinstance(t, dict) and "text" in t:
                return (t.get("text") or "").strip()
    return ""


def _is_bot_message(event: dict) -> bool:
    """True if message is from a bot (e.g. GitHub app)."""
    return bool(event.get("bot_id") or event.get("bot_profile") or event.get("subtype") == "bot_message")


def _bot_name(event: dict) -> str:
    """Bot name for logging."""
    bp = event.get("bot_profile") or {}
    return bp.get("name") or event.get("username") or "bot"


def run_gateway(
    command_channel_id: str,
    on_trigger: Callable[[TriggerResult, ParsedIntent, dict], None],
    default_repo: str = "",
    default_branch: str = "main",
    pending_replies: Optional[dict] = None,
) -> None:
    """
    Start the Slack gateway (blocking). Listens to command channel; on valid trigger
    calls on_trigger(trigger_result, parsed_intent, slack_event).
    Requires: slack_bolt, SLACK_BOT_TOKEN, SLACK_APP_TOKEN (Socket Mode).
    """

    app = App(token=os.getenv("SLACK_BOT_TOKEN"))

    def handle_message(message: dict, say: Callable, client: Any, context: Any):
        event = message
        channel_id = event.get("channel") or ""
        thread_ts = event.get("thread_ts") or event.get("ts")
        text_preview = (_get_message_text(event) or "")[:80]
        logger.info(f"[Gateway] Message received channel={channel_id} (expect {command_channel_id}) text={text_preview!r}")
        if channel_id != command_channel_id:
            logger.debug(f"[Gateway] Ignoring message: wrong channel (expected {command_channel_id})")
            return
        # If we're waiting for a user reply (e.g. Jira ticket or retry/resolved), treat this as the reply
        if pending_replies:
            key = (channel_id, (event.get("thread_ts") or ""))
            if key in pending_replies:
                event_obj, reply_list = pending_replies.pop(key, (None, None))
                text = _get_message_text(event)
                if reply_list is not None:
                    reply_list.append(text)
                if event_obj is not None:
                    try:
                        event_obj.set()
                    except Exception:
                        pass
                return
        # Skip our own messages
        user_id = event.get("user") or ""
        if context.get("bot_user_id") and user_id == context.get("bot_user_id"):
            return
        text = _get_message_text(event)
        is_bot = _is_bot_message(event)
        bot_name = _bot_name(event) if is_bot else ""

        result = filter_trigger(text, is_bot=is_bot, bot_name=bot_name)
        if not result.should_run:
            logger.info(f"[Gateway] Trigger not matched: is_bot={is_bot} text={text[:60]!r}")
            return

        if result.source == "user":
            parsed = parse_user_run_intent(text, default_repo=default_repo, default_branch=default_branch)
        else:
            # PR/bot: use parse_pr_event_for_branch to get branch/repo from message (and optional payload)
            payload = event.get("payload") or event.get("github_payload")  # if gateway ever has GitHub payload
            parsed = parse_pr_event_for_branch(text, payload=payload)
            parsed.raw_text = text
            # Overlay trigger filter result (e.g. from trigger_filter parsing)
            if result.pr_number is not None:
                parsed.pr_number = result.pr_number
            if result.branch:
                parsed.branch = result.branch
            if result.repo:
                parsed.repo = result.repo
            if not parsed.branch:
                parsed.branch = default_branch
            if not parsed.repo:
                parsed.repo = default_repo

        logger.info(f"[Gateway] Trigger: source={result.source} branch={parsed.branch} pr={parsed.pr_number}")
        try:
            on_trigger(result, parsed, {"event": event, "say": say, "client": client})
        except Exception as e:
            logger.exception(f"[Gateway] on_trigger failed: {e}")
            say(text=f":x: Pipeline trigger failed: {e}", channel=channel_id)

    app.message("")(handle_message)

    app_token = os.getenv("SLACK_APP_TOKEN")
    if not app_token:
        logger.error("[Gateway] SLACK_APP_TOKEN required for Socket Mode")
        raise ValueError("SLACK_APP_TOKEN required for Socket Mode")

    handler = SocketModeHandler(app, app_token)
    logger.info("[Gateway] Starting Socket Mode handler (command channel: %s)", command_channel_id)
    handler.start()


def run_gateway_with_pending(
    command_channel_id: str,
    on_trigger: Callable[[TriggerResult, ParsedIntent, dict], None],
    pending_replies: dict,
    default_repo: str = "",
    default_branch: str = "main",
) -> None:
    """Same as run_gateway but passes pending_replies for user-reply handling."""
    run_gateway(
        command_channel_id=command_channel_id,
        on_trigger=on_trigger,
        default_repo=default_repo,
        default_branch=default_branch,
        pending_replies=pending_replies,
    )


def run_gateway_in_thread(
    command_channel_id: str,
    on_trigger: Callable[[TriggerResult, ParsedIntent, dict], None],
    default_repo: str = "",
    default_branch: str = "main",
    pending_replies: Optional[dict] = None,
) -> threading.Thread:
    """Run the gateway in a background thread."""
    t = threading.Thread(
        target=run_gateway,
        kwargs=dict(
            command_channel_id=command_channel_id,
            on_trigger=on_trigger,
            default_repo=default_repo,
            default_branch=default_branch,
            pending_replies=pending_replies or {},
        ),
        daemon=False,
    )
    t.start()
    return t
