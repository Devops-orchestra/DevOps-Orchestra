from .code_analysis_flow import get_code_analysis_flow
from agents.build_agent.workflow.build_flow import get_build_flow 

def get_all_flows():
    return {
        "code_analysis": get_code_analysis_flow(),
        "build": get_build_flow()
    }
