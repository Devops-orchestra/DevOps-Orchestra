"""
Parse user message or trigger context into: branch, PR number, repo, optional Jira ticket.
"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedIntent:
    branch: Optional[str] = None
    pr_number: Optional[str] = None
    repo: Optional[str] = None
    jira_ticket: Optional[str] = None  # e.g. PROJ-123
    raw_text: str = ""


# Jira key: PROJECT-NUMBER
JIRA_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


def extract_jira_key(text: str) -> Optional[str]:
    """Extract first Jira ticket key from text (e.g. PROJ-123)."""
    if not text:
        return None
    m = JIRA_KEY_PATTERN.search(text)
    return m.group(1) if m else None


def parse_user_run_intent(text: str, default_repo: str = "", default_branch: str = "main") -> ParsedIntent:
    """
    Parse user message for run pipeline intent.
    Extracts branch name, PR number, Jira ticket if mentioned.
    """
    text = (text or "").strip()
    out = ParsedIntent(raw_text=text)

    # PR number
    pr_m = re.search(r"(?:PR|pull\s*request|#)\s*#?(\d+)", text, re.I)
    if pr_m:
        out.pr_number = pr_m.group(1)

    # Jira key
    out.jira_ticket = extract_jira_key(text)

    # Branch name: prefer "branch X" (so "for branch main" -> main), then "for X", then "run pipeline X"
    branch_explicit = re.search(r"branch\s+([a-zA-Z0-9/_.-]+)", text, re.I)
    if branch_explicit:
        out.branch = branch_explicit.group(1).strip()
    else:
        for_m = re.search(r"for\s+([a-zA-Z0-9/_.-]+)", text, re.I)
        if for_m:
            cand = for_m.group(1).strip()
            if cand and cand.lower() not in ("branch", "pr", "pipeline", "run") and not cand.isdigit():
                out.branch = cand
        if not out.branch:
            # "run pipeline feature/login" style (no "for" or "branch")
            run_m = re.search(r"(?:run\s+pipeline|pipeline|build)\s+(?:for\s+)?(?:branch\s+)?([a-zA-Z0-9/_.-]+)", text, re.I)
            if run_m:
                cand = run_m.group(1).strip()
                if cand and cand.lower() not in ("pr", "pipeline", "run", "branch", "for") and not cand.isdigit():
                    out.branch = cand

    if not out.branch and not out.pr_number:
        out.branch = default_branch
    if default_repo and not out.repo:
        out.repo = default_repo

    return out


def parse_pr_event_for_branch(attachments_or_text: str, payload: Optional[dict] = None) -> ParsedIntent:
    """
    From a GitHub PR event (e.g. from Slack attachment or webhook payload), get branch and repo.
    payload: if we had raw GitHub webhook payload, would contain head.ref, base.repo.clone_url, etc.
    Here we only have Slack message text/attachments; we can try to parse link or use defaults.
    """
    out = ParsedIntent(raw_text=attachments_or_text or "")
    if payload:
        try:
            head = payload.get("pull_request", {}).get("head", {})
            out.branch = head.get("ref", "").strip() or out.branch
            repo = payload.get("repository", {}) or payload.get("pull_request", {}).get("base", {}).get("repo", {})
            out.repo = repo.get("clone_url") or repo.get("full_name", "").strip() or out.repo
            out.pr_number = str(payload.get("pull_request", {}).get("number", "") or "")
        except Exception:
            pass
    # Fallback: parse "branch" from text if present
    if not out.branch and attachments_or_text:
        m = re.search(r"branch\s*[:\s]+([a-zA-Z0-9/_.-]+)", attachments_or_text, re.I)
        if m:
            out.branch = m.group(1).strip()
    return out
