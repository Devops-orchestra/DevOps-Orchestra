# File: langgraph_flows/code_analysis_flow.py

from langgraph.graph import StateGraph
from langgraph_flows.shared_nodes import run_code_analysis_node

def get_code_analysis_flow() -> StateGraph:
    builder = StateGraph(dict)
    builder.add_node("analyze_code", run_code_analysis_node)
    builder.set_entry_point("analyze_code")
    return builder.compile()
