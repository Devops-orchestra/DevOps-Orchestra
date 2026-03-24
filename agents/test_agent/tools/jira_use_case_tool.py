"""
Tool: get use case from Jira (summary, description, acceptance criteria).
Used by the Test agent to generate test cases aligned with the Jira use case.
"""
import os
import requests
from dataclasses import dataclass
from typing import Optional, List
import base64
from shared_modules.utils.logger import logger


@dataclass
class JiraUseCase:
    """Use case fetched from Jira."""
    key: str
    summary: str
    description: str
    acceptance_criteria: List[str]
    raw: Optional[dict] = None


def get_jira_use_case(ticket_key: str) -> JiraUseCase:
    """
    Fetch a Jira issue by key and return summary, description, and acceptance criteria.
    Uses JIRA_BASE_URL, JIRA_API_TOKEN, and optionally JIRA_EMAIL (for basic auth).
    """
    base_url = (os.getenv("JIRA_BASE_URL") or "").rstrip("/")
    api_token = os.getenv("JIRA_API_TOKEN") or ""
    email = os.getenv("JIRA_EMAIL") or ""

    if not base_url or not api_token:
        raise ValueError("JIRA_BASE_URL and JIRA_API_TOKEN must be set")

    url = f"{base_url}/rest/api/3/issue/{ticket_key}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if email:
        # Basic auth with email + API token (Atlassian)
        auth = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        headers["Authorization"] = f"Basic {auth}"
    else:
        headers["Authorization"] = f"Bearer {api_token}"

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error(f"[Jira] Failed to fetch {ticket_key}: {e}")
        raise

    fields = data.get("fields") or {}
    summary = (fields.get("summary") or "").strip()
    # Description can be ADF (Atlassian Document Format) or plain string
    desc_raw = fields.get("description")
    if isinstance(desc_raw, dict):
        # Simple ADF to plain text: concatenate text from content blocks
        description = _adf_to_plain(desc_raw)
    else:
        description = (desc_raw or "").strip() if desc_raw else ""

    # Acceptance criteria: often in a custom field or in description
    acceptance_criteria: List[str] = []
    # Common custom field names
    for field_name in ("customfield_10014", "customfield_10015", "acceptance criteria", "Acceptance Criteria"):
        val = fields.get(field_name)
        if val and isinstance(val, str):
            for line in val.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    acceptance_criteria.append(line)
        elif val and isinstance(val, dict):
            acceptance_criteria.append(_adf_to_plain(val))
    # Fallback: look for "Acceptance criteria" section in description
    if not acceptance_criteria and description:
        if "acceptance criteria" in description.lower() or "acceptance criteria" in description:
            for part in description.split("\n\n"):
                if "acceptance" in part.lower() or part.strip().startswith("-"):
                    for line in part.splitlines():
                        line = line.lstrip("-* ").strip()
                        if line:
                            acceptance_criteria.append(line)

    return JiraUseCase(
        key=ticket_key,
        summary=summary,
        description=description,
        acceptance_criteria=acceptance_criteria or [description] if description else [],
        raw=data,
    )


def _adf_to_plain(node: dict) -> str:
    """Convert Atlassian Document Format node to plain text (simplified)."""
    if not node:
        return ""
    buf = []
    if node.get("type") == "paragraph" or node.get("type") == "text":
        for c in node.get("content") or []:
            if c.get("type") == "text":
                buf.append(c.get("text") or "")
            else:
                buf.append(_adf_to_plain(c))
    elif node.get("type") == "bulletList" or node.get("type") == "orderedList":
        for item in node.get("content") or []:
            buf.append(_adf_to_plain(item))
    else:
        for c in node.get("content") or []:
            buf.append(_adf_to_plain(c))
    return "\n".join(buf).strip()
