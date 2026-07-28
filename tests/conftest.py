from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _sandbox_home(tmp_path_factory, monkeypatch):
    """Every test gets a throwaway HOME so installers/uninstallers can never
    touch the developer's real ~/.claude, ~/.gemini, ~/.codebuddy, ~/.copilot,
    ~/.config, ~/.agents (issue #2168).

    Allocated via tmp_path_factory (not inside tmp_path) so tests that assert
    the exact contents of their own tmp_path are unaffected."""
    home = tmp_path_factory.mktemp("sandbox-home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))              # Windows ntpath.expanduser
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)     # escape hatch that bypasses Path.home
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home

# --------------------------------------------------------------------------
# FalkorDB-backed graph fixtures (NetworkX replacement).
# Every test that needs a graph gets a fresh, uniquely-named GraphStore bound
# to a running FalkorDB. Skips cleanly when none is reachable.
#   docker run -d -p 6379:6379 falkordb/falkordb:latest
# Overridable via FALKORDB_URI / FALKORDB_HOST / FALKORDB_PORT.
# --------------------------------------------------------------------------
def _falkordb_uri() -> str:
    if os.environ.get("FALKORDB_URI"):
        return os.environ["FALKORDB_URI"]
    host = os.environ.get("FALKORDB_HOST", "localhost")
    port = os.environ.get("FALKORDB_PORT", "6379")
    return f"falkordb://{host}:{port}"


@pytest.fixture(scope="session")
def falkordb_uri() -> str:
    return _falkordb_uri()


@pytest.fixture(scope="session")
def _require_falkordb(falkordb_uri):
    """Skip only tests that actually need a live FalkorDB. NOT autouse — the
    DB-backed fixtures (store/seed_graph/make_store) depend on it, so DB tests
    skip when no engine is reachable while DB-free tests (graphjson, _minhash,
    detect, security, ...) still run, instead of the whole suite vanishing.
    Session-scoped so the ping happens once."""
    pytest.importorskip("falkordb")
    from graphify.store import _connect

    try:
        _connect(falkordb_uri).connection.ping()
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"no FalkorDB reachable at {falkordb_uri} ({e})")


_store_counter = {"n": 0}


@pytest.fixture()
def store(falkordb_uri, _require_falkordb):
    """A fresh, empty, uniquely-named GraphStore; cleaned up after the test."""
    from graphify.store import GraphStore

    _store_counter["n"] += 1
    gs = GraphStore(graph_name=f"pytest_{os.getpid()}_{_store_counter['n']}", uri=falkordb_uri)
    gs.clear()
    try:
        yield gs
    finally:
        try:
            gs.clear()
        except Exception:
            pass


@pytest.fixture()
def seed_graph(falkordb_uri, _require_falkordb):
    """Seed a FalkorDB graph for an output dir from node-link data, writing the
    pointer file so the CLI/serve loaders find it (replaces writing graph.json).

    Usage: seed_graph(tmp_path, nodes=[...], links=[...]) -> GraphStore.
    Each node dict needs an ``id``; each link dict ``source``/``target``.
    """
    from graphify.store import open_store

    created = []

    def _seed(out_dir, nodes=(), links=(), *, write_artifact=True):
        store = open_store(out_dir, uri=falkordb_uri, create=True)
        store.clear()
        store.add_nodes_from([
            (n["id"], {k: v for k, v in n.items() if k != "id"}) for n in nodes
        ])
        store.add_edges_from([
            (e["source"], e["target"], {k: v for k, v in e.items() if k not in ("source", "target")})
            for e in links
        ])
        created.append(store)
        if write_artifact:
            import json as _json
            from pathlib import Path as _Path
            (_Path(out_dir) / "graph.json").write_text(
                _json.dumps({"directed": True, "multigraph": False, "graph": {},
                             "nodes": list(nodes), "links": list(links)}),
                encoding="utf-8",
            )
        return store

    try:
        yield _seed
    finally:
        for s in created:
            try:
                s.clear()
            except Exception:
                pass


@pytest.fixture()
def make_store(falkordb_uri, _require_falkordb):
    """Factory for tests needing more than one graph (e.g. graph_diff)."""
    from graphify.store import GraphStore

    created = []

    def _make():
        _store_counter["n"] += 1
        gs = GraphStore(graph_name=f"pytest_{os.getpid()}_{_store_counter['n']}", uri=falkordb_uri)
        gs.clear()
        created.append(gs)
        return gs

    try:
        yield _make
    finally:
        for gs in created:
            try:
                gs.clear()
            except Exception:
                pass


_ANALYZE_WARNING_FILTERS = (
    "ignore:Tensorflow not installed; ParametricUMAP will be unavailable:ImportWarning:umap",
    "ignore:Please import `random` from the `scipy\\.sparse` namespace.*:"
    "DeprecationWarning:hyppo\\.independence\\.hhg",
    "ignore:The keyword argument 'nopython=False' was supplied.*:Warning:numba\\.core\\.decorators",
)


def pytest_collection_modifyitems(items: list[Any]) -> None:
    for item in items:
        if item.path.name != "test_analyze.py":
            continue
        for warning_filter in _ANALYZE_WARNING_FILTERS:
            item.add_marker(pytest.mark.filterwarnings(warning_filter))
