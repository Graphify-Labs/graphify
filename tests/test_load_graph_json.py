"""Direct tests for build.load_graph_json — the shared node-link loader.

merge-graphs, and the global graph each grew their own copy of "load node-link
JSON, normalize the legacy key, stash direction markers", and each copy carried
a different subset of the #738/#2261/#2309/#2484 fixes. The shared loader is
covered transitively by those callers' tests; these pin its own contract —
especially the validation branches, which reject a malformed graph.json with a
ValueError instead of letting it propagate a confusing NetworkX error.
"""
import json

import networkx as nx
import pytest

from graphify.build import load_graph_json, merge_prefixed_into


def _write(tmp_path, payload):
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _minimal(**overrides):
    data = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [{"id": "a"}, {"id": "b"}],
        "links": [{"source": "a", "target": "b", "relation": "calls"}],
    }
    data.update(overrides)
    return data


# --- validation branches: every malformed shape becomes a ValueError ---------

@pytest.mark.parametrize(
    "payload",
    [
        ["not", "a", "mapping"],
        _minimal(nodes={"id": "a"}),
        _minimal(nodes=[["not-a-dict"]]),
        _minimal(nodes=[{"label": "no id"}]),
        _minimal(nodes=[{"id": ["un", "hashable"]}]),
        {"nodes": [{"id": "a"}]},  # neither links nor edges
        _minimal(links={"source": "a"}),
        _minimal(links=["not-a-dict"]),
        _minimal(links=[{"target": "b"}]),  # missing source
        _minimal(links=[{"source": "a"}]),  # missing target
        _minimal(links=[{"source": ["un", "hashable"], "target": "b"}]),
    ],
    ids=[
        "top-level-not-mapping",
        "nodes-not-list",
        "node-not-mapping",
        "node-missing-id",
        "node-id-unhashable",
        "no-links-or-edges",
        "links-not-list",
        "link-not-mapping",
        "link-missing-source",
        "link-missing-target",
        "link-endpoint-unhashable",
    ],
)
def test_malformed_graph_raises_value_error(tmp_path, payload):
    path = _write(tmp_path, payload)
    with pytest.raises(ValueError, match=r"cannot load graph"):
        load_graph_json(path)


def test_missing_file_raises_value_error(tmp_path):
    with pytest.raises(ValueError, match=r"cannot load graph"):
        load_graph_json(tmp_path / "absent.json")


def test_invalid_json_raises_value_error(tmp_path):
    p = tmp_path / "graph.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match=r"cannot load graph"):
        load_graph_json(p)


# --- happy paths --------------------------------------------------------------

def test_loads_canonical_links_spelling(tmp_path):
    G = load_graph_json(_write(tmp_path, _minimal()))
    assert set(G.nodes()) == {"a", "b"}
    assert G.has_edge("a", "b")


def test_loads_legacy_edges_spelling(tmp_path):
    """#738: older runs persisted the list under "edges" instead of "links"."""
    data = _minimal()
    data["edges"] = data.pop("links")
    G = load_graph_json(_write(tmp_path, data))
    assert G.has_edge("a", "b")
    assert G["a"]["b"]["relation"] == "calls"


def test_directed_returns_digraph_in_stored_order(tmp_path):
    """#760: an undirected round-trip re-emits endpoints by node insertion
    order; directed=True must preserve the stored caller→callee arc."""
    G = load_graph_json(_write(tmp_path, _minimal()), directed=True)
    assert isinstance(G, nx.DiGraph)
    assert G.has_edge("a", "b")
    assert not G.has_edge("b", "a")


def test_preserve_direction_stashes_src_tgt_markers(tmp_path):
    """#2261: the graph stays undirected, but each edge carries the stored
    endpoints so a re-serialization can restore the true direction."""
    G = load_graph_json(_write(tmp_path, _minimal()), preserve_direction=True)
    assert not G.is_directed()
    d = G["a"]["b"]
    assert d["_src"] == "a"
    assert d["_tgt"] == "b"


def test_preserve_direction_keeps_existing_markers(tmp_path):
    """#2309: a link persisted in flipped endpoint order carries its truth in
    pre-existing _src/_tgt markers; the loader must not overwrite them."""
    data = _minimal(
        links=[{"source": "b", "target": "a", "relation": "calls",
                "_src": "a", "_tgt": "b"}],
    )
    G = load_graph_json(_write(tmp_path, data), preserve_direction=True)
    d = G["a"]["b"]
    assert d["_src"] == "a", "pre-existing marker was clobbered by the arc tail"
    assert d["_tgt"] == "b"


def test_top_level_hyperedges_restored(tmp_path):
    """#2484: node_link_graph only restores the nested graph.hyperedges slot; a
    file whose hyperedges live only at the top level must not lose them."""
    data = _minimal(hyperedges=[{"id": "h1", "nodes": ["a", "b"]}])
    G = load_graph_json(_write(tmp_path, data))
    assert G.graph.get("hyperedges") == [{"id": "h1", "nodes": ["a", "b"]}]


def test_nested_hyperedges_not_overwritten_by_top_level(tmp_path):
    data = _minimal(
        graph={"hyperedges": [{"id": "nested"}]},
        hyperedges=[{"id": "top-level"}],
    )
    G = load_graph_json(_write(tmp_path, data))
    assert G.graph["hyperedges"] == [{"id": "nested"}]


def test_default_coerces_stored_digraph_to_simple_graph(tmp_path):
    """Established callers (merge-graphs) compose into nx.Graph; a directed or
    multi input must be coerced so nx.compose never sees mixed types (#1606)."""
    G = load_graph_json(_write(tmp_path, _minimal(directed=True)))
    assert type(G) is nx.Graph


def test_preserve_type_keeps_stored_digraph(tmp_path):
    G = load_graph_json(
        _write(tmp_path, _minimal(directed=True)), preserve_type=True
    )
    assert isinstance(G, nx.DiGraph)


@pytest.mark.parametrize(
    ("directed", "expected_type"),
    [(False, nx.MultiGraph), (True, nx.MultiDiGraph)],
)
def test_preserve_type_keeps_keyed_parallel_edges(tmp_path, directed, expected_type):
    data = _minimal(
        multigraph=True,
        links=[
            {"source": "a", "target": "b", "key": "calls", "relation": "calls"},
            {
                "source": "a",
                "target": "b",
                "key": "references",
                "relation": "references",
            },
        ],
    )
    G = load_graph_json(
        _write(tmp_path, data), preserve_type=True, directed=directed
    )
    assert type(G) is expected_type
    assert set(G["a"]["b"]) == {"calls", "references"}


def test_size_cap_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_MAX_GRAPH_BYTES", "10")
    path = _write(tmp_path, _minimal())
    with pytest.raises(ValueError, match=r"cannot load graph"):
        load_graph_json(path)


# --- merge_prefixed_into -------------------------------------------------------

def _prefixed(tag: str, *, external_label: str = "requests") -> nx.Graph:
    G = nx.Graph()
    G.add_node(f"{tag}::app", label="app", source_file="app.py", repo=tag)
    G.add_node(f"{tag}::ext_requests", label=external_label, repo=tag)  # external: no source_file
    G.add_edge(f"{tag}::app", f"{tag}::ext_requests", relation="imports")
    return G


def test_merge_prefixed_into_dedups_externals_by_label():
    G = nx.Graph()
    added_one = merge_prefixed_into(G, _prefixed("one"))
    added_two = merge_prefixed_into(G, _prefixed("two"))
    assert added_one == 2
    assert added_two == 1, "the shared external must dedup onto the existing node"
    externals = [n for n, d in G.nodes(data=True) if not d.get("source_file")]
    assert len(externals) == 1
    # Both repos' import edges were rewired onto the shared external.
    assert G.degree(externals[0]) == 2


def test_merge_prefixed_into_skips_self_loops_from_remap():
    G = nx.Graph()
    G.add_node("ext", label="requests")  # existing sourceless external
    prefixed = nx.Graph()
    prefixed.add_node("one::a", label="requests")  # dedups onto "ext"
    prefixed.add_node("one::b", label="requests2")
    prefixed.add_edge("one::a", "one::b", relation="uses")
    prefixed.add_edge("one::a", "one::a", relation="self")
    merge_prefixed_into(G, prefixed)
    assert not G.has_edge("ext", "ext"), "remapping must not introduce self-loops"
