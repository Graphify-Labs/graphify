"""REQ-QML-022-AC06: real metadata-only updates, durable rejection and recovery."""
import json
import os
import stat

import pytest

import graphify.__main__ as mainmod
from graphify.extractors.qml_facts import qml_metadata
from tests.qml_persistence_helpers import protected_snapshot
from tests.qml_types_qt612_helpers import module


def run_update(root, monkeypatch):
    """Use the production CLI and parser; isolate only external skill notices."""
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda *_: None)
    monkeypatch.setattr(mainmod, "_refresh_stale_skills", lambda: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "update", str(root), "--no-cluster"])
    try:
        mainmod.main()
    except SystemExit as exc:
        return exc.code
    return 0


def line_values(root):
    payload = json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8"))
    return [m["value"] for n in payload["nodes"] if (m := qml_metadata(n)).get("kind") == "qmltypes_field"
            and m.get("field_name") == "lineNumber"]


def project(root):
    """A neutral mixed corpus retains unrelated Python and generated tooling facts."""
    path = root / "plugins.qmltypes"
    path.write_text(module(), encoding="utf-8")
    (root / "keep.py").write_text("def retained(): return 7\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("bad_field", ["lineNumber: true", 'isTypeOpaque: true; exports: ["Example/Backend 1.0"]'])
def test_req_qml022_ac06_metadata_only_rejection_retains_graph_and_recovers(tmp_path, monkeypatch, capsys, bad_field):
    """A rejected changed generator file cannot replace the accepted graph/manifest cohort."""
    path = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert run_update(tmp_path, monkeypatch) == 0
    assert 12 in line_values(tmp_path)
    accepted = protected_snapshot(tmp_path / "graphify-out")
    assert "manifest.json" in accepted and "graph.json" in accepted
    assert run_update(tmp_path, monkeypatch) == 0
    assert protected_snapshot(tmp_path / "graphify-out") == accepted
    path.write_text(module().replace("lineNumber: 12", bad_field), encoding="utf-8")
    assert run_update(tmp_path, monkeypatch) == 1
    assert protected_snapshot(tmp_path / "graphify-out") == accepted
    # update's rebuild owner reports integrity diagnostics on stdout; the CLI
    # additionally emits its failed-update summary on stderr.
    captured = capsys.readouterr()
    assert "QML_GRAPH_PRESERVED" in captured.out + captured.err
    path.write_text(module().replace("lineNumber: 12", "lineNumber: 43"), encoding="utf-8")
    assert run_update(tmp_path, monkeypatch) == 0
    assert 43 in line_values(tmp_path) and 12 not in line_values(tmp_path)
    recovered = protected_snapshot(tmp_path / "graphify-out")
    assert recovered != accepted
    assert run_update(tmp_path, monkeypatch) == 0
    assert protected_snapshot(tmp_path / "graphify-out") == recovered


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only output replacement boundary")
def test_req_qml022_ac06_valid_generator_edit_write_failure_retains_and_retries(tmp_path, monkeypatch):
    """Real filesystem rejection preserves accepted output and leaves the edit retryable."""
    path = project(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert run_update(tmp_path, monkeypatch) == 0
    out = tmp_path / "graphify-out"
    accepted = protected_snapshot(out)
    path.write_text(module().replace("lineNumber: 12", "lineNumber: 45"), encoding="utf-8")
    graph = out / "graph.json"
    graph.chmod(stat.S_IREAD)
    try:
        assert run_update(tmp_path, monkeypatch) == 1
        assert protected_snapshot(out) == accepted
        assert not list(out.glob(".gfy-*.tmp"))
    finally:
        graph.chmod(stat.S_IWRITE)
    assert run_update(tmp_path, monkeypatch) == 0
    assert 45 in line_values(tmp_path) and 12 not in line_values(tmp_path)
    recovered = protected_snapshot(out)
    assert run_update(tmp_path, monkeypatch) == 0
    assert protected_snapshot(out) == recovered
