from langgraph.graph import StateGraph
from langgraph_flows.shared_nodes import run_observability_node


def get_observability_flow() -> StateGraph:
    builder = StateGraph(dict)
    
    builder.add_node("monitor_resources", run_observability_node)
    builder.set_entry_point("monitor_resources")
    
    return builder.compile()
