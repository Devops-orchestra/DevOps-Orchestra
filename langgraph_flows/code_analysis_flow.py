import os
from langgraph.graph import StateGraph
from agents.code_analysis_agent.models.schemas import LLMCodeAnalysisInput
from agents.code_analysis_agent.tools.llm_code_analyzer import analyze_code_with_llm
from shared_modules.state.devops_state import DevOpsAgentState
from agents.code_analysis_agent.tools.llm_utils import parse_llm_summary

REPO_BASE_PATH = "/tmp/gitops_repos"

def run_code_analysis(inputs: dict) -> dict:
    event = inputs["event_data"]
    state: DevOpsAgentState = inputs["state"]
    input_data = LLMCodeAnalysisInput(
        repo=event['repo_context']["repo"],
        branch=event['repo_context']["branch"],
        commit_id=event['repo_context']["commit"],
        repo_path=os.path.join(REPO_BASE_PATH, event['repo_context']["repo"]),
        file_limit=10,
        llm_model="llama-3.3-70b-versatile"
    )

    llm_result = analyze_code_with_llm(input_data)

    if llm_result["results"]:
        parsed = parse_llm_summary(llm_result["results"][0]["analysis"])
        state.code_analysis.passed = parsed.passed
        state.code_analysis.errors = parsed.errors
        state.code_analysis.warnings = parsed.warnings
    print(state)
    return {
        "event_data": event,
        "state": state
    }

def get_code_analysis_flow() -> StateGraph:
    builder = StateGraph(dict)
    builder.add_node("analyze_code", run_code_analysis)
    builder.set_entry_point("analyze_code")
    return builder.compile()
