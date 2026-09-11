"""OMP owns registration; Graphify supplies a wheel-contained native package."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from graphify.install import dispatch_install_cli


def test_omp_path_is_a_complete_native_package(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["graphify", "omp", "path"])
    assert dispatch_install_cli("omp")
    package = Path(capsys.readouterr().out.strip())
    manifest = json.loads((package / "package.json").read_text(encoding="utf-8"))
    assert manifest["omp"]["extensions"]
    for entry in manifest["omp"]["extensions"]:
        assert (package / entry).is_file()
        assert (package / entry).resolve().is_relative_to(package)


def test_omp_install_delegates_to_host_and_propagates_failure(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["graphify", "omp", "install"])
    monkeypatch.setattr("graphify.install.shutil.which", lambda name: "/usr/bin/omp")

    def host(argv, *, check):
        assert argv[:3] == ["/usr/bin/omp", "plugin", "install"]
        assert (Path(argv[3]) / "package.json").is_file()
        return SimpleNamespace(returncode=23)

    monkeypatch.setattr("subprocess.run", host)
    with pytest.raises(SystemExit) as error:
        dispatch_install_cli("omp")
    assert error.value.code == 23


def test_omp_install_without_host_does_not_create_configuration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["graphify", "omp", "install"])
    monkeypatch.setattr("graphify.install.shutil.which", lambda name: None)
    with pytest.raises(SystemExit) as error:
        dispatch_install_cli("omp")
    assert error.value.code == 1
    assert not list(tmp_path.iterdir())
