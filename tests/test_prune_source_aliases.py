"""Excluding a corpus alias must not delete its target's graph (#5273)."""
import json

import pytest

from graphify.build import build_merge, merge_raw_extraction


@pytest.mark.parametrize("raw", [True, False])
@pytest.mark.parametrize("absolute", [True, False])
@pytest.mark.parametrize("deleted", [True, False])
@pytest.mark.parametrize("pruned", ["link.py", "b.py"])
def test_prune_only_named_corpus_path(
    tmp_path, requires_symlinks, raw, absolute, deleted, pruned
):
    (tmp_path / "b.py").write_text("def beta(): pass\n", encoding="utf-8")
    (tmp_path / "link.py").symlink_to("b.py")
    if deleted:
        (tmp_path / pruned).unlink()
    kept = "b.py" if pruned == "link.py" else "link.py"
    # Three nodes per source keep hyperedges valid in the clustered path.
    nodes = [{"id": f"{stem}_{i}", "label": f"{stem} {i}",
              "source_file": sf, "file_type": "code", "_origin": "ast"}
             for sf, stem in [("b.py", "b"), ("link.py", "link")]
             for i in range(3)]
    edges = [{"source": f"{stem}_0", "target": f"{stem}_1", "source_file": sf,
              "relation": "calls", "confidence": "EXTRACTED"}
             for sf, stem in [("b.py", "b"), ("link.py", "link")]]
    hyperedges = [{"id": stem, "source_file": sf,
                   "nodes": [f"{stem}_{i}" for i in range(3)]}
                  for sf, stem in [("b.py", "b"), ("link.py", "link")]]
    graph_path = tmp_path / "graphify-out" / "graph.json"
    graph_path.parent.mkdir()
    graph_path.write_text(json.dumps({"nodes": nodes, "edges": edges,
                                      "hyperedges": hyperedges}), encoding="utf-8")
    source = str(tmp_path / pruned) if absolute else pruned
    if raw:
        merged = merge_raw_extraction({"nodes": [], "edges": []}, graph_path,
                                      prune_sources=[source], root=tmp_path)
        result_nodes, result_edges, result_hyper = (
            merged["nodes"], merged["edges"], merged.get("hyperedges", []))
    else:
        graph = build_merge([], graph_path, prune_sources=[source], root=tmp_path,
                            dedup=False)
        result_nodes = list(dict(graph.nodes).values())
        result_edges = [data for _, _, data in graph.edges(data=True)]
        result_hyper = graph.graph.get("hyperedges", [])
    assert {n["source_file"] for n in result_nodes} == {kept}
    assert {e["source_file"] for e in result_edges} == {kept}
    assert {h["source_file"] for h in result_hyper} == {kept}


def test_cli_exclusion_keeps_included_target(tmp_path, requires_symlinks):
    import subprocess
    import sys

    (tmp_path / "b.py").write_text("def beta():\n    return 2\n", encoding="utf-8")
    (tmp_path / "app.py").write_text(
        "from b import beta\n\ndef main():\n    return beta()\n", encoding="utf-8")

    def run():
        subprocess.run([sys.executable, "-m", "graphify", "extract", str(tmp_path),
                        "--code-only"], cwd=tmp_path, check=True, capture_output=True,
                       text=True, timeout=60)

    def ids():
        data = json.loads((tmp_path / "graphify-out" / "graph.json").read_text())
        return {n["id"] for n in data["nodes"]}

    run()
    (tmp_path / "link.py").symlink_to("b.py")
    run()
    assert {"b", "b_beta", "link", "link_beta"} <= ids()
    (tmp_path / ".graphifyignore").write_text("link.py\n", encoding="utf-8")
    run()
    assert {"b", "b_beta", "app", "app_main"} <= ids()
    assert not {"link", "link_beta"} & ids()
