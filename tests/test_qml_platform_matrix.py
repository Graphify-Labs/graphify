"""Keep the declared artifact lanes and clean-install source boundaries honest."""
from __future__ import annotations

import ast
from itertools import product
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent


def test_advertised_twelve_lanes_equal_actual_wheel_workflow():
    workflow = (ROOT / ".github/workflows/qml-wheel.yml").read_text(encoding="utf-8")
    os_values = re.search(r"^\s+os: \[(.*?)\]$", workflow, re.MULTILINE)
    python_values = re.search(r"^\s+python: \[(.*?)\]$", workflow, re.MULTILINE)
    assert os_values is not None and python_values is not None
    operating_systems = [value.strip() for value in os_values.group(1).split(",")]
    interpreters = ast.literal_eval("[" + python_values.group(1) + "]")
    actual = set(product(operating_systems, interpreters))
    document = (ROOT / "docs/qt-qml/PLATFORM_MATRIX.md").read_text(encoding="utf-8")
    declared = set(re.findall(r"^\| ((?:ubuntu|windows|macos)-latest) \| (3\.\d+) \|", document, re.MULTILINE))
    assert len(actual) == len(declared) == 12
    assert declared == actual


def test_wheel_runner_keeps_optional_core_and_isolated_offline_smoke_boundaries():
    # Characterize the shipped CI runner rather than replace it with a mock CLI.
    runner = (ROOT / "tests/qml_ci.py").read_text(encoding="utf-8")
    smoke = (ROOT / "tests/qml_installed_smoke.py").read_text(encoding="utf-8")
    tree = ast.parse(runner)
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr in {"skip", "xfail"} for node in ast.walk(tree))
    assert 'str(wheel) + "[qml,watch]"' in runner
    assert 'interpreter(core), str(wheel)' in runner
    assert 'interpreter(extra), "-I", smoke' in runner
    assert 'interpreter(core), "-I", smoke, "--core-only"' in runner
    assert '"GRAPHIFY_QML_TEST_WHEEL"' in runner or "GRAPHIFY_QML_TEST_WHEEL=" in runner
    assert 'path.name.startswith(("test_qml_", "test_qt_"))' in runner
    assert '"socket.connect"' in smoke and '"subprocess.Popen"' in smoke
    assert "sys.addaudithook(offline_guard)" in smoke
    assert "QML_PARSER_MISSING" in smoke
    assert "validate_extraction(batch)" in smoke and "build_from_json(batch" in smoke
