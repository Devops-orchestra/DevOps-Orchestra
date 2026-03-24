"""Tests for conditional routing in langgraph_flows.combined_flow (standalone DAG)."""

import pytest

from langgraph_flows import combined_flow
from shared_modules.state.devops_state import DevOpsAgentState, StatusEnum


def _wrap(state: DevOpsAgentState) -> dict:
    return {"state": state}


def test_should_build_routes_on_code_analysis_passed(
    state_with_successful_analysis: DevOpsAgentState,
    state_with_failed_analysis: DevOpsAgentState,
) -> None:
    assert combined_flow.should_build(_wrap(state_with_successful_analysis)) == "build_image"
    assert (
        combined_flow.should_build(_wrap(state_with_failed_analysis))
        == "notify_code_analysis_failure"
    )


def test_check_build_status_success_goes_to_tests(state_with_successful_analysis: DevOpsAgentState) -> None:
    state_with_successful_analysis.build_result.status = StatusEnum.SUCCESS
    assert combined_flow.check_build_status(_wrap(state_with_successful_analysis)) == "test_code"


def test_check_build_status_failed_schedules_retry(
    state_with_successful_analysis: DevOpsAgentState,
) -> None:
    s = state_with_successful_analysis
    s.build_result.status = StatusEnum.FAILED
    s.build_result.retries = 0
    assert combined_flow.check_build_status(_wrap(s)) == "build_image"
    assert s.build_result.retries == 1


def test_check_build_status_failed_after_max_retries_notifies() -> None:
    s = DevOpsAgentState()
    s.build_result.status = StatusEnum.FAILED
    s.build_result.retries = combined_flow.MAX_RETRIES - 1
    assert combined_flow.check_build_status(_wrap(s)) == "notify_build_failure"
    assert s.build_result.retries == combined_flow.MAX_RETRIES


def test_check_test_status_success_provisions_infra(state_with_successful_analysis: DevOpsAgentState) -> None:
    state_with_successful_analysis.test_results.status = StatusEnum.SUCCESS
    assert combined_flow.check_test_status(_wrap(state_with_successful_analysis)) == "provision_infra"


def test_check_infrastructure_and_deploy_routing() -> None:
    s = DevOpsAgentState()
    s.infra.status = StatusEnum.SUCCESS
    assert combined_flow.check_infrastructure_status(_wrap(s)) == "deploy"

    s2 = DevOpsAgentState()
    s2.infra.status = StatusEnum.FAILED
    assert combined_flow.check_infrastructure_status(_wrap(s2)) == "notify_infra_failure"

    s3 = DevOpsAgentState()
    s3.deployment.status = StatusEnum.SUCCESS
    assert combined_flow.check_deploy_status(_wrap(s3)) == "end"

    s4 = DevOpsAgentState()
    s4.deployment.status = StatusEnum.FAILED
    assert combined_flow.check_deploy_status(_wrap(s4)) == "rollback"
