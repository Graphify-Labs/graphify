"""A complete `graphify extract` must not force-write a shrink that dedup caused (#3774).

A full build sets force=True, and to_json then skips the #479 node-count check.
Dedup can merge a same-file duplicate and replace graph.json with no message.
A deleted file is a different shrink: that write still happens.
`--allow-dedup-shrink` is the only flag that accepts the dedup shrink.
"""
from __future__ import annotations

import json

import pytest

import graphify.__main__ as mainmod


def _notes(corpus):
    readme = str(corpus / "README.md")
    return [
        {
            "id": "readme_decisions_a",
            "label": "Decisions",
            "file_type": "document",
            "source_file": readme,
            "source_location": "L1",
        },
        {
            "id": "readme_decisions_b",
            "label": "Decisions",
            "file_type": "document",
            "source_file": readme,
            "source_location": "L2",
        },
        {
            "id": "readme_overview",
            "label": "Overview",
            "file_type": "document",
            "source_file": readme,
            "source_location": "L3",
        },
    ]


def _write_graph(path, nodes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"nodes": nodes, "links": []}),
        encoding="utf-8",
    )


def _node_ids(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return [n["id"] for n in data["nodes"]]


def _corpus(tmp_path):
    (tmp_path / "README.md").write_text("# Notes\nThe entry point overview.\n", encoding="utf-8")
    (tmp_path / "GUIDE.md").write_text("# Guide\nHow to use the thing.\n", encoding="utf-8")
    return tmp_path


def _arm(monkeypatch, tmp_path, *, nodes, extra_argv=()):
    corpus = _corpus(tmp_path)
    out_dir = tmp_path / "out"
    graph_path = out_dir / "graphify-out" / "graph.json"
    _write_graph(graph_path, nodes)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    def _stub_corpus(paths, **kwargs):
        on_chunk = kwargs.get("on_chunk_done")
        if on_chunk:
            on_chunk(0, 1, {"nodes": [], "edges": [], "hyperedges": []})
        return {
            "nodes": nodes,
            "edges": [],
            "hyperedges": [],
            "input_tokens": 10,
            "output_tokens": 5,
        }

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _stub_corpus)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude",
         "--out", str(out_dir), *extra_argv],
    )
    return graph_path


def _run():
    try:
        mainmod.main()
    except SystemExit as exc:
        return exc.code
    return 0


def test_complete_run_refuses_a_same_file_dedup_shrink(monkeypatch, tmp_path, capsys):
    """Two same-file duplicates plus one keeper. Dedup merges the pair.
    The file on disk must keep all three nodes."""
    graph_path = _arm(monkeypatch, tmp_path, nodes=_notes(tmp_path))
    code = _run()
    err = capsys.readouterr().err
    assert code not in (None, 0)
    assert _node_ids(graph_path) == [
        "readme_decisions_a",
        "readme_decisions_b",
        "readme_overview",
    ]
    assert "3" in err and "2" in err
    # the message attributes the shrink to the actual dedup contribution
    # (1 merged node), not the whole 3->2 delta
    assert "merged 1" in err
    assert "--allow-dedup-shrink" in err


def test_allow_dedup_shrink_writes_the_smaller_graph(monkeypatch, tmp_path):
    graph_path = _arm(
        monkeypatch, tmp_path, nodes=_notes(tmp_path),
        extra_argv=["--allow-dedup-shrink"],
    )
    code = _run()
    ids = _node_ids(graph_path)
    assert code in (None, 0)
    assert len(ids) == 2
    assert "readme_overview" in ids
    assert not {"readme_decisions_a", "readme_decisions_b"} <= set(ids)
    raw = graph_path.read_text(encoding="utf-8")
    assert "_dedup_collapsed" not in raw
    assert "_pruned_node_count" not in raw


def test_a_deleted_file_still_writes(monkeypatch, tmp_path):
    """The shrink is one missing file. Dedup merges nothing. The write proceeds."""
    corpus = tmp_path
    readme = str(corpus / "README.md")
    gone = str(corpus / "gone.md")
    nodes = [
        {
            "id": "readme_overview",
            "label": "Overview",
            "file_type": "document",
            "source_file": readme,
            "source_location": "L1",
        },
        {
            "id": "gone_notes",
            "label": "Gone notes",
            "file_type": "document",
            "source_file": gone,
            "source_location": "L1",
        },
    ]
    fresh = [nodes[0]]
    graph_path = _arm(monkeypatch, tmp_path, nodes=fresh)
    # Replace the seeded graph with both files. The stub still returns only README.
    _write_graph(graph_path, nodes)
    code = _run()
    ids = _node_ids(graph_path)
    assert code in (None, 0)
    assert "gone_notes" not in ids
    assert "readme_overview" in ids


def test_to_json_does_not_store_shrink_accounting(tmp_path):
    """build() records the counters on the graph object. to_json must not
    write them. Callers other than extract follow that path (#3774)."""
    from graphify.build import build
    from graphify.export import to_json

    G = build([{"nodes": _notes(tmp_path), "edges": [], "hyperedges": []}])
    assert G.graph.get("_dedup_collapsed") == 1
    out = tmp_path / "graph.json"
    assert to_json(G, {}, str(out), force=True) is True
    raw = out.read_text(encoding="utf-8")
    assert "_dedup_collapsed" not in raw
    assert "_pruned_node_count" not in raw


def test_pruned_node_count_ignores_a_stub_created_this_run(tmp_path):
    """A source-less stub minted this run and then orphaned by the prune is
    not a saved node. It must not excuse a dedup shrink."""
    from graphify.build import build_merge

    root = tmp_path / "repo"
    root.mkdir()
    kept = "README.md"
    gone = "gone.md"
    disk = [
        {"id": "kept", "label": "Overview", "file_type": "document", "source_file": kept},
        {"id": "gone", "label": "Gone", "file_type": "document", "source_file": gone},
    ]
    graph_path = root / "graphify-out" / "graph.json"
    _write_graph(graph_path, disk)
    stub_edge = {"source": "gone", "target": "fresh_stub", "source_file": gone}
    chunk = {
        "nodes": [
            {"id": "kept", "label": "Overview", "file_type": "document", "source_file": kept},
            {"id": "fresh_stub", "label": "Path", "file_type": "code"},
        ],
        "edges": [stub_edge],
        "hyperedges": [],
    }
    G = build_merge([chunk], graph_path, prune_sources=[gone], dedup=False, root=root)
    assert "gone" not in G
    assert "fresh_stub" not in G
    assert G.graph.get("_pruned_node_count") == 1
