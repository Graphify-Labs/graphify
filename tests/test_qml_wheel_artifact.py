"""QML-01 built-artifact contract, complementing clean dependency-install CI.

Set GRAPHIFY_QML_TEST_WHEEL to a reviewed built wheel. These tests deliberately
use installed host dependencies and force parser absence at the import boundary;
they are not substitutes for isolated full-extra/core-only installation jobs.
"""
from __future__ import annotations

from email.parser import Parser
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

from packaging.requirements import Requirement
import pytest

from tests.qml_test_helpers import WHEEL_PROBE, by_kind, write_qml


@pytest.fixture(scope="module")
def wheel():
    """Do not rebuild/mutate the shared checkout or silently invent an artifact."""
    value = os.environ.get("GRAPHIFY_QML_TEST_WHEEL")
    if not value:
        pytest.skip("Supply GRAPHIFY_QML_TEST_WHEEL from the built-wheel acceptance job")
    path = Path(value)
    assert path.is_file() and path.suffix == ".whl", "Reviewed built wheel unavailable"
    return path


def test_qml001_ac01_built_wheel_contains_adapter_and_optional_extra_metadata(wheel):
    """Shipping metadata selects the pinned optional grammar rather than changing core install."""
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        assert "graphify/extractors/qml.py" in names
        assert "graphify/extractors/qml_ast.py" in names
        assert "graphify/extractors/qml_declarations.py" in names
        assert "graphify/extractors/qml_facts.py" in names
        assert not any(name.startswith("tests/") for name in names)
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = Parser().parsestr(archive.read(metadata_name).decode("utf-8"))
    assert "qml" in metadata.get_all("Provides-Extra", [])
    requirements = [Requirement(value) for value in metadata.get_all("Requires-Dist", [])]
    grammar = [requirement for requirement in requirements if requirement.name == "tree-sitter-language-pack"]
    assert any(requirement.marker is not None and requirement.marker.evaluate({"extra": "qml"}) and str(requirement.specifier) == "==0.11.0" for requirement in grammar)
    assert all(requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}) for requirement in grammar)


@pytest.mark.parametrize("mode", ["qml", "core"])
def test_qml001_ac01_ac03_built_artifact_production_import_and_parser_boundary(wheel, tmp_path, mode):
    """A fresh interpreter imports the wheel artifact and exercises its actual adapter."""
    target = tmp_path / "artifact"
    target.mkdir()
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(target)
    corpus = tmp_path / "corpus"
    write_qml(corpus)
    (corpus / "safe.py").write_text("def safe():\n    return 1\n", encoding="utf-8")
    cwd = tmp_path / "empty-working-directory"
    cwd.mkdir()
    child = subprocess.run([sys.executable, "-I", "-c", WHEEL_PROBE, str(target), str(corpus), mode], cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=45)
    assert child.returncode == 0, child.stderr
    result = json.loads(child.stdout)
    assert result["python_ok"] is True
    if mode == "qml":
        assert not result["qml"].get("error")
        assert len(by_kind(result["qml"], "component")) == 1
        assert len(by_kind(result["qml"], "property")) == 6
    else:
        assert result["qml"].get("error") and result["qml"]["nodes"] == []
        assert any(diagnostic["code"] == "QML_PARSER_MISSING" for diagnostic in result["qml"]["diagnostics"])
