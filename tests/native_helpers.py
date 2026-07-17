"""Real embedded-Helix fixtures used by Graphify integration tests."""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

from graphify.helix.model import GraphBuildData
from graphify.helix.persistence import HelixEmbeddedStore
from graphify.helix.state import new_state
from graphify.helix.model import graphify_attributes


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


class _NodeAccessor:
    def __init__(self, owner: "MutableNativeGraph") -> None:
        self.owner = owner

    def __call__(self):
        return self.owner._snapshot().nodes()

    def __getitem__(self, node_id):
        node = self.owner._snapshot().node(node_id)
        if node is None:
            raise KeyError(node_id)
        return graphify_attributes(node.attributes)


class MutableNativeGraph:
    """Small test builder whose reads delegate to a real immutable Helix snapshot.

    This keeps legacy mutation-heavy unit setup concise without introducing a
    NetworkX dependency or exercising a compatibility graph in production.
    """

    def __init__(self, *, directed: bool = False, multigraph: bool = False) -> None:
        self._kind = (
            "multidigraph" if directed and multigraph else
            "digraph" if directed else
            "multigraph" if multigraph else
            "graph"
        )
        self._nodes: dict[Any, dict[str, Any]] = {}
        self._edges: list[dict[str, Any]] = []
        self._dirty = True
        self._graph = None
        self.graph: dict[str, Any] = {}
        self.nodes = _NodeAccessor(self)

    def add_node(self, node_id, **attributes) -> None:
        self._nodes[node_id] = dict(attributes)
        self._dirty = True

    def add_edge(self, source, target, **attributes) -> None:
        self._nodes.setdefault(source, {})
        self._nodes.setdefault(target, {})
        if "multi" not in self._kind:
            for index, edge in enumerate(self._edges):
                same = edge["source"] == source and edge["target"] == target
                reverse = (
                    self._kind == "graph"
                    and edge["source"] == target
                    and edge["target"] == source
                )
                if same or reverse:
                    self._edges[index] = {"source": source, "target": target, **attributes}
                    self._dirty = True
                    return
        self._edges.append({"source": source, "target": target, **attributes})
        self._dirty = True

    def number_of_nodes(self) -> int:
        return len(self._nodes)

    def _snapshot(self):
        if self._dirty or self._graph is None:
            self._graph = graph_from_payload(
                [{"id": node_id, **attributes} for node_id, attributes in self._nodes.items()],
                list(self._edges),
                kind=self._kind,
            )
            self._dirty = False
        return self._graph

    def __getattr__(self, name):
        return getattr(self._snapshot(), name)


class NativeGraphNamespace:
    @staticmethod
    def Graph() -> MutableNativeGraph:
        return MutableNativeGraph()

    @staticmethod
    def DiGraph() -> MutableNativeGraph:
        return MutableNativeGraph(directed=True)

    @staticmethod
    def MultiGraph() -> MutableNativeGraph:
        return MutableNativeGraph(multigraph=True)

    @staticmethod
    def MultiDiGraph() -> MutableNativeGraph:
        return MutableNativeGraph(directed=True, multigraph=True)


native_graphs = NativeGraphNamespace()
