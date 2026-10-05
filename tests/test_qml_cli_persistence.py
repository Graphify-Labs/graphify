"""Production CLI QML rejection, real graph retention, retry and scope refresh."""
import json

import pytest

import graphify.__main__ as mainmod
import graphify.extract as ex
from tests.qml_persistence_helpers import failing_qml, healthy_qml, make_project, protected_snapshot


def _run(monkeypatch, project, *, no_cluster=True, flags=()):
    argv = ["graphify", "extract", str(project), "--code-only", *flags]
    if no_cluster:
        argv.append("--no-cluster")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    try:
        mainmod.main()
    except SystemExit as exc:
        return exc.code
    return 0


@pytest.mark.parametrize("kind", ["missing", "incompatible", "read", "partial"])
@pytest.mark.parametrize("no_cluster", [False, True])
@pytest.mark.parametrize("extra_nodes", [0, 8], ids=["equal-count-edge-loss", "larger-candidate"])
def test_cli_qml_failure_preserves_graph_and_manifest_despite_override(
    tmp_path, monkeypatch, capsys, kind, no_cluster, extra_nodes,
):
    """QML-001/002/011: completed products survive error even at equal/higher counts."""
    project = make_project(tmp_path)
    monkeypatch.setitem(ex._DISPATCH, ".qml", healthy_qml)
    assert _run(monkeypatch, project) == 0
    out = project / "graphify-out"
    before = protected_snapshot(out)
    assert "manifest.json" in before
    graph = json.loads(before["graph.json"])
    assert graph.get("links", graph.get("edges"))
    (project / "Main.qml").write_text("Item { property int changed: 2 }\n", encoding="utf-8")
    monkeypatch.setitem(ex._DISPATCH, ".qml", failing_qml(kind, extra_nodes=extra_nodes))

    assert _run(monkeypatch, project, no_cluster=no_cluster, flags=("--force", "--allow-partial")) == 1
    assert protected_snapshot(out) == before
    assert "QML_GRAPH_PRESERVED" in capsys.readouterr().err


def test_cli_failed_first_scan_publishes_no_graph_or_manifest(tmp_path, monkeypatch):
    """An unavailable QML parser cannot publish a successful Python-only graph."""
    project = make_project(tmp_path)
    monkeypatch.setitem(ex._DISPATCH, ".qml", failing_qml("missing"))
    assert _run(monkeypatch, project, flags=("--allow-partial",)) == 1
    out = project / "graphify-out"
    assert not (out / "graph.json").exists()
    assert not (out / "manifest.json").exists()


def test_cli_retry_uses_changed_qml_and_settles_after_recovery(tmp_path, monkeypatch):
    """Retaining the prior manifest leaves failed source edits pending for retry."""
    project = make_project(tmp_path)
    monkeypatch.setitem(ex._DISPATCH, ".qml", healthy_qml)
    assert _run(monkeypatch, project) == 0
    source = project / "Main.qml"
    source.write_text("import QtQuick\nItem { property int count: 2 }\n", encoding="utf-8")
    monkeypatch.setitem(ex._DISPATCH, ".qml", failing_qml("partial"))
    before = protected_snapshot(project / "graphify-out")
    assert _run(monkeypatch, project) == 1
    assert protected_snapshot(project / "graphify-out") == before

    calls = []
    def recovered(path):
        calls.append(path.name)
        return healthy_qml(path)
    monkeypatch.setitem(ex._DISPATCH, ".qml", recovered)
    assert _run(monkeypatch, project) == 0
    assert calls == ["Main.qml"]
    calls.clear()
    assert _run(monkeypatch, project) == 0
    assert calls == []


def test_cli_qml_change_refreshes_unchanged_code_facts(tmp_path, monkeypatch):
    """QML-011 initial policy supplies the whole live code corpus to resolution."""
    project = make_project(tmp_path)
    monkeypatch.setitem(ex._DISPATCH, ".qml", healthy_qml)
    assert _run(monkeypatch, project) == 0
    (project / "Main.qml").write_text("Item { property int changed: 1 }\n", encoding="utf-8")
    called = []
    real = ex.extract
    def record(paths, **kwargs):
        called.extend(p.name for p in paths)
        return real(paths, **kwargs)
    monkeypatch.setattr(ex, "extract", record)
    assert _run(monkeypatch, project) == 0
    assert set(called) == {"Main.qml", "keep.py"}
