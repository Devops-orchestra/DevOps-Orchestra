"""LangGraph flow registry: compiled graphs for each pipeline stage.
get_all_flows() returns named graphs for agents and the full pipeline.
"""
from .code_analysis_flow import get_code_analysis_flow
from .build_flow import get_build_flow
from .test_flow import get_test_flow
from .combined_flow import get_combined_flow, get_pipeline_agent_flow
from .pipeline_graph import get_full_pipeline_flow
from .infra_deploy_graph import get_infra_prepare_graph, get_post_approval_deploy_graph
from .infra_flow import get_infra_flow
from .deployment_flow import get_deployment_flow
from .rollback_flow import get_rollback_flow
from .observability_flow import get_observability_flow


def get_all_flows():
    return {
        "code_analysis": get_code_analysis_flow(),
        "build": get_build_flow(),
        "test": get_test_flow(),
        "combined": get_combined_flow(),
        "pipeline_agent": get_pipeline_agent_flow(),
        "full_pipeline": get_full_pipeline_flow(),
        "infra_prepare": get_infra_prepare_graph(),
        "post_approval_deploy": get_post_approval_deploy_graph(),
        "infra": get_infra_flow(),
        "deployment": get_deployment_flow(),
        "rollback": get_rollback_flow(),
        "observability": get_observability_flow(),
    }
