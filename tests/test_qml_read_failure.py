"""A real source-disappearance read failure cannot commit a partial QML graph."""
import pytest

import graphify.__main__ as mainmod
import graphify.extract as ex
from graphify.watch import _rebuild_code
from tests.qml_persistence_helpers import healthy_qml, make_project, protected_snapshot


@pytest.mark.parametrize("operation", ["extract", "update"])
def test_qml_read_race_preserves_prior_products_then_recovers(tmp_path, monkeypatch, operation):
    """QML-001/002: OS read failure passes through real extraction and persistence gates."""
    project = make_project(tmp_path)
    source = project / "Main.qml"
    monkeypatch.setitem(ex._DISPATCH, ".qml", healthy_qml)
    assert _rebuild_code(project, no_cluster=True, acquire_lock=False)
    out = project / "graphify-out"
    # A prior full build may also own presentation products. The integrity gate
    # must return before any of those products or the root marker can advance.
    for name in ("graph.html", "GRAPH_REPORT.md", ".graphify_labels.json", "callflow.html"):
        (out / name).write_text("previous complete output\n", encoding="utf-8")
    before = protected_snapshot(out)
    source.write_text("Item { property int changed: 4 }\n", encoding="utf-8")

    def source_disappears(path):
        # Simulate a filesystem race after discovery, with an actual failed read.
        path.unlink()
        path.read_bytes()

    monkeypatch.setitem(ex._DISPATCH, ".qml", source_disappears)
    if operation == "extract":
        monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
        monkeypatch.setattr(mainmod.sys, "argv", [
            "graphify", "extract", str(project), "--code-only", "--no-cluster",
            "--force", "--allow-partial",
        ])
        with pytest.raises(SystemExit) as info:
            mainmod.main()
        assert info.value.code == 1
    else:
        assert not _rebuild_code(project, changed_paths=[source], no_cluster=True,
                                 force=True, acquire_lock=False)
    assert not source.exists()
    assert protected_snapshot(out) == before

    # Restoring the source and parser recovers without deleting graph/cache data.
    source.write_text("Item { property int changed: 5 }\n", encoding="utf-8")
    monkeypatch.setitem(ex._DISPATCH, ".qml", healthy_qml)
    assert _rebuild_code(project, changed_paths=[source], no_cluster=True, acquire_lock=False)
