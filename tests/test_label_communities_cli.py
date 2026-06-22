"""Tests for the `graphify label-communities` producer.

serve._load_community_labels / report.py / analyze.py all READ a
`.graphify_labels.json` next to the graph and fall back to "Community <id>"
when it is absent. This subcommand is the producer for that file.
"""
from __future__ import annotations

import json

import graphify.__main__ as mainmod


def _write_graph(tmp_path):
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            # community 0 — billing area, strongest concept = "Payment gateway"
            {"id": "pg", "label": "Payment gateway", "file_type": "concept",
             "source_file": "billing/gateway.py", "community": 0},
            {"id": "charge", "label": "charge()", "file_type": "code",
             "source_file": "billing/charge.py", "community": 0},
            {"id": "refund", "label": "refund()", "file_type": "code",
             "source_file": "billing/refund.py", "community": 0},
            # community 1 — auth area, strongest concept = "Token validator"
            {"id": "tv", "label": "Token validator", "file_type": "concept",
             "source_file": "auth/validator.py", "community": 1},
            {"id": "login", "label": "login()", "file_type": "code",
             "source_file": "auth/login.py", "community": 1},
        ],
        "links": [
            {"source": "charge", "target": "pg", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "refund", "target": "pg", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "login", "target": "tv", "relation": "calls", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def _run(monkeypatch, capsys, graph_path):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "label-communities", "--graph", str(graph_path)],
    )
    mainmod.main()
    return capsys.readouterr().out


def test_label_communities_writes_labels_file(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(tmp_path)
    out = _run(monkeypatch, capsys, graph_path)

    labels_path = tmp_path / ".graphify_labels.json"
    assert labels_path.exists()
    labels = json.loads(labels_path.read_text())

    # area · strongest-concept-phrase, highest-degree concept wins.
    assert labels["0"] == "billing · Payment gateway"
    assert labels["1"] == "auth · Token validator"
    assert "Labeled 2 communities" in out

    # Keys must parse back as ints — the exact contract _load_community_labels uses.
    assert {int(k) for k in labels} == {0, 1}


def test_label_communities_errors_without_community_attr(monkeypatch, tmp_path, capsys):
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [{"id": "a", "label": "A", "source_file": "x.py"}],
        "links": [],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))

    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "label-communities", "--graph", str(p)],
    )
    import pytest

    with pytest.raises(SystemExit) as exc:
        mainmod.main()
    assert exc.value.code == 1
    assert "no node has a 'community' attribute" in capsys.readouterr().err
