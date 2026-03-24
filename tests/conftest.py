"""Shared pytest fixtures for DevOps Orchestra tests."""

import pytest

from shared_modules.state.devops_state import DevOpsAgentState, StatusEnum


@pytest.fixture
def fresh_state() -> DevOpsAgentState:
    return DevOpsAgentState()


@pytest.fixture
def state_with_successful_analysis() -> DevOpsAgentState:
    # Do not depend on `fresh_state`: pytest reuses one sub-fixture instance per test.
    s = DevOpsAgentState()
    s.code_analysis.passed = True
    s.code_analysis.errors = []
    return s


@pytest.fixture
def state_with_failed_analysis() -> DevOpsAgentState:
    s = DevOpsAgentState()
    s.code_analysis.passed = False
    s.code_analysis.errors = ["syntax error"]
    return s
