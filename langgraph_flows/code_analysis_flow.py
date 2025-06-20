import os
from langgraph.graph import StateGraph
from agents.code_analysis_agent.models.schemas import LLMCodeAnalysisInput
from agents.code_analysis_agent.tools.llm_code_analyzer import analyze_code_with_llm

REPO_BASE_PATH = "/tmp/gitops_repos"

def run_code_analysis(event: dict) -> dict:
    input_data = LLMCodeAnalysisInput(
        repo=event['repo_context']["repo"],
        branch=event['repo_context']["branch"],
        commit_id=event['repo_context']["commit"],
        repo_path=os.path.join(REPO_BASE_PATH, event['repo_context']["repo"]),
        file_limit=10,
        llm_model="llama-3.3-70b-versatile"
    )
    return analyze_code_with_llm(input_data)

def get_code_analysis_flow() -> StateGraph:
    builder = StateGraph(dict)
    builder.add_node("analyze_code", run_code_analysis)
    builder.set_entry_point("analyze_code")
    return builder.compile()
