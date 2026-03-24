"""Tests for devops_orchestra.yaml schema validation (OrchestraConfig)."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from agents.gitops_agent.tools.handlers.config_validator import (
    OrchestraConfig,
    run_config_validation,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_CONFIG = REPO_ROOT / "devops_orchestra.yaml"


def test_sample_devops_orchestra_yaml_parses() -> None:
    assert SAMPLE_CONFIG.is_file()
    raw = yaml.safe_load(SAMPLE_CONFIG.read_text(encoding="utf-8"))
    cfg = OrchestraConfig(**raw)
    assert cfg.project.name == "my-app"
    assert cfg.project.language == "python"
    assert cfg.testing.enabled is True
    assert cfg.observability is not None
    assert cfg.observability.thresholds is not None
    assert cfg.observability.thresholds.cpu_usage == 80


def test_orchestra_config_rejects_missing_required_section() -> None:
    minimal = {"project": {"name": "x", "language": "py", "framework": "f", "repo": "https://x"}}
    with pytest.raises(ValidationError):
        OrchestraConfig(**minimal)


def test_run_config_validation_happy_path(tmp_path: Path) -> None:
    dest = tmp_path / "devops_orchestra.yaml"
    dest.write_text(SAMPLE_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    out = run_config_validation({"config_path": str(dest)})
    assert "valid" in out["message"].lower()
    assert out["project"] == "my-app"


def test_run_config_validation_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_config_validation({"config_path": str(tmp_path / "nope.yaml")})
