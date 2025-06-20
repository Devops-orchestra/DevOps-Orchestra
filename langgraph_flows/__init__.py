from .code_analysis_flow import get_code_analysis_flow

def get_all_flows():
    return {
        "code_analysis": get_code_analysis_flow()
    }
