"""Smoke-compile LangGraph pipelines (structure only; no agent execution)."""

from langgraph_flows.combined_flow import get_combined_flow
from langgraph_flows.pipeline_graph import get_full_pipeline_flow, get_pipeline_agent_flow


def test_combined_flow_compiles() -> None:
    g = get_combined_flow()
    assert g is not None


def test_full_pipeline_flow_compiles() -> None:
    g1 = get_full_pipeline_flow()
    g2 = get_pipeline_agent_flow()
    assert g1 is not None
    assert g2 is not None
