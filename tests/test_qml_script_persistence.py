"""Actual imported JS failure cannot replace the prior completed graph/manifest."""

import pytest

from graphify.watch import _rebuild_code
from tests.qml_persistence_helpers import protected_snapshot
from tests.test_qml_cli_persistence import _run


@pytest.mark.parametrize("operation", ["cli", "watch"])
@pytest.mark.parametrize("failure", ["syntax", "read"])
def test_imported_script_failure_preserves_products_and_recovers(tmp_path, monkeypatch, operation, failure):
    """QML-007/011: real source parsing/read failure wins over force/partial flags."""
    project = tmp_path / "project"
    project.mkdir()
    qml = project / "Main.qml"
    script = project / "helper.js"
    qml.write_text('import "helper.js" as H\nQtObject { property int value: H.answer() }', encoding="utf-8")
    script.write_text("function answer() { return 1; }", encoding="utf-8")
    def run():
        if operation == "cli":
            return _run(monkeypatch, project, flags=("--force", "--allow-partial")) == 0
        return _rebuild_code(project, changed_paths=[script], no_cluster=True, force=True, acquire_lock=False)
    assert run()
    before = protected_snapshot(project / "graphify-out")
    assert {"graph.json", "manifest.json"}.issubset(before)
    if failure == "syntax":
        script.write_text("function answer( {", encoding="utf-8")
        assert not run()
    else:
        import graphify.extractors.qml_scripts as scripts
        parse = scripts.parse_script
        def disappear(path):
            # Deterministic race after generic JS extraction but before the
            # QML-owned overlay: the actual source read now fails on disk.
            path.unlink()
            return parse(path)
        with monkeypatch.context() as race:
            race.setattr(scripts, "parse_script", disappear)
            assert not run()
    assert protected_snapshot(project / "graphify-out") == before
    script.write_text("function answer() { return 2; }", encoding="utf-8")
    assert run()
    assert "manifest.json" in protected_snapshot(project / "graphify-out")
