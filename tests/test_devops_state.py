"""Tests for shared Pydantic state models and serialization."""

import json

import pytest

from shared_modules.state.devops_state import (
    DevOpsAgentState,
    PipelineMeta,
    PipelineSkips,
    StatusEnum,
)


def test_devops_agent_state_defaults(fresh_state: DevOpsAgentState) -> None:
    assert fresh_state.pipeline.status == StatusEnum.NOT_STARTED
    assert fresh_state.pipeline.skips.validate_config is False
    assert fresh_state.test_results.retries == 0
    assert fresh_state.test_results.last_generated_code is None


def test_pipeline_skips_partial_update() -> None:
    skips = PipelineSkips(code_analysis=True, build=True)
    assert skips.test is False
    assert skips.code_analysis is True


def test_test_results_retry_fields_roundtrip() -> None:
    from shared_modules.state.devops_state import TestResults

    tr = TestResults(
        retries=2,
        last_generated_code="def test_x(): pass",
        last_run_failure_logs="AssertionError",
        status=StatusEnum.FAILED,
    )
    data = tr.model_dump()
    tr2 = TestResults(**data)
    assert tr2.last_generated_code == tr.last_generated_code
    assert tr2.retries == 2


def test_devops_agent_state_json_roundtrip(fresh_state: DevOpsAgentState) -> None:
    fresh_state.pipeline = PipelineMeta(
        pipeline_id="run-1",
        trigger_type="slack",
        status=StatusEnum.IN_PROGRESS,
        last_failed_step="build_image",
    )
    payload = json.loads(fresh_state.model_dump_json())
    restored = DevOpsAgentState.model_validate(payload)
    assert restored.pipeline.pipeline_id == "run-1"
    assert restored.pipeline.last_failed_step == "build_image"


@pytest.mark.parametrize(
    "status_val,expected_str",
    [
        (StatusEnum.SUCCESS, "success"),
        (StatusEnum.FAILED, "failed"),
    ],
)
def test_status_enum_string_compat(status_val: StatusEnum, expected_str: str) -> None:
    assert status_val == expected_str
    assert str(status_val).lower().endswith(expected_str)
