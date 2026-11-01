"""INC-QML-69: the actual stacked review retains ordinary full PR validation."""
from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize("name", ["ci.yml", "qml-wheel.yml"])
def test_qt_audit_stack_base_receives_normal_pull_request_validation(name):
    """An actual Qt integration base is admitted with no duplicate feature push."""
    path = Path(__file__).resolve().parents[1] / ".github/workflows" / name
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    triggers = workflow["on"]
    branch = "codex/qt-qml-upstream-094"
    assert any(fnmatchcase(branch, pattern) for pattern in triggers["pull_request"]["branches"])
    assert not any(fnmatchcase(branch, pattern) for pattern in triggers["push"]["branches"])
    assert {"v8", "main"} <= set(triggers["push"]["branches"])
    assert "pull_request_target" not in triggers and "workflow_run" not in triggers
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"
    if name == "qml-wheel.yml":
        matrix = workflow["jobs"]["qml-wheel"]["strategy"]["matrix"]
        assert matrix["os"] == ["ubuntu-latest", "windows-latest", "macos-latest"]
        assert matrix["python"] == ["3.10", "3.12", "3.13", "3.14"]
    else:
        assert {"skillgen-check", "test", "windows-compatibility", "pi-guard", "security-scan"} == set(workflow["jobs"])
