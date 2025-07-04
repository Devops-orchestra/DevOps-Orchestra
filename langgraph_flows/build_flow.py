# File: langgraph_flows/build_flow.py

from langgraph.graph import StateGraph
from langgraph_flows.shared_nodes import run_build_node

def get_build_flow() -> StateGraph:
    builder = StateGraph(dict)
    builder.add_node("build_image", run_build_node)
    builder.set_entry_point("build_image")
    return builder.compile()
