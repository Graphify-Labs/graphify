"""Tests for `graphify resolve-entities` CLI subcommand."""
from __future__ import annotations
import json
import pytest

import graphify.__main__ as mainmod


def _write_graph(tmp_path, extra_nodes=None):
    """Two nodes in the same source_file with the same normalized label —
    deduplicate_entities() will merge them via the exact-normalization pass."""
    nodes = [
        {"id": "n1", "label": "PaymentService",
         "source_file": "billing.py", "community": 0,
         "file_type": "concept"},
        {"id": "n2", "label": "Payment Service",  # casefold + collapse space → same as n1
         "source_file": "billing.py", "community": 0,
         "file_type": "concept"},
        {"id": "u1", "label": "uniqueOther",
         "source_file": "elsewhere.py", "community": 1,
         "file_type": "concept"},
    ]
    if extra_nodes:
        nodes.extend(extra_nodes)
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": nodes,
        "links": [
            {"source": "n1", "target": "u1", "relation": "uses",
             "confidence": "EXTRACTED"},
            {"source": "n2", "target": "u1", "relation": "uses",
             "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def _run(monkeypatch, argv, capsys):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    try:
        mainmod.main()
    except SystemExit as e:
        if e.code not in (None, 0):
            raise
    return capsys.readouterr()


def test_dry_run_does_not_mutate(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    original = p.read_text()
    out = _run(
        monkeypatch,
        ["graphify", "resolve-entities", str(tmp_path), "--graph", str(p), "--dry-run"],
        capsys,
    )
    assert "DRY RUN" in out.out
    assert "→" in out.out  # before/after summary
    assert p.read_text() == original, "graph.json was modified during --dry-run"
    assert not p.with_suffix(p.suffix + ".bak").exists(), "backup was written during --dry-run"


def test_apply_merges_and_backs_up(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    backup = p.with_suffix(p.suffix + ".bak")
    out = _run(
        monkeypatch,
        ["graphify", "resolve-entities", str(tmp_path),
         "--graph", str(p), "--skip-recluster"],
        capsys,
    )
    assert "Backed up" in out.out
    assert backup.exists(), "no .bak written"
    data = json.loads(p.read_text())
    # Two duplicate nodes should collapse into one (n1 or n2 picked, u1 untouched)
    assert len(data["nodes"]) == 2, f"expected 2 nodes after merge, got {len(data['nodes'])}: {data['nodes']}"
    # Both n1→u1 and n2→u1 edges should have been rewired to the survivor.
    # (deduplicate_entities does not collapse parallel edges, so both remain.)
    surviving_ids = {n["id"] for n in data["nodes"]}
    for link in data["links"]:
        assert link["source"] in surviving_ids, f"orphan edge source: {link}"
        assert link["target"] in surviving_ids, f"orphan edge target: {link}"


def test_apply_no_merges_skips_write(monkeypatch, tmp_path, capsys):
    """When dedup finds nothing to merge, the file should remain untouched."""
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "a", "label": "alpha", "source_file": "a.py",
             "community": 0, "file_type": "concept"},
            {"id": "b", "label": "beta",  "source_file": "b.py",
             "community": 1, "file_type": "concept"},
        ],
        "links": [],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    original = p.read_text()
    out = _run(
        monkeypatch,
        ["graphify", "resolve-entities", str(tmp_path),
         "--graph", str(p), "--skip-recluster"],
        capsys,
    )
    assert "No merges found" in out.out
    assert p.read_text() == original


def test_missing_graph_errors(monkeypatch, tmp_path, capsys):
    nonexistent = tmp_path / "nope.json"
    with pytest.raises(SystemExit) as exc:
        _run(
            monkeypatch,
            ["graphify", "resolve-entities", str(tmp_path), "--graph", str(nonexistent)],
            capsys,
        )
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "no graph found" in err
