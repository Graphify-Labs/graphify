"""Production update/watch QML retention and conservative refresh contracts."""
import pytest

import graphify.extract as ex
from graphify.watch import _batch_needs_llm_flag, _batch_triggers_rebuild, _rebuild_code
from tests.qml_persistence_helpers import failing_qml, healthy_qml, make_project, protected_snapshot


@pytest.mark.parametrize("kind", ["missing", "incompatible", "read", "partial"])
@pytest.mark.parametrize("no_cluster", [False, True])
@pytest.mark.parametrize("extra_nodes", [0, 8], ids=["equal-count-edge-loss", "larger-candidate"])
def test_watch_qml_failure_preserves_completed_products_with_force(
    tmp_path, monkeypatch, capsys, kind, no_cluster, extra_nodes,
):
    """QML-001/002/011: real graph/manifest writes cannot bypass the QML gate."""
    project = make_project(tmp_path)
    monkeypatch.setitem(ex._DISPATCH, ".qml", healthy_qml)
    assert _rebuild_code(project, no_cluster=True, acquire_lock=False)
    before = protected_snapshot(project / "graphify-out")
    monkeypatch.setitem(ex._DISPATCH, ".qml", failing_qml(kind, extra_nodes=extra_nodes))
    source = project / "Main.qml"
    source.write_text("Item { property int changed: 2 }\n", encoding="utf-8")

    assert not _rebuild_code(project, changed_paths=[source], force=True,
                             no_cluster=no_cluster, acquire_lock=False)
    assert protected_snapshot(project / "graphify-out") == before
    assert "QML_GRAPH_PRESERVED" in capsys.readouterr().out


def test_watch_first_failure_produces_no_graph_or_manifest(tmp_path, monkeypatch):
    project = make_project(tmp_path)
    monkeypatch.setitem(ex._DISPATCH, ".qml", failing_qml("missing"))
    assert not _rebuild_code(project, no_cluster=True, force=True, acquire_lock=False)
    assert not (project / "graphify-out" / "graph.json").exists()
    assert not (project / "graphify-out" / "manifest.json").exists()


def test_watch_qml_recovery_after_failed_edit(tmp_path, monkeypatch):
    """Recovery re-extracts the pending edit and leaves a complete manifest."""
    project = make_project(tmp_path)
    monkeypatch.setitem(ex._DISPATCH, ".qml", healthy_qml)
    assert _rebuild_code(project, no_cluster=True, acquire_lock=False)
    source = project / "Main.qml"
    source.write_text("Item { property int changed: 3 }\n", encoding="utf-8")
    monkeypatch.setitem(ex._DISPATCH, ".qml", failing_qml("partial"))
    assert not _rebuild_code(project, changed_paths=[source], no_cluster=True, acquire_lock=False)
    monkeypatch.setitem(ex._DISPATCH, ".qml", healthy_qml)
    assert _rebuild_code(project, changed_paths=[source], no_cluster=True, acquire_lock=False)
    settled = protected_snapshot(project / "graphify-out")
    assert _rebuild_code(project, changed_paths=[source], no_cluster=True, acquire_lock=False)
    assert protected_snapshot(project / "graphify-out") == settled


def test_relative_subfolder_qml_update_keeps_prior_products(tmp_path, monkeypatch, capsys):
    """QML scope IDs cannot safely use the legacy path-only subfolder rebase."""
    project = make_project(tmp_path)
    monkeypatch.setitem(ex._DISPATCH, ".qml", healthy_qml)
    assert _rebuild_code(project, no_cluster=True, acquire_lock=False)
    before = protected_snapshot(project / "graphify-out")
    monkeypatch.chdir(tmp_path)
    assert not _rebuild_code(project.relative_to(tmp_path), force=True,
                             no_cluster=True, acquire_lock=False)
    assert protected_snapshot(project / "graphify-out") == before
    assert "QML_ROOT_MISMATCH" in capsys.readouterr().out


@pytest.mark.parametrize("changed_name", ["Main.qml", "qmldir", "helpers.js"])
def test_watch_qml_input_refreshes_the_live_code_corpus(tmp_path, monkeypatch, changed_name):
    """QML-011 initial policy keeps unchanged components in the fresh resolver set."""
    project = make_project(tmp_path)
    monkeypatch.setitem(ex._DISPATCH, ".qml", healthy_qml)
    assert _rebuild_code(project, no_cluster=True, acquire_lock=False)
    source = project / changed_name
    content = {
        "Main.qml": "Item {}\n",
        "qmldir": "module Example\nMain 1.0 Main.qml\n",
        "helpers.js": "function helper() { return 1; }\n",
    }
    source.write_text(content[changed_name], encoding="utf-8")
    called = []
    real = ex.extract
    def record(paths, **kwargs):
        called.extend(p.name for p in paths)
        return real(paths, **kwargs)
    monkeypatch.setattr(ex, "extract", record)
    assert _rebuild_code(project, changed_paths=[source], no_cluster=True, acquire_lock=False)
    assert {"Main.qml", "keep.py"} <= set(called)


def test_named_qml_metadata_watch_event_routes_to_local_rebuild(tmp_path):
    """qmldir is extensionless metadata, not a semantic/LLM document."""
    source = tmp_path / "qmldir"
    source.write_text("module Example\n", encoding="utf-8")
    assert _batch_triggers_rebuild([source])
    assert not _batch_needs_llm_flag([source])
