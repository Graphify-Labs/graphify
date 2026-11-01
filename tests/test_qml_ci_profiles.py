"""INC-QML-55: keep clean wheel proof separate from native joint-test admission."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
import yaml

from tests import qml_ci


@dataclass
class Invocation:
    """Retain only public command/profile facts from the subprocess boundary."""

    arguments: list[str]
    cwd: Path | None
    cwd_exists: bool
    wheel_environment: str | None
    utf8: str | None


@pytest.fixture
def profile(tmp_path, monkeypatch):
    """Run the real launcher against a public tree; only external processes are isolated."""
    root = tmp_path / "public-checkout"
    tests = root / "tests"
    tests.mkdir(parents=True)
    for name in ("test_qml_public.py", "test_qt_public.py", "test_upstream_qt_public.py", "test_unrelated.py"):
        (tests / name).write_text("def test_public(): pass\n", encoding="utf-8")
    workspace = root / ".venv/qml-ci"
    state = SimpleNamespace(root=root, workspace=workspace,
                            wheel=workspace / "wheel/graphifyy-0.9.92-py3-none-any.whl",
                            extra=workspace / "extra", core=workspace / "core", calls=[], failure=None)
    monkeypatch.setattr(qml_ci, "__file__", str(tests / "qml_ci.py"))
    monkeypatch.setattr(qml_ci.sys, "argv", ["qml_ci.py"])
    # Existing local command contracts are independent of an outer CI report.
    monkeypatch.delenv("GRAPHIFY_QML_JUNIT_PATH", raising=False)

    def external_process(arguments, *, check, **kwargs):
        """A successful uv build creates its sole artifact; failures preserve real check semantics."""
        assert check is True
        arguments = list(arguments)
        cwd = Path(kwargs["cwd"]) if "cwd" in kwargs else None
        environment = kwargs.get("env", {})
        state.calls.append(Invocation(arguments, cwd, bool(cwd and cwd.is_dir()),
                                      environment.get("GRAPHIFY_QML_TEST_WHEEL"), environment.get("PYTHONUTF8")))
        if arguments[:2] == ["uv", "build"]:
            state.wheel.parent.mkdir(parents=True)
            state.wheel.write_bytes(b"public subprocess-boundary wheel fixture")
        is_addon = arguments[-1] == str(state.wheel) + "[terraform]"
        is_smoke = "-I" in arguments
        mode = "core" if "--core-only" in arguments else "qml"
        if (state.failure == "addon" and is_addon) or (state.failure == mode and is_smoke):
            raise subprocess.CalledProcessError(1, arguments)
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(qml_ci.subprocess, "run", external_process)
    return state


def clean_prefix(profile):
    """These existing installs and isolated smoke arguments remain the optional/core contract."""
    smoke = str(profile.root / "tests/qml_installed_smoke.py")
    return [
        ["uv", "build", "--wheel", "--python", qml_ci.sys.executable,
         "--out-dir", str(profile.wheel.parent)],
        ["uv", "venv", "--python", qml_ci.sys.executable, str(profile.extra)],
        ["uv", "venv", "--python", qml_ci.sys.executable, str(profile.core)],
        ["uv", "pip", "install", "--python", qml_ci.interpreter(profile.extra),
         str(profile.wheel) + "[qml,watch]", "pytest>=8,<10", "packaging"],
        ["uv", "pip", "install", "--python", qml_ci.interpreter(profile.core), str(profile.wheel)],
        [qml_ci.interpreter(profile.extra), "-I", smoke],
        [qml_ci.interpreter(profile.core), "-I", smoke, "--core-only"],
    ]


def addon(profile):
    return ["uv", "pip", "install", "--python", qml_ci.interpreter(profile.extra),
            str(profile.wheel) + "[terraform]"]


def pytest_command(profile, selected):
    return [qml_ci.interpreter(profile.extra), "-X", "utf8", "-m", "pytest",
            *selected, "-q", "-ra", "--tb=short"]


def assert_neutral_smokes(profile):
    """Both real temporary working directories existed and were outside the source checkout."""
    qml, core = profile.calls[5:7]
    assert qml.cwd == core.cwd and qml.cwd != profile.root
    assert qml.cwd_exists and core.cwd_exists
    assert qml.wheel_environment is None and core.wheel_environment is None


def test_req_core004_ac02_native_profile_adds_terraform_after_clean_wheel_smokes(profile):
    """Native joint Terraform/Qt cases get the same built wheel's extra after clean proof succeeds."""
    qml_ci.main()
    selected = [str(Path("tests") / name) for name in
                ("test_qml_public.py", "test_qt_public.py", "test_upstream_qt_public.py")]
    assert [call.arguments for call in profile.calls] == [
        *clean_prefix(profile), addon(profile), pytest_command(profile, selected)]
    assert_neutral_smokes(profile)
    assert profile.calls[-1].cwd == profile.root
    assert profile.calls[-1].wheel_environment == str(profile.wheel)
    assert profile.calls[-1].utf8 == "1"


def test_req_core004_ac02_artifact_profile_preserves_clean_optional_boundaries(profile, monkeypatch):
    """Ubuntu artifact-only proof never admits Terraform and still tests the built wheel."""
    monkeypatch.setattr(qml_ci.sys, "argv", ["qml_ci.py", "--artifact-only"])
    qml_ci.main()
    assert [call.arguments for call in profile.calls] == [
        *clean_prefix(profile), pytest_command(profile, ["tests/test_qml_wheel_artifact.py"])]
    assert_neutral_smokes(profile)
    assert profile.calls[-1].wheel_environment == str(profile.wheel)


def test_req_qml022_ac06_native_profile_collects_shared_cpp_csharp_ownership(profile):
    """Core parser regressions join native source lanes after unchanged isolated-wheel smokes."""
    names = ("test_cpp_members.py", "test_csharp_fields.py", "test_field_call_ownership.py",
             "test_source_relationship_consumers.py")
    for name in names:
        (profile.root / "tests" / name).write_text("def test_boundary(): pass\n", encoding="utf-8")
    qml_ci.main()
    selected = profile.calls[-1].arguments
    assert all(str(Path("tests") / name) in selected for name in names)
    assert str(Path("tests") / "test_unrelated.py") not in selected
    assert [call.arguments for call in profile.calls[:-1]] == [*clean_prefix(profile), addon(profile)]
    assert_neutral_smokes(profile)


def test_req_qml018_ac06_native_profile_collects_upstream100_joint_and_generic_cases(profile):
    """Native lanes retain merge regressions and their upstream controls after clean smokes."""
    names = ("test_upstream_100_publication.py", "test_upstream_100_extraction.py",
             "test_upstream_100_cache.py", "test_4874_jvm_resolution.py",
             "test_4909_reference_binding_scale.py", "test_case_only_decl_ids_4904.py",
             "test_scala_extension_methods.py", "test_php_class_const_initializer_refs.py")
    for name in names:
        (profile.root / "tests" / name).write_text("def test_boundary(): pass\n", encoding="utf-8")
    qml_ci.main()
    selected = profile.calls[-1].arguments
    assert all(str(Path("tests") / name) in selected for name in names)
    assert str(Path("tests") / "test_unrelated.py") not in selected
    assert [call.arguments for call in profile.calls[:-1]] == [*clean_prefix(profile), addon(profile)]
    assert_neutral_smokes(profile)


def test_req_core004_ac03_failed_addon_stops_before_native_pytest(profile):
    """A failed declared-extra install remains a failed lane without retrying a reduced test set."""
    profile.failure = "addon"
    with pytest.raises(subprocess.CalledProcessError):
        qml_ci.main()
    assert [call.arguments for call in profile.calls] == [*clean_prefix(profile), addon(profile)]
    assert_neutral_smokes(profile)


@pytest.mark.parametrize("mode", ["qml", "core"])
def test_req_core004_ac03_failed_clean_smoke_cannot_admit_native_addon(profile, mode):
    """Either isolated smoke failure rejects before the extra install or native pytest can run."""
    profile.failure = mode
    with pytest.raises(subprocess.CalledProcessError):
        qml_ci.main()
    expected = clean_prefix(profile)[:6 if mode == "qml" else 7]
    assert [call.arguments for call in profile.calls] == expected


def test_req_core004_ac03_workflow_retains_matrix_bound_xml_on_all_outcomes():
    """The actual existing matrix retains each job's report even on a failed pytest exit."""
    path = Path(__file__).resolve().parents[1] / ".github/workflows/qml-wheel.yml"
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["qml-wheel"]
    assert job["strategy"]["matrix"] == {
        "os": ["ubuntu-latest", "windows-latest", "macos-latest"],
        "python": ["3.10", "3.12", "3.13", "3.14"]}
    steps = job["steps"]
    verify = next(step for step in steps if step.get("name") == "Verify installed wheels and platform contracts")
    report = next(step for step in steps if step.get("name") == "Retain per-case QML test evidence")
    expected = "${{ runner.temp }}/graphify-qml-results/tests.xml"
    assert verify["env"] == {"GRAPHIFY_QML_JUNIT_PATH": expected}
    assert verify["run"] == ("uv run --no-project --python ${{ matrix.python }} python tests/qml_ci.py "
                             "${{ runner.os == 'Linux' && '--artifact-only' || '' }}")
    assert report["if"] == "always()"
    assert report["uses"] == "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
    assert report["with"] == {
        "name": "qml-wheel-tests-${{ matrix.os }}-python-${{ matrix.python }}-${{ github.run_id }}-${{ github.run_attempt }}",
        "path": expected, "retention-days": "14", "if-no-files-found": "error"}
