"""Pi owns registration; Graphify supplies a wheel-contained native package."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from graphify.install import dispatch_install_cli

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]


def test_pi_guard_path_is_a_complete_packaged_extension(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["graphify", "pi", "guard", "path"])
    assert dispatch_install_cli("pi")
    package = Path(capsys.readouterr().out.strip())
    manifest = json.loads((package / "package.json").read_text(encoding="utf-8"))
    entries = manifest["pi"]["extensions"]
    assert entries
    pyproject = tomllib.loads((package.parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]["graphify"]
    assert "pi/package.json" in package_data
    for entry in entries:
        assert (package / entry).is_file()
        assert (package / entry).resolve().is_relative_to(package)
        assert f"pi/{Path(entry).name}" in package_data


@pytest.mark.parametrize(("action", "verb"), [("install", "install"), ("uninstall", "remove")])
def test_pi_guard_delegates_to_host_and_propagates_failure(monkeypatch, action, verb):
    monkeypatch.setattr(sys, "argv", ["graphify", "pi", "guard", action])
    monkeypatch.setattr("graphify.install.shutil.which", lambda name: "/usr/bin/pi")

    def host(argv, *, check):
        assert argv[:2] == ["/usr/bin/pi", verb]
        assert (Path(argv[2]) / "package.json").is_file()
        return SimpleNamespace(returncode=23)

    monkeypatch.setattr("subprocess.run", host)
    with pytest.raises(SystemExit) as error:
        dispatch_install_cli("pi")
    assert error.value.code == 23


def test_pi_guard_without_host_does_not_create_configuration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["graphify", "pi", "guard", "install"])
    monkeypatch.setattr("graphify.install.shutil.which", lambda name: None)
    with pytest.raises(SystemExit) as error:
        dispatch_install_cli("pi")
    assert error.value.code == 1
    assert not list(tmp_path.iterdir())
