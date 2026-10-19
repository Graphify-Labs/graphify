"""D33: retained uncertainty survives Qt removal and clears on real source proof."""
from __future__ import annotations

import json
import os
import stat

import pytest

import graphify.__main__ as mainmod
from graphify.watch import _rebuild_code
from tests.test_qt_cpp_file_roles import cpp_fixture

FIELD = "qt_import_retention"


def read(root):
    return json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8"))


def update(root, monkeypatch, operation, no_cluster, changes=None, *, force=False):
    """Use the real CLI/watch producers, isolating only installed-skill notices."""
    if operation == "watch":
        assert _rebuild_code(root, changed_paths=changes, no_cluster=no_cluster, force=force, acquire_lock=False)
    else:
        monkeypatch.setattr(mainmod, "_check_skill_version", lambda *_: None)
        monkeypatch.setattr(mainmod, "_refresh_stale_skills", lambda: None)
        argv = ["graphify", "update", str(root)]
        if no_cluster:
            argv.append("--no-cluster")
        if force:
            argv.append("--force")
        monkeypatch.setattr(mainmod.sys, "argv", argv)
        mainmod.main()
    return read(root)


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("no_cluster", [True, False], ids=["raw", "clustered"])
def test_unproved_native_import_survives_last_qt_removal_and_real_proof_recovers(
    tmp_path, monkeypatch, operation, no_cluster,
):
    """Raw incidence restricts cleanup; ordinary Python legacy orphan healing stays intact."""
    cpp_fixture(tmp_path)
    (tmp_path / "keep.py").write_text("import json\ndef retained(): return json.dumps(7)\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    initial = update(tmp_path, monkeypatch, operation, no_cluster)
    path = tmp_path / "graphify-out/graph.json"
    edge = next(edge for edge in initial["links"] if edge.get("relation") == "imports"
                and edge.get("source_file") == "backend.cpp")
    edge["_origin"] = "semantic"
    # This unrelated old canonical orphan must still heal in the same mixed
    # graph. Neither a Qt corpus nor a same-shaped node grants blanket retention.
    initial["nodes"].append({"id": "requests", "label": "requests", "type": "external",
                             "external": True, "file_type": "concept", "source_file": "",
                             "_origin": "semantic"})
    path.write_text(json.dumps(initial), encoding="utf-8")
    source = tmp_path / "backend.cpp"
    source.unlink()
    retained = update(tmp_path, monkeypatch, operation, no_cluster, [source])
    assert retained.get("graph", {}).get(FIELD) == {"schema": 1, "ids": ["missing"]}
    assert "missing" in {node["id"] for node in retained["nodes"]}
    assert "requests" not in {node["id"] for node in retained["nodes"]}
    before = path.read_bytes()
    update(tmp_path, monkeypatch, operation, no_cluster, [])
    assert path.read_bytes() == before


    # After the final Qt source disappears, the same graph remains the sole
    # owner of the restriction. A later generic update cannot reinterpret it.
    retired = [tmp_path / name for name in ("CMakeLists.txt", "resources.qrc", "qml/ResizeHandle.qml")]
    for item in retired:
        item.unlink()
    removed = update(tmp_path, monkeypatch, operation, no_cluster, retired)
    assert removed.get("graph", {}).get(FIELD) == {"schema": 1, "ids": ["missing"]}
    before = path.read_bytes()
    update(tmp_path, monkeypatch, operation, no_cluster, [])
    assert path.read_bytes() == before
    update(tmp_path, monkeypatch, operation, no_cluster)
    assert path.read_bytes() == before

    # A new actual producer import clears the restriction in that accepted run;
    # removing its last proved reference then retires the ordinary placeholder.
    source.write_text('#include "missing.hpp"\nint restored() { return 1; }\n', encoding="utf-8")
    repaired = update(tmp_path, monkeypatch, operation, no_cluster, [source])
    assert FIELD not in repaired.get("graph", {})
    assert "missing" in {node["id"] for node in repaired["nodes"]}
    source.write_text("int restored() { return 2; }\n", encoding="utf-8")
    retired = update(tmp_path, monkeypatch, operation, no_cluster, [source])
    assert "missing" not in {node["id"] for node in retired["nodes"]}
    before = path.read_bytes()
    update(tmp_path, monkeypatch, operation, no_cluster, [])
    assert path.read_bytes() == before

@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only publication boundary")
@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("no_cluster", [True, False], ids=["raw", "clustered"])
def test_retention_context_publication_failure_keeps_prior_cohort_and_retries(
    tmp_path, monkeypatch, operation, no_cluster,
):
    """A new graph-owned context is accepted only with its existing product cohort."""
    from tests.test_qt_readonly_publication import durable
    cpp_fixture(tmp_path)
    (tmp_path / "keep.py").write_text("def retained(): return 7\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    data = update(tmp_path, monkeypatch, operation, no_cluster)
    path = tmp_path / "graphify-out/graph.json"
    edge = next(edge for edge in data["links"] if edge.get("relation") == "imports"
                and edge.get("source_file") == "backend.cpp")
    edge["_origin"] = "semantic"
    path.write_text(json.dumps(data), encoding="utf-8")
    accepted = durable(tmp_path)
    source = tmp_path / "backend.cpp"
    source.unlink()
    path.chmod(stat.S_IREAD)
    try:
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                update(tmp_path, monkeypatch, operation, no_cluster, [source], force=True)
            assert rejected.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=[source], no_cluster=no_cluster,
                                     force=True, acquire_lock=False)
        assert durable(tmp_path) == accepted
        assert not list(path.parent.glob(".gfy-*.tmp"))
    finally:
        path.chmod(stat.S_IWRITE)
    recovered = update(tmp_path, monkeypatch, operation, no_cluster, [source])
    assert recovered["graph"][FIELD] == {"schema": 1, "ids": ["missing"]}
    accepted = durable(tmp_path)
    update(tmp_path, monkeypatch, operation, no_cluster, [])
    assert durable(tmp_path) == accepted

@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("no_cluster", [True, False], ids=["raw", "clustered"])
@pytest.mark.parametrize("corruption", ["unknown_id", "version", "scalar"])
def test_corrupt_retention_refuses_force_preserves_cohort_and_recovers(
    tmp_path, monkeypatch, capsys, operation, no_cluster, corruption,
):
    """A malformed prior graph must never become a fresh-only successful rebuild."""
    from tests.test_qt_readonly_publication import durable
    cpp_fixture(tmp_path)
    keep = tmp_path / "keep.py"
    keep.write_text("def retained(): return 7\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    data = update(tmp_path, monkeypatch, operation, no_cluster)
    path = tmp_path / "graphify-out/graph.json"
    # A valid explicit cleanup restriction is a preservation-only graph fact.
    data.setdefault("graph", {})[FIELD] = {"schema": 1, "ids": ["missing"]}
    valid = json.dumps(data).encode("utf-8")
    data["graph"][FIELD] = {"unknown_id": {"schema": 1, "ids": ["absent"]},
                            "version": {"schema": 2, "ids": ["missing"]},
                            "scalar": "private-needle\nforged"}[corruption]
    path.write_text(json.dumps(data), encoding="utf-8")
    accepted = durable(tmp_path)
    keep.write_text("def retained(): return 8\n", encoding="utf-8")
    if operation == "manual":
        with pytest.raises(SystemExit) as rejected:
            update(tmp_path, monkeypatch, operation, no_cluster, [keep], force=True)
        assert rejected.value.code == 1
    else:
        assert not _rebuild_code(tmp_path, changed_paths=[keep], no_cluster=no_cluster,
                                 force=True, acquire_lock=False)
    captured = capsys.readouterr()
    assert "QT_IMPORT_RETENTION_INVALID" in captured.out + captured.err
    assert "private-needle" not in captured.out + captured.err
    assert durable(tmp_path) == accepted
    path.write_bytes(valid)
    repaired = update(tmp_path, monkeypatch, operation, no_cluster, [keep])
    # The actual still-present source import supplies valid producer evidence.
    assert FIELD not in repaired.get("graph", {})
    accepted = durable(tmp_path)
    update(tmp_path, monkeypatch, operation, no_cluster, [])
    assert durable(tmp_path) == accepted
