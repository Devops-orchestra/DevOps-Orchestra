"""Tests for GitOps + agent pipeline routing (langgraph_flows.pipeline_graph)."""

from langgraph_flows import pipeline_graph
from shared_modules.state.devops_state import DevOpsAgentState, StatusEnum


def _wrap(state: DevOpsAgentState) -> dict:
    return {"state": state}


def test_route_after_index_skips_to_build_when_flag_set() -> None:
    s = DevOpsAgentState()
    s.pipeline.skips.code_analysis = True
    assert pipeline_graph.route_after_index(_wrap(s)) == "build_image"

    s2 = DevOpsAgentState()
    s2.pipeline.skips.code_analysis = False
    assert pipeline_graph.route_after_index(_wrap(s2)) == "code_analysis"


def test_should_build_after_analysis_respects_skip_and_pass() -> None:
    s = DevOpsAgentState()
    s.pipeline.skips.code_analysis = True
    s.code_analysis.passed = False
    assert pipeline_graph.should_build_after_analysis(_wrap(s)) == "build_image"

    s2 = DevOpsAgentState()
    s2.pipeline.skips.code_analysis = False
    s2.code_analysis.passed = True
    assert pipeline_graph.should_build_after_analysis(_wrap(s2)) == "build_image"

    s3 = DevOpsAgentState()
    s3.pipeline.skips.code_analysis = False
    s3.code_analysis.passed = False
    assert pipeline_graph.should_build_after_analysis(_wrap(s3)) == "end"


def test_pipeline_check_build_skip_flag() -> None:
    s = DevOpsAgentState()
    s.pipeline.skips.build = True
    s.build_result.status = StatusEnum.FAILED
    assert pipeline_graph.check_build_status(_wrap(s)) == "test_code"


def test_pipeline_check_test_skip_then_end() -> None:
    s = DevOpsAgentState()
    s.pipeline.skips.test = True
    s.test_results.status = StatusEnum.FAILED
    assert pipeline_graph.check_test_status_then_end(_wrap(s)) == "end"


def test_pipeline_check_test_success_then_end() -> None:
    s = DevOpsAgentState()
    s.test_results.status = StatusEnum.SUCCESS
    assert pipeline_graph.check_test_status_then_end(_wrap(s)) == "end"


def test_pipeline_check_test_retries_then_end() -> None:
    s = DevOpsAgentState()
    s.test_results.status = StatusEnum.FAILED
    s.test_results.retries = pipeline_graph.MAX_RETRIES - 1
    assert pipeline_graph.check_test_status_then_end(_wrap(s)) == "end"
