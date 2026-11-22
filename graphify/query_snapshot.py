"""A disposable, read-only query projection of one published graph.json."""

from __future__ import annotations

from array import array
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import Literal, overload
from unicodedata import unidata_version

import networkx as nx

try:
    import sqlite3
except ImportError:  # A CPython build can omit the optional SQLite module.
    sqlite3 = None


# Bump when the persisted search text, label normalization, or row format changes.
_FORMAT = 2
_BATCH = 512
_GraphIdentity = tuple[int, int, int, int, int, str | None]
_SCHEMA = """
CREATE TABLE metadata (value TEXT NOT NULL);
CREATE TABLE nodes (position INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL,
                    payload TEXT NOT NULL, degree INTEGER NOT NULL);
CREATE TABLE search (position INTEGER PRIMARY KEY, label BLOB NOT NULL, text BLOB NOT NULL);
CREATE INDEX search_labels ON search(label);
CREATE TABLE postings (gram TEXT PRIMARY KEY, positions BLOB NOT NULL) WITHOUT ROWID;
CREATE TABLE edges (position INTEGER PRIMARY KEY, signature INTEGER NOT NULL, payload TEXT NOT NULL);
CREATE TABLE adjacency (node INTEGER, position INTEGER, neighbor INTEGER, edge INTEGER,
                        PRIMARY KEY(node,position)) WITHOUT ROWID;
CREATE TABLE context_degrees (signature INTEGER, node INTEGER, degree INTEGER,
                              PRIMARY KEY(signature,node)) WITHOUT ROWID;
"""


def _json(data):
    return json.dumps(data, ensure_ascii=True, separators=(",", ":"))


def _params(values):
    return ",".join("?" for _ in values)


def graph_identity(path: Path) -> _GraphIdentity | None:
    from graphify.build import legacy_id_source_prefix

    try:
        stat = path.stat()
    except OSError:
        return None
    return (
        stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns,
        legacy_id_source_prefix(path),
    )


def _cache_file(graph_path: Path, identity: _GraphIdentity) -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        root = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    try:
        release = version("graphifyy")
    except PackageNotFoundError:
        release = None
    scope = sha256(os.fsencode(graph_path)).hexdigest()
    generation = sha256(_json([_FORMAT, release, sys.byteorder, unidata_version, identity]).encode()).hexdigest()
    return root.resolve() / "graphify" / "query-snapshots" / scope / f"{generation}.sqlite3"


class SnapshotReadError(Exception):
    """A derived snapshot could not serve the request."""


def _usable_metadata(metadata) -> bool:
    if not isinstance(metadata, dict):
        return False
    for key in ("nodes", "edges", "hub"):
        value = metadata.get(key)
        if type(value) is not int or value < 0:
            return False
    signatures = metadata.get("signatures")
    return (
        isinstance(metadata.get("legacy"), bool)
        and isinstance(metadata.get("learning_overlay"), (dict, type(None)))
        and isinstance(signatures, list)
        and all(
            isinstance(pair, list) and len(pair) == 2
            and not any(isinstance(part, (list, dict)) for part in pair)
            for pair in signatures
        )
    )


def open_snapshot(graph_path: Path, identity: _GraphIdentity | None) -> QuerySnapshot | None:
    if sqlite3 is None or identity is None:
        return None
    db = None
    try:
        cached = _cache_file(graph_path, identity)
        if not cached.is_file():
            return None
        db = sqlite3.connect(cached.as_uri() + "?mode=ro&immutable=1", uri=True)
        db.execute("PRAGMA trusted_schema=OFF")
        row = db.execute("SELECT value FROM metadata").fetchone()
        metadata = json.loads(row[0]) if row else {}
        if (
            _usable_metadata(metadata) and metadata.get("format") == _FORMAT
            and metadata.get("identity") == list(identity) and graph_identity(graph_path) == identity
        ):
            return QuerySnapshot(db, metadata)
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, RuntimeError):
        pass
    if db is not None:
        db.close()
    return None


def write_snapshot(graph_path: Path, identity: _GraphIdentity, graph, legacy: bool, *, repair: bool = False) -> None:
    """Build a generation in private storage and publish the completed file atomically."""
    if (
        sqlite3 is None or array("I").itemsize != 4
        or graph.is_directed() or graph.is_multigraph()
        or any(not isinstance(node, str) for node in graph)
        or graph.number_of_nodes() >= 2**32
    ):
        return
    temporary = None
    lock = None
    try:
        target = _cache_file(graph_path, identity)
        if graph_identity(graph_path) != identity:
            return
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # A separate SQLite transaction serializes builders and releases its
        # lock even if the writer exits. Contenders already have a JSON answer.
        lock = sqlite3.connect(target.parent / ".build-lock", timeout=0)
        lock.execute("BEGIN IMMEDIATE")
        if not repair:
            existing = open_snapshot(graph_path, identity)
            if existing is not None:
                existing.close()
                return
        fd, name = tempfile.mkstemp(prefix=".building-", suffix=".sqlite3", dir=target.parent)
        temporary = Path(name)
        os.close(fd)
        db = sqlite3.connect(temporary)
        try:
            # The file stays private until commit and close succeed.
            db.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; " + _SCHEMA)
            _write_projection(db, graph, legacy, identity)
            db.commit()
        finally:
            db.close()
        if graph_identity(graph_path) == identity:
            temporary.replace(target)
            # Keep the most recent prior generation for processes racing a publish.
            older = sorted(
                (file for file in target.parent.glob("[0-9a-f]*.sqlite3") if file != target),
                key=lambda file: file.stat().st_mtime_ns,
                reverse=True,
            )
            for stale in older[1:]:
                stale.unlink(missing_ok=True)
    except (OSError, sqlite3.Error, AttributeError, TypeError, ValueError, OverflowError, MemoryError, RuntimeError):
        pass  # The canonical JSON path already supplied the answer.
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        if lock is not None:
            lock.close()


def _write_projection(db, graph, legacy: bool, identity: _GraphIdentity) -> None:
    from graphify.serve import _node_fields, _node_search_text_from_fields, _trigrams

    ids = list(graph)
    fields = _node_fields(graph)
    position = {node: i for i, node in enumerate(ids)}
    degrees = dict(graph.degree)
    db.executemany(
        "INSERT INTO nodes VALUES (?, ?, ?, ?)",
        ((i, node, _json(graph.nodes[node]), degrees[node]) for i, node in enumerate(ids)),
    )

    postings = defaultdict(lambda: array("I"))

    def search_rows():
        for i, node in enumerate(ids):
            label = fields[node].norm_label
            if label != label.lower():
                # Qualified-name scoring can fold cased labels even when a
                # case-sensitive substring lookup in the projection cannot.
                raise ValueError("snapshot requires normalized labels")
            text = _node_search_text_from_fields(fields[node], node)
            for gram in _trigrams(text):
                if len(gram) == 3 and "\0" not in gram:
                    postings[gram].append(i)
            yield i, label.encode(), text.encode()

    db.executemany("INSERT INTO search VALUES (?, ?, ?)", search_rows())
    db.executemany(
        "INSERT INTO postings VALUES (?, ?)",
        ((gram, values.tobytes()) for gram, values in postings.items()),
    )

    signatures = {}
    context_degrees = Counter()
    edge_positions = {}

    def edge_rows():
        for i, (source, target, data) in enumerate(graph.edges(data=True)):
            signature = signatures.setdefault((data.get("context"), data.get("relation")), len(signatures))
            a, b = position[source], position[target]
            edge_positions[a, b] = edge_positions[b, a] = i
            context_degrees[signature, a] += 1
            context_degrees[signature, b] += 1
            yield i, signature, _json(data)

    db.executemany("INSERT INTO edges VALUES (?, ?, ?)", edge_rows())
    db.executemany(
        "INSERT INTO adjacency VALUES (?, ?, ?, ?)",
        (
            (position[node], rank, position[neighbor], edge_positions[position[node], position[neighbor]])
            for node in ids
            for rank, neighbor in enumerate(graph.neighbors(node))
        ),
    )
    db.executemany(
        "INSERT INTO context_degrees VALUES (?, ?, ?)",
        ((signature, node, degree) for (signature, node), degree in context_degrees.items()),
    )
    population = len(ids)
    by_degree = sorted(degrees.values())
    metadata = {
        "format": _FORMAT,
        "identity": identity,
        "nodes": population,
        "edges": graph.number_of_edges(),
        "legacy": legacy,
        "signatures": list(signatures),
        "hub": max(50, by_degree[int(population * .99)]) if population else 50,
        "learning_overlay": graph.graph.get("_learning_overlay"),
    }
    db.execute("INSERT INTO metadata VALUES (?)", (_json(metadata),))


class _Nodes(Mapping[str, dict]):
    def __init__(self, snapshot: QuerySnapshot):
        self._snapshot = snapshot

    def __getitem__(self, node: str) -> dict:
        return self._snapshot._node(node)[1]

    def __contains__(self, node: object) -> bool:
        if not isinstance(node, str):
            return False
        rows = self._snapshot._select("SELECT 1 FROM nodes WHERE id = ?", (node,))
        return next(rows, None) is not None

    def __iter__(self) -> Iterator[str]:
        return (node for (node,) in self._snapshot._select("SELECT id FROM nodes ORDER BY position"))

    def __len__(self) -> int:
        return self._snapshot.number_of_nodes()

    @overload
    def __call__(self, *, data: Literal[True]) -> Iterator[tuple[str, dict]]: ...

    @overload
    def __call__(self, *, data: Literal[False] = False) -> Iterator[str]: ...

    def __call__(self, *, data: bool = False) -> Iterator[str] | Iterator[tuple[str, dict]]:
        if data:
            return (
                (node, self._snapshot._decode(payload))
                for node, payload in self._snapshot._select("SELECT id, payload FROM nodes ORDER BY position")
            )
        return iter(self)


class QuerySnapshot:
    """Read-only graph operations used by the query ranker and renderer."""

    def __init__(self, db, metadata, *, signatures=None, degrees=None, nodes=None):
        self._db = db
        self._metadata = metadata
        self._signatures = signatures
        self._degrees = degrees
        self._node_cache = {} if nodes is None else nodes
        self._adjacency_cache = {}
        self._idf = {}
        self.nodes = _Nodes(self)
        self.graph = {"_learning_overlay": metadata["learning_overlay"]} if signatures is None else {}
        self.legacy = metadata["legacy"]

    def close(self) -> None:
        self._db.close()

    def _select(self, sql, parameters=()):
        assert sqlite3 is not None
        try:
            yield from self._db.execute(sql, parameters)
        except sqlite3.Error as exc:
            raise SnapshotReadError from exc

    @staticmethod
    def _decode(payload) -> dict:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError, RecursionError) as exc:
            raise SnapshotReadError from exc
        if not isinstance(data, dict):
            raise SnapshotReadError
        return data

    def _node(self, node: str):
        if node not in self._node_cache:
            row = next(self._select("SELECT position, payload, degree FROM nodes WHERE id = ?", (node,)), None)
            if row is None:
                raise SnapshotReadError
            self._node_cache[node] = row[0], self._decode(row[1]), row[2]
        return self._node_cache[node]

    def __contains__(self, node: object) -> bool:
        return node in self.nodes

    def __iter__(self) -> Iterator[str]:
        return iter(self.nodes)

    def __getitem__(self, node: str) -> dict[str, dict]:
        if node not in self._adjacency_cache:
            params = [self._node(node)[0]]
            order = "a.position"
            where = ""
            if self._signatures is not None:
                if not self._signatures:
                    return {}
                params.extend(self._signatures)
                where = f" AND e.signature IN ({_params(self._signatures)})"
                # The eager context graph adds edges in original global edge order.
                order = "a.edge"
            self._adjacency_cache[node] = {
                neighbor: self._decode(payload)
                for neighbor, payload in self._select(f"""
                    SELECT n.id, e.payload FROM adjacency a
                    JOIN edges e ON e.position = a.edge
                    JOIN nodes n ON n.position = a.neighbor
                    WHERE a.node = ?{where} ORDER BY {order}
                """, params)
            }
        return self._adjacency_cache[node]

    def neighbors(self, node: str) -> Iterator[str]:
        return iter(self[node])

    @overload
    def edges(self, nodes: str | Iterable[str] | None = None, *, data: Literal[True]) -> Iterator[tuple[str, str, dict]]: ...

    @overload
    def edges(self, nodes: str | Iterable[str] | None = None, *, data: Literal[False] = False) -> Iterator[tuple[str, str]]: ...

    def edges(
        self, nodes: str | Iterable[str] | None = None, *, data: bool = False,
    ) -> Iterator[tuple[str, str] | tuple[str, str, dict]]:
        if nodes is None:
            nodes = self.nodes
        elif isinstance(nodes, str):
            nodes = (nodes,)
        seen = set()
        for node in nodes:
            for neighbor, attributes in self[node].items():
                if neighbor not in seen:
                    yield (node, neighbor, attributes) if data else (node, neighbor)
            seen.add(node)

    @staticmethod
    def is_directed() -> bool:
        return False

    def number_of_nodes(self) -> int:
        return self._metadata["nodes"]

    def number_of_edges(self) -> int:
        return self._metadata["edges"] if self._degrees is None else sum(self._degrees.values()) // 2

    def degree(self, node: str) -> int:
        position, _, degree = self._node(node)
        return degree if self._degrees is None else self._degrees.get(position, 0)

    def filtered(self, contexts: set[str], relations: set[str]) -> QuerySnapshot:
        signatures = [
            index for index, (context, relation) in enumerate(self._metadata["signatures"])
            if context in contexts or relation in relations
        ]
        degrees = dict(self._select(f"""
            SELECT node, sum(degree) FROM context_degrees
            WHERE signature IN ({_params(signatures)}) GROUP BY node
        """, signatures)) if signatures else {}
        return QuerySnapshot(self._db, self._metadata, signatures=signatures, degrees=degrees, nodes=self._node_cache)

    def hub_threshold(self) -> int:
        if self._degrees is None:
            return self._metadata["hub"]
        n = self.number_of_nodes()
        index = int(n * .99) - (n - len(self._degrees))
        return max(50, sorted(self._degrees.values())[index]) if n and index >= 0 else 50

    def idf(self, terms: list[str]) -> dict[str, float]:
        population = self.number_of_nodes() or 1
        for term in terms:
            if term not in self._idf:
                count, = next(self._select("SELECT count(*) FROM search WHERE instr(label, ?) > 0", (term.encode(),)))
                self._idf[term] = math.log(1 + population / (1 + count))
        return {term: self._idf[term] for term in terms}

    def candidates(self, needles: list[str]) -> list[str] | None:
        """Use the same search fields as the in-memory trigram prefilter."""
        from graphify.serve import _trigrams

        if any("\0" in needle for needle in needles):
            return None

        positions = set()
        for needle in dict.fromkeys(filter(None, needles)):
            value = needle.encode()
            grams = list(_trigrams(needle)) if len(needle) >= 3 else []
            if grams:
                # Batches also keep very long queries below SQLite's bind limit.
                sizes = [
                    row
                    for start in range(0, len(grams), _BATCH)
                    for batch in (grams[start:start + _BATCH],)
                    for row in self._select(
                        f"SELECT gram, length(positions) FROM postings WHERE gram IN ({_params(batch)})",
                        batch,
                    )
                ]
                if len(sizes) != len(grams):
                    continue
                gram, size = min(sizes, key=lambda row: row[1])
                if size // 4 < self.number_of_nodes() // 8:
                    blob, = next(self._select("SELECT positions FROM postings WHERE gram = ?", (gram,)), (None,))
                    if blob is None or len(blob) % 4:
                        raise SnapshotReadError
                    rare = array("I", blob)
                    for start in range(0, len(rare), _BATCH):
                        batch = rare[start:start + _BATCH]
                        positions.update(row[0] for row in self._select(
                            f"SELECT position FROM search WHERE position IN ({_params(batch)}) AND instr(text, ?) > 0",
                            [*batch, value],
                        ))
                    continue
            positions.update(row[0] for row in self._select("SELECT position FROM search WHERE instr(text, ?) > 0", (value,)))

        ordered = sorted(positions)
        result = []
        for start in range(0, len(ordered), _BATCH):
            batch = ordered[start:start + _BATCH]
            for node, position, payload, degree in self._select(
                f"SELECT id, position, payload, degree FROM nodes WHERE position IN ({_params(batch)}) ORDER BY position",
                batch,
            ):
                if node not in self._node_cache:
                    self._node_cache[node] = position, self._decode(payload), degree
                result.append(node)
        return result


QueryGraph = nx.Graph | QuerySnapshot
