"""Real embedded-Helix fixtures used by Graphify integration tests."""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

from graphify.helix.model import GraphBuildData
from graphify.helix.persistence import HelixEmbeddedStore
from graphify.helix.state import new_state


def make_loaded(
    root: Path | None = None,
    *,
    nodes: list[dict[str, Any]] | None = None,
    edges: list[dict[str, Any]] | None = None,
    kind: str = "graph",
    graph: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
):
    directed = kind in {"digraph", "multidigraph"}
    multigraph = kind in {"multigraph", "multidigraph"}
    root = Path(tempfile.mkdtemp(prefix="graphify-native-test-")) if root is None else root
    payload = {
        "directed": directed,
        "multigraph": multigraph,
        "graph": graph or {},
        "nodes": nodes or [],
        "links": edges or [],
    }
    build = GraphBuildData.from_node_link(payload)
    store_path = root / "graph.helix"
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(build, state or new_state())
    with HelixEmbeddedStore(store_path, read_only=True) as store:
        return store.load()


def triangle(root: Path):
    return make_loaded(
        root,
        nodes=[
            {"id": "a", "label": "A", "source_file": "a.py", "file_type": "code"},
            {"id": "b", "label": "B", "source_file": "b.py", "file_type": "code"},
            {"id": "c", "label": "C", "source_file": "c.py", "file_type": "code"},
        ],
        edges=[
            {"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED", "weight": 1.0},
            {"source": "b", "target": "c", "relation": "imports", "confidence": "INFERRED", "weight": 0.8},
            {"source": "c", "target": "a", "relation": "references", "confidence": "AMBIGUOUS", "weight": 0.5},
        ],
    )


def graph_from_payload(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
    *,
    kind: str = "graph",
):
    """Return a real immutable embedded-Helix snapshot for unit tests."""
    return make_loaded(nodes=nodes, edges=edges or [], kind=kind).graph


def graph_from_build(build: GraphBuildData):
    """Persist transient build data and return a real native snapshot."""
    root = Path(tempfile.mkdtemp(prefix="graphify-native-build-test-"))
    store_path = root / "graph.helix"
    with HelixEmbeddedStore(store_path) as store:
        store.save_generation(build, new_state())
    with HelixEmbeddedStore(store_path, read_only=True) as store:
        return store.load().graph
