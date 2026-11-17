"""Tests for `graphify label --from <path>` (#3808).

An external naming tool (its own hub/candidate heuristic, no LLM key) hands
graphify a `{community_id: name}` map instead of reimplementing
`community_member_sigs` byte-for-byte to produce a `.graphify_labels.json.sig`
`cluster-only` would trust later. `--from` writes both files itself.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import graphify.__main__ as cli
from graphify.cluster import community_member_sigs


def _write_graph(tmp_path, nodes):
    out = tmp_path / "graphify-out"
    out.mkdir()
    graph = {
        "directed": False,
        "multigraph": False,
        "nodes": nodes,
        "links": [],
    }
    (out / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    return out


def _run_label(tmp_path, monkeypatch, from_file):
    monkeypatch.setattr("graphify.export.to_html", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sys, "argv",
        ["graphify", "label", str(tmp_path), "--from", str(from_file), "--no-viz"],
    )
    cli.main()


def test_from_file_names_every_community(tmp_path, monkeypatch):
    out = _write_graph(tmp_path, [
        {"id": "n1", "label": "NodeOne", "community": 0},
        {"id": "n2", "label": "NodeTwo", "community": 1},
    ])
    names = tmp_path / "names.json"
    names.write_text(json.dumps({"0": "Custom Name A", "1": "Custom Name B"}), encoding="utf-8")

    _run_label(tmp_path, monkeypatch, names)

    labels = json.loads((out / ".graphify_labels.json").read_text(encoding="utf-8"))
    assert labels == {"0": "Custom Name A", "1": "Custom Name B"}

    sig_path = out / ".graphify_labels.json.sig"
    assert sig_path.exists()
    saved_sigs = json.loads(sig_path.read_text(encoding="utf-8"))
    expected_sigs = {str(k): v for k, v in community_member_sigs({0: ["n1"], 1: ["n2"]}).items()}
    assert saved_sigs == expected_sigs


def test_from_file_falls_back_to_hub_label_for_unnamed_community(tmp_path, monkeypatch):
    out = _write_graph(tmp_path, [
        {"id": "n1", "label": "NodeOne", "community": 0},
        {"id": "n2", "label": "NodeTwo", "community": 1},
    ])
    names = tmp_path / "names.json"
    names.write_text(json.dumps({"0": "Custom Name A"}), encoding="utf-8")

    _run_label(tmp_path, monkeypatch, names)

    labels = json.loads((out / ".graphify_labels.json").read_text(encoding="utf-8"))
    assert labels["0"] == "Custom Name A"
    assert labels["1"] == "NodeTwo"  # hub-labeled, not an LLM/placeholder name


def test_from_file_warns_and_ignores_unknown_community_id(tmp_path, monkeypatch, capsys):
    out = _write_graph(tmp_path, [
        {"id": "n1", "label": "NodeOne", "community": 0},
    ])
    names = tmp_path / "names.json"
    names.write_text(json.dumps({"0": "Custom Name A", "99": "Ghost Community"}), encoding="utf-8")

    _run_label(tmp_path, monkeypatch, names)

    labels = json.loads((out / ".graphify_labels.json").read_text(encoding="utf-8"))
    assert labels == {"0": "Custom Name A"}
    assert "99" in capsys.readouterr().err


def test_from_file_missing_path_is_clean_error(tmp_path, monkeypatch, capsys):
    _write_graph(tmp_path, [{"id": "n1", "label": "NodeOne", "community": 0}])
    missing = tmp_path / "does-not-exist.json"
    monkeypatch.setattr(
        sys, "argv",
        ["graphify", "label", str(tmp_path), "--from", str(missing), "--no-viz"],
    )
    try:
        cli.main()
        raised = False
    except SystemExit as exc:
        raised = True
        assert exc.code != 0
    assert raised
    err = capsys.readouterr().err
    assert "could not read --from" in err
    assert "Traceback" not in err


def test_from_file_rejects_malformed_json(tmp_path, monkeypatch, capsys):
    _write_graph(tmp_path, [{"id": "n1", "label": "NodeOne", "community": 0}])
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv",
        ["graphify", "label", str(tmp_path), "--from", str(bad), "--no-viz"],
    )
    try:
        cli.main()
        raised = False
    except SystemExit:
        raised = True
    assert raised
    assert "not valid JSON" in capsys.readouterr().err


def test_from_file_rejects_non_object_payload(tmp_path, monkeypatch, capsys):
    _write_graph(tmp_path, [{"id": "n1", "label": "NodeOne", "community": 0}])
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv",
        ["graphify", "label", str(tmp_path), "--from", str(bad), "--no-viz"],
    )
    try:
        cli.main()
        raised = False
    except SystemExit:
        raised = True
    assert raised
    assert "must be a JSON object" in capsys.readouterr().err


def test_from_file_rejects_non_string_name(tmp_path, monkeypatch, capsys):
    _write_graph(tmp_path, [{"id": "n1", "label": "NodeOne", "community": 0}])
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"0": 123}), encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv",
        ["graphify", "label", str(tmp_path), "--from", str(bad), "--no-viz"],
    )
    try:
        cli.main()
        raised = False
    except SystemExit:
        raised = True
    assert raised
    assert "must be a non-empty" in capsys.readouterr().err


def test_from_file_also_works_on_cluster_only(tmp_path, monkeypatch):
    """--from is not limited to the `label` alias."""
    out = _write_graph(tmp_path, [
        {"id": "n1", "label": "NodeOne", "community": 0},
    ])
    names = tmp_path / "names.json"
    names.write_text(json.dumps({"0": "Custom Name A"}), encoding="utf-8")

    monkeypatch.setattr("graphify.export.to_html", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sys, "argv",
        ["graphify", "cluster-only", str(tmp_path), "--from", str(names), "--no-viz"],
    )
    cli.main()

    labels = json.loads((out / ".graphify_labels.json").read_text(encoding="utf-8"))
    assert labels == {"0": "Custom Name A"}
