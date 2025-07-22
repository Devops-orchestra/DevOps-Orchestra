from langgraph.graph import StateGraph
from langgraph_flows.shared_nodes import run_infra_node

def get_infra_flow() -> StateGraph:
    builder = StateGraph(dict)
    builder.add_node("provision_infra", run_infra_node)
    builder.set_entry_point("provision_infra")
    return builder.compile() 