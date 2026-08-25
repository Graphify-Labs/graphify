"""A /bin/sh launcher wrapper must not be probed as if it were python (#3027).

pipx (via distlib's "exec trick", used when the install path has spaces)
generates a `graphify` launcher whose shebang is `#!/bin/sh` and whose second
line execs the real interpreter. The hook parsed that shebang into
GRAPHIFY_PYTHON and ran `/bin/sh -c "import graphify"` — which is not a
shell builtin, so it resolved on PATH to ImageMagick's `import` screenshot
tool and dumped its usage text on every commit. Only stderr was silenced.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from graphify.hooks import _PYTHON_DETECT

pytestmark = pytest.mark.skipif(shutil.which("sh") is None, reason="sh required to run the probe chain")


def _stub(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8", newline="\n")
    path.chmod(0o755)
    return path


def _machine(tmp_path: Path, *, wrapper_exec: str | None):
    """PATH holds: a /bin/sh `graphify` wrapper, ImageMagick's `import`, and
    ambient pythons that cannot import graphify. `wrapper_exec` is the
    interpreter the wrapper execs (None: a wrapper with no exec line)."""
    stub_bin = tmp_path / "stubbin"
    stub_bin.mkdir()
    _stub(stub_bin / "import", '#!/bin/sh\necho "Usage: import [options ...] [ file ]"\nexit 1\n')
    for name in ("python3", "python"):
        _stub(stub_bin / name, "#!/bin/sh\nexit 1\n")
    exec_line = f"'''exec' \"{wrapper_exec}\" \"$0\" \"$@\"\n' '''\n" if wrapper_exec else "echo wrapper\n"
    _stub(stub_bin / "graphify", "#!/bin/sh\n" + exec_line)
    home = tmp_path / "home"
    home.mkdir()
    return home, stub_bin


def _venv_python(tmp_path: Path, ok: bool = True) -> Path:
    venv = tmp_path / "pipx venvs" / "graphifyy" / "bin"  # a space, as in the wild
    venv.mkdir(parents=True)
    return _stub(venv / "python", "#!/bin/sh\nexit 0\n" if ok else "#!/bin/sh\nexit 1\n")


def _run(tmp_path: Path, home: Path, stub_bin: Path) -> subprocess.CompletedProcess:
    script = tmp_path / "detect_run.sh"
    script.write_text(_PYTHON_DETECT + '\necho "RESOLVED=$GRAPHIFY_PYTHON"\n', encoding="utf-8", newline="\n")
    env = dict(os.environ)
    env["HOME"] = str(home)
    env.pop("UV_TOOL_DIR", None)
    env["PATH"] = str(stub_bin) + os.pathsep + env["PATH"]
    return subprocess.run(["sh", script.name], capture_output=True, text=True, cwd=str(tmp_path), env=env)


def test_the_wrappers_interpreter_is_used_and_imagemagick_is_never_run(tmp_path):
    py = _venv_python(tmp_path)
    home, stub_bin = _machine(tmp_path, wrapper_exec=py.as_posix())
    res = _run(tmp_path, home, stub_bin)
    assert res.returncode == 0, res.stderr
    assert "Usage: import" not in res.stdout + res.stderr, "the shell was probed with -c 'import ...'"
    assert f"RESOLVED={py.as_posix()}" in res.stdout, res.stdout + res.stderr


def test_a_wrapper_with_no_exec_line_falls_through_quietly(tmp_path):
    home, stub_bin = _machine(tmp_path, wrapper_exec=None)
    res = _run(tmp_path, home, stub_bin)
    assert "Usage: import" not in res.stdout + res.stderr
    assert "RESOLVED=/bin/sh" not in res.stdout
    assert "RESOLVED=sh" not in res.stdout


def test_a_wrapper_whose_interpreter_cannot_import_graphify_is_not_adopted(tmp_path):
    py = _venv_python(tmp_path, ok=False)
    home, stub_bin = _machine(tmp_path, wrapper_exec=py.as_posix())
    res = _run(tmp_path, home, stub_bin)
    assert f"RESOLVED={py.as_posix()}" not in res.stdout
    assert "Usage: import" not in res.stdout + res.stderr


def test_a_plain_python_shebang_still_resolves_as_before(tmp_path):
    py = _venv_python(tmp_path)
    home, stub_bin = _machine(tmp_path, wrapper_exec=None)
    _stub(stub_bin / "graphify", f"#!{py.as_posix()}\nimport sys\n")
    res = _run(tmp_path, home, stub_bin)
    assert f"RESOLVED={py.as_posix()}" in res.stdout, res.stdout + res.stderr


def test_only_python_like_interpreters_are_ever_probed():
    """The emitted script gates the probe on the interpreter's name."""
    assert "python*|pypy*)" in _PYTHON_DETECT
