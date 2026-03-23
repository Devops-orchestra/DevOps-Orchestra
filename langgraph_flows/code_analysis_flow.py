# File: langgraph_flows/code_analysis_flow.py

from langgraph.graph import StateGraph
from langgraph_flows.shared_nodes import run_index_repo_node, run_code_analysis_node

def get_code_analysis_flow() -> StateGraph:
    builder = StateGraph(dict)
    builder.add_node("index_repo", run_index_repo_node)
    builder.add_node("analyze_code", run_code_analysis_node)
    builder.add_edge("index_repo", "analyze_code")
    builder.set_entry_point("index_repo")
    return builder.compile()
