"""Git metadata helper: clone path/branch always set; optional real-git smoke test."""

import shutil
import subprocess
from pathlib import Path

import pytest

from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.utils.git_metadata import populate_git_metadata


def test_populate_git_metadata_sets_local_path_and_branch() -> None:
    state = DevOpsAgentState()
    populate_git_metadata(state, "/tmp/fake-clone", "feature/x")
    assert state.git_meta.local_path == "/tmp/fake-clone"
    assert state.git_meta.branch == "feature/x"


@pytest.mark.skipif(not shutil.which("git"), reason="git binary not available")
def test_populate_git_metadata_with_real_repo(tmp_path: Path) -> None:
    init = subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, text=True)
    if init.returncode != 0:
        pytest.skip(f"git init not supported in this environment: {init.stderr or init.stdout}")
    subprocess.run(
        ["git", "config", "user.email", "ci@test.dev"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "CI Test"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / "file.txt").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    state = DevOpsAgentState()
    populate_git_metadata(state, str(tmp_path), "main")

    assert state.git_meta.local_path == str(tmp_path)
    assert state.git_meta.branch == "main"
    assert isinstance(state.git_meta.changed_files, list)
    assert state.git_meta.diff_summary is not None
