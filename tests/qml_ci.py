"""Verify optional QML wheels in clean environments on each CI host/Python lane."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile


# These incoming regressions use only core grammars; native source lanes must
# keep their generic controls alongside the merge-specific Qt/source contracts.
_UPSTREAM_NATIVE_TESTS = frozenset({
    "test_4874_jvm_resolution.py", "test_4909_reference_binding_scale.py",
    "test_case_only_decl_ids_4904.py", "test_scala_extension_methods.py",
    "test_php_class_const_initializer_refs.py",
})


def selected_tests(root, *, artifact_only=False):
    """Own the native source inventory without changing isolated wheel admission."""
    if artifact_only:
        return ["tests/test_qml_wheel_artifact.py"]
    return sorted(str(path.relative_to(root)) for path in (root / "tests").glob("test_*.py")
                  if path.name in _UPSTREAM_NATIVE_TESTS or path.name.startswith((
                      "test_qml_", "test_qt_", "test_upstream_qt_", "test_upstream_100_",
                      "test_cpp_", "test_csharp_", "test_field_call_", "test_source_relationship_")))


def run(*args, **kwargs):
    subprocess.run(list(args), check=True, **kwargs)


def interpreter(environment):
    return str(environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))


def main():
    root = Path(__file__).resolve().parent.parent
    workspace = root / ".venv/qml-ci"
    wheel_directory = workspace / "wheel"
    run("uv", "build", "--wheel", "--python", sys.executable, "--out-dir", str(wheel_directory), cwd=root)
    wheels = list(wheel_directory.glob("*.whl"))
    assert len(wheels) == 1, "Expected exactly one reviewed Graphify wheel"
    wheel = wheels[0]
    extra, core = workspace / "extra", workspace / "core"
    for environment in (extra, core):
        run("uv", "venv", "--python", sys.executable, str(environment))
    run("uv", "pip", "install", "--python", interpreter(extra), str(wheel) + "[qml,watch]",
        "pytest>=8,<10", "packaging")
    run("uv", "pip", "install", "--python", interpreter(core), str(wheel))
    smoke = str(root / "tests/qml_installed_smoke.py")
    with tempfile.TemporaryDirectory() as neutral:
        run(interpreter(extra), "-I", smoke, cwd=neutral)
        run(interpreter(core), "-I", smoke, "--core-only", cwd=neutral)
    # Native source tests include joint Terraform/Qt refresh contracts. Admit
    # that declared extra only after clean QML/core wheel proof has succeeded;
    # Ubuntu's artifact-only profile retains its original optional boundaries.
    if "--artifact-only" not in sys.argv:
        run("uv", "pip", "install", "--python", interpreter(extra), str(wheel) + "[terraform]")
    environment = dict(os.environ, GRAPHIFY_QML_TEST_WHEEL=str(wheel), PYTHONUTF8="1")
    # Only this owning pytest process may write the CI report. Nested launcher
    # fixtures must not inherit its destination and overwrite outer evidence.
    report_path = environment.pop("GRAPHIFY_QML_JUNIT_PATH", None)
    report_arguments = [f"--junitxml={report_path}"] if report_path else []
    # The same stateless inventory drives execution and offline collection
    # guards. Linux still owns the full suite; artifact-only keeps clean smokes.
    tests = selected_tests(root, artifact_only="--artifact-only" in sys.argv)
    run(interpreter(extra), "-X", "utf8", "-m", "pytest", *tests, "-q", "-ra", "--tb=short", *report_arguments,
        cwd=root, env=environment)


if __name__ == "__main__":
    main()
