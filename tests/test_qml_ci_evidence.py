"""INC-QML-115: retain real per-case pytest XML without changing QML profiles."""
from __future__ import annotations

import os
import subprocess
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

from tests import qml_ci


@pytest.fixture
def reporter(tmp_path, monkeypatch):
    """Fake only installs/smokes; the actual launcher runs a tiny real pytest child."""
    root = tmp_path / "public-checkout"
    tests = root / "tests"
    tests.mkdir(parents=True)
    (root / "pytest.ini").write_text("[pytest]\naddopts =\n", encoding="utf-8")
    state = SimpleNamespace(root=root, report=tmp_path / "report space_Δ" / "tests.xml",
                            calls=[], actual_pytest=[], fail=False, artifact_only=False)
    monkeypatch.setattr(qml_ci, "__file__", str(tests / "qml_ci.py"))
    monkeypatch.setattr(qml_ci, "interpreter", lambda _environment: qml_ci.sys.executable)
    monkeypatch.setattr(qml_ci.sys, "argv", ["qml_ci.py"])
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    real_run = subprocess.run

    def external_process(arguments, *, check, **kwargs):
        """The owned fixture avoids installs and never redirects or simulates XML writes."""
        arguments = list(arguments)
        state.calls.append(arguments)
        if arguments[:2] == ["uv", "build"]:
            directory = root / ".venv/qml-ci/wheel"
            directory.mkdir(parents=True)
            (directory / "graphifyy-0.9.99-py3-none-any.whl").write_bytes(b"inert wheel fixture")
        if "pytest" in arguments:
            state.actual_pytest.append((arguments, dict(kwargs["env"])))
            return real_run(arguments, check=check, capture_output=True, text=True,
                            encoding="utf-8", timeout=45, **kwargs)
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(qml_ci.subprocess, "run", external_process)
    return state


def prepare(reporter, monkeypatch, *, artifact_only, fail=False):
    """Preserve the real native/artifact selection while bounding child execution."""
    reporter.artifact_only = artifact_only
    name = "test_qml_wheel_artifact.py" if artifact_only else "test_qt_public.py"
    count = 3 if artifact_only else 2
    source = "import os\n\n"
    for index in range(count):
        source += (f"def test_public_{index}():\n"
                   "    assert 'GRAPHIFY_QML_JUNIT_PATH' not in os.environ\n"
                   f"    assert {not (fail and index == count - 1)!r}\n\n")
    (reporter.root / "tests" / name).write_text(source, encoding="utf-8")
    monkeypatch.setattr(qml_ci.sys, "argv", ["qml_ci.py", *(["--artifact-only"] if artifact_only else [])])
    monkeypatch.setenv("GRAPHIFY_QML_JUNIT_PATH", str(reporter.report))
    return count


def read_cases(reporter, expected):
    """Names/outcomes come from pytest's durable report, not mocked arguments."""
    cases = list(ET.parse(reporter.report).iter("testcase"))
    assert len(cases) == expected
    assert {case.get("name") for case in cases} == {f"test_public_{index}" for index in range(expected)}
    assert all(case.find("skipped") is None and case.find("error") is None for case in cases)
    return cases


@pytest.mark.parametrize("artifact_only", [False, True])
def test_req_core004_ac03_actual_profiles_persist_individual_passes(reporter, monkeypatch, artifact_only):
    """Both existing profiles write exact passed IDs and keep outer report state out of the child."""
    expected = prepare(reporter, monkeypatch, artifact_only=artifact_only)
    qml_ci.main()
    cases = read_cases(reporter, expected)
    assert all(case.find("failure") is None for case in cases)
    (arguments, environment), = reporter.actual_pytest
    assert arguments[-1] == f"--junitxml={reporter.report}"
    assert "GRAPHIFY_QML_JUNIT_PATH" not in environment
    assert os.environ["GRAPHIFY_QML_JUNIT_PATH"] == str(reporter.report)
    assert any("[terraform]" in argument for call in reporter.calls for argument in call) is not artifact_only


@pytest.mark.parametrize("artifact_only", [False, True])
def test_req_core004_ac03_failed_profile_retains_exact_failed_case(reporter, monkeypatch, artifact_only):
    """A real child assertion failure stays nonzero and retains its individual failed XML record."""
    expected = prepare(reporter, monkeypatch, artifact_only=artifact_only, fail=True)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        qml_ci.main()
    assert caught.value.returncode == 1
    cases = read_cases(reporter, expected)
    failed = [case.get("name") for case in cases if case.find("failure") is not None]
    assert failed == [f"test_public_{expected - 1}"]
    assert "GRAPHIFY_QML_JUNIT_PATH" not in reporter.actual_pytest[0][1]


@pytest.mark.parametrize("artifact_only", [False, True])
def test_req_core004_ac03_directory_report_destination_retains_owned_sentinel(reporter, monkeypatch, artifact_only):
    """Pytest's actual directory-destination preflight retains the owned prior sentinel."""
    prepare(reporter, monkeypatch, artifact_only=artifact_only)
    reporter.report.mkdir(parents=True)
    sentinel = reporter.report / "accepted.bin"
    sentinel.write_bytes(b"accepted report directory\x00\xff")
    before = sentinel.read_bytes()
    with pytest.raises(subprocess.CalledProcessError) as caught:
        qml_ci.main()
    assert caught.value.returncode == 4
    output = (caught.value.stdout or "") + (caught.value.stderr or "")
    assert "--junitxml must be a filename" in output
    assert reporter.report.is_dir() and sentinel.read_bytes() == before
    assert list(reporter.report.iterdir()) == [sentinel]
    assert f"--junitxml={reporter.report}" in reporter.actual_pytest[0][0]


@pytest.mark.parametrize("artifact_only", [False, True])
def test_req_core004_ac03_actual_report_write_failure_retains_accepted_parent(reporter, monkeypatch, artifact_only):
    """A real pytest report write fails on an owned file-parent and retains its accepted bytes."""
    prepare(reporter, monkeypatch, artifact_only=artifact_only)
    parent = reporter.report.parent
    parent.write_bytes(b"accepted parent artifact\x00\xff")
    before = parent.read_bytes()
    with pytest.raises(subprocess.CalledProcessError) as caught:
        qml_ci.main()
    output = (caught.value.stdout or "") + (caught.value.stderr or "")
    assert caught.value.returncode != 0
    assert "FileExistsError" in output or "NotADirectoryError" in output
    assert parent.is_file() and parent.read_bytes() == before
    assert not reporter.report.exists()
    assert f"--junitxml={reporter.report}" in reporter.actual_pytest[0][0]


@pytest.mark.parametrize("value", [None, ""])
def test_req_core004_ac03_unset_report_path_preserves_local_command(reporter, monkeypatch, value):
    """A local unset hook retains the prior command and produces no report side effect."""
    prepare(reporter, monkeypatch, artifact_only=False)
    if value is None:
        monkeypatch.delenv("GRAPHIFY_QML_JUNIT_PATH")
    else:
        monkeypatch.setenv("GRAPHIFY_QML_JUNIT_PATH", value)
    qml_ci.main()
    assert not reporter.report.exists()
    assert not any(value.startswith("--junitxml") for value in reporter.actual_pytest[0][0])
