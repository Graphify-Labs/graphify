"""Tests for optional graph-first retrieval sidecar."""
from __future__ import annotations

import json

import networkx as nx
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod


def _write_semantic_gap_graph(tmp_path):
    G = nx.Graph()
    G.add_node("n_auth", label="LoginSession", source_file="auth.py", source_location="L1", community=0)
    G.add_node("n_billing", label="InvoiceAccount", source_file="billing.py", source_location="L2", community=1)
    G.add_node("n_noise", label="Unrelated", source_file="misc.py", source_location="L3", community=2)
    G.add_edge("n_auth", "n_billing", relation="shares_data_with", confidence="INFERRED", context="semantic")
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(json_graph.node_link_data(G, edges="links")), encoding="utf-8")
    return graph_path


def test_index_cli_writes_sidecar_manifest(monkeypatch, tmp_path, capsys):
    graph_path = _write_semantic_gap_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "index", "--graph", str(graph_path), "--out-dir", str(tmp_path)])

    mainmod.main()

    out = capsys.readouterr().out
    manifest = json.loads((tmp_path / "vector-index" / "manifest.json").read_text(encoding="utf-8"))
    assert "Indexed 3 nodes, 1 relations" in out
    assert manifest["backend"] == "tfidf-local"
    assert manifest["node_count"] == 3
    assert (tmp_path / "vector-index" / "nodes.jsonl").exists()
    assert (tmp_path / "vector-index" / "relations.jsonl").exists()


def test_query_hybrid_uses_sidecar_and_writes_debug(monkeypatch, tmp_path, capsys):
    graph_path = _write_semantic_gap_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "index", "--graph", str(graph_path), "--out-dir", str(tmp_path)])
    mainmod.main()
    capsys.readouterr()

    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "invoice", "--mode", "hybrid", "--debug-retrieval", "--graph", str(graph_path)],
    )
    mainmod.main()

    out = capsys.readouterr().out
    debug_path = tmp_path / "retrieval-debug" / "last-query.json"
    debug = json.loads(debug_path.read_text(encoding="utf-8"))
    assert "Traversal: HYBRID" in out
    assert "Retrieval debug:" in out
    assert "InvoiceAccount" in out
    assert debug["mode"] == "hybrid"
    assert debug["semantic_candidates"]["nodes"]
    assert "selected_seeds" in debug


def test_hybrid_relation_hit_can_outrank_weak_lexical_noise(tmp_path):
    from graphify.retrieval import build_vector_index, load_index, merge_seed_candidates, search_index

    graph_path = _write_semantic_gap_graph(tmp_path)
    G = nx.Graph()
    G.add_node("n_target", label="PaymentLedger", source_file="billing.py")
    G.add_node("n_source", label="Checkout", source_file="checkout.py")
    for idx in range(8):
        G.add_node(f"n_noise_{idx}", label=f"noise auth placeholder {idx}", source_file="noise.py")
    G.add_edge("n_source", "n_target", relation="handles", context="invoice reconciliation")
    graph_path.write_text(json.dumps(json_graph.node_link_data(G, edges="links")), encoding="utf-8")
    build_vector_index(G, graph_path, tmp_path)
    index = load_index(graph_path, tmp_path)
    assert index is not None

    lexical = [(0.01, f"n_noise_{idx}") for idx in range(5)]
    hits = search_index(index, "invoice", k=5)
    seeds = merge_seed_candidates(lexical, hits, k=5)

    assert "n_target" in seeds[:2]


def test_load_index_rejects_partial_or_corrupt_sidecar(tmp_path):
    from graphify.retrieval import build_vector_index, load_index

    graph_path = _write_semantic_gap_graph(tmp_path)
    G = json_graph.node_link_graph(json.loads(graph_path.read_text(encoding="utf-8")), edges="links")
    build_vector_index(G, graph_path, tmp_path)
    (tmp_path / "vector-index" / "relations.jsonl").unlink()
    assert load_index(graph_path, tmp_path) is None

    build_vector_index(G, graph_path, tmp_path)
    (tmp_path / "vector-index" / "manifest.json").write_text("{not json", encoding="utf-8")
    assert load_index(graph_path, tmp_path) is None


def test_eval_cli_reports_retrieval_quality(monkeypatch, tmp_path, capsys):
    graph_path = _write_semantic_gap_graph(tmp_path)
    queries_path = tmp_path / "queries.jsonl"
    queries_path.write_text(
        json.dumps({"question": "invoice", "expected_labels": ["InvoiceAccount"], "forbidden_labels": ["Unrelated"]}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "index", "--graph", str(graph_path), "--out-dir", str(tmp_path)])
    mainmod.main()
    capsys.readouterr()

    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "eval", str(queries_path), "--graph", str(graph_path)])
    mainmod.main()

    out = capsys.readouterr().out
    assert "Eval: 1 queries | mode=hybrid | k=5 | depth=2" in out
    assert "hit_rate@5: 1.000" in out
    assert "MRR: 1.000" in out
    assert "forbidden_hits: 0" in out


def test_eval_cli_json_requires_fresh_index(monkeypatch, tmp_path, capsys):
    graph_path = _write_semantic_gap_graph(tmp_path)
    queries_path = tmp_path / "queries.jsonl"
    queries_path.write_text(json.dumps({"question": "invoice", "expected_nodes": ["n_billing"]}) + "\n", encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)

    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "eval", str(queries_path), "--graph", str(graph_path), "--json"])
    try:
        mainmod.main()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected missing hybrid index to fail eval")

    assert "hybrid eval requires a fresh vector-index" in capsys.readouterr().err
