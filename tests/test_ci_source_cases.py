"""INC-QML-56: bind the emitted source-retention gate to real collected cases."""
from __future__ import annotations

import ast
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODULES = (
    "tests.test_upstream_qt_cache_integration",
    "tests.test_upstream_qt_discovery_integration",
    "tests.test_upstream_qt_export_integration",
    "tests.test_upstream_qt_path_integration",
    "tests.test_upstream_qt_shared_integration",
)


def _gate():
    """Execute the actual workflow's bounded inventory/acceptance block."""
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    start = workflow.index("          integrated = {")
    end = workflow.index("          client = None", start)
    tree = ast.parse(textwrap.dedent(workflow[start:end]))
    assignment = tree.body[0]
    assert isinstance(assignment, ast.Assign), "The source inventory must remain explicit"
    inventory = ast.literal_eval(assignment.value)
    assert set(inventory) == set(MODULES), "A reviewed joint boundary was omitted"
    assert all(isinstance(names, set) and names and all(isinstance(name, str) for name in names)
               for names in inventory.values())
    return compile(tree, ".github/workflows/ci.yml:source-retention", "exec"), inventory


@pytest.fixture(scope="module")
def collected_cases(tmp_path_factory):
    """Collect production regressions without executing fixtures or copying their matrix."""
    output = tmp_path_factory.mktemp("ci_source_collection") / "cases.json"
    collector = """import json
from pathlib import Path
import sys
import pytest

class Collector:
    def pytest_collection_finish(self, session):
        cases = [(item.module.__name__, item.name) for item in session.items]
        Path(sys.argv[1]).write_text(json.dumps(cases), encoding="utf-8")

raise SystemExit(pytest.main([*sys.argv[2:], "--collect-only", "-q", "-p", "no:cacheprovider"],
                             plugins=[Collector()]))
"""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", collector, str(output),
         *(module.replace(".", "/") + ".py" for module in MODULES)],
        cwd=ROOT, env=dict(os.environ, PYTEST_ADDOPTS="", PYTHONUTF8="1"),
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-4000:]
    identities = json.loads(output.read_text(encoding="utf-8"))
    assert len({tuple(identity) for identity in identities}) == len(identities)
    assert {module for module, _ in identities} == set(MODULES)
    return [ET.Element("testcase", classname=module, name=name) for module, name in identities]


def _outcomes(cases):
    code, _ = _gate()
    namespace = {"cases": cases, "proof": {}}
    exec(code, namespace)
    return namespace["proof"]


def test_req_qml014_ac04_source_gate_accepts_every_collected_joint_case(collected_cases):
    """All actual schema/version combinations must pass the same gate used by CI."""
    code, inventory = _gate()
    assert code and len(collected_cases) == sum(map(len, inventory.values()))
    outcomes = _outcomes(collected_cases)
    assert set(outcomes) == set(MODULES) and all(outcomes.values()), outcomes


@pytest.mark.parametrize("outcome", ["missing", "duplicate", "duplicate_replacing_case", "foreign_name",
                                   "skipped", "failure", "error", "foreign"])
def test_req_qml014_ac04_source_gate_rejects_incomplete_or_failed_case(collected_cases, outcome):
    """Corrupt an actual cache outcome; the production gate must reject that module."""
    cases = deepcopy(collected_cases)
    selected = next(case for case in cases if case.get("classname") == MODULES[0])
    if outcome == "missing":
        cases.remove(selected)
    elif outcome == "duplicate":
        cases.append(deepcopy(selected))
    elif outcome == "duplicate_replacing_case":
        replaced = next(case for case in cases if case is not selected and case.get("classname") == MODULES[0])
        cases[cases.index(replaced)] = deepcopy(selected)
    elif outcome == "foreign_name":
        selected.set("name", "unreviewed_replacement_case")
    elif outcome == "foreign":
        selected.set("classname", "tests.unreviewed_boundary")
    else:
        ET.SubElement(selected, outcome)
    assert _outcomes(cases)[MODULES[0]] is False


def test_req_qml014_ac04_source_gate_rejects_unreviewed_matrix_growth(collected_cases):
    """New parametrizations need a reviewed gate update instead of stale green counts."""
    cases = deepcopy(collected_cases)
    cases.append(ET.Element("testcase", classname=MODULES[0], name="unreviewed_new_combination"))
    assert _outcomes(cases)[MODULES[0]] is False
