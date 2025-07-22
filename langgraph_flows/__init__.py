from .code_analysis_flow import get_code_analysis_flow
from .build_flow import get_build_flow
from .test_flow import get_test_flow
from .combined_flow import get_combined_flow  # if using connected flow
from .infra_flow import get_infra_flow

def get_all_flows():
    return {
        "code_analysis": get_code_analysis_flow(),
        "build": get_build_flow(),
        "test": get_test_flow,
        "combined": get_combined_flow(),
        "infra": get_infra_flow()
    }
