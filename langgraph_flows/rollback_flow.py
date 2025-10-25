from langgraph.graph import StateGraph
from langgraph_flows.shared_nodes import run_rollback_node


def get_rollback_flow() -> StateGraph:
    builder = StateGraph(dict)

    builder.add_node("rollback", run_rollback_node)
    builder.add_node("end", lambda x: x)

    builder.add_edge("rollback", "end")

    builder.set_entry_point("rollback")
    return builder.compile()
