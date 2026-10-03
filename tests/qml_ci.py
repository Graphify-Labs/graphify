"""Verify optional QML wheels in clean environments on each CI host/Python lane."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile


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
    environment = dict(os.environ, GRAPHIFY_QML_TEST_WHEEL=str(wheel), PYTHONUTF8="1")
    tests = (["tests/test_qml_wheel_artifact.py"] if "--artifact-only" in sys.argv
             else sorted(str(path.relative_to(root)) for path in (root / "tests").glob("test_qml_*.py")))
    run(interpreter(extra), "-X", "utf8", "-m", "pytest", *tests, "-q", "-ra", "--tb=short",
        cwd=root, env=environment)


if __name__ == "__main__":
    main()
