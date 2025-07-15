from langgraph.graph import StateGraph
from langgraph_flows.shared_nodes import run_tests_node


def get_test_flow() -> StateGraph:
    builder = StateGraph(dict)
    builder.add_node("test_code", run_tests_node)
    builder.set_entry_point("test_code")
    return builder.compile()
