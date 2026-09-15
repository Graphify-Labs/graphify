"""Regression tests for Graphify issue #3477:
Scoped entity deduplication during incremental build_merge().

Ensures:
1. Untouched existing nodes are protected from collapsing with other untouched existing nodes.
2. Incoming nodes can still merge into an untouched node, with the untouched node surviving as canonical.
3. Incoming nodes that match multiple untouched nodes attach to at most one protected survivor without
   transitively collapsing the protected nodes.
4. Incoming duplicates deduplicate normally among themselves.
5. Full build() with protected_ids=None retains existing global dedup behavior.
6. Fuzzy dedup respects the same protected invariants.
"""
import json
from pathlib import Path
import pytest
import networkx as nx

import graphify.build as buildmod
from graphify.build import build, build_merge
from graphify.dedup import deduplicate_entities


def _write_graph(graph_path: Path, nodes, edges=(), hyperedges=()) -> None:
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(
        json.dumps(
            {
                "nodes": list(nodes),
                "edges": list(edges),
                "hyperedges": list(hyperedges),
            }
        ),
        encoding="utf-8",
    )


def test_untouched_duplicate_nodes_survive_incremental_merge(tmp_path):
    """#3477: Two duplicate-labeled nodes in two untouched files must not be collapsed
    when an unrelated third file is incrementally updated with dedup=True."""
    gp = tmp_path / "graphify-out" / "graph.json"
    node_a = {
        "id": "a_auth_service",
        "label": "Authentication Service Component",
        "file_type": "concept",
        "source_file": "a.md",
        "_origin": "semantic",
    }
    node_b = {
        "id": "b_auth_service",
        "label": "Authentication Service Component",
        "file_type": "concept",
        "source_file": "b.md",
        "_origin": "semantic",
    }
    _write_graph(gp, [node_a, node_b])

    # Incremental update touches unrelated c.md
    chunk_c = {
        "nodes": [
            {
                "id": "c_worker",
                "label": "Background Worker Job",
                "file_type": "concept",
                "source_file": "c.md",
                "_origin": "semantic",
            }
        ],
        "edges": [],
    }

    G = build_merge([chunk_c], gp, dedup=True)

    # Both untouched nodes must survive with their original IDs
    assert "a_auth_service" in G
    assert "b_auth_service" in G
    assert "c_worker" in G
    assert G.number_of_nodes() == 3


def test_incoming_duplicate_merges_into_untouched_node_as_canonical_survivor(tmp_path):
    """#3477: An incoming entity duplicate merges into an untouched entity, and the
    untouched node MUST be the canonical survivor, with edges rewired."""
    gp = tmp_path / "graphify-out" / "graph.json"
    untouched_cache = {
        "id": "a_cache_mgr",
        "label": "Memory Cache Manager System",
        "file_type": "concept",
        "source_file": "a.md",
        "attributes": {"tier": "primary"},
        "_origin": "semantic",
    }
    _write_graph(gp, [untouched_cache])

    # Incoming extraction from changed b.md has a richer duplicate
    incoming_cache = {
        "id": "b_cache_mgr",  # shorter ID, would normally win on tiebreak
        "label": "Memory Cache Manager System",
        "file_type": "concept",
        "source_file": "b.md",
        "summary": "Distributed memory cache manager for session state",
        "_origin": "semantic",
    }
    incoming_caller = {
        "id": "b_client",
        "label": "Cache Client Worker",
        "file_type": "concept",
        "source_file": "b.md",
        "_origin": "semantic",
    }
    call_edge = {
        "source": "b_client",
        "target": "b_cache_mgr",
        "relation": "calls",
        "confidence": "EXTRACTED",
        "source_file": "b.md",
    }
    chunk_b = {
        "nodes": [incoming_cache, incoming_caller],
        "edges": [call_edge],
    }

    G = build_merge([chunk_b], gp, dedup=True)

    # The untouched node MUST survive as the canonical ID
    assert "a_cache_mgr" in G
    assert "b_cache_mgr" not in G
    assert "b_client" in G

    # Missing fields from incoming loser should be merged into survivor
    survivor_attrs = G.nodes["a_cache_mgr"]
    assert survivor_attrs.get("summary") == "Distributed memory cache manager for session state"

    # Edge must be rewired to the untouched survivor
    assert G.has_edge("b_client", "a_cache_mgr")


def test_two_untouched_plus_one_incoming_duplicate_bridge_case(tmp_path):
    """#3477: When two untouched duplicate nodes exist and an incoming node shares the same label:
    - Both untouched nodes survive as separate entities.
    - Incoming node resolves to at most one protected survivor.
    - The two protected nodes do not become transitively connected."""
    gp = tmp_path / "graphify-out" / "graph.json"
    node_a = {
        "id": "a_auth",
        "label": "Authentication Service Gateway",
        "file_type": "concept",
        "source_file": "a.md",
        "_origin": "semantic",
    }
    node_b = {
        "id": "b_auth",
        "label": "Authentication Service Gateway",
        "file_type": "concept",
        "source_file": "b.md",
        "_origin": "semantic",
    }
    _write_graph(gp, [node_a, node_b])

    # Incoming extraction from c.md introduces another duplicate
    node_c = {
        "id": "c_auth",
        "label": "Authentication Service Gateway",
        "file_type": "concept",
        "source_file": "c.md",
        "_origin": "semantic",
    }
    edge_c = {
        "source": "c_client",
        "target": "c_auth",
        "relation": "uses",
        "confidence": "EXTRACTED",
        "source_file": "c.md",
    }
    chunk_c = {
        "nodes": [
            node_c,
            {
                "id": "c_client",
                "label": "Gateway Client",
                "file_type": "concept",
                "source_file": "c.md",
                "_origin": "semantic",
            },
        ],
        "edges": [edge_c],
    }

    G = build_merge([chunk_c], gp, dedup=True)

    # BOTH untouched nodes must survive
    assert "a_auth" in G
    assert "b_auth" in G

    # Incoming node was folded into one of the protected nodes
    assert "c_auth" not in G
    # Total nodes: 2 protected + 1 client = 3 nodes
    assert G.number_of_nodes() == 3


def test_two_incoming_duplicate_nodes_deduplicate_normally(tmp_path):
    """#3477: Multiple incoming duplicates still deduplicate normally during build_merge."""
    gp = tmp_path / "graphify-out" / "graph.json"
    untouched_node = {
        "id": "a_existing",
        "label": "Existing Untouched Component",
        "file_type": "concept",
        "source_file": "a.md",
        "_origin": "semantic",
    }
    _write_graph(gp, [untouched_node])

    # Re-extracting / adding new files b.md and c.md that both emit a shared concept
    chunk_b = {
        "nodes": [
            {
                "id": "b_telemetry",
                "label": "Telemetry Event Dispatcher",
                "file_type": "concept",
                "source_file": "b.md",
                "_origin": "semantic",
            }
        ],
        "edges": [],
    }
    chunk_c = {
        "nodes": [
            {
                "id": "c_telemetry",
                "label": "Telemetry Event Dispatcher",
                "file_type": "concept",
                "source_file": "c.md",
                "_origin": "semantic",
            }
        ],
        "edges": [],
    }

    G = build_merge([chunk_b, chunk_c], gp, dedup=True)

    # Untouched survives
    assert "a_existing" in G
    # Incoming nodes collapsed into one
    surviving_telemetry = [n for n in G.nodes if "telemetry" in n]
    assert len(surviving_telemetry) == 1
    assert G.number_of_nodes() == 2


def test_full_build_protected_ids_none_retains_global_dedup():
    """#3477: When build() is called without protected_ids (cold build), normal global dedup occurs."""
    chunk_a = {
        "nodes": [
            {
                "id": "a_auth",
                "label": "Authentication Service Gateway",
                "file_type": "concept",
                "source_file": "a.md",
                "_origin": "semantic",
            }
        ],
        "edges": [],
    }
    chunk_b = {
        "nodes": [
            {
                "id": "b_auth",
                "label": "Authentication Service Gateway",
                "file_type": "concept",
                "source_file": "b.md",
                "_origin": "semantic",
            }
        ],
        "edges": [],
    }

    # Full build with protected_ids=None collapses both into 1 node
    G = build([chunk_a, chunk_b], dedup=True, protected_ids=None)
    assert G.number_of_nodes() == 1


def test_fuzzy_dedup_protected_nodes_do_not_merge(tmp_path):
    """#3477: Pass 2 fuzzy dedup must not collapse two near-identical nodes in untouched files."""
    gp = tmp_path / "graphify-out" / "graph.json"
    # Near-identical labels that clear the Jaro threshold
    node_a = {
        "id": "a_auth_system",
        "label": "Authentication Manager Processing Engine",
        "file_type": "concept",
        "source_file": "a.md",
        "_origin": "semantic",
    }
    node_b = {
        "id": "b_auth_system",
        "label": "Authentication Manager Processng Engine",  # typo on token >= 6 chars
        "file_type": "concept",
        "source_file": "b.md",
        "_origin": "semantic",
    }
    _write_graph(gp, [node_a, node_b])

    chunk_c = {
        "nodes": [
            {
                "id": "c_unrelated",
                "label": "Unrelated Database Connector",
                "file_type": "concept",
                "source_file": "c.md",
                "_origin": "semantic",
            }
        ],
        "edges": [],
    }

    G = build_merge([chunk_c], gp, dedup=True)

    # Both untouched nodes must survive
    assert "a_auth_system" in G
    assert "b_auth_system" in G
    assert G.number_of_nodes() == 3


def test_fuzzy_dedup_incoming_merges_into_protected_as_canonical(tmp_path):
    """#3477: Pass 2 fuzzy dedup merges incoming typo into untouched canonical node."""
    gp = tmp_path / "graphify-out" / "graph.json"
    untouched = {
        "id": "a_auth_system",
        "label": "Authentication Manager Processing Engine",
        "file_type": "concept",
        "source_file": "a.md",
        "_origin": "semantic",
    }
    _write_graph(gp, [untouched])

    incoming_typo = {
        "id": "b_auth_system",
        "label": "Authentication Manager Processng Engine",
        "file_type": "concept",
        "source_file": "b.md",
        "_origin": "semantic",
    }
    chunk_b = {"nodes": [incoming_typo], "edges": []}

    G = build_merge([chunk_b], gp, dedup=True)

    # Untouched survives as canonical winner
    assert "a_auth_system" in G
    assert "b_auth_system" not in G
    assert G.number_of_nodes() == 1


def test_fuzzy_dedup_incoming_bridge_case(tmp_path):
    """#3477: In fuzzy dedup, an incoming node must not bridge two untouched nodes."""
    gp = tmp_path / "graphify-out" / "graph.json"
    node_a = {
        "id": "a_cluster",
        "label": "Distributed Storage Processing Cluster Subsystem",
        "file_type": "concept",
        "source_file": "a.md",
        "_origin": "semantic",
    }
    node_b = {
        "id": "b_cluster",
        "label": "Distributed Storage Processng Cluster Subsystem",
        "file_type": "concept",
        "source_file": "b.md",
        "_origin": "semantic",
    }
    _write_graph(gp, [node_a, node_b])

    # Incoming node in c.md matching a.md
    node_c = {
        "id": "c_cluster",
        "label": "Distributed Storage Processing Cluster Subsystem",
        "file_type": "concept",
        "source_file": "c.md",
        "_origin": "semantic",
    }
    chunk_c = {"nodes": [node_c], "edges": []}

    G = build_merge([chunk_c], gp, dedup=True)

    # Both untouched nodes must survive
    assert "a_cluster" in G
    assert "b_cluster" in G
    assert "c_cluster" not in G
    assert G.number_of_nodes() == 2
