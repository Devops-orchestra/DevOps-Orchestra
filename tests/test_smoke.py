"""Fast import smoke checks for CI environments."""

def test_import_langgraph_flows() -> None:
    import langgraph_flows.combined_flow  # noqa: F401
    import langgraph_flows.pipeline_graph  # noqa: F401
