"""Linked copies excluded by detection must not survive a full reconcile."""
import json
from pathlib import Path
import subprocess
import pytest

from graphify.detect import detect, ignored_predicate
from graphify.watch import _reconcile_existing_graph


def workspace(tmp_path):
    main = tmp_path / "app"
    main.mkdir()
    source = main / "a.py"
    source.write_text("def answer(): return 42\n", encoding="utf-8")
    def git(*args):
        subprocess.run(["git", "-C", str(main), *args], check=True, capture_output=True)
    git("init", "-q")
    git("add", ".")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.com", "commit", "-qm", "fixture")
    linked = tmp_path / "app-feature"
    git("worktree", "add", "-q", "-b", "fixture-linked", str(linked))
    return source, linked / "a.py", linked


def test_predicate_matches_scan_for_linked_worktree(tmp_path):
    source, linked_source, linked = workspace(tmp_path)
    files = {Path(p).resolve() for group in detect(tmp_path)["files"].values() for p in group}
    assert source.resolve() in files
    assert linked_source.resolve() not in files
    assert ignored_predicate(tmp_path)(linked_source)
    # Scanning the linked copy itself is intentional, and a main checkout
    # outside the scan root must not suppress its only scanned copy.
    assert not ignored_predicate(linked)(linked_source)


@pytest.mark.parametrize("linked_node", [False, True])
def test_reconcile_prunes_node_edge_and_hyperedge_owned_by_linked_copy(tmp_path, linked_node):
    source, linked_source, _ = workspace(tmp_path)
    control = tmp_path / "unexplained.txt"
    control.write_text("still here", encoding="utf-8")
    nodes = [{"id": n, "label": n, "source_file": str(source), "_origin": "ast"} for n in ["a", "b"]]
    old = {"nodes": nodes + [{"id": "linked", "label": "linked", "source_file": str(linked_source), "_origin": "ast"},
                             {"id": "control", "label": "control", "source_file": str(control), "_origin": "semantic"}],
           "links": [{"source": "a", "target": "b", "relation": "references", "source_file": str(linked_source), "_origin": "semantic"},
                     {"source": "b", "target": "a", "relation": "references", "source_file": str(control), "_origin": "semantic"}],
           "hyperedges": [{"id": "linked-edge", "nodes": ["a", "b"], "source_file": str(linked_source)},
                          {"id": "control-edge", "nodes": ["a", "b"], "source_file": str(control)}]}
    if not linked_node:
        old["nodes"] = [n for n in old["nodes"] if n["id"] != "linked"]
    out = tmp_path / "graphify-out"
    out.mkdir()
    graph = out / "graph.json"
    graph.write_text(json.dumps(old), encoding="utf-8")
    result, _ = _reconcile_existing_graph(graph, {"nodes": nodes, "edges": [], "hyperedges": []},
        out=out, project_root=tmp_path, watch_root=tmp_path,
        code_files=[source], extract_targets=[source], full_rebuild=True,
        deleted_paths=set(), deleted_source_identities=set(),
        is_ignored_full=ignored_predicate(tmp_path))
    assert {n["id"] for n in result["nodes"]} == {"a", "b", "control"}
    assert [e["source_file"] for e in result["edges"]] == [control.relative_to(tmp_path).as_posix()]
    assert [h["id"] for h in result["hyperedges"]] == ["control-edge"]
