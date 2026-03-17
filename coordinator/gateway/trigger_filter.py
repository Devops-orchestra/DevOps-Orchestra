"""
Trigger filter: pipeline runs only on user run-request or pull_request.
Push and commit events are NOT validated/triggered.
"""
import re
from typing import Optional
from dataclasses import dataclass


@dataclass
class TriggerResult:
    should_run: bool
    source: str  # "user" | "pull_request" | ""
    branch: Optional[str] = None
    pr_number: Optional[str] = None
    repo: Optional[str] = None
    raw_text: str = ""


# User message patterns that mean "run pipeline"
RUN_PATTERNS = [
    re.compile(r"run\s+pipeline\s+(?:for\s+)?(?:branch\s+)?([^\s#]+)", re.I),
    re.compile(r"pipeline\s+(?:for\s+)?(?:branch\s+)?([^\s#]+)", re.I),
    re.compile(r"run\s+(?:for\s+)?(?:branch\s+)?([^\s#]+)", re.I),
    re.compile(r"build\s+(?:branch\s+)?([^\s#]+)", re.I),
]
# PR pattern in user message: "run pipeline for PR #42" or "pipeline PR #42"
PR_PATTERN_USER = re.compile(r"(?:PR|pull\s*request)\s*#?(\d+)", re.I)

# When GitHub app posts to Slack, message often contains "opened a pull request" or "pull request #N"
# We treat messages from bots that contain pull request as PR trigger; push/commit we ignore.
PR_PATTERN_GITHUB = re.compile(
    r"(?:opened|created|synchronize).*pull\s*request|pull\s*request\s*#(\d+)|PR\s*#(\d+)",
    re.I | re.DOTALL
)
PUSH_PATTERN = re.compile(r"pushed\s+to|push\s+to|committed?", re.I)


def is_user_run_request(text: str, is_bot: bool) -> TriggerResult:
    """Check if this is a user asking to run the pipeline (branch or PR)."""
    if is_bot:
        return TriggerResult(should_run=False, source="", raw_text=text)
    text = (text or "").strip()
    if not text:
        return TriggerResult(should_run=False, source="", raw_text=text)

    # Check for PR in user message
    pr_match = PR_PATTERN_USER.search(text)
    if pr_match:
        pr_num = pr_match.group(1)
        return TriggerResult(should_run=True, source="user", pr_number=pr_num, raw_text=text)

    # Check for branch name
    for pat in RUN_PATTERNS:
        m = pat.search(text)
        if m:
            branch = m.group(1).strip()
            if len(branch) < 2 or branch.lower() in ("pr", "pipeline", "run", "for"):
                continue
            return TriggerResult(should_run=True, source="user", branch=branch, raw_text=text)

    return TriggerResult(should_run=False, source="", raw_text=text)


def is_pull_request_event(text: str, is_bot: bool, bot_name: str = "") -> TriggerResult:
    """
    Check if this message represents a GitHub pull_request event.
    Push and commit events return should_run=False.
    """
    if not is_bot:
        return TriggerResult(should_run=False, source="", raw_text=text or "")
    text = (text or "").strip()
    # Ignore push/commit
    if PUSH_PATTERN.search(text) and "pull" not in text.lower() and "pr" not in text.upper():
        return TriggerResult(should_run=False, source="", raw_text=text)
    # Check for pull request
    m = PR_PATTERN_GITHUB.search(text)
    if m:
        pr_num = m.group(1) or m.group(2) if m.lastindex and m.lastindex >= 2 else None
        return TriggerResult(
            should_run=True,
            source="pull_request",
            pr_number=pr_num or "",
            raw_text=text
        )
    return TriggerResult(should_run=False, source="", raw_text=text)


def filter_trigger(
    text: str,
    is_bot: bool,
    bot_name: str = "",
) -> TriggerResult:
    """
    Decide if this Slack message should trigger the pipeline.
    Returns TriggerResult with should_run=True only for:
    - User message that is a run request (branch or PR), or
    - Bot message that is a pull_request event (not push/commit).
    """
    # First try user run request (only for non-bot)
    r = is_user_run_request(text, is_bot)
    if r.should_run:
        return r
    # Then try PR event from bot (e.g. GitHub app)
    r = is_pull_request_event(text, is_bot, bot_name)
    if r.should_run:
        return r
    return TriggerResult(should_run=False, source="", raw_text=text or "")
