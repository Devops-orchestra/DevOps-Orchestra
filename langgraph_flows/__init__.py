from .code_analysis_flow import get_code_analysis_flow
from .build_flow import get_build_flow
from .test_flow import get_test_flow
from .combined_flow import get_combined_flow  # if using connected flow
from .infra_flow import get_infra_flow
from .deployment_flow import get_deployment_flow
from .rollback_flow import get_rollback_flow

def get_all_flows():
    return {
        "code_analysis": get_code_analysis_flow(),
        "build": get_build_flow(),
        "test": get_test_flow,
        "combined": get_combined_flow(),
        "infra": get_infra_flow(),
        "deployment": get_deployment_flow(),
        "rollback": get_rollback_flow(),
    }
