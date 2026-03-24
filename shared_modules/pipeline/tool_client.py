"""HTTP client for the GitOps tool server (clone, config_validator, license_audit, repo_size)."""
import os
from typing import Any, Dict

import httpx

from shared_modules.utils.logger import logger

TOOL_SERVER_URL = os.getenv("TOOL_SERVER_URL", "http://localhost:8001/invoke")


def call_tool(tool_name: str, input_payload: Dict[str, Any]) -> dict:
    try:
        r = httpx.post(
            TOOL_SERVER_URL,
            json={"tool_name": tool_name, "input": input_payload},
            timeout=120.0,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"[ToolClient] {tool_name} failed: {e}")
        return {"status": "error", "output": {"message": str(e)}}
