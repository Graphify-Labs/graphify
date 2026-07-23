"""File-node labels are disambiguated when basenames collide (#2032).

In directory-per-entrypoint repos (Supabase Edge Functions, Next.js pages,
Rust mod.rs, Python __init__.py) many files share a basename, so basename-only
file-node labels collide and `explain`/discovery can't tell them apart. When a
basename collides, file nodes get a shortest-unique directory-qualified label;
unique basenames are left bare. Ids/edges are never changed — only labels.
"""
from __future__ import annotations

from graphify.build import (
    _disambiguate_file_node_labels,
    _is_file_node_label,
    _shortest_unique_suffix,
    disambiguate_file_labels_in_nodes,
)
from graphify.helix.model import GraphBuildData, NodeData
from graphify.helix.model import node_attributes
from tests.native_helpers import loaded_from_build


def test_disambiguate_raw_node_list_for_no_cluster_path():
    """The extract --no-cluster path writes the merged node dicts directly
    (bypassing build_from_json), so the list-based variant must relabel too."""
    nodes = [
        {"id": "po", "label": "index.ts", "file_type": "code", "source_file": "fn/process-order/index.ts"},
        {"id": "sr", "label": "index.ts", "file_type": "code", "source_file": "fn/send-receipt/index.ts"},
        {"id": "m", "label": "main.ts", "file_type": "code", "source_file": "main.ts"},
        {"id": "sym", "label": "handler", "file_type": "code", "source_file": "fn/process-order/index.ts"},
    ]
    disambiguate_file_labels_in_nodes(nodes)
    by_id = {n["id"]: n["label"] for n in nodes}
    assert by_id["po"] == "process-order/index.ts"
    assert by_id["sr"] == "send-receipt/index.ts"
    assert by_id["m"] == "main.ts"
    assert by_id["sym"] == "handler"


def test_is_file_node_label_and_suffix_helpers():
    assert _is_file_node_label("index.ts", "a/b/index.ts")
    assert _is_file_node_label("b/index.ts", "a/b/index.ts")  # qualified form
    assert not _is_file_node_label("index", "a/b/index.ts")   # a symbol, not the file
    assert not _is_file_node_label("helper()", "a/b/index.ts")
    all_sfs = {"supabase/functions/process-order/index.ts",
               "supabase/functions/send-receipt/index.ts"}
    assert _shortest_unique_suffix("supabase/functions/process-order/index.ts", all_sfs) == "process-order/index.ts"
    # root-level file colliding with a nested one keeps the bare basename
    assert _shortest_unique_suffix("index.ts", {"index.ts", "a/index.ts"}) == "index.ts"


def _file_node(nid, sf):
    return NodeData(
        nid,
        {"label": sf.rsplit("/", 1)[-1], "file_type": "code", "source_file": sf},
    )


def _labels(graph: GraphBuildData) -> dict[str, str]:
    return {node.id: str(node.attributes["label"]) for node in graph.nodes}


def test_colliding_file_labels_are_qualified_uniques_left_bare():
    graph = GraphBuildData(kind="digraph", nodes=[
        _file_node(nid, sf) for nid, sf in [
        ("po", "supabase/functions/process-order/index.ts"),
        ("sr", "supabase/functions/send-receipt/index.ts"),
        ("main", "src/main.ts"),
    ]])
    # a symbol inside one of the files must NOT be relabeled
    graph.nodes.append(NodeData(
        "sym",
        {"label": "handler", "file_type": "code", "source_file": "supabase/functions/process-order/index.ts"},
    ))

    _disambiguate_file_node_labels(graph)
    labels = _labels(graph)

    assert labels["po"] == "process-order/index.ts"
    assert labels["sr"] == "send-receipt/index.ts"
    assert labels["main"] == "main.ts", "unique basename must stay bare"
    assert labels["sym"] == "handler", "symbol nodes must be untouched"


def test_disambiguation_is_idempotent():
    graph = GraphBuildData(kind="digraph", nodes=[
        _file_node("a", "x/a/index.ts"),
        _file_node("b", "x/b/index.ts"),
    ])
    _disambiguate_file_node_labels(graph)
    first = _labels(graph)
    # Re-run over already-qualified labels: must be stable (derived from path).
    _disambiguate_file_node_labels(graph)
    assert _labels(graph) == first
    assert first == {"a": "a/index.ts", "b": "b/index.ts"}


def test_three_way_collision_grows_suffix_until_unique():
    graph = GraphBuildData(kind="digraph", nodes=[
        _file_node("a", "a/x/index.ts"),
        _file_node("b", "b/x/index.ts"),
    ])
    _disambiguate_file_node_labels(graph)
    labels = _labels(graph)
    # basename + one dir ("x/index.ts") still collides, so grow to two dirs.
    assert labels["a"] == "a/x/index.ts"
    assert labels["b"] == "b/x/index.ts"


def test_end_to_end_build_and_lookup(tmp_path):
    """Full pipeline: two entry-point index.ts files get distinguishable labels
    and both resolve via serve._find_node."""
    from graphify.extract import extract
    from graphify.build import build_from_extraction
    from graphify.serve import _find_node

    fns = tmp_path / "supabase" / "functions"
    (fns / "process-order").mkdir(parents=True)
    (fns / "send-receipt").mkdir(parents=True)
    (fns / "process-order" / "index.ts").write_text("export function processOrder() { return 1; }\n")
    (fns / "send-receipt" / "index.ts").write_text("export function sendReceipt() { return 2; }\n")
    (tmp_path / "main.ts").write_text("export function main() { return 0; }\n")

    result = extract(
        [fns / "process-order" / "index.ts", fns / "send-receipt" / "index.ts", tmp_path / "main.ts"],
        cache_root=tmp_path / "cache", parallel=False,
    )
    loaded = loaded_from_build(build_from_extraction(result, root=str(tmp_path)))
    graph = loaded.graph

    file_labels = {
        attrs["label"] for node in graph.nodes()
        if _is_file_node_label(
            (attrs := node_attributes(graph, node.id)).get("label"),
            attrs.get("source_file"),
        )
    }
    assert "process-order/index.ts" in file_labels
    assert "send-receipt/index.ts" in file_labels
    assert "main.ts" in file_labels  # unique basename stays bare

    # Discovery works for both the directory name and the qualified path.
    assert _find_node(graph, "process-order", native_query=loaded.query)
    assert _find_node(graph, "process-order/index.ts", native_query=loaded.query)
    po = _find_node(graph, "process-order/index.ts", native_query=loaded.query)[0]
    assert node_attributes(graph, po)["label"] == "process-order/index.ts"
