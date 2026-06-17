"""FalkorDB-backed graph store — the single replacement for NetworkX.

`GraphStore` wraps a named FalkorDB graph and exposes a NetworkX-shaped API so
the rest of graphify can treat it almost exactly like the `nx.Graph` it used to
pass around. FalkorDB is the source of truth and the compute engine:

* **Writes / mutation** go straight to FalkorDB (batched `UNWIND ... MERGE`).
* **Algorithms** run server-side — built-in `algo.*` where they exist, and the
  JS UDFs in ``graphify/udfs/graphify_algos.js`` (louvain, edge betweenness,
  simple cycles) where they don't.
* **Reads** (the `G.nodes[id]`, `G.edges(data=True)`, `G.degree(n)` patterns used
  in ~200 call sites) are served from a read cache that is bulk-loaded from
  FalkorDB once via Cypher and invalidated on mutation. This keeps the hot
  analysis loops fast (in-memory, like the old nx graph) without reimplementing
  any algorithm in Python.

Schema
------
Every node has the base label ``:Entity`` plus a sanitized ``file_type`` label;
``id`` is the key and a unique index on ``:Entity(id)`` (created at init) makes
MERGE/MATCH fast. Edges are stored DIRECTED in original orientation with the
sanitized relation as the Cypher type and the raw relation kept as the
``relation`` property. Parallel edges are native, so the old ``_src``/``_tgt``
markers are gone. Graph-level metadata (e.g. ``hyperedges``) lives on a singleton
``:GraphMeta`` node and is mirrored to the in-memory ``.graph`` dict.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path
from urllib.parse import urlparse

_UDF_LIB = "graphify_algos"
_UDF_SRC = Path(__file__).parent / "udfs" / "graphify_algos.js"
_udf_loaded_servers: set[str] = set()
_udf_lock = threading.Lock()

DEFAULT_URI = "falkordb://localhost:6379"
_META_KEY = "__graphmeta__"

# FalkorDB caps rows returned per query at RESULTSET_SIZE (default 10000), which
# silently truncates bulk reads on large graphs. We raise it at connect time so
# row-returning procedures (e.g. algo.betweenness) aren't truncated, and ALSO
# paginate the cache-load below at a page size safely under the default cap so
# the read cache is complete even if the config raise is rejected.
_RESULTSET_SIZE = 1_000_000_000
_PAGE = 9000
# Default read TIMEOUT is 1000ms, which the server-side UDFs (Louvain, edge
# betweenness) blow past on large graphs. Raise the server defaults at connect
# and also pass this per-query timeout on heavy READ calls (not writes — FalkorDB
# disallows timeouts on write queries).
_QUERY_TIMEOUT_MS = 600_000
_server_configured: set[str] = set()


def _safe_label(label: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_]", "", label or "")
    return sanitized if sanitized else "Entity"


def _safe_rel(relation: str) -> str:
    return re.sub(r"[^A-Z0-9_]", "_", (relation or "").upper().replace(" ", "_").replace("-", "_")) or "RELATED_TO"


def _scalar_props(data: dict) -> dict:
    return {
        k: v
        for k, v in data.items()
        if isinstance(v, (str, int, float, bool)) and not k.startswith("_")
    }


def graph_name_for(path: str | Path) -> str:
    """Stable, key-safe FalkorDB graph name derived from a directory path."""
    resolved = str(Path(path).resolve())
    base = _safe_label(Path(resolved).name) or "graph"
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:8]
    return f"graphify_{base}_{digest}"


def pointer_path(out_dir: str | Path = "graphify-out") -> Path:
    """Path of the FalkorDB pointer file that records the graph name + URI."""
    return Path(out_dir) / "falkordb.json"


def open_store(
    out_dir: str | Path = "graphify-out",
    uri: str = DEFAULT_URI,
    *,
    create: bool = True,
    directed: bool = True,
) -> "GraphStore":
    """Open the GraphStore for an output directory.

    The graph name + URI are recorded in ``<out_dir>/falkordb.json`` (the FalkorDB
    replacement for the old ``graph.json`` location). When absent, the name is
    derived deterministically from the project root (the parent of ``out_dir``).
    """
    p = pointer_path(out_dir)
    name = None
    if p.exists():
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
            name = cfg.get("graph_name")
            uri = cfg.get("uri", uri)
        except Exception:
            name = None
    if not name:
        root = Path(out_dir).resolve().parent
        name = graph_name_for(root)
        if create:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"graph_name": name, "uri": uri}), encoding="utf-8")
    return GraphStore(graph_name=name, uri=uri, directed=directed)


def _connect_lite(dbfile: str):
    """Embedded FalkorDB Lite (redislite): run the engine in-process from an RDB
    file — no external server. Opt-in via the GRAPHIFY_FALKORDB_LITE env var."""
    # redis 8.0.0 crashes enabling maintenance-notifications on the host-less
    # unix-socket connection redislite uses; it is irrelevant for an embedded
    # engine, so neutralize it.
    import redis.connection as _rc
    for _name in ("AbstractConnection", "Connection", "UnixDomainSocketConnection"):
        _cls = getattr(_rc, _name, None)
        if _cls and hasattr(_cls, "activate_maint_notifications_handling_if_enabled"):
            _cls.activate_maint_notifications_handling_if_enabled = lambda self, **kw: None
    import redislite
    return redislite.FalkorDB(dbfilename=dbfile)


def _connect(uri: str, user: str | None = None, password: str | None = None):
    import os
    # Embedded FalkorDB Lite is selected by (in priority order) the
    # GRAPHIFY_FALKORDB_LITE env var pointing at an RDB file, or a
    # `falkordb-lite://<path>` / `lite://<path>` URI. Default server path otherwise.
    _lite = os.environ.get("GRAPHIFY_FALKORDB_LITE")
    if _lite:
        return _connect_lite(_lite)
    parsed = urlparse(uri if "://" in uri else f"redis://{uri}")
    if parsed.scheme in ("falkordb-lite", "lite"):
        return _connect_lite(parsed.path or None)

    try:
        from falkordb import FalkorDB
    except ImportError as e:  # pragma: no cover
        raise ImportError("falkordb SDK not installed. Run: pip install falkordb") from e
    connect_user = parsed.username or (user if password else None)
    connect_password = parsed.password or (password or None)
    return FalkorDB(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        username=connect_user,
        password=connect_password,
    )


# ---------------------------------------------------------------------------
# NetworkX-shaped views over the read cache
# ---------------------------------------------------------------------------
class _NodeView:
    """Mimics nx ``G.nodes``: iterable, callable(data=), subscriptable [id]."""

    def __init__(self, store: "GraphStore"):
        self._s = store

    def __call__(self, data=False):
        self._s._ensure_cache()
        items = [(nid, self._s._ncache[nid]) for nid in self._s._nsorted]
        if data:
            return iter(items)
        return iter([nid for nid, _ in items])

    def __iter__(self):
        self._s._ensure_cache()
        return iter(self._s._nsorted)

    def __getitem__(self, node_id):
        self._s._ensure_cache()
        return self._s._ncache[node_id]

    def __contains__(self, node_id):
        self._s._ensure_cache()
        return node_id in self._s._ncache

    def __len__(self):
        self._s._ensure_cache()
        return len(self._s._ncache)

    def get(self, node_id, default=None):
        self._s._ensure_cache()
        return self._s._ncache.get(node_id, default)


class _EdgeView:
    """Mimics nx ``G.edges``: callable(nbunch=None, data=) and iterable."""

    def __init__(self, store: "GraphStore"):
        self._s = store

    def __call__(self, nbunch=None, data=False):
        self._s._ensure_cache()
        if nbunch is None:
            rows = self._s._esorted
        else:
            if isinstance(nbunch, (str, bytes)):
                wanted = {nbunch}
            else:
                wanted = set(nbunch)
            rows = [e for e in self._s._esorted if e[0] in wanted or e[1] in wanted]
        if data:
            return iter([(u, v, dict(a)) for u, v, a in rows])
        return iter([(u, v) for u, v, _ in rows])

    def __iter__(self):
        self._s._ensure_cache()
        return iter([(u, v) for u, v, _ in self._s._esorted])

    def __getitem__(self, pair):
        """nx-style ``G.edges[u, v]`` -> edge attrs (first match, either direction)."""
        u, v = pair
        self._s._ensure_cache()
        for a, b, attrs in self._s._esorted:
            if (a == u and b == v) or (a == v and b == u):
                return attrs
        raise KeyError(pair)


class _DegreeView:
    """Mimics nx ``G.degree``: callable() -> items, callable(n) -> int."""

    def __init__(self, store: "GraphStore"):
        self._s = store

    def __call__(self, nbunch=None):
        degs = self._s._degree_map()
        if nbunch is None:
            return list(degs.items())
        if isinstance(nbunch, (str, bytes)):
            return degs.get(nbunch, 0)
        return [(n, degs.get(n, 0)) for n in nbunch]

    def __getitem__(self, node_id):
        return self._s._degree_map().get(node_id, 0)


class _SubgraphView:
    """Lightweight subgraph supporting the operations cohesion scoring needs."""

    def __init__(self, store: "GraphStore", node_ids):
        self._s = store
        self._ids = set(node_ids)

    def number_of_nodes(self):
        return len(self._ids)

    def number_of_edges(self):
        self._s._ensure_cache()
        return sum(1 for u, v, _ in self._s._esorted if u in self._ids and v in self._ids)

    def is_directed(self):
        return self._s.directed

    def to_undirected(self, as_view: bool = False):
        return self

    def neighbors(self, node_id):
        self._s._ensure_cache()
        out = set()
        for u, v, _ in self._s._esorted:
            if u not in self._ids or v not in self._ids:
                continue
            if u == node_id:
                out.add(v)
            elif v == node_id:
                out.add(u)
        return iter(sorted(out))

    def louvain_partition(self, resolution: float = 1.0) -> dict:
        self._s._ensure_cache()
        edges = [
            [u, v, float(a.get("weight", 1.0) or 1.0)]
            for u, v, a in self._s._esorted
            if u in self._ids and v in self._ids
        ]
        return self._s.run_louvain(edges, resolution)

    def nodes(self, data=False):
        self._s._ensure_cache()
        ids = sorted(self._ids)
        if data:
            return iter([(n, self._s._ncache.get(n, {})) for n in ids])
        return iter(ids)

    def edges(self, data=False):
        self._s._ensure_cache()
        rows = [(u, v, a) for u, v, a in self._s._esorted if u in self._ids and v in self._ids]
        if data:
            return iter([(u, v, dict(a)) for u, v, a in rows])
        return iter([(u, v) for u, v, _ in rows])


class MemGraph:
    """In-memory read-only graph with the same view API as GraphStore.

    Used for transient derived graphs (e.g. context-filtered subgraphs) that
    must not touch FalkorDB. Built from explicit node/edge lists.
    """

    def __init__(self, nodes, edges, directed: bool = True):
        # nodes: iterable of (id, attrs); edges: iterable of (u, v, attrs)
        self._ncache = {nid: dict(a) for nid, a in nodes}
        self._nsorted = sorted(self._ncache.keys(), key=str)
        self._esorted = [(u, v, dict(a)) for u, v, a in edges]
        self._esorted.sort(key=lambda e: (str(e[0]), str(e[1]), json.dumps(e[2], sort_keys=True, default=str)))
        self.directed = directed
        self._degmap = None
        self.graph: dict = {}

    def _ensure_cache(self):
        return

    def _degree_map(self):
        if self._degmap is None:
            degs = {nid: 0 for nid in self._ncache}
            for u, v, _ in self._esorted:
                degs[u] = degs.get(u, 0) + 1
                degs[v] = degs.get(v, 0) + 1
            self._degmap = degs
        return self._degmap

    # views
    nodes = property(lambda self: _NodeView(self))
    edges = property(lambda self: _EdgeView(self))
    degree = property(lambda self: _DegreeView(self))

    def is_directed(self):
        return self.directed

    def is_multigraph(self):
        return False

    def to_undirected(self, as_view: bool = False):
        return self

    def number_of_nodes(self):
        return len(self._ncache)

    def number_of_edges(self):
        return len(self._esorted)

    def __contains__(self, node_id):
        return node_id in self._ncache

    def __iter__(self):
        return iter(self._nsorted)

    def __len__(self):
        return len(self._ncache)

    def __getitem__(self, node_id):
        adj: dict = {}
        for u, v, a in self._esorted:
            if u == node_id:
                adj.setdefault(v, a)
            elif v == node_id:
                adj.setdefault(u, a)
        return adj

    def has_node(self, node_id):
        return node_id in self._ncache

    def has_edge(self, u, v):
        for a, b, _ in self._esorted:
            if (a == u and b == v) or (a == v and b == u):
                return True
        return False

    def has_directed_edge(self, u, v):
        return any(a == u and b == v for a, b, _ in self._esorted)

    def neighbors(self, node_id):
        out = set()
        for u, v, _ in self._esorted:
            if u == node_id:
                out.add(v)
            elif v == node_id:
                out.add(u)
        return iter(sorted(out))

    def successors(self, node_id):
        return iter(sorted({v for u, v, _ in self._esorted if u == node_id}))

    def predecessors(self, node_id):
        return iter(sorted({u for u, v, _ in self._esorted if v == node_id}))

    def in_edges(self, node_id, data=False):
        rows = [(u, v, a) for u, v, a in self._esorted if v == node_id]
        if data:
            return [(u, v, dict(a)) for u, v, a in rows]
        return [(u, v) for u, v, _ in rows]

    def subgraph(self, node_ids):
        return _SubgraphView(self, node_ids)

    def shortest_path(self, src, tgt, max_hops: int = 8):
        from collections import deque

        if src not in self._ncache or tgt not in self._ncache:
            return None
        adj: dict = {}
        for u, v, _ in self._esorted:
            adj.setdefault(u, set()).add(v)
            adj.setdefault(v, set()).add(u)
        prev = {src: None}
        q = deque([(src, 0)])
        while q:
            node, d = q.popleft()
            if node == tgt:
                path = []
                while node is not None:
                    path.append(node)
                    node = prev[node]
                return list(reversed(path))
            if d >= max_hops:
                continue
            for nb in sorted(adj.get(node, ())):
                if nb not in prev:
                    prev[nb] = node
                    q.append((nb, d + 1))
        return None


# ---------------------------------------------------------------------------
# Cache-free views for GraphStore: every access is a live FalkorDB query or a
# paginated stream. The graph is NEVER materialized in Python — the store holds
# no node/edge data, only a connection.
# ---------------------------------------------------------------------------
class _SNodeView:
    def __init__(self, s):
        self._s = s

    def __call__(self, data=False):
        return self._s._iter_nodes(data=data)

    def __iter__(self):
        return self._s._iter_nodes(data=False)

    def __getitem__(self, nid):
        return self._s._node_attrs(nid)  # raises KeyError if absent

    def __contains__(self, nid):
        return self._s.has_node(nid)

    def __len__(self):
        return self._s.number_of_nodes()

    def get(self, nid, default=None):
        try:
            return self._s._node_attrs(nid)
        except KeyError:
            return default


class _SEdgeView:
    def __init__(self, s):
        self._s = s

    def __call__(self, nbunch=None, data=False):
        return self._s._iter_edges(nbunch=nbunch, data=data)

    def __iter__(self):
        return self._s._iter_edges(nbunch=None, data=False)

    def __getitem__(self, pair):
        u, v = pair
        d = self._s._edge_attrs(u, v)
        if d is None:
            raise KeyError(pair)
        return d


class _SDegreeView:
    def __init__(self, s):
        self._s = s

    def __call__(self, nbunch=None):
        if nbunch is None:
            return list(self._s._iter_degrees())
        if isinstance(nbunch, (str, bytes)):
            return self._s._degree_one(nbunch)
        return [(n, self._s._degree_one(n)) for n in nbunch]

    def __getitem__(self, nid):
        return self._s._degree_one(nid)


class _SStoreSubgraph:
    """Subgraph restricted to a node-id set; all ops run as scoped queries."""

    def __init__(self, store, node_ids):
        self._s = store
        self._ids = list(node_ids)

    def number_of_nodes(self):
        return len(self._ids)

    def number_of_edges(self):
        if not self._ids:
            return 0
        return self._s._rows(
            "MATCH (a:Entity)-[r]-(b:Entity) WHERE a.id IN $ids AND b.id IN $ids "
            "AND id(a) < id(b) RETURN count(r)",
            {"ids": self._ids}, timeout=_QUERY_TIMEOUT_MS,
        )[0][0]

    def louvain_partition(self, resolution: float = 1.0) -> dict:
        if not self._ids:
            return {}
        edges = self._s._rows(
            "MATCH (a:Entity)-[r]->(b:Entity) WHERE a.id IN $ids AND b.id IN $ids "
            "RETURN a.id, b.id, coalesce(r.weight, 1.0)",
            {"ids": self._ids}, timeout=_QUERY_TIMEOUT_MS,
        )
        return self._s.run_louvain([[str(u), str(v), float(w)] for u, v, w in edges], resolution)

    def is_directed(self):
        return self._s.directed

    def to_undirected(self, as_view: bool = False):
        return self


class GraphStore:
    """A named FalkorDB graph with a NetworkX-shaped API.

    Holds NO graph data in Python — the graph lives in FalkorDB. Every read is a
    scoped query or a paginated stream; nothing is cached/materialized.
    """

    def __init__(
        self,
        graph_name: str = "graphify",
        uri: str = DEFAULT_URI,
        *,
        user: str | None = None,
        password: str | None = None,
        directed: bool = True,
    ):
        self.graph_name = graph_name
        self.uri = uri
        self.directed = directed
        self._db = _connect(uri, user, password)
        self._g = self._db.select_graph(graph_name)
        p = urlparse(uri if "://" in uri else "redis://" + uri)
        self._server_key = f"{p.hostname}:{p.port or 6379}"
        self.graph: dict = {}  # graph-level metadata only (hyperedges) — NOT the graph
        self._ensure_resultset_size()
        self._ensure_schema()
        # UDFs (louvain/edgeBetweenness/simpleCycles) are loaded lazily by the
        # algorithm wrappers that need them — not here — so interactive commands
        # (query/path/explain/affected) don't pay a UDF reload on every process.
        self._load_meta()

    # ---- views (nx-compatible, cache-free: each access is a live query) -----
    @property
    def nodes(self):
        return _SNodeView(self)

    @property
    def edges(self):
        return _SEdgeView(self)

    @property
    def degree(self):
        return _SDegreeView(self)

    # ---- streaming + scoped read helpers (no materialization) ---------------
    def _stream(self, match_return: str, order_by: str, params: dict | None = None):
        """Yield rows page-by-page (only one page in memory at a time)."""
        skip = 0
        while True:
            rows = self._rows(
                f"{match_return} ORDER BY {order_by} SKIP {skip} LIMIT {_PAGE}",
                params, timeout=_QUERY_TIMEOUT_MS,
            )
            for r in rows:
                yield r
            if len(rows) < _PAGE:
                break
            skip += _PAGE

    def _iter_nodes(self, data=False):
        for r in self._stream("MATCH (n:Entity) RETURN n.id, properties(n)", "id(n)"):
            if data:
                d = dict(r[1]); d.pop(_META_KEY, None)
                yield (r[0], d)
            else:
                yield r[0]

    def _iter_edges(self, nbunch=None, data=False):
        if nbunch is None:
            gen = self._stream("MATCH (a:Entity)-[r]->(b:Entity) RETURN a.id, b.id, properties(r)", "id(r)")
        else:
            ids = [nbunch] if isinstance(nbunch, (str, bytes)) else list(nbunch)
            gen = self._stream(
                "MATCH (a:Entity)-[r]->(b:Entity) WHERE a.id IN $ids OR b.id IN $ids "
                "RETURN a.id, b.id, properties(r)", "id(r)", {"ids": ids},
            )
        for r in gen:
            if data:
                yield (r[0], r[1], dict(r[2]))
            else:
                yield (r[0], r[1])

    def _iter_degrees(self):
        for r in self._stream("MATCH (n:Entity) RETURN n.id, size((n)--())", "id(n)"):
            yield (r[0], int(r[1]))

    def _node_attrs(self, nid):
        rows = self._rows("MATCH (n:Entity {id:$id}) RETURN properties(n)", {"id": nid}, timeout=_QUERY_TIMEOUT_MS)
        if not rows:
            raise KeyError(nid)
        d = dict(rows[0][0]); d.pop(_META_KEY, None)
        return d

    def _edge_attrs(self, u, v):
        rows = self._rows(
            "MATCH (a:Entity {id:$u})-[r]-(b:Entity {id:$v}) RETURN properties(r) LIMIT 1",
            {"u": u, "v": v}, timeout=_QUERY_TIMEOUT_MS,
        )
        return dict(rows[0][0]) if rows else None

    def _degree_one(self, nid):
        rows = self._rows(
            "MATCH (n:Entity {id:$id}) OPTIONAL MATCH (n)-[r]-() RETURN count(r)",
            {"id": nid}, timeout=_QUERY_TIMEOUT_MS,
        )
        return rows[0][0] if rows else 0

    # ---- low-level helpers --------------------------------------------------
    def query(self, cypher: str, params: dict | None = None, timeout: int | None = None):
        if timeout is not None:
            return self._g.query(cypher, params or {}, timeout=timeout)
        return self._g.query(cypher, params or {})

    def _rows(self, cypher: str, params: dict | None = None, timeout: int | None = None) -> list:
        return self.query(cypher, params, timeout=timeout).result_set

    def _ensure_resultset_size(self) -> None:
        """Raise the row cap and query timeouts so large-graph reads aren't
        silently truncated (RESULTSET_SIZE) or killed (TIMEOUT)."""
        with _udf_lock:
            if self._server_key in _server_configured:
                return
            for key, val in (
                ("RESULTSET_SIZE", _RESULTSET_SIZE),
                ("TIMEOUT_DEFAULT", _QUERY_TIMEOUT_MS),
                ("TIMEOUT_MAX", _QUERY_TIMEOUT_MS),
            ):
                try:
                    self._db.connection.execute_command("GRAPH.CONFIG", "SET", key, str(val))
                except Exception:
                    pass  # managed server may forbid it; per-query timeout + pagination cover us
            _server_configured.add(self._server_key)

    def _ensure_schema(self) -> None:
        try:
            self._g.query("CREATE INDEX FOR (n:Entity) ON (n.id)")
        except Exception:
            pass

    def _ensure_udfs(self) -> None:
        with _udf_lock:
            if self._server_key in _udf_loaded_servers:
                return
            src = _UDF_SRC.read_text()
            try:
                self._db.connection.execute_command("GRAPH.UDF", "LOAD", "REPLACE", _UDF_LIB, src)
            except Exception:
                try:
                    self._db.connection.execute_command("GRAPH.UDF", "LOAD", _UDF_LIB, src)
                except Exception:
                    pass
            _udf_loaded_servers.add(self._server_key)

    def _invalidate(self) -> None:
        # No cache to invalidate — the store holds no graph data. Kept as a no-op
        # so mutation methods don't need to special-case it.
        return

    # ---- graph-level metadata ----------------------------------------------
    def _load_meta(self) -> None:
        try:
            rows = self._rows("MATCH (m:GraphMeta {key:$k}) RETURN m.data", {"k": _META_KEY})
            if rows and rows[0][0]:
                self.graph = json.loads(rows[0][0])
        except Exception:
            self.graph = {}

    def save_meta(self) -> None:
        """Persist the in-memory `.graph` dict (hyperedges etc.) to FalkorDB."""
        payload = json.dumps({k: v for k, v in self.graph.items() if not k.startswith("_")}, default=str)
        self._g.query(
            "MERGE (m:GraphMeta {key:$k}) SET m.data = $d", {"k": _META_KEY, "d": payload}
        )

    # ---- lifecycle ----------------------------------------------------------
    def clear(self) -> None:
        try:
            self._g.delete()
        except Exception:
            pass
        self._g = self._db.select_graph(self.graph_name)
        self.graph = {}
        self._invalidate()
        self._ensure_schema()

    def __getitem__(self, node_id):
        """Adjacency access: ``G[u]`` -> {neighbor_id: edge_attrs} (both directions), scoped."""
        rows = self._rows(
            "MATCH (n:Entity {id:$id})-[r]-(m:Entity) RETURN m.id, properties(r)",
            {"id": node_id}, timeout=_QUERY_TIMEOUT_MS,
        )
        adj: dict = {}
        for mid, props in rows:
            adj.setdefault(mid, dict(props))
        return adj

    def __contains__(self, node_id):
        return self.has_node(node_id)

    def __iter__(self):
        return self._iter_nodes(data=False)

    def __len__(self):
        return self.number_of_nodes()

    def is_directed(self) -> bool:
        return self.directed

    def is_multigraph(self) -> bool:
        return False

    def to_undirected(self, as_view: bool = False):
        return self

    def copy(self):
        return self

    # ---- construction (batched) --------------------------------------------
    _BATCH = 1000

    def add_nodes_from(self, rows, *, fresh: bool = False) -> None:
        """Bulk-upsert nodes. When ``fresh`` (graph known empty/just cleared, ids
        unique) use CREATE — it skips MERGE's existence check and is several times
        faster on a from-scratch build."""
        by_label: dict[str, list[dict]] = {}
        materialized = []
        for item in rows:
            if isinstance(item, tuple):
                node_id, attrs = item
            else:
                node_id, attrs = item, {}
            props = _scalar_props(attrs)
            props["id"] = node_id
            # _origin (AST provenance) is the one underscore-marker that must
            # survive into the store: incremental rebuild reads it back from
            # graph.json to evict stale AST symbols removed from a surviving
            # file (#1116). Other _-prefixed keys stay dropped.
            if isinstance(attrs.get("_origin"), str):
                props["_origin"] = attrs["_origin"]
            ftype = _safe_label(str(attrs.get("file_type", "Entity")).capitalize())
            by_label.setdefault(ftype, []).append(props)
            materialized.append(1)
        for ftype, batch in by_label.items():
            verb = f"CREATE (n:Entity:{ftype})" if fresh else f"MERGE (n:Entity {{id: row.id}}) SET n:{ftype}"
            for i in range(0, len(batch), self._BATCH):
                chunk = batch[i : i + self._BATCH]
                self._g.query(f"UNWIND $rows AS row {verb} SET n += row", {"rows": chunk})
        if materialized:
            self._invalidate()

    def add_node(self, node_id: str, **attrs) -> None:
        self.add_nodes_from([(node_id, attrs)])

    def add_edges_from(self, rows, *, fresh: bool = False) -> None:
        """Bulk-upsert edges. When ``fresh`` use CREATE instead of MERGE (no
        edge-existence check) — endpoints must already exist."""
        by_rel: dict[str, list[dict]] = {}
        for u, v, attrs in rows:
            rel = _safe_rel(str(attrs.get("relation", "RELATED_TO")))
            props = _scalar_props(attrs)
            props.setdefault("relation", attrs.get("relation", rel))
            by_rel.setdefault(rel, []).append({"src": u, "tgt": v, "props": props})
        for rel, batch in by_rel.items():
            verb = "CREATE" if fresh else "MERGE"
            for i in range(0, len(batch), self._BATCH):
                chunk = batch[i : i + self._BATCH]
                self._g.query(
                    f"UNWIND $rows AS row MATCH (a:Entity {{id: row.src}}), (b:Entity {{id: row.tgt}}) "
                    f"{verb} (a)-[r:{rel}]->(b) SET r += row.props",
                    {"rows": chunk},
                )
        self._invalidate()

    def add_edge(self, u: str, v: str, **attrs) -> None:
        self.add_edges_from([(u, v, attrs)])

    # ---- mutation -----------------------------------------------------------
    def remove_nodes(self, node_ids) -> None:
        ids = list(node_ids)
        if not ids:
            return
        self._g.query("UNWIND $ids AS nid MATCH (n:Entity {id: nid}) DETACH DELETE n", {"ids": ids})
        self._invalidate()

    remove_nodes_from = remove_nodes

    def remove_node(self, node_id: str) -> None:
        self.remove_nodes([node_id])

    def remove_edges(self, pairs) -> None:
        rows = [{"src": u, "tgt": v} for u, v in pairs]
        if not rows:
            return
        self._g.query(
            "UNWIND $rows AS row MATCH (a:Entity {id: row.src})-[r]-(b:Entity {id: row.tgt}) DELETE r",
            {"rows": rows},
        )
        self._invalidate()

    remove_edges_from = remove_edges

    def remove_edge(self, u: str, v: str) -> None:
        self.remove_edges([(u, v)])

    def has_node(self, node_id: str) -> bool:
        return bool(self._rows("MATCH (n:Entity {id:$id}) RETURN 1 LIMIT 1", {"id": node_id}))

    def has_edge(self, u: str, v: str) -> bool:
        return bool(self._rows(
            "MATCH (a:Entity {id:$u})-[]-(b:Entity {id:$v}) RETURN 1 LIMIT 1", {"u": u, "v": v}))

    def has_directed_edge(self, u: str, v: str) -> bool:
        """True only if an edge is stored in the u -> v orientation."""
        return bool(self._rows(
            "MATCH (a:Entity {id:$u})-[]->(b:Entity {id:$v}) RETURN 1 LIMIT 1", {"u": u, "v": v}))

    def number_of_nodes(self) -> int:
        # count() is uncapped and cheap — independent of the read cache.
        return self._rows("MATCH (n:Entity) RETURN count(n)")[0][0]

    def number_of_edges(self) -> int:
        return self._rows("MATCH (:Entity)-[r]->(:Entity) RETURN count(r)")[0][0]

    def neighbors(self, node_id: str):
        rows = self._rows(
            "MATCH (n:Entity {id:$id})-[]-(m:Entity) RETURN DISTINCT m.id",
            {"id": node_id}, timeout=_QUERY_TIMEOUT_MS,
        )
        return iter(sorted(str(r[0]) for r in rows))

    def in_edges(self, node_id: str, data: bool = False):
        rows = self._rows(
            "MATCH (s:Entity)-[r]->(n:Entity {id:$id}) RETURN s.id, properties(r)",
            {"id": node_id}, timeout=_QUERY_TIMEOUT_MS,
        )
        rows.sort(key=lambda r: str(r[0]))
        if data:
            return [(str(s), node_id, dict(p)) for s, p in rows]
        return [(str(s), node_id) for s, _ in rows]

    def successors(self, node_id: str):
        """Outgoing neighbors (directed), sorted."""
        rows = self._rows("MATCH (n:Entity {id:$id})-[]->(m:Entity) RETURN DISTINCT m.id", {"id": node_id})
        return iter(sorted(str(r[0]) for r in rows))

    def predecessors(self, node_id: str):
        """Incoming neighbors (directed), sorted."""
        rows = self._rows("MATCH (m:Entity)-[]->(n:Entity {id:$id}) RETURN DISTINCT m.id", {"id": node_id})
        return iter(sorted(str(r[0]) for r in rows))

    def subgraph(self, node_ids):
        return _SStoreSubgraph(self, node_ids)

    def set_communities(self, communities: dict) -> None:
        """Persist community ids onto nodes: {cid: [node_ids]} -> n.community."""
        rows = []
        for cid, node_ids in communities.items():
            for nid in node_ids:
                rows.append({"id": nid, "c": int(cid)})
        if not rows:
            return
        for i in range(0, len(rows), self._BATCH):
            chunk = rows[i : i + self._BATCH]
            self._g.query(
                "UNWIND $rows AS row MATCH (n:Entity {id: row.id}) SET n.community = row.c",
                {"rows": chunk},
            )
        self._invalidate()

    def prune_repo(self, repo_tag: str) -> int:
        before = self.number_of_nodes()
        self._g.query("MATCH (n:Entity {repo: $t}) DETACH DELETE n", {"t": repo_tag})
        self._invalidate()
        return before - self.number_of_nodes()

    # ---- algorithms ---------------------------------------------------------
    def shortest_path(self, src: str, tgt: str, max_hops: int = 8):
        """Undirected shortest path via level-batched BFS in the engine — one
        query per BFS level expanding the whole frontier (not the whole graph).
        Avoids algo.SPpaths (pathologically slow undirected) and never loads the
        graph into Python."""
        if src == tgt:
            return [src] if self.has_node(src) else None
        prev = {src: None}
        frontier = [src]
        for _ in range(int(max_hops)):
            if not frontier:
                break
            rows = self._rows(
                "UNWIND $f AS fid MATCH (n:Entity {id: fid})-[]-(m:Entity) RETURN fid, m.id",
                {"f": frontier}, timeout=_QUERY_TIMEOUT_MS,
            )
            nxt = []
            for fid, mid in sorted(rows, key=lambda r: (str(r[0]), str(r[1]))):
                if mid in prev:
                    continue
                prev[mid] = fid
                if mid == tgt:
                    path = [mid]
                    while path[-1] is not None:
                        path.append(prev[path[-1]])
                    return list(reversed(path[:-1]))
                nxt.append(mid)
            frontier = nxt
        return None

    _RENDER_COLS = "n.label, n.source_file, n.source_location, n.community"

    def subgraph_render_data(self, node_ids, edge_pairs, *, limit=None, seeds=None):
        """Fetch node attrs+degree and edge attrs for a subgraph, for rendering
        query/path results. Returns ``(nodes, eattrs, total)`` where ``total`` is
        the full node count.

        When ``limit`` is set and the subgraph is larger, only the top-``limit``
        nodes by degree (plus ``seeds``, always kept) are fetched — the engine
        ranks+truncates so a hub query never pulls attributes for tens of
        thousands of nodes just to discard all but the slice the caller's token
        budget can show. Edges are fetched only among the kept nodes."""
        ids = list(node_ids)
        total = len(ids)
        nodes: dict = {}

        def _absorb(rows):
            for r in rows:
                nodes[r[0]] = {"label": r[1], "source_file": r[2], "source_location": r[3],
                               "community": r[4], "degree": int(r[5])}

        if ids and (limit is None or total <= limit):
            _absorb(self._rows(
                f"UNWIND $ids AS i MATCH (n:Entity {{id: i}}) "
                f"RETURN i, {self._RENDER_COLS}, size((n)--())",
                {"ids": ids}, timeout=_QUERY_TIMEOUT_MS,
            ))
        elif ids:
            # Seeds are always kept (rendered first); the rest are ranked by
            # degree in-engine and truncated to fill out the limit.
            id_set = set(ids)
            seed_list = [s for s in (seeds or []) if s in id_set]
            if seed_list:
                _absorb(self._rows(
                    f"UNWIND $ids AS i MATCH (n:Entity {{id: i}}) "
                    f"RETURN i, {self._RENDER_COLS}, size((n)--())",
                    {"ids": seed_list}, timeout=_QUERY_TIMEOUT_MS,
                ))
            k = max(0, limit - len(nodes))
            others = [i for i in ids if i not in nodes]
            if k and others:
                _absorb(self._rows(
                    f"UNWIND $ids AS i MATCH (n:Entity {{id: i}}) "
                    f"WITH n, size((n)--()) AS deg ORDER BY deg DESC LIMIT $k "
                    f"RETURN n.id, {self._RENDER_COLS}, deg",
                    {"ids": others, "k": k}, timeout=_QUERY_TIMEOUT_MS,
                ))

        eattrs: dict = {}
        pairs = [[u, v] for u, v in edge_pairs if u in nodes and v in nodes]
        if pairs:
            for u, v, rel, conf, ctx in self._rows(
                "UNWIND $pairs AS p MATCH (a:Entity {id: p[0]})-[r]-(b:Entity {id: p[1]}) "
                "RETURN p[0], p[1], r.relation, r.confidence, r.context",
                {"pairs": pairs}, timeout=_QUERY_TIMEOUT_MS,
            ):
                eattrs.setdefault((u, v), {"relation": rel, "confidence": conf, "context": ctx})
        return nodes, eattrs, total

    def node_detail(self, node_id: str):
        """(attrs, degree) for one node, in one scoped query. None if absent."""
        rows = self._rows(
            "MATCH (n:Entity {id:$id}) RETURN properties(n), size((n)--())",
            {"id": node_id}, timeout=_QUERY_TIMEOUT_MS,
        )
        if not rows:
            return None
        attrs = dict(rows[0][0])
        attrs.pop(_META_KEY, None)
        return attrs, int(rows[0][1])

    def node_connections(self, node_id: str) -> list[dict]:
        """All edges incident to a node (both directions) with neighbor label +
        degree + relation/confidence — one scoped query, no full-graph load."""
        rows = self._rows(
            "MATCH (n:Entity {id:$id})-[r]->(m:Entity) "
            "RETURN 'out' AS dir, m.id AS mid, m.label AS mlabel, r.relation AS rel, "
            "r.confidence AS conf, size((m)--()) AS mdeg "
            "UNION ALL "
            "MATCH (n:Entity {id:$id})<-[r]-(m:Entity) "
            "RETURN 'in' AS dir, m.id AS mid, m.label AS mlabel, r.relation AS rel, "
            "r.confidence AS conf, size((m)--()) AS mdeg",
            {"id": node_id}, timeout=_QUERY_TIMEOUT_MS,
        )
        return [
            {"dir": r[0], "id": r[1], "label": r[2] or r[1], "relation": r[3] or "",
             "confidence": r[4] or "", "degree": int(r[5])}
            for r in rows
        ]

    def search_nodes(self, terms) -> list[dict]:
        """Candidate nodes whose norm_label / id / source_file contains any term.
        This is the in-engine prefilter for query/explain — only nodes that could
        score > 0 are returned, so Python scores a small set, never the whole graph."""
        terms = [t for t in terms if t]
        if not terms:
            return []
        conds, params = [], {}
        for i, t in enumerate(terms):
            params[f"t{i}"] = t
            # coalesce: graphs built without a stored norm_label (e.g. test fixtures)
            # still match on the lowercased label.
            conds.append(
                f"(coalesce(n.norm_label, toLower(n.label)) CONTAINS $t{i} "
                f"OR toLower(n.id) CONTAINS $t{i} OR toLower(n.source_file) CONTAINS $t{i})"
            )
        rows = self._rows(
            f"MATCH (n:Entity) WHERE {' OR '.join(conds)} "
            "RETURN n.id, n.label, n.norm_label, n.source_file",
            params, timeout=_QUERY_TIMEOUT_MS,
        )
        return [
            {"id": r[0], "label": r[1] or "", "norm_label": r[2] or "", "source_file": r[3] or ""}
            for r in rows
        ]

    def doc_freqs(self, terms) -> dict:
        """{term: number of nodes whose norm_label contains term} — for IDF, in-engine."""
        out = {}
        for t in terms:
            if not t:
                continue
            out[t] = self._rows(
                "MATCH (n:Entity) WHERE n.norm_label CONTAINS $t RETURN count(n)",
                {"t": t}, timeout=_QUERY_TIMEOUT_MS,
            )[0][0]
        return out

    def confidence_counts(self) -> dict:
        """{confidence_label: edge_count} over all edges — one in-engine aggregation
        (so graph_stats/audit never stream every edge into Python)."""
        rows = self._rows(
            "MATCH (:Entity)-[r]->(:Entity) "
            "RETURN coalesce(r.confidence, 'EXTRACTED'), count(r)",
            timeout=_QUERY_TIMEOUT_MS,
        )
        return {str(k): int(v) for k, v in rows}

    def find_node_ids(self, *, label=None, source_file=None, label_contains=None, limit=None) -> list:
        """Scoped node lookup by exact label / exact source_file / label substring."""
        if label is not None:
            q, v = "MATCH (n:Entity) WHERE toLower(n.label) = $v RETURN n.id", label.lower()
        elif source_file is not None:
            q, v = "MATCH (n:Entity) WHERE toLower(n.source_file) = $v RETURN n.id", source_file.lower()
        else:
            q, v = "MATCH (n:Entity) WHERE toLower(n.label) CONTAINS $v RETURN n.id", label_contains.lower()
        if limit:
            q += f" LIMIT {int(limit)}"
        return [r[0] for r in self._rows(q, {"v": v}, timeout=_QUERY_TIMEOUT_MS)]

    def incoming_edges(self, frontier_ids, relations) -> list:
        """All (frontier_id, src_id, relation) incoming edges for a frontier whose
        relation is in `relations` — one query for the whole frontier level."""
        if not frontier_ids:
            return []
        return self._rows(
            "UNWIND $f AS fid MATCH (src:Entity)-[r]->(n:Entity {id: fid}) "
            "WHERE r.relation IN $rels RETURN fid, src.id, r.relation",
            {"f": list(frontier_ids), "rels": list(relations)},
            timeout=_QUERY_TIMEOUT_MS,
        )

    def node_attrs_batch(self, ids) -> dict:
        """Fetch properties for many node ids in one query."""
        ids = list(ids)
        if not ids:
            return {}
        rows = self._rows(
            "UNWIND $ids AS i MATCH (n:Entity {id: i}) RETURN i, properties(n)",
            {"ids": ids},
            timeout=_QUERY_TIMEOUT_MS,
        )
        return {r[0]: dict(r[1]) for r in rows}

    def top_degree_nodes(self, limit: int = 500) -> list[dict]:
        """Top-N nodes by (undirected) degree, computed in-engine. Returns only
        `limit` rows with the attrs god_nodes needs — no full-graph load."""
        rows = self._rows(
            "MATCH (n:Entity) WITH n, size((n)--()) AS deg "
            "RETURN n.id, n.label, n.source_file, deg ORDER BY deg DESC LIMIT $lim",
            {"lim": int(limit)},
            timeout=_QUERY_TIMEOUT_MS,
        )
        return [
            {"id": r[0], "label": r[1] or "", "source_file": r[2] or "", "degree": int(r[3])}
            for r in rows
        ]

    def stream_full_edges(self):
        """Stream edges with endpoint label/source/degree + relation/confidence so
        surprise analysis needs no per-edge node lookups. Page-at-a-time, no load."""
        for r in self._stream(
            "MATCH (a:Entity)-[r]->(b:Entity) "
            "WITH a, b, r, size((a)--()) AS da, size((b)--()) AS db "
            "RETURN a.id, a.label, a.source_file, da, b.id, b.label, b.source_file, db, "
            "r.relation, r.confidence", "id(r)",
        ):
            yield {
                "u": r[0], "u_label": r[1] or "", "u_source": r[2] or "", "u_deg": int(r[3]),
                "v": r[4], "v_label": r[5] or "", "v_source": r[6] or "", "v_deg": int(r[7]),
                "relation": r[8] or "", "confidence": r[9] or "EXTRACTED",
            }

    def node_betweenness(self) -> dict:
        # Scope to :Entity so the internal :GraphMeta bookkeeping node (which has
        # no id and no edges) never leaks in as a phantom "None" key.
        rows = self._rows("CALL algo.betweenness() YIELD node, score WHERE node:Entity RETURN node.id, score", timeout=_QUERY_TIMEOUT_MS)
        return {str(nid): float(s) for nid, s in rows}

    def _all_weighted_edges(self):
        # Transient marshaling for the Louvain UDF param (the UDF can't read edges
        # itself). Streamed page-by-page; not retained as a cache.
        return [
            [r[0], r[1], float(r[2] if r[2] is not None else 1.0)]
            for r in self._stream(
                "MATCH (a:Entity)-[r]->(b:Entity) RETURN a.id, b.id, coalesce(r.weight, 1.0)", "id(r)")
        ]

    def run_louvain(self, edges, resolution: float = 1.0) -> dict:
        """Run the Louvain UDF over an explicit weighted edge list."""
        if not edges:
            return {}
        self._ensure_udfs()
        rows = self._rows(f"RETURN {_UDF_LIB}.louvain($e, $res)", {"e": edges, "res": resolution}, timeout=_QUERY_TIMEOUT_MS)
        return {str(k): int(v) for k, v in dict(rows[0][0]).items()}

    def louvain_partition(self, resolution: float = 1.0) -> dict:
        edges = self._all_weighted_edges()
        if not edges:
            return {nid: i for i, nid in enumerate(self.nodes)}
        return self.run_louvain(edges, resolution)

    def edge_betweenness(self) -> dict:
        edges = [[r[0], r[1]] for r in self._stream(
            "MATCH (a:Entity)-[r]->(b:Entity) RETURN a.id, b.id", "id(r)")]
        if not edges:
            return {}
        self._ensure_udfs()
        res = self._rows(f"RETURN {_UDF_LIB}.edgeBetweenness($e)", {"e": edges}, timeout=_QUERY_TIMEOUT_MS)
        out: dict = {}
        for key, score in dict(res[0][0]).items():
            u, v = key.split("\t", 1)
            out[(u, v)] = float(score)
        return out

    def simple_cycles(self, edges, max_len: int = 5):
        payload = [[str(u), str(v), 1.0] for u, v in edges]
        if not payload:
            return []
        self._ensure_udfs()
        rows = self._rows(f"RETURN {_UDF_LIB}.simpleCycles($e, $n)", {"e": payload, "n": int(max_len)}, timeout=_QUERY_TIMEOUT_MS)
        return [[str(x) for x in cyc] for cyc in rows[0][0]]

    # ---- traversal (hub-capped, level-batched in the engine) ----------------
    def _hub_threshold(self) -> int:
        # Graph-level constant (p99 of the degree distribution). Computing it scans
        # every node's degree (~0.4s), so cache it in graph metadata and reuse it
        # across query invocations. Cleared automatically on rebuild (clear() drops
        # the GraphMeta node); SET-only ops like community labels don't change it.
        cached = self.graph.get("hub_threshold")
        if cached is not None:
            return int(cached)
        rows = self._rows(
            "MATCH (n:Entity) WITH size((n)--()) AS d RETURN percentileDisc(d, 0.99)",
            timeout=_QUERY_TIMEOUT_MS,
        )
        p99 = rows[0][0] if rows and rows[0][0] is not None else 0
        hub = max(50, int(p99))
        self.graph["hub_threshold"] = hub
        try:
            self.save_meta()
        except Exception:
            pass
        return hub

    def bfs(self, seeds, depth, hub_threshold=None, contexts=None):
        return self._traverse(seeds, depth, hub_threshold, contexts)

    def dfs(self, seeds, depth, hub_threshold=None, contexts=None):
        # Depth-bounded neighborhood is gathered the same way; results are
        # relevance-ranked downstream, so DFS vs BFS ordering does not matter here.
        return self._traverse(seeds, depth, hub_threshold, contexts)

    def _traverse(self, seeds, depth, hub_threshold, contexts=None):
        """Hub-capped depth-bounded traversal — one query per level expanding the
        whole frontier in the engine (never loads the graph). When ``contexts`` is
        given, only edges whose ``context`` matches are followed (in-engine, so the
        graph is never copied into Python for context filtering)."""
        seeds = list(seeds)
        if hub_threshold is None:
            hub_threshold = self._hub_threshold()
        contexts = list(contexts) if contexts else None
        edge_match = "MATCH (n)-[r]-(m:Entity)"
        edge_where = " WHERE r.context IN $ctx" if contexts else ""
        seed_set = set(seeds)
        visited = set(seeds)
        edges_seen: list = []
        frontier = seeds
        for _ in range(depth):
            if not frontier:
                break
            params = {"f": frontier, "seeds": seeds, "hub": hub_threshold}
            if contexts:
                params["ctx"] = contexts
            rows = self._rows(
                "UNWIND $f AS fid MATCH (n:Entity {id: fid}) "
                "WITH fid, n, size((n)--()) AS deg "
                "WHERE fid IN $seeds OR deg < $hub "
                f"{edge_match}{edge_where} RETURN fid, m.id",
                params,
                timeout=_QUERY_TIMEOUT_MS,
            )
            nxt = []
            for fid, mid in sorted(rows, key=lambda r: (str(r[0]), str(r[1]))):
                if mid not in visited:
                    visited.add(mid)
                    edges_seen.append((fid, mid))
                    nxt.append(mid)
            frontier = nxt
        return visited, edges_seen
