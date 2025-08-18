from langgraph.graph import StateGraph
from langgraph_flows.shared_nodes import run_observability_node


def get_observability_flow() -> StateGraph:
    builder = StateGraph(dict)
    builder.add_node("observe", run_observability_node)
    builder.set_entry_point("observe")
    return builder.compile()


