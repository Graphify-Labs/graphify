"""Corrupt native generations produce actionable recovery errors."""
from __future__ import annotations

import pytest

from graphify.build import build_from_extraction, build_merge
from graphify.affected import load_graph
from graphify.helix.persistence import HelixEmbeddedStore
from graphify.security import validate_store_path
from tests.native_helpers import make_loaded


def _corrupt(tmp_path):
    store_path = make_loaded(tmp_path, nodes=[{"id": "a"}]).store_path
    with HelixEmbeddedStore(store_path) as store:
        generation = store.active_generation
        traversal = store._helix.g().n_with_label_where(
            "GraphifyMeta",
            store._helix.SourcePredicate.eq("graphify_generation", generation),
        ).set_property("section_state_checksum", "sha256:corrupt")
        store._query(
            store._helix.write_batch().var_as("corrupt", traversal).returning(["corrupt"])
        )
    return store_path


def test_build_merge_corrupt_graph_raises_runtimeerror(tmp_path):
    p = _corrupt(tmp_path)
    with HelixEmbeddedStore(p, read_only=True) as store:
        with pytest.raises(RuntimeError, match="checksum verification"):
            store.verify()


def test_affected_load_graph_corrupt_raises_runtimeerror(tmp_path):
    p = _corrupt(tmp_path)
    with pytest.raises(RuntimeError, match=r"Cannot open Helix store|regenerate"):
        load_graph(p)


def test_diagnostics_read_corrupt_raises_runtimeerror(tmp_path):
    p = tmp_path / "legacy.json"
    p.write_text('{"nodes": [', encoding="utf-8")
    with pytest.raises(ValueError, match=r"obsolete|rebuild"):
        validate_store_path(p)


def test_valid_graph_still_loads(tmp_path):
    """A valid native store loads and its transient DTO can be updated."""
    p = make_loaded(tmp_path, nodes=[{"id": "a", "label": "a"}]).store_path
    graph = load_graph(p)
    assert graph.contains_node("a")
    base = build_from_extraction({"nodes": [{"id": "a", "label": "a"}], "edges": []})
    merged = build_merge([], graph_path=p, base_graph=base, dedup=False)
    assert merged.node_count == 1
