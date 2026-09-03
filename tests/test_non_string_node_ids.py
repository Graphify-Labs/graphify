"""Non-string node ids from LLM backends must not crash the build (#2326).

A backend can emit ``{"id": 10}`` where the schema says ``{"id": "10"}``. Every
id consumer downstream assumes ``str``, so an int id used to abort the whole
build in three different places. These tests pin the crash sites and the
edge/hyperedge linkage that a node-only coercion would silently break.
"""
import networkx as nx
import pytest

from graphify.build import build, build_from_json


def _node(nid, label, **kw):
    return {
        "id": nid,
        "label": label,
        "file_type": "concept",
        "source_file": "a.py",
        **kw,
    }


def _edge(src, tgt):
    return {"source": src, "target": tgt, "relation": "uses", "confidence": "EXTRACTED"}


def test_pick_winner_survives_int_id_in_duplicate_group():
    """dedup._pick_winner regex-searched the raw id (the issue's traceback).

    Driven through ``build`` because that is dedup's only production caller, so
    ``build`` is where the coercion has to land for this path to be fixed.
    """
    ext = {"nodes": [_node(10, "Alpha"), _node("alpha_c1", "Alpha")], "edges": []}
    G = build([ext], dedup=True)
    assert all(isinstance(nid, str) for nid in G.nodes)


def test_build_accepts_a_single_int_id_node_with_no_duplicate():
    """build_from_json's sorted(node_set) crashed even with nothing to dedup."""
    ext = {"nodes": [_node(10, "Alpha"), _node("b", "Beta")], "edges": [_edge(10, "b")]}
    G = build([ext], dedup=True)
    assert "10" in G.nodes
    assert 10 not in G.nodes


def test_int_id_endpoints_stay_connected_after_coercion():
    """Coercing node ids without coercing endpoints would orphan the edge."""
    ext = {"nodes": [_node(10, "Alpha"), _node(20, "Beta")], "edges": [_edge(10, 20)]}
    G = build([ext], dedup=True)
    assert G.has_edge("10", "20")


def test_int_id_survives_a_fuzzy_dedup_group():
    ext = {
        "nodes": [_node(10, "PaymentProcessor"), _node("b", "PaymentProcessors")],
        "edges": [_edge(10, "b")],
    }
    G = build([ext], dedup=True)
    assert all(isinstance(nid, str) for nid in G.nodes)


def test_float_id_is_coerced_too():
    ext = {"nodes": [_node(1.5, "Alpha"), _node("b", "Beta")], "edges": [_edge(1.5, "b")]}
    G = build([ext], dedup=True)
    assert G.has_edge("1.5", "b")


def test_legacy_from_to_endpoints_are_coerced():
    """dedup reads the legacy from/to aliases (#803), so they need it as well."""
    ext = {
        "nodes": [_node(10, "Alpha"), _node("b", "Beta")],
        "edges": [{"from": 10, "to": "b", "relation": "uses", "confidence": "EXTRACTED"}],
    }
    G = build([ext], dedup=True)
    assert G.has_edge("10", "b")


def test_hyperedge_members_are_coerced_with_their_nodes():
    ext = {
        "nodes": [_node(10, "Alpha"), _node("b", "Beta")],
        "edges": [],
        "hyperedges": [{"id": "he1", "label": "grp", "nodes": [10, "b"]}],
    }
    G = build([ext], dedup=True)
    members = G.graph["hyperedges"][0]["nodes"]
    assert members == ["10", "b"]


def test_build_from_json_coerces_on_the_direct_entry():
    """Reloading a persisted graph does not go through build()/dedup."""
    G = build_from_json({"nodes": [_node(10, "Alpha")], "edges": []})
    assert list(G.nodes) == ["10"]


def test_numeric_endpoint_with_no_matching_node_matches_the_string_case():
    """A numeric endpoint with no node of its own must behave like a string one.

    Both are dangling references, which build_from_json drops — the point is that
    coercion makes the int indistinguishable from the str, rather than crashing
    or leaving a half-typed endpoint behind.
    """
    def graph_for(target):
        G = build_from_json(
            {"nodes": [_node("a", "Alpha")], "edges": [_edge("a", target)]}
        )
        return sorted(G.nodes), sorted(G.edges)

    assert graph_for(99) == graph_for("99")


@pytest.mark.parametrize("bad", [None, ["x"], {"k": "v"}])
def test_non_scalar_ids_are_left_for_validation(bad):
    """Only numeric scalars are coerced; str(None) == 'None' would be a lie."""
    from graphify.build import _coerce_non_string_ids

    ext = {"nodes": [{"id": bad, "label": "Alpha"}], "edges": []}
    _coerce_non_string_ids(ext)
    assert ext["nodes"][0]["id"] == bad


def test_bool_id_is_not_coerced():
    from graphify.build import _coerce_non_string_ids

    ext = {"nodes": [{"id": True, "label": "Alpha"}], "edges": []}
    _coerce_non_string_ids(ext)
    assert ext["nodes"][0]["id"] is True


def test_string_ids_are_untouched():
    """Regression guard: the normal path must be byte-identical."""
    ext = {"nodes": [_node("a", "Alpha"), _node("b", "Beta")], "edges": [_edge("a", "b")]}
    G = build([ext], dedup=True)
    assert isinstance(G, nx.Graph)
    assert set(G.nodes) == {"a", "b"}
    assert G.has_edge("a", "b")
