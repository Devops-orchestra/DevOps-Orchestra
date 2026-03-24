"""Pipeline utilities: HTTP client to the GitOps tool server.
Re-exports call_tool for clone, validate, license, and repo-size steps.
"""
from shared_modules.pipeline.tool_client import call_tool

__all__ = ["call_tool"]
