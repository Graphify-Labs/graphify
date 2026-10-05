"""INC-QML-46: real update CLI discovery profiles and pre-publication rejection."""
from __future__ import annotations

import pytest

import graphify.__main__ as entrypoint
import graphify.watch as watch
from tests.test_qt_final_incremental_parity import manual_update, normalized, project, published
from tests.test_qt_product_publication import snapshot
from tests.test_source_alias_provenance import directory_alias  # noqa: F401
from tests.test_watch_physical_coowners import cache_bytes


def test_req_qml011_ac01_ac04_cli_default_and_optin_reach_real_publication(tmp_path, monkeypatch):
    """The parser forwards each profile through actual nested rebuilds without changing default facts."""
    root = tmp_path.resolve()
    project(root)
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    observed, real_rebuild = [], watch._rebuild_code

    def rebuild(*args, **kwargs):
        observed.append(kwargs.get("follow_symlinks", False))
        return real_rebuild(*args, **kwargs)

    monkeypatch.setattr(watch, "_rebuild_code", rebuild)
    manual_update(root, monkeypatch)
    before, graph = snapshot(root / "graphify-out"), normalized(published(root))
    assert observed and set(observed) == {False}
    observed.clear()
    manual_update(root, monkeypatch, follow_symlinks=True)
    assert observed and set(observed) == {True}
    assert normalized(published(root)) == graph and snapshot(root / "graphify-out") == before


@pytest.mark.parametrize("arguments,message", [
    (["root", "--not-supported", "--follow-symlinks"], "unknown update option"),
    (["--follow-symlinks", "root", "--not-supported"], "unknown update option"),
    (["root", "--follow-symlinks", "other"], "at most one path"),
    (["--follow-symlinks", "root", "other"], "at most one path"),
])
def test_req_qml011_ac03_invalid_cli_profile_refuses_before_rebuild_or_publication(
        tmp_path, monkeypatch, capsys, arguments, message):
    """Invalid flags or multiple roots retain a real accepted cohort and cache before any rebuild."""
    root = tmp_path.resolve()
    project(root)
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    manual_update(root, monkeypatch)
    output = root / "graphify-out"
    before, cached = snapshot(output), cache_bytes(output)
    assert cached

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid parser input reached rebuild")

    monkeypatch.setattr(watch, "_rebuild_code", forbidden)
    argv = [str(root) if item == "root" else str(root / "other") if item == "other" else item
            for item in arguments]
    monkeypatch.setattr(entrypoint.sys, "argv", ["graphify", "update", *argv])
    capsys.readouterr()
    with pytest.raises(SystemExit) as rejected:
        entrypoint.main()
    assert rejected.value.code == 2 and message in capsys.readouterr().err
    assert snapshot(output) == before and cache_bytes(output) == cached


def test_req_qml011_ac01_optin_cannot_discover_foreign_qt_provider(
        tmp_path, directory_alias, monkeypatch):
    """Following an external alias cannot add an ambiguous native provider or alter accepted facts."""
    root, foreign = tmp_path / "repo", tmp_path / "foreign"
    root.mkdir()
    foreign.mkdir()
    project(root)
    (foreign / "Foreign.h").write_text('class Foreign : public QObject { Q_OBJECT '
        'QML_NAMED_ELEMENT(Service) public: Q_INVOKABLE void stolen(); };\n', encoding="utf-8")
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    manual_update(root, monkeypatch)
    before, graph = snapshot(root / "graphify-out"), normalized(published(root))
    directory_alias(root / "outside", foreign)
    manual_update(root, monkeypatch, follow_symlinks=True)
    assert normalized(published(root)) == graph and snapshot(root / "graphify-out") == before
    assert (foreign / "Foreign.h").exists()


def test_req_qml011_ac01_cli_help_exposes_supported_optin(monkeypatch, capsys):
    """Actual help makes the supported discovery option and unchanged default visible."""
    monkeypatch.setattr(entrypoint.sys, "argv", ["graphify", "--help"])
    entrypoint.main()
    section = capsys.readouterr().out.split("update <path>", 1)[1].split("cluster-only", 1)[0]
    assert "--follow-symlinks" in section and "default: off" in section
