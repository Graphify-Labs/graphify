"""Tier-0 retrieval index contracts."""

import json
import os

import networkx as nx
from networkx.readwrite import json_graph

from graphify.query_index import QueryIndex, QueryIndexStore


def _graph() -> nx.Graph:
    graph = nx.Graph()
    graph.add_node(
        "lookup",
        label="performSfappDbLookUp",
        source_file="stack/SFAPP/SfappUdrLookup.C",
        aliases=["UDR lookup", "subscriber cache lookup"],
    )
    graph.add_node(
        "update",
        label="createAndLaunchUdrUpdateQuery",
        source_file="stack/SFAPP/SfappUdrLookup.C",
    )
    graph.add_node("noise", label="renderDashboard", source_file="gui/dashboard.ts")
    graph.add_edge("lookup", "update", relation="calls", confidence="EXTRACTED")
    return graph


def test_tier_zero_ranks_symbols_aliases_and_strong_relations():
    index = QueryIndex.from_graph(_graph())

    packet = index.search("how is the subscriber cache lookup processed", limit=3)

    assert packet.candidates[0].node_id == "lookup"
    assert packet.candidates[0].matched_terms >= {"cache", "lookup", "subscriber"}
    assert packet.candidates[0].strong_relations == ("calls",)


def test_tier_zero_negative_lookup_returns_no_candidates_without_an_llm():
    packet = QueryIndex.from_graph(_graph()).search("unrelated quantum ledger", limit=3)

    assert packet.candidates == ()
    assert packet.llm_invoked is False


def test_serialized_index_rejects_a_different_graph_fingerprint():
    graph = _graph()
    index = QueryIndex.from_graph(graph)
    restored = QueryIndex.from_dict(index.to_dict())

    assert restored.matches_graph(graph)
    graph.add_node("new", label="newNode")
    assert not restored.matches_graph(graph)


def test_query_index_store_reuses_sidecar_until_graph_file_changes(tmp_path):
    """Removing persistence must turn the second CLI query into another full build."""
    graph = _graph()
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps(json_graph.node_link_data(graph, edges="links")),
        encoding="utf-8",
    )
    store = QueryIndexStore(graph_path)

    first, first_hit = store.load_or_build(graph)
    second, second_hit = store.load_or_build(graph)

    assert first_hit is False
    assert second_hit is True
    assert second.search("subscriber cache lookup").candidates[0].node_id == "lookup"
    assert store.index_path.is_file()

    original_stat = graph_path.stat()
    changed = graph_path.read_text(encoding="utf-8").replace(
        "renderDashboard", "renderDashboare"
    )
    graph_path.write_text(changed, encoding="utf-8")
    os.utime(
        graph_path,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )
    _third, third_hit = store.load_or_build(graph)
    assert third_hit is False


def test_query_index_store_rejects_sidecar_for_different_in_memory_graph(tmp_path):
    """Direct API callers must not receive evidence indexed from another graph."""
    graph = _graph()
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps(json_graph.node_link_data(graph, edges="links")),
        encoding="utf-8",
    )
    store = QueryIndexStore(graph_path)
    store.load_or_build(graph)

    different = nx.Graph()
    different.add_node("different", label="loadUdrCacheFromDisk")
    index, cache_hit = store.load_or_build(different)

    assert cache_hit is False
    assert index.search("load udr cache disk").candidates[0].node_id == "different"
