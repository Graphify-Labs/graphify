"""Every edge endpoint in graph.json must be a declared node (#2873).

`graph.json` used to ship `imports`/`imports_from`/`re_exports` edges whose
target was an external module (stdlib, a third-party dependency) with no
matching entry in `nodes[]`. Every loader (networkx `node_link_graph`)
materialises such an endpoint as an attribute-less phantom node, so the node
set the file declares and the node set it produces disagree, and `merge-graphs`
fragments the same external module into one node per repo. These tests pin the
fix: mint a typed external stub node instead, keep it global across repos, and
never stub a non-import relation (a sourceless external call target stays
suppressed per #3156).
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from graphify.build import (
    build_from_json,
    mint_external_stubs_in_data,
    prefix_graph_for_global,
)


def _import_extraction(target: str, relation: str = "imports") -> dict:
    return {
        "nodes": [
            {"id": "pkg_a", "label": "a.py", "file_type": "code", "source_file": "pkg/a.py"},
        ],
        "links": [
            {"source": "pkg_a", "target": target, "relation": relation,
             "source_file": "pkg/a.py", "confidence": "EXTRACTED", "weight": 1.0},
        ],
    }


def test_build_from_json_mints_external_import_stub():
    G = build_from_json(_import_extraction("typing"))
    assert "typing" in G.nodes, "external import target must be a declared node, not dangling"
    assert G.nodes["typing"].get("external") is True
    assert G.nodes["typing"].get("type") == "external"
    assert G.has_edge("pkg_a", "typing"), "the import edge must survive"


def test_external_stub_makes_serialized_graph_self_consistent():
    from networkx.readwrite import json_graph

    G = build_from_json(_import_extraction("pathlib", relation="imports_from"))
    data = json_graph.node_link_data(G, edges="links")
    declared = {n["id"] for n in data["nodes"]}
    for e in data["links"]:
        assert e["source"] in declared and e["target"] in declared, (
            "serialized graph must have no undeclared edge endpoint"
        )


def test_non_import_dangling_edge_is_still_dropped():
    """A sourceless external CALL target is deliberately suppressed (#3156) to
    avoid a phantom god-node: only import-family relations get a stub."""
    G = build_from_json(_import_extraction("some_external_fn", relation="calls"))
    assert "some_external_fn" not in G.nodes
    assert not G.has_edge("pkg_a", "some_external_fn")


def test_mint_external_stubs_in_data_is_idempotent():
    data = {
        "nodes": [{"id": "pkg_a", "label": "a.py", "file_type": "code",
                   "source_file": "pkg/a.py"}],
        "links": [{"source": "pkg_a", "target": "typing", "relation": "imports"}],
    }
    mint_external_stubs_in_data(data)
    mint_external_stubs_in_data(data)  # second pass must not duplicate
    stubs = [n for n in data["nodes"] if n.get("external")]
    assert [n["id"] for n in stubs] == ["typing"]


def test_external_stub_unifies_across_repos_in_merge():
    def mk(file_id: str) -> nx.Graph:
        return build_from_json({
            "nodes": [{"id": file_id, "label": f"{file_id}.py", "file_type": "code",
                       "source_file": f"{file_id}.py"}],
            "links": [{"source": file_id, "target": "typing", "relation": "imports",
                       "source_file": f"{file_id}.py", "confidence": "EXTRACTED", "weight": 1.0}],
        })

    merged = nx.compose(
        prefix_graph_for_global(mk("a"), "repoA"),
        prefix_graph_for_global(mk("b"), "repoB"),
    )
    assert "typing" in merged.nodes, "external module must stay a single global id"
    assert "repoA::typing" not in merged.nodes and "repoB::typing" not in merged.nodes
    assert merged.nodes["typing"].get("repo") is None, "an external node belongs to no repo"
    # both repos' import edges land on the one shared node
    assert merged.degree("typing") == 2


def test_no_cluster_update_leaves_no_undeclared_endpoint(tmp_path: Path):
    """End-to-end: `graphify update --no-cluster` writes the raw merged
    extraction, not a build_from_json graph, so it must stub external endpoints
    on that path too. Routes through the real watch rebuild."""
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    (corpus / "pkg").mkdir(parents=True)
    (corpus / "pkg" / "a.py").write_text(
        "import typing\nfrom pathlib import Path\nfrom .b import helper\n\n"
        "def go(x: 'typing.Any') -> None:\n    helper(Path(str(x)))\n",
        encoding="utf-8",
    )
    (corpus / "pkg" / "b.py").write_text(
        "import re\n\ndef helper(x):\n    return re.match(r'.', str(x))\n", encoding="utf-8"
    )
    (corpus / "pkg" / "__init__.py").write_text("from .a import go\n", encoding="utf-8")

    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    data = json.loads((corpus / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    declared = {n["id"] for n in data["nodes"]}
    dangling = [
        (e.get("source"), e.get("target"))
        for e in data["links"]
        if e.get("source") not in declared or e.get("target") not in declared
    ]
    assert not dangling, f"graph.json has undeclared edge endpoints: {dangling}"
    # networkx must not have to materialise any phantom node
    G = nx.node_link_graph(data, edges="links")
    assert G.number_of_nodes() == len(data["nodes"])
    # the stdlib imports resolved to typed external stubs
    externals = {n["id"] for n in data["nodes"] if n.get("external")}
    assert {"typing", "pathlib", "re"} <= externals
