"""Native, revision-pinned embedded Helix runtime for Graphify."""

from .model import EdgeData, GraphBuildData, LoadedGraph, NodeData
from .native import NativeBackendUnavailable, native_backend_info
from .persistence import (
    DEFAULT_GLOBAL_STORE,
    DEFAULT_PROJECT_STORE,
    HelixEmbeddedStore,
    HelixGraphReader,
    graph_storage_exists,
    load_graph,
    load_graph_payload,
    persist_graph,
    persist_graph_data,
)

__all__ = [
    "HelixEmbeddedStore",
    "HelixGraphReader",
    "DEFAULT_GLOBAL_STORE",
    "DEFAULT_PROJECT_STORE",
    "NativeBackendUnavailable",
    "EdgeData",
    "GraphBuildData",
    "LoadedGraph",
    "NodeData",
    "graph_storage_exists",
    "load_graph",
    "load_graph_payload",
    "native_backend_info",
    "persist_graph",
    "persist_graph_data",
]
