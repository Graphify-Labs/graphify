"""Persistent Graphify schema implemented on the official embedded Helix SDK."""

from __future__ import annotations

import base64
from collections.abc import Iterable, Iterator
from concurrent import futures
from contextlib import contextmanager
import copy
from dataclasses import dataclass
from enum import Enum, auto
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time
from typing import Any
import unicodedata
import uuid

import helixdb
from helixdb.dsl import RepeatConfig, SourcePredicate, SubTraversal, g, read_batch
from helixdb.graph import external_id_from_json, external_id_to_json

from .model import GraphBuildData, LoadedGraph, import_identity
from .native import open_embedded_client, validate_native_backend


_SCHEMA_VERSION = 9
_NODE_LABEL = "GraphifyNode"
_META_LABEL = "GraphifyMeta"
_CONTROL_LABEL = "GraphifyControl"
_STATE_LABEL = "GraphifyState"
_EXTERNAL_KEY = "external_key"
_STORAGE_KEY = "storage_key"
_GENERATION = "graphify_generation"
_CONTROL_KEY = "control_key"
_ACTIVE_GENERATION = "active_generation"
_PREVIOUS_GENERATION = "previous_generation"
_ATTRS = "attrs"
_ORDER = "graphify_order"
_LEGACY_TARGET_KEY = "target_key"
_EDGE_KEY = "edge_key"
_NATIVE_WEIGHT = "graphify_weight"
_EDGE_CONTEXT = "graphify_context"
_RECORD_HASH = "record_hash"
_EDGE_IDENTITY = "edge_identity"
_IDENTITY_BUCKET = "identity_bucket"
_TOPOLOGY_REVISION = "topology_revision"
_NODE_BUCKET_HASHES = "node_bucket_hashes"
_EDGE_BUCKET_HASHES = "edge_bucket_hashes"
_SEARCH_LABEL = "search_label"
_SEARCH_TEXT = "search_text"
_WRITER_LOCK_FILE = ".graphify-writer.lock"
_WRITER_LOCK_TIMEOUT_SECONDS = 120.0
_WRITE_CHUNK_SIZE = 1_000
_STAGED_EDGE_WRITE_CHUNK_SIZE = 750
_STATE_WRITE_CHUNK_SIZE = 1_000
_BUFFERED_WRITE_CONCURRENCY = 2
_IDENTITY_BUCKET_COUNT = 1_024
_DELTA_MAX_MUTATIONS = 2_000
_DELTA_MAX_RATIO = 0.10
DEFAULT_MAX_NODES = 1_000_000
DEFAULT_MAX_EDGES = 5_000_000
DEFAULT_PROJECT_STORE = Path("graphify-out/graph.helix")
DEFAULT_GLOBAL_STORE = Path.home() / ".graphify" / "global-graph.helix"
_DURABLE_STATE = "graphify_state"
_STATE_TYPE = "$graphify_state_type"
_STATE_KIND = "state_kind"
_STATE_KEY = "state_key"
_STATE_PAYLOAD = "payload"
_STATE_REVISION = "state_revision"
_ACTIVE_STATE_REVISION = "active_state_revision"
_CHECKSUM_MODE = "checksum_mode"
_SPLIT_CHECKSUM_MODE = "topology-state-v1"
_STREAM_CHECKSUM_MODE = "topology-stream-v1"
_TOPOLOGY_CHECKSUM = "topology_checksum"
_STATE_KINDS = ("section", "community", "file", "cache")
_STATE_REVISION_KEYS = {kind: f"active_{kind}_revision" for kind in _STATE_KINDS}
_STATE_CHECKSUM_KEYS = {kind: f"{kind}_state_checksum" for kind in _STATE_KINDS}
_STATE_COUNT_KEYS = {kind: f"{kind}_state_count" for kind in _STATE_KINDS}
_SEARCH_TOKEN_RE = re.compile(r"\w+")


@dataclass(frozen=True, slots=True)
class _PreparedNode:
    encoded_id: str
    external_id: Any
    attributes: tuple[tuple[str, Any], ...]
    search_label: str
    search_text: str
    identity_bucket: int
    record_hash: str


@dataclass(frozen=True, slots=True)
class _PreparedEdge:
    source: str
    target: str
    source_id: Any
    target_id: Any
    key: Any
    relation: str
    stored_attributes: tuple[tuple[str, Any], ...]
    context: str | None
    weight: float | None
    stable_identity: str
    identity_bucket: int
    record_hash: str

    @property
    def shape(self) -> tuple[str, bool, bool, bool]:
        return (
            self.relation,
            self.context is not None,
            self.weight is not None,
            bool(self.stored_attributes),
        )


@dataclass(frozen=True, slots=True)
class _CanonicalEdge:
    source: str
    target: str
    source_id: Any
    target_id: Any
    key: Any
    key_identity: dict[str, Any]
    relation: str
    stored_attributes: tuple[tuple[str, Any], ...]
    context: str | None
    weight: float | None
    encoded_record: bytes


@dataclass(frozen=True, slots=True)
class _PreparedTopology:
    directed: bool
    multigraph: bool
    graph_attributes: dict[str, Any]
    extras: dict[str, Any]
    nodes: list[_PreparedNode]
    edges: list[_PreparedEdge]
    checksum: str
    node_bucket_hashes: list[str]
    edge_bucket_hashes: list[str]


@dataclass(frozen=True, slots=True)
class _PreparedState:
    encoded: dict[str, Any] | None
    records: list[tuple[str, str, Any, int]]
    category_records: dict[str, list[tuple[str, str, Any, int]]]
    category_checksums: dict[str, str]
    category_counts: dict[str, int]
    checksum: str


@dataclass(frozen=True, slots=True)
class _StoredNode:
    internal_id: int
    record_hash: str


@dataclass(frozen=True, slots=True)
class _StoredEdge:
    internal_id: int
    record_hash: str


@dataclass(frozen=True, slots=True)
class _TopologyDelta:
    added_nodes: list[_PreparedNode]
    updated_nodes: list[tuple[_StoredNode, _PreparedNode]]
    dropped_nodes: list[_StoredNode]
    added_edges: list[_PreparedEdge]
    dropped_edges: list[_StoredEdge]

    @property
    def mutation_count(self) -> int:
        return (
            len(self.added_nodes)
            + len(self.updated_nodes)
            + len(self.dropped_nodes)
            + len(self.added_edges)
            + len(self.dropped_edges)
        )


@dataclass(frozen=True, slots=True)
class _StagedProposal:
    graph: Any
    prepared: _PreparedTopology


@dataclass(frozen=True, slots=True)
class _PublishedStage:
    pass


@dataclass(slots=True)
class _StagedGraph:
    generation: str
    state: dict[str, Any]
    metadata: dict[str, Any]
    store_path: Path
    _phase: _StagedProposal | _PublishedStage
    query: None = None

    @property
    def graph(self) -> Any:
        phase = self._phase
        if isinstance(phase, _PublishedStage):
            raise RuntimeError("staged Helix proposal has already been activated")
        return phase.graph

    @property
    def prepared(self) -> _PreparedTopology:
        phase = self._phase
        if isinstance(phase, _PublishedStage):
            raise RuntimeError("staged Helix proposal has already been activated")
        return phase.prepared

    def mark_published(self) -> None:
        if isinstance(self._phase, _PublishedStage):
            raise RuntimeError("staged Helix proposal has already been activated")
        self._phase = _PublishedStage()


@dataclass(slots=True)
class _StagedDeltaGraph(_StagedGraph):
    pass


@dataclass(slots=True)
class _StagedFullGraph(_StagedGraph):
    pass


class _DeltaAttempt(Enum):
    PUBLISHED = auto()
    FALLBACK = auto()
    FALLBACK_NATIVE_VALIDATED = auto()


def _close_public_client(client: Any) -> None:
    """Close the synchronous public SDK outside an active asyncio loop.

    The public b3 client intentionally rejects synchronous embedded calls from
    an event-loop thread. Resource finalizers can run on such a thread, so move
    the public ``close()`` call to a short-lived worker in that one case.
    """
    try:
        import asyncio

        asyncio.get_running_loop()
    except RuntimeError:
        client.close()
        return

    errors: list[BaseException] = []

    def close() -> None:
        try:
            client.close()
        except BaseException as exc:  # pragma: no cover - propagated below
            errors.append(exc)

    worker = threading.Thread(target=close, name="graphify-helix-close")
    worker.start()
    worker.join()
    if errors:
        raise errors[0]


def _public_store_rebuild_message(exc: BaseException, path: Path) -> str | None:
    """Translate public SDK format/index failures into a source-rebuild action."""
    detail = str(exc)
    blockers = (
        "Migration required: writer migration must complete",
        "Index lifecycle unavailable for secondary",
    )
    if not any(blocker in detail for blocker in blockers):
        return None
    return (
        f"embedded Helix store at {path} was created by an incompatible public "
        "runtime and cannot be upgraded safely; move that graph.helix directory "
        "aside and run graphify update from source"
    )


class _StoreLock:
    """Cross-platform process lock held for the lifetime of an embedded handle."""

    def __init__(
        self,
        path: Path,
        *,
        shared: bool,
        timeout: float = _WRITER_LOCK_TIMEOUT_SECONDS,
    ) -> None:
        self.path = path
        self.shared = shared
        self.timeout = timeout
        self._stream: Any | None = None

    def acquire(self) -> None:
        # Helix's embedded reader is snapshot-safe alongside a writer.  Only
        # serialize competing writers; reader/writer exclusion would prevent
        # readers from retaining the previous active generation during staging.
        if self.shared:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("rb" if self.shared else "a+b")
        if not self.shared and self.path.stat().st_size == 0:
            stream.write(b"\0")
            stream.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self._lock(stream)
                break
            except (BlockingIOError, OSError) as exc:
                if time.monotonic() >= deadline:
                    stream.close()
                    raise TimeoutError(
                        f"timed out waiting for embedded Helix store lock {self.path}"
                    ) from exc
                time.sleep(0.05)
        if not self.shared:
            stream.seek(0)
            stream.truncate()
            stream.write(f"{os.getpid()}\n".encode("ascii"))
            stream.flush()
        self._stream = stream

    def _lock(self, stream: Any) -> None:
        if os.name == "nt":
            import msvcrt

            stream.seek(0)
            mode = msvcrt.LK_NBRLCK if self.shared else msvcrt.LK_NBLCK
            msvcrt.locking(stream.fileno(), mode, 1)
        else:
            import fcntl

            mode = fcntl.LOCK_SH if self.shared else fcntl.LOCK_EX
            fcntl.flock(stream.fileno(), mode | fcntl.LOCK_NB)

    def release(self) -> None:
        stream = self._stream
        if stream is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()
            self._stream = None


def _json_value(value: Any, context: str) -> Any:
    """Validate and normalize a value to the JSON types accepted by Helix."""
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        return json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{context} must contain JSON-compatible values: {exc}") from exc


def _encode_state_value(value: Any) -> Any:
    """Encode typed graph identifiers inside otherwise JSON-compatible state."""
    if isinstance(value, bytes):
        return {_STATE_TYPE: "bytes", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, tuple):
        return {_STATE_TYPE: "tuple", "value": [_encode_state_value(item) for item in value]}
    if isinstance(value, frozenset):
        return {
            _STATE_TYPE: "frozenset",
            "value": [_encode_state_value(item) for item in sorted(value, key=_encode_key)],
        }
    if isinstance(value, list):
        return [_encode_state_value(item) for item in value]
    if isinstance(value, dict):
        if all(isinstance(key, str) for key in value):
            return {key: _encode_state_value(item) for key, item in value.items()}
        return {
            _STATE_TYPE: "mapping",
            "value": [
                [_encode_state_value(key), _encode_state_value(item)] for key, item in value.items()
            ],
        }
    return value


def _decode_state_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode_state_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    kind = value.get(_STATE_TYPE) if set(value) == {_STATE_TYPE, "value"} else None
    if kind is None:
        return {key: _decode_state_value(item) for key, item in value.items()}
    raw = value.get("value")
    if kind == "bytes" and isinstance(raw, str):
        return base64.b64decode(raw, validate=True)
    if kind == "tuple" and isinstance(raw, list):
        return tuple(_decode_state_value(item) for item in raw)
    if kind == "frozenset" and isinstance(raw, list):
        return frozenset(_decode_state_value(item) for item in raw)
    if kind == "mapping" and isinstance(raw, list):
        return {
            _decode_state_value(pair[0]): _decode_state_value(pair[1])
            for pair in raw
            if isinstance(pair, list) and len(pair) == 2
        }
    raise RuntimeError(f"embedded Helix durable state has invalid typed value {kind!r}")


def _tagged_key(value: Any) -> dict[str, Any]:
    """Return Helix's canonical tagged external-identity envelope."""
    return external_id_to_json(value)


def _encode_key(value: Any) -> str:
    return json.dumps(
        _tagged_key(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_tagged_key(value: dict[str, Any]) -> Any:
    try:
        return external_id_from_json(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"embedded Helix graph identifier is invalid: {exc}") from exc


def _decode_key(value: str) -> Any:
    try:
        tagged = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("embedded Helix graph contains an invalid encoded identifier") from exc
    if not isinstance(tagged, dict):
        raise RuntimeError("embedded Helix graph identifier is not a tagged object")
    return _decode_tagged_key(tagged)


def _decode_identity(value: Any) -> Any:
    if not isinstance(value, dict):
        raise RuntimeError("embedded Helix identity property is not tagged")
    return _decode_tagged_key(value)


def _normalize_search_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).lower()
    return "".join(character for character in text if not unicodedata.combining(character))


def _search_properties(node_id: Any, attrs: dict[str, Any]) -> dict[str, str]:
    """Denormalize public, searchable node fields for Helix predicates."""
    label = _normalize_search_text(attrs.get("norm_label") or attrs.get("label"))
    source = _normalize_search_text(attrs.get("source_file"))
    identity = _normalize_search_text(node_id)
    tokenized_label = " ".join(part for part in _SEARCH_TOKEN_RE.findall(label))
    tokenized_source = " ".join(part for part in _SEARCH_TOKEN_RE.findall(source))
    return {
        _SEARCH_LABEL: label,
        _SEARCH_TEXT: "\0".join((label, tokenized_label, identity, source, tokenized_source)),
    }


def _canonical_bytes(payload: Any) -> bytes:
    """Encode one value into Graphify's stable checksum representation."""

    def encode_non_json(value: Any) -> Any:
        if isinstance(value, bytes):
            return {"$graphify_bytes": base64.b64encode(value).decode("ascii")}
        if isinstance(value, frozenset):
            return {"$graphify_frozenset": sorted(_encode_key(item) for item in value)}
        raise TypeError(f"cannot checksum {type(value).__name__}")

    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
        default=encode_non_json,
    ).encode("utf-8")


def _checksum(payload: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical_bytes(payload)).hexdigest()}"


def _record_hash(payload: Any) -> str:
    """Return a compact comparison hash for one persisted topology record."""
    return _record_hash_bytes(_canonical_bytes(payload))


def _record_hash_bytes(encoded: bytes) -> str:
    return hashlib.blake2b(encoded, digest_size=16).hexdigest()


def _edge_identity(
    *,
    directed: bool,
    multigraph: bool,
    source: str,
    target: str,
    key: dict[str, Any],
    anonymous_ordinal: int | None = None,
) -> str:
    """Return a stable logical identity used only for delta comparison."""
    if not directed and target < source:
        source, target = target, source
    payload: dict[str, Any] = {"source": source, "target": target}
    if multigraph:
        payload["key"] = key
        if anonymous_ordinal is not None:
            payload["anonymous_ordinal"] = anonymous_ordinal
    return _record_hash(payload)


def _identity_bucket(identity: str) -> int:
    digest = hashlib.blake2b(identity.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % _IDENTITY_BUCKET_COUNT


def _identity_bucket_hashes(records: list[tuple[str, str]]) -> list[str]:
    grouped: list[list[tuple[str, str]]] = [[] for _ in range(_IDENTITY_BUCKET_COUNT)]
    for identity, record_hash in records:
        grouped[_identity_bucket(identity)].append((identity, record_hash))
    return ["" if not bucket else _record_hash(sorted(bucket)) for bucket in grouped]


def _changed_buckets(old: Any, new: list[str]) -> set[int] | None:
    if (
        not isinstance(old, list)
        or len(old) != _IDENTITY_BUCKET_COUNT
        or any(not isinstance(value, str) for value in old)
    ):
        return None
    return {index for index, (left, right) in enumerate(zip(old, new)) if left != right}


def _generation_checksum(topology_checksum: str, state_checksum: str) -> str:
    """Bind independently verified topology and state into one generation hash."""
    return _checksum(
        {
            _TOPOLOGY_CHECKSUM: topology_checksum,
            "state_checksum": state_checksum,
        }
    )


class _TopologyStreamChecksum:
    """Order-stable checksum that can be produced from bounded record pages."""

    def __init__(
        self,
        *,
        directed: bool,
        multigraph: bool,
        graph: dict[str, Any],
        extras: dict[str, Any],
    ) -> None:
        self._digest = hashlib.sha256()
        self._add(
            b"header",
            _canonical_bytes(
                {
                    "header": {
                        "directed": directed,
                        "multigraph": multigraph,
                        "graph": graph,
                        "extras": extras,
                    }
                }
            ),
        )

    def _add(self, kind: bytes, encoded: bytes) -> None:
        self._digest.update(kind)
        self._digest.update(len(encoded).to_bytes(8, "big"))
        self._digest.update(encoded)

    def node(self, value: dict[str, Any] | bytes) -> None:
        encoded = value if isinstance(value, bytes) else _canonical_bytes(value)
        self._add(b"node", encoded)

    def edge(self, value: dict[str, Any] | bytes) -> None:
        encoded = value if isinstance(value, bytes) else _canonical_bytes(value)
        self._add(b"edge", encoded)

    def hexdigest(self) -> str:
        return f"sha256:{self._digest.hexdigest()}"


def _node_topology_record(node_id: Any, attributes: dict[str, Any]) -> dict[str, Any]:
    return {"id": node_id, "attributes": attributes}


def _edge_topology_record(
    source: Any,
    target: Any,
    key: Any,
    relation: str,
    attributes: dict[str, Any],
    *,
    multigraph: bool,
) -> dict[str, Any]:
    record = {
        "source": source,
        "target": target,
        "relation": relation,
        "attributes": attributes,
    }
    if multigraph:
        record["key"] = key
    return record


def _prepare_topology(
    graph: GraphBuildData,
    *,
    max_nodes: int,
    max_edges: int,
) -> _PreparedTopology:
    """Validate one construction DTO without materializing node-link copies."""
    if len(graph.nodes) > max_nodes or len(graph.edges) > max_edges:
        raise ValueError(
            "graph exceeds configured embedded ingestion bounds: "
            f"{len(graph.nodes)}/{len(graph.edges)} > {max_nodes}/{max_edges}"
        )
    graph_attributes = _json_value(dict(graph.attributes), "graph metadata")
    extras = _json_value(dict(graph.extras), "graph top-level metadata")
    if not isinstance(graph_attributes, dict) or not isinstance(extras, dict):
        raise TypeError("graph metadata and top-level extras must be mappings")

    node_ids: set[str] = set()
    prepared_nodes: list[tuple[_PreparedNode, bytes]] = []
    for input_index, node in enumerate(graph.nodes):
        node_id = import_identity(node.id)
        encoded_id = _encode_key(node_id)
        if encoded_id in node_ids:
            raise ValueError(f"duplicate graph node identifier at nodes[{input_index}]")
        node_ids.add(encoded_id)
        attributes = _json_value(dict(node.attributes), f"graph nodes[{input_index}] attributes")
        if not isinstance(attributes, dict):
            raise TypeError(f"graph nodes[{input_index}] attributes must be a mapping")
        search = _search_properties(node_id, attributes)
        encoded_record = _canonical_bytes(_node_topology_record(node_id, attributes))
        prepared_nodes.append(
            (
                _PreparedNode(
                    encoded_id=encoded_id,
                    external_id=node_id,
                    attributes=tuple(attributes.items()),
                    search_label=search[_SEARCH_LABEL],
                    search_text=search[_SEARCH_TEXT],
                    identity_bucket=_identity_bucket(encoded_id),
                    record_hash=_record_hash_bytes(encoded_record),
                ),
                encoded_record,
            )
        )

    edge_identities: set[str] = set()
    prepared_edges: list[tuple[_PreparedEdge, bytes]] = []
    anonymous_groups: dict[tuple[str, str], list[_CanonicalEdge]] = {}
    none_identity = _tagged_key(None)
    for input_index, edge in enumerate(graph.edges):
        source = import_identity(edge.source)
        target = import_identity(edge.target)
        encoded_source = _encode_key(source)
        encoded_target = _encode_key(target)
        if encoded_source not in node_ids or encoded_target not in node_ids:
            raise ValueError(f"graph edges[{input_index}] references a missing node")
        key = import_identity(edge.key) if graph.multigraph else None
        raw_attributes = dict(edge.attributes)
        raw_weight = raw_attributes.get("weight")
        if raw_weight is not None and (
            isinstance(raw_weight, bool)
            or not isinstance(raw_weight, (int, float))
            or not math.isfinite(float(raw_weight))
        ):
            raise TypeError(f"graph edges[{input_index}] weight must be finite numeric")
        attributes = _json_value(raw_attributes, f"graph edges[{input_index}] attributes")
        if not isinstance(attributes, dict):
            raise TypeError(f"graph edges[{input_index}] attributes must be a mapping")
        relation = attributes.pop("relation", "related_to")
        if not isinstance(relation, str) or not relation:
            raise TypeError(f"graph edges[{input_index}] relation must be a non-empty string")
        key_identity = none_identity if key is None else _tagged_key(key)
        context = attributes.get("context")
        native_context = context if isinstance(context, str) and context else None
        weight = attributes.get("weight")
        native_weight = None if weight is None else float(weight)
        encoded_record = _canonical_bytes(
            _edge_topology_record(
                source,
                target,
                key,
                relation,
                attributes,
                multigraph=graph.multigraph,
            )
        )
        canonical = _CanonicalEdge(
            source=encoded_source,
            target=encoded_target,
            source_id=source,
            target_id=target,
            key=key,
            key_identity=key_identity,
            relation=relation,
            stored_attributes=tuple(item for item in attributes.items() if item[0] != "weight"),
            context=native_context,
            weight=native_weight,
            encoded_record=encoded_record,
        )
        if graph.multigraph and key is None:
            anonymous_pair = (
                (encoded_source, encoded_target)
                if graph.directed or encoded_source <= encoded_target
                else (encoded_target, encoded_source)
            )
            anonymous_groups.setdefault(anonymous_pair, []).append(canonical)
            continue
        stable_identity = _edge_identity(
            directed=graph.directed,
            multigraph=graph.multigraph,
            source=canonical.source,
            target=canonical.target,
            key=canonical.key_identity,
        )
        if stable_identity in edge_identities:
            raise ValueError(f"duplicate graph edge identity {stable_identity!r}")
        edge_identities.add(stable_identity)
        prepared_edges.append(
            (
                _PreparedEdge(
                    source=canonical.source,
                    target=canonical.target,
                    source_id=canonical.source_id,
                    target_id=canonical.target_id,
                    key=canonical.key,
                    relation=canonical.relation,
                    stored_attributes=canonical.stored_attributes,
                    context=canonical.context,
                    weight=canonical.weight,
                    stable_identity=stable_identity,
                    identity_bucket=_identity_bucket(stable_identity),
                    record_hash=_record_hash_bytes(canonical.encoded_record),
                ),
                canonical.encoded_record,
            )
        )

    for group in anonymous_groups.values():
        for ordinal, canonical in enumerate(sorted(group, key=lambda item: item.encoded_record)):
            stable_identity = _edge_identity(
                directed=graph.directed,
                multigraph=True,
                source=canonical.source,
                target=canonical.target,
                key=canonical.key_identity,
                anonymous_ordinal=ordinal,
            )
            assert stable_identity not in edge_identities, "anonymous edge identity must be unique"
            edge_identities.add(stable_identity)
            prepared_edges.append(
                (
                    _PreparedEdge(
                        source=canonical.source,
                        target=canonical.target,
                        source_id=canonical.source_id,
                        target_id=canonical.target_id,
                        key=None,
                        relation=canonical.relation,
                        stored_attributes=canonical.stored_attributes,
                        context=canonical.context,
                        weight=canonical.weight,
                        stable_identity=stable_identity,
                        identity_bucket=_identity_bucket(stable_identity),
                        record_hash=_record_hash_bytes(canonical.encoded_record),
                    ),
                    canonical.encoded_record,
                )
            )

    prepared_nodes.sort(key=lambda item: item[0].encoded_id)
    prepared_edges.sort(key=lambda item: item[0].stable_identity)

    checksum = _TopologyStreamChecksum(
        directed=graph.directed,
        multigraph=graph.multigraph,
        graph=graph_attributes,
        extras=extras,
    )
    for _, encoded_record in prepared_nodes:
        checksum.node(encoded_record)
    for _, encoded_record in prepared_edges:
        checksum.edge(encoded_record)
    nodes = [node for node, _ in prepared_nodes]
    edges = [edge for edge, _ in prepared_edges]

    return _PreparedTopology(
        directed=graph.directed,
        multigraph=graph.multigraph,
        graph_attributes=graph_attributes,
        extras=extras,
        nodes=nodes,
        edges=edges,
        checksum=checksum.hexdigest(),
        node_bucket_hashes=_identity_bucket_hashes(
            [(node.encoded_id, node.record_hash) for node in nodes]
        ),
        edge_bucket_hashes=_identity_bucket_hashes(
            [(edge.stable_identity, edge.record_hash) for edge in edges]
        ),
    )


def _state_revision(metadata: dict[str, Any], kind: str) -> str | None:
    revision = metadata.get(_STATE_REVISION_KEYS[kind])
    if not isinstance(revision, str):
        revision = metadata.get(_ACTIVE_STATE_REVISION)
    return revision if isinstance(revision, str) else None


def _state_category_checksum(
    records: list[tuple[str, str, Any, int]],
) -> str:
    return _checksum(
        {
            "records": [
                {"kind": kind, "key": key, "payload": payload, "order": order}
                for kind, key, payload, order in records
            ]
        }
    )


def _combined_state_checksum(checksums: dict[str, str]) -> str:
    return _checksum({"categories": checksums})


def _state_category_value(state: dict[str, Any], kind: str, generation: str) -> Any:
    if kind == "community":
        return state.get("communities", [])
    incremental = state.get("incremental", {})
    if not isinstance(incremental, dict):
        incremental = {}
    if kind == "file":
        return incremental.get("files", {})
    if kind == "cache":
        return incremental.get("extraction_cache", {})

    sections: dict[str, Any] = {}
    for key, value in state.items():
        if key == "communities":
            if isinstance(value, list) and not value:
                sections[key] = []
            continue
        if key == "incremental" and isinstance(value, dict):
            metadata = {
                name: item
                for name, item in value.items()
                if name not in {"files", "extraction_cache"}
            }
            metadata["last_successful_generation"] = generation
            if "files" in value and not value.get("files"):
                metadata["files"] = {}
            if "extraction_cache" in value and not value.get("extraction_cache"):
                metadata["extraction_cache"] = {}
            sections[key] = metadata
            continue
        if key == "build" and isinstance(value, dict):
            build = dict(value)
            build["generation"] = generation
            sections[key] = build
            continue
        sections[key] = value
    sections.setdefault("build", {"generation": generation})
    sections.setdefault("incremental", {"last_successful_generation": generation})
    return sections


def _properties(row: Any, context: str) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise RuntimeError(f"embedded Helix {context} row is not a mapping")
    nested = row.get("properties")
    if isinstance(nested, dict):
        return {**row, **nested}
    return row


def _rows(result: Any, name: str) -> list[Any]:
    if not isinstance(result, dict):
        raise RuntimeError("embedded Helix query returned a non-mapping response")
    value = result.get(name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError(f"embedded Helix query variable {name!r} is not a list")
    return value


class HelixNodeQuery:
    """Long-lived public reader for bounded native node predicates."""

    def __init__(
        self,
        path: str | Path,
        generation: str,
        *,
        max_candidates: int = 50_000,
        client: Any | None = None,
    ) -> None:
        self.path = Path(path).expanduser().resolve()
        self.generation = generation
        self.max_candidates = max_candidates
        self._client = client or open_embedded_client(
            self.path,
            read_only=True,
            disable_cache=True,
        )
        self._lock = threading.RLock()
        self._closed = False

    def _query(self, batch: Any) -> Any:
        with self._lock:
            if self._closed:
                raise RuntimeError("native Helix node query is closed")
            return self._client.query(batch.to_query_request())

    def _predicate(self, property_name: str, values: list[str]) -> Any | None:
        normalized = list(
            dict.fromkeys(value for raw in values if (value := _normalize_search_text(raw)))
        )
        if not normalized:
            return None
        matches = [SourcePredicate.contains(property_name, value) for value in normalized]
        match = matches[0] if len(matches) == 1 else SourcePredicate.or_(matches)
        return SourcePredicate.and_(
            (
                SourcePredicate.eq(_GENERATION, self.generation),
                match,
            )
        )

    def candidate_ids(self, values: list[str]) -> list[Any]:
        """Return an order-stable, bounded superset from public predicates."""
        predicate = self._predicate(_SEARCH_TEXT, values)
        if predicate is None:
            return []
        batch = (
            read_batch()
            .var_as(
                "nodes",
                g()
                .n_with_label_where(_NODE_LABEL, predicate)
                .limit(self.max_candidates)
                .value_map(),
            )
            .returning(["nodes"])
        )
        rows = [_properties(row, "search node") for row in _rows(self._query(batch), "nodes")]
        rows.sort(key=lambda row: str(row.get(_STORAGE_KEY, "")))
        return [
            _decode_identity(row[_EXTERNAL_KEY])
            for row in rows
            if isinstance(row.get(_EXTERNAL_KEY), dict)
        ]

    def document_frequencies(self, terms: list[str]) -> dict[str, int]:
        """Count label matches natively without reconstructing topology."""
        normalized = list(
            dict.fromkeys(value for raw in terms if (value := _normalize_search_text(raw)))
        )
        if not normalized:
            return {}
        batch = read_batch()
        variables: list[str] = []
        for index, term in enumerate(normalized):
            variable = f"count_{index}"
            variables.append(variable)
            predicate = SourcePredicate.and_(
                (
                    SourcePredicate.eq(_GENERATION, self.generation),
                    SourcePredicate.contains(_SEARCH_LABEL, term),
                )
            )
            batch = batch.var_as(
                variable,
                g().n_with_label_where(_NODE_LABEL, predicate).count(),
            )
        result = self._query(batch.returning(variables))
        return {term: int(result.get(variable, 0)) for term, variable in zip(normalized, variables)}

    def traverse_ids(
        self,
        seeds: list[Any],
        depth: int,
        *,
        contexts: set[str],
    ) -> list[Any]:
        """Traverse context-filtered edges through the public query DSL."""
        if not seeds:
            return []
        storage_keys = [
            HelixEmbeddedStore._storage_key(self.generation, _encode_key(seed)) for seed in seeds
        ]
        seed_predicate = SourcePredicate.and_(
            (
                SourcePredicate.eq(_GENERATION, self.generation),
                SourcePredicate.is_in(_STORAGE_KEY, storage_keys),
            )
        )
        traversal = g().n_with_label_where(_NODE_LABEL, seed_predicate)
        if depth > 0 and contexts:
            edge_predicate = SourcePredicate.and_(
                (
                    SourcePredicate.eq(_GENERATION, self.generation),
                    SourcePredicate.is_in(_EDGE_CONTEXT, sorted(contexts)),
                )
            )
            step = SubTraversal.new().both_e().where(edge_predicate).other_n().dedup()
            traversal = traversal.repeat(RepeatConfig.new(step).times(depth).emit_all())
        batch = (
            read_batch()
            .var_as(
                "nodes",
                traversal.dedup().limit(self.max_candidates).value_map(),
            )
            .returning(["nodes"])
        )
        rows = [_properties(row, "traversed node") for row in _rows(self._query(batch), "nodes")]
        rows.sort(key=lambda row: str(row.get(_STORAGE_KEY, "")))
        return [
            _decode_identity(row[_EXTERNAL_KEY])
            for row in rows
            if isinstance(row.get(_EXTERNAL_KEY), dict)
        ]

    def close(self) -> None:
        if not self._closed:
            _close_public_client(self._client)
            self._closed = True

    # Deliberately no __del__: async native close can re-enter while
    # Python is garbage-collecting inside another embedded request.


@dataclass
class HelixEmbeddedStore:
    """Graphify's durable graph schema on an in-process Helix ``Disk`` client."""

    path: Path
    _client: Any | None
    _helix: Any
    _read_only: bool
    _closed: bool
    _store_lock: _StoreLock
    _open_lock: threading.Lock
    _open_future: futures.Future[Any] | None
    _open_executor: futures.ThreadPoolExecutor | None
    _fresh: bool
    _max_nodes: int
    _max_edges: int
    _retain_rollback: bool

    def __init__(
        self,
        path: str | Path,
        *,
        read_only: bool = False,
        retain_rollback: bool = False,
        max_nodes: int = DEFAULT_MAX_NODES,
        max_edges: int = DEFAULT_MAX_EDGES,
    ) -> None:
        for name, value in (("max_nodes", max_nodes), ("max_edges", max_edges)):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        self.path = Path(path).expanduser().resolve()
        if read_only:
            if not self.path.is_dir():
                raise FileNotFoundError(f"embedded Helix store not found: {self.path}")
        else:
            self.path.mkdir(parents=True, exist_ok=True)
        self._fresh = not any(child.name != _WRITER_LOCK_FILE for child in self.path.iterdir())
        validate_native_backend()
        self._helix = helixdb
        self._read_only = read_only
        self._retain_rollback = bool(retain_rollback)
        self._max_nodes = max_nodes
        self._max_edges = max_edges
        self._closed = False
        self._client = None
        self._open_lock = threading.Lock()
        self._open_future = None
        self._open_executor = None
        self._store_lock = _StoreLock(
            self.path / _WRITER_LOCK_FILE,
            shared=read_only,
        )
        self._store_lock.acquire()
        if not read_only and self._fresh:
            try:
                self._open_executor = futures.ThreadPoolExecutor(
                    max_workers=1,
                    thread_name_prefix="graphify-helix-open",
                )
                self._open_future = self._open_executor.submit(
                    open_embedded_client,
                    self.path,
                    read_only=False,
                    disable_cache=True,
                )
            except Exception:
                self._store_lock.release()
                raise
            return
        try:
            self._client = open_embedded_client(
                self.path,
                read_only=read_only,
                disable_cache=True,
            )
        except Exception as exc:
            self._store_lock.release()
            if message := _public_store_rebuild_message(exc, self.path):
                raise RuntimeError(message) from exc
            raise
        if not read_only:
            try:
                self._validate_active_schema()
                self._cleanup_inactive_generations()
                self._cleanup_inactive_state_revisions()
            except Exception as exc:
                try:
                    _close_public_client(self._client)
                finally:
                    self._store_lock.release()
                if message := _public_store_rebuild_message(exc, self.path):
                    raise RuntimeError(message) from exc
                raise

    def _ensure_client(self) -> Any:
        if self._closed:
            raise RuntimeError("embedded Helix store is closed")
        if self._client is not None:
            return self._client
        with self._open_lock:
            if self._client is not None:
                return self._client
            future = self._open_future
            assert future is not None, "an open store must own a client or open future"
            try:
                self._client = future.result()
            except BaseException as exc:
                self._closed = True
                self._store_lock.release()
                if message := _public_store_rebuild_message(exc, self.path):
                    raise RuntimeError(message) from exc
                raise
            finally:
                executor = self._open_executor
                self._open_future = None
                self._open_executor = None
                if executor is not None:
                    executor.shutdown(wait=False)
            return self._client

    def _query(
        self,
        batch: Any,
        *,
        params: Any | None = None,
        values: dict[str, Any] | None = None,
        client: Any | None = None,
        await_durability: bool | None = None,
    ) -> Any:
        if self._closed:
            raise RuntimeError("embedded Helix store is closed")
        selected = client if client is not None else self._ensure_client()
        request = batch.to_query_request(params, values)
        if await_durability is None:
            return selected.query(request)
        return selected.execute(request, await_durability=await_durability)

    def _snapshot_query(self, batch: Any, client: Any | None) -> Any:
        return self._query(batch) if client is None else self._query(batch, client=client)

    def _run_buffered_queries(
        self,
        jobs: Iterable[tuple[Any, Any, dict[str, Any]]],
    ) -> None:
        """Execute a bounded number of independent buffered pages concurrently."""
        pending: set[futures.Future[Any]] = set()
        with futures.ThreadPoolExecutor(max_workers=_BUFFERED_WRITE_CONCURRENCY) as executor:
            for batch, params, values in jobs:
                pending.add(
                    executor.submit(
                        self._query,
                        batch,
                        params=params,
                        values=values,
                        await_durability=False,
                    )
                )
                if len(pending) < _BUFFERED_WRITE_CONCURRENCY:
                    continue
                completed, pending = futures.wait(
                    pending,
                    return_when=futures.FIRST_COMPLETED,
                )
                for result in completed:
                    result.result()
            for result in pending:
                result.result()

    def _validate_active_schema(self) -> None:
        """Reject stores written by an obsolete Graphify Helix schema.

        Production readers never reconstruct a graph in Python to upgrade it.
        Rebuild the project from source when an older store is encountered.
        """
        generation = self._active_generation(required=False)
        if generation is None:
            return
        meta = self._metadata(generation)
        version = meta.get("schema_version")
        if version != _SCHEMA_VERSION:
            raise RuntimeError(
                "unsupported embedded Helix graph schema: "
                f"expected {_SCHEMA_VERSION}, got {version!r}; rebuild from source"
            )

    def save(self, graph: GraphBuildData, *, state: dict[str, Any] | None = None) -> None:
        self._save_graph(graph, state=state, activate=True)

    def save_generation(self, graph: GraphBuildData, state: dict[str, Any]) -> None:
        """Atomically stage topology and every durable Graphify record together."""
        if self._read_only:
            raise RuntimeError("cannot write through a read-only embedded Helix store")
        prepared = _prepare_topology(
            graph,
            max_nodes=self._max_nodes,
            max_edges=self._max_edges,
        )
        attempt = _DeltaAttempt.FALLBACK if self._fresh else self._try_delta(prepared, state)
        if attempt is _DeltaAttempt.PUBLISHED:
            return
        self._save_prepared_graph(
            prepared,
            state=state,
            activate=True,
            native_validated=attempt is _DeltaAttempt.FALLBACK_NATIVE_VALIDATED,
        )

    def topology_matches(self, graph: GraphBuildData) -> bool:
        """Return whether build data exactly matches the active native topology."""
        generation = self._active_generation(required=False)
        if generation is None:
            return False
        expected = self._metadata(generation).get(_TOPOLOGY_CHECKSUM)
        if not isinstance(expected, str):
            return False
        prepared = _prepare_topology(
            graph,
            max_nodes=self._max_nodes,
            max_edges=self._max_edges,
        )
        return expected == prepared.checksum

    def save_data(self, payload: dict[str, Any]) -> None:
        """Stage, verify, and atomically activate a durable graph generation."""
        self._save_data(payload, activate=True)

    def _save_data(self, payload: dict[str, Any], *, activate: bool) -> str:
        if self._read_only:
            raise RuntimeError("cannot write through a read-only embedded Helix store")
        if not isinstance(payload, dict):
            raise TypeError("node-link graph payload must be a mapping")
        raw_state = payload.get(_DURABLE_STATE)
        graph = GraphBuildData.from_node_link(payload)
        return self._save_graph(graph, state=raw_state, activate=activate)

    def _save_graph(
        self,
        graph: GraphBuildData,
        *,
        state: dict[str, Any] | None,
        activate: bool,
    ) -> str:
        if self._read_only:
            raise RuntimeError("cannot write through a read-only embedded Helix store")
        prepared = _prepare_topology(
            graph,
            max_nodes=self._max_nodes,
            max_edges=self._max_edges,
        )
        return self._save_prepared_graph(prepared, state=state, activate=activate)

    def _save_prepared_graph(
        self,
        prepared: _PreparedTopology,
        *,
        state: dict[str, Any] | None,
        activate: bool,
        generation: str | None = None,
        native_validated: bool = False,
    ) -> str:
        if not native_validated:
            self._validate_proposed_native_graph(prepared)
        generation = generation or uuid.uuid4().hex
        prepared_state = self._prepare_state(state, generation)
        manifest = {
            "schema_version": _SCHEMA_VERSION,
            "directed": prepared.directed,
            "multigraph": prepared.multigraph,
            "graph": prepared.graph_attributes,
            "extras": prepared.extras,
            "node_count": len(prepared.nodes),
            "edge_count": len(prepared.edges),
            "state_record_count": len(prepared_state.records),
            "state_checksum": prepared_state.checksum,
            _ACTIVE_STATE_REVISION: generation,
            _CHECKSUM_MODE: _STREAM_CHECKSUM_MODE,
            _TOPOLOGY_CHECKSUM: prepared.checksum,
            _TOPOLOGY_REVISION: generation,
            _NODE_BUCKET_HASHES: prepared.node_bucket_hashes,
            _EDGE_BUCKET_HASHES: prepared.edge_bucket_hashes,
            **{key: generation for key in _STATE_REVISION_KEYS.values()},
            **{
                _STATE_CHECKSUM_KEYS[kind]: prepared_state.category_checksums[kind]
                for kind in _STATE_KINDS
            },
            **{
                _STATE_COUNT_KEYS[kind]: prepared_state.category_counts[kind]
                for kind in _STATE_KINDS
            },
            "checksum": _generation_checksum(prepared.checksum, prepared_state.checksum),
        }

        previous_generation = self._active_generation(required=False)
        try:
            self._stage_generation(
                generation,
                manifest,
                prepared.nodes,
                prepared.edges,
                prepared_state.encoded,
            )
            if activate:
                self._activate_generation(
                    generation,
                    create=previous_generation is None,
                    previous=previous_generation,
                    retain_previous=self._retain_rollback,
                )
        except Exception:
            try:
                self._drop_generation(generation)
            except Exception:
                pass
            raise

        if activate:
            self._fresh = False
            self._cleanup_inactive_generations()
        return generation

    def _try_delta(
        self,
        prepared: _PreparedTopology,
        state: dict[str, Any],
        *,
        native_validated: bool = False,
    ) -> _DeltaAttempt:
        """Publish a small compatible topology/state change in one transaction."""
        generation = self._active_generation(required=False)
        if generation is None or self._retain_rollback:
            return _DeltaAttempt.FALLBACK
        metadata = self._metadata(generation)
        if (
            metadata.get("directed") is not prepared.directed
            or metadata.get("multigraph") is not prepared.multigraph
            or metadata.get("graph") != prepared.graph_attributes
            or metadata.get("extras") != prepared.extras
        ):
            return _DeltaAttempt.FALLBACK

        prepared_state = self._prepare_state(state, generation)
        changed_state_kinds = [
            kind
            for kind in _STATE_KINDS
            if metadata.get(_STATE_CHECKSUM_KEYS[kind]) != prepared_state.category_checksums[kind]
            or metadata.get(_STATE_COUNT_KEYS[kind]) != prepared_state.category_counts[kind]
        ]
        topology_changed = metadata.get(_TOPOLOGY_CHECKSUM) != prepared.checksum
        if not topology_changed and not changed_state_kinds:
            return _DeltaAttempt.PUBLISHED

        delta = _TopologyDelta([], [], [], [], [])
        stored_nodes: dict[str, _StoredNode] = {}
        if topology_changed:
            if native_validated:
                candidate = self._topology_delta_candidate(generation, metadata, prepared)
            else:
                with futures.ThreadPoolExecutor(max_workers=2) as executor:
                    validation = executor.submit(self._validate_proposed_native_graph, prepared)
                    candidate = self._topology_delta_candidate(generation, metadata, prepared)
                    validation.result()
            if candidate is None:
                return (
                    _DeltaAttempt.FALLBACK
                    if native_validated
                    else _DeltaAttempt.FALLBACK_NATIVE_VALIDATED
                )
            delta, stored_nodes = candidate

        revision = uuid.uuid4().hex
        try:
            for kind in changed_state_kinds:
                self._write_state_records(
                    generation,
                    prepared_state.category_records[kind],
                    revision,
                    await_durability=False,
                )
            self._publish_delta(
                generation,
                prepared,
                prepared_state,
                metadata,
                changed_state_kinds,
                revision,
                delta,
                stored_nodes,
            )
        except Exception:
            # A storage commit can succeed even if its response is lost. Trust
            # the atomically published metadata before removing staged rows.
            published = False
            try:
                current = self._metadata(generation)
                published = current.get(_TOPOLOGY_CHECKSUM) == prepared.checksum and all(
                    current.get(_STATE_REVISION_KEYS[kind]) == revision
                    and current.get(_STATE_CHECKSUM_KEYS[kind])
                    == prepared_state.category_checksums[kind]
                    and current.get(_STATE_COUNT_KEYS[kind]) == prepared_state.category_counts[kind]
                    for kind in changed_state_kinds
                )
            except Exception:
                pass
            if published:
                self._cleanup_inactive_state_revisions()
                return _DeltaAttempt.PUBLISHED
            for kind in changed_state_kinds:
                try:
                    self._drop_state_revision(generation, revision, kind=kind)
                except Exception:
                    pass
            raise
        self._cleanup_inactive_state_revisions()
        return _DeltaAttempt.PUBLISHED

    def _topology_delta_candidate(
        self,
        generation: str,
        metadata: dict[str, Any],
        prepared: _PreparedTopology,
    ) -> tuple[_TopologyDelta, dict[str, _StoredNode]] | None:
        if not hasattr(self._helix, "NativeGraphBuilder"):
            return None
        changed_node_buckets = _changed_buckets(
            metadata.get(_NODE_BUCKET_HASHES), prepared.node_bucket_hashes
        )
        changed_edge_buckets = _changed_buckets(
            metadata.get(_EDGE_BUCKET_HASHES), prepared.edge_bucket_hashes
        )
        if changed_node_buckets is None or changed_edge_buckets is None:
            return None
        stored_nodes, stored_edges = self._stored_topology(
            generation, changed_node_buckets, changed_edge_buckets
        )
        delta = self._topology_delta(
            [node for node in prepared.nodes if node.identity_bucket in changed_node_buckets],
            [edge for edge in prepared.edges if edge.identity_bucket in changed_edge_buckets],
            stored_nodes,
            stored_edges,
        )
        added_node_ids = {node.encoded_id for node in delta.added_nodes}
        required_endpoint_ids = {
            encoded_id
            for edge in delta.added_edges
            for encoded_id in (edge.source, edge.target)
            if encoded_id not in added_node_ids and encoded_id not in stored_nodes
        }
        stored_nodes.update(self._stored_node_ids(generation, required_endpoint_ids))
        old_size = metadata.get("node_count", 0) + metadata.get("edge_count", 0)
        if (
            delta.mutation_count > _DELTA_MAX_MUTATIONS
            or delta.mutation_count / max(1, old_size) > _DELTA_MAX_RATIO
        ):
            return None
        return delta, stored_nodes

    def _stored_topology(
        self,
        generation: str,
        node_buckets: set[int],
        edge_buckets: set[int],
    ) -> tuple[dict[str, _StoredNode], dict[str, _StoredEdge]]:
        node_predicate = self._bucket_predicate(generation, node_buckets)
        edge_predicate = self._bucket_predicate(generation, edge_buckets)
        batch = self._helix.read_batch()
        returned: list[str] = []
        if node_buckets:
            returned.append("nodes")
            batch = batch.var_as(
                "nodes",
                self._helix.g()
                .n_with_label_where(_NODE_LABEL, node_predicate)
                .value_map(["$id", _STORAGE_KEY, _RECORD_HASH]),
            )
        if edge_buckets:
            returned.append("edges")
            batch = batch.var_as(
                "edges",
                self._helix.g()
                .e_where(edge_predicate)
                .value_map(["$id", _EDGE_IDENTITY, _RECORD_HASH]),
            )
        result = self._query(batch.returning(returned))
        nodes: dict[str, _StoredNode] = {}
        for raw in _rows(result, "nodes"):
            row = _properties(raw, "delta node")
            internal_id = row.get("$id")
            storage_key = row.get(_STORAGE_KEY)
            record_hash = row.get(_RECORD_HASH)
            if (
                not isinstance(internal_id, int)
                or not isinstance(storage_key, str)
                or not isinstance(record_hash, str)
                or not storage_key.startswith(f"{generation}:")
            ):
                raise RuntimeError("embedded Helix delta node is missing schema fields")
            external_key = storage_key[len(generation) + 1 :]
            if external_key in nodes:
                raise RuntimeError("embedded Helix delta nodes duplicate an identity")
            nodes[external_key] = _StoredNode(internal_id, record_hash)

        edges: dict[str, _StoredEdge] = {}
        for raw in _rows(result, "edges"):
            row = _properties(raw, "delta edge")
            internal_id = row.get("$id")
            identity = row.get(_EDGE_IDENTITY)
            record_hash = row.get(_RECORD_HASH)
            if (
                not isinstance(internal_id, int)
                or not isinstance(identity, str)
                or not isinstance(record_hash, str)
            ):
                raise RuntimeError("embedded Helix delta edge is missing schema fields")
            if identity in edges:
                raise RuntimeError("embedded Helix delta edges duplicate an identity")
            edges[identity] = _StoredEdge(internal_id, record_hash)
        return nodes, edges

    def _bucket_predicate(self, generation: str, buckets: set[int]) -> Any:
        generation_predicate = self._helix.SourcePredicate.eq(_GENERATION, generation)
        if not buckets:
            return self._helix.SourcePredicate.and_(
                (
                    generation_predicate,
                    self._helix.SourcePredicate.eq(_IDENTITY_BUCKET, -1),
                )
            )
        return self._helix.SourcePredicate.and_(
            (
                generation_predicate,
                self._helix.SourcePredicate.is_in(_IDENTITY_BUCKET, sorted(buckets)),
            )
        )

    def _stored_node_ids(self, generation: str, encoded_ids: set[str]) -> dict[str, _StoredNode]:
        if not encoded_ids:
            return {}
        storage_keys = [
            self._storage_key(generation, encoded_id) for encoded_id in sorted(encoded_ids)
        ]
        predicate = self._helix.SourcePredicate.and_(
            (
                self._helix.SourcePredicate.eq(_GENERATION, generation),
                self._helix.SourcePredicate.is_in(_STORAGE_KEY, storage_keys),
            )
        )
        result = self._query(
            self._helix.read_batch()
            .var_as(
                "nodes",
                self._helix.g()
                .n_with_label_where(_NODE_LABEL, predicate)
                .value_map(["$id", _STORAGE_KEY]),
            )
            .returning(["nodes"])
        )
        stored: dict[str, _StoredNode] = {}
        for raw in _rows(result, "nodes"):
            row = _properties(raw, "delta edge endpoint")
            internal_id = row.get("$id")
            storage_key = row.get(_STORAGE_KEY)
            if not isinstance(internal_id, int) or not isinstance(storage_key, str):
                raise RuntimeError("embedded Helix delta endpoint is missing schema fields")
            encoded_id = storage_key[len(generation) + 1 :]
            stored[encoded_id] = _StoredNode(internal_id, "")
        if stored.keys() != encoded_ids:
            raise RuntimeError("embedded Helix delta edge endpoint is missing")
        return stored

    @staticmethod
    def _topology_delta(
        prepared_nodes: list[_PreparedNode],
        prepared_edges: list[_PreparedEdge],
        stored_nodes: dict[str, _StoredNode],
        stored_edges: dict[str, _StoredEdge],
    ) -> _TopologyDelta:
        proposed_nodes = {node.encoded_id: node for node in prepared_nodes}
        proposed_edges = {edge.stable_identity: edge for edge in prepared_edges}
        changed_edges = {
            identity
            for identity in proposed_edges.keys() & stored_edges.keys()
            if proposed_edges[identity].record_hash != stored_edges[identity].record_hash
        }
        return _TopologyDelta(
            added_nodes=[
                proposed_nodes[key] for key in sorted(proposed_nodes.keys() - stored_nodes.keys())
            ],
            updated_nodes=[
                (stored_nodes[key], proposed_nodes[key])
                for key in sorted(proposed_nodes.keys() & stored_nodes.keys())
                if proposed_nodes[key].record_hash != stored_nodes[key].record_hash
            ],
            dropped_nodes=[
                stored_nodes[key] for key in sorted(stored_nodes.keys() - proposed_nodes.keys())
            ],
            added_edges=[
                proposed_edges[key]
                for key in sorted((proposed_edges.keys() - stored_edges.keys()) | changed_edges)
            ],
            dropped_edges=[
                stored_edges[key]
                for key in sorted((stored_edges.keys() - proposed_edges.keys()) | changed_edges)
            ],
        )

    def _validate_proposed_native_graph(self, prepared: _PreparedTopology) -> Any:
        kind = (
            "multidigraph"
            if prepared.directed and prepared.multigraph
            else "digraph"
            if prepared.directed
            else "multigraph"
            if prepared.multigraph
            else "graph"
        )
        builder = self._helix.NativeGraphBuilder(kind, len(prepared.nodes), len(prepared.edges))
        for offset in range(0, len(prepared.nodes), _WRITE_CHUNK_SIZE):
            builder.add_nodes(
                [
                    self._helix.GraphNode(
                        node.external_id,
                        _NODE_LABEL,
                        {_ATTRS: dict(node.attributes)},
                    )
                    for node in prepared.nodes[offset : offset + _WRITE_CHUNK_SIZE]
                ]
            )
        edges = builder.begin_edges()
        for offset in range(0, len(prepared.edges), _STAGED_EDGE_WRITE_CHUNK_SIZE):
            edges.add_edges(
                [
                    self._helix.GraphEdge(
                        self._helix.GraphEdgeId.original(edge.stable_identity),
                        edge.source_id,
                        edge.target_id,
                        edge.key if prepared.multigraph else None,
                        edge.relation,
                        edge.weight,
                        ({_ATTRS: dict(edge.stored_attributes)} if edge.stored_attributes else {}),
                    )
                    for edge in prepared.edges[offset : offset + _STAGED_EDGE_WRITE_CHUNK_SIZE]
                ]
            )
        return edges.finish(prepared.graph_attributes)

    def _publish_delta(
        self,
        generation: str,
        prepared: _PreparedTopology,
        prepared_state: _PreparedState,
        metadata: dict[str, Any],
        changed_state_kinds: list[str],
        revision: str,
        delta: _TopologyDelta,
        stored_nodes: dict[str, _StoredNode],
    ) -> None:
        batch = self._helix.write_batch()
        if delta.dropped_edges:
            batch = batch.var_as(
                "drop_delta_edges",
                self._helix.g().drop_edge_by_id(
                    self._helix.EdgeRef.ids(edge.internal_id for edge in delta.dropped_edges)
                ),
            )

        added_node_variables: dict[str, str] = {}
        for index, node in enumerate(delta.added_nodes):
            variable = f"add_delta_node_{index}"
            added_node_variables[node.encoded_id] = variable
            batch = batch.var_as(
                variable,
                self._helix.g().add_n(
                    _NODE_LABEL,
                    self._node_properties(generation, node),
                ),
            )
        for index, (stored, node) in enumerate(delta.updated_nodes):
            traversal = self._helix.g().n(self._helix.NodeRef.id(stored.internal_id))
            for key, value in self._node_properties(generation, node).items():
                traversal = traversal.set_property(key, value)
            batch = batch.var_as(f"update_delta_node_{index}", traversal)

        if delta.dropped_nodes:
            batch = batch.var_as(
                "drop_delta_nodes",
                self._helix.g()
                .n(self._helix.NodeRef.ids(node.internal_id for node in delta.dropped_nodes))
                .drop(),
            )

        for index, edge in enumerate(delta.added_edges):
            source = self._delta_node_ref(edge.source, added_node_variables, stored_nodes)
            target = self._delta_node_ref(edge.target, added_node_variables, stored_nodes)
            batch = batch.var_as(
                f"add_delta_edge_{index}",
                self._helix.g()
                .n(source)
                .add_e(
                    edge.relation,
                    target,
                    self._edge_properties(
                        generation,
                        edge,
                        multigraph=prepared.multigraph,
                    ),
                ),
            )

        state_checksum = prepared_state.checksum
        updates = {
            "node_count": len(prepared.nodes),
            "edge_count": len(prepared.edges),
            "state_record_count": len(prepared_state.records),
            "state_checksum": state_checksum,
            _TOPOLOGY_CHECKSUM: prepared.checksum,
            _NODE_BUCKET_HASHES: prepared.node_bucket_hashes,
            _EDGE_BUCKET_HASHES: prepared.edge_bucket_hashes,
            "checksum": _generation_checksum(prepared.checksum, state_checksum),
            **{
                _STATE_CHECKSUM_KEYS[kind]: prepared_state.category_checksums[kind]
                for kind in changed_state_kinds
            },
            **{
                _STATE_COUNT_KEYS[kind]: prepared_state.category_counts[kind]
                for kind in changed_state_kinds
            },
            **{_STATE_REVISION_KEYS[kind]: revision for kind in changed_state_kinds},
        }
        if delta.mutation_count:
            updates[_TOPOLOGY_REVISION] = revision
        if changed_state_kinds:
            updates[_ACTIVE_STATE_REVISION] = revision
        elif not isinstance(metadata.get(_ACTIVE_STATE_REVISION), str):
            updates[_ACTIVE_STATE_REVISION] = generation
        traversal = self._helix.g().n_with_label_where(
            _META_LABEL,
            self._helix.SourcePredicate.eq(_GENERATION, generation),
        )
        for key, value in updates.items():
            traversal = traversal.set_property(key, value)
        batch = batch.var_as("publish_delta", traversal)
        for index, kind in enumerate(changed_state_kinds):
            old_revision = _state_revision(metadata, kind)
            if old_revision is None:
                continue
            predicate = self._helix.SourcePredicate.and_(
                (
                    self._helix.SourcePredicate.eq(_GENERATION, generation),
                    self._helix.SourcePredicate.eq(_STATE_KIND, kind),
                    self._helix.SourcePredicate.eq(_STATE_REVISION, old_revision),
                )
            )
            batch = batch.var_as(
                f"drop_old_delta_state_{index}",
                self._helix.g().n_with_label_where(_STATE_LABEL, predicate).drop(),
            )
        self._query(batch, await_durability=True)

    def _delta_node_ref(
        self,
        encoded_id: str,
        added_node_variables: dict[str, str],
        stored_nodes: dict[str, _StoredNode],
    ) -> Any:
        if encoded_id in added_node_variables:
            return self._helix.NodeRef.var(added_node_variables[encoded_id])
        stored = stored_nodes.get(encoded_id)
        if stored is None:
            raise RuntimeError("delta edge references a missing persisted node")
        return self._helix.NodeRef.id(stored.internal_id)

    @staticmethod
    def _node_properties(generation: str, node: _PreparedNode) -> dict[str, Any]:
        return {
            _GENERATION: generation,
            _STORAGE_KEY: HelixEmbeddedStore._storage_key(generation, node.encoded_id),
            _EXTERNAL_KEY: _tagged_key(node.external_id),
            _ATTRS: dict(node.attributes),
            _IDENTITY_BUCKET: node.identity_bucket,
            _RECORD_HASH: node.record_hash,
            _SEARCH_LABEL: node.search_label,
            _SEARCH_TEXT: node.search_text,
        }

    @staticmethod
    def _edge_properties(
        generation: str,
        edge: _PreparedEdge,
        *,
        multigraph: bool,
    ) -> dict[str, Any]:
        properties = {
            _GENERATION: generation,
            _EDGE_IDENTITY: edge.stable_identity,
            _IDENTITY_BUCKET: edge.identity_bucket,
            _RECORD_HASH: edge.record_hash,
        }
        if multigraph:
            properties[_EDGE_KEY] = _tagged_key(edge.key)
        if edge.stored_attributes:
            properties[_ATTRS] = dict(edge.stored_attributes)
        if edge.shape[1]:
            properties[_EDGE_CONTEXT] = edge.context
        if edge.shape[2]:
            properties[_NATIVE_WEIGHT] = edge.weight
        return properties

    @staticmethod
    def _global_identity(repo: str, node_id: Any, attrs: dict[str, Any]) -> str:
        """Return a stable aggregate ID, coalescing external nodes by label."""
        label = attrs.get("label")
        if not attrs.get("source_file") and label:
            normalized = _normalize_search_text(label).strip()
            digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
            return f"external::{digest}"
        return f"{repo}::{node_id}"

    def _source_node_pages(self, generation: str) -> Any:
        predicate = self._helix.SourcePredicate.eq(_GENERATION, generation)
        offset = 0
        while True:
            traversal = (
                self._helix.g()
                .n_with_label_where(_NODE_LABEL, predicate)
                .order_by(_STORAGE_KEY, self._helix.Order.ASC)
                .skip(offset)
                .limit(_WRITE_CHUNK_SIZE)
                .project(
                    (
                        self._helix.Projection.property(_EXTERNAL_KEY),
                        self._helix.Projection.property(_ATTRS),
                        self._helix.Projection.property(_STORAGE_KEY, _ORDER),
                    )
                )
            )
            rows = _rows(
                self._query(
                    self._helix.read_batch().var_as("nodes", traversal).returning(["nodes"])
                ),
                "nodes",
            )
            if not rows:
                return
            yield rows
            if len(rows) < _WRITE_CHUNK_SIZE:
                return
            offset += len(rows)

    def _source_edge_pages(self, generation: str) -> Any:
        predicate = self._helix.SourcePredicate.eq(_GENERATION, generation)
        offset = 0
        while True:
            traversal = (
                self._helix.g()
                .e_where(predicate)
                .order_by(_EDGE_IDENTITY, self._helix.Order.ASC)
                .skip(offset)
                .limit(_WRITE_CHUNK_SIZE)
                .project(
                    (
                        self._helix.Projection.from_endpoint(_EXTERNAL_KEY, "source_external_key"),
                        self._helix.Projection.to_endpoint(_EXTERNAL_KEY, "target_external_key"),
                        self._helix.Projection.from_endpoint(_ATTRS, "source_attrs"),
                        self._helix.Projection.to_endpoint(_ATTRS, "target_attrs"),
                        self._helix.Projection.property(_EDGE_KEY),
                        self._helix.Projection.property(_ATTRS),
                        self._helix.Projection.property(_NATIVE_WEIGHT),
                        self._helix.Projection.property("$label", "relation"),
                        self._helix.Projection.property(_EDGE_IDENTITY, _ORDER),
                    )
                )
            )
            rows = _rows(
                self._query(
                    self._helix.read_batch().var_as("edges", traversal).returning(["edges"])
                ),
                "edges",
            )
            if not rows:
                return
            yield rows
            if len(rows) < _WRITE_CHUNK_SIZE:
                return
            offset += len(rows)

    def _write_aggregate_nodes(
        self,
        generation: str,
        rows: list[tuple[str, dict[str, Any], str]],
    ) -> None:
        batch = self._helix.write_batch()
        for local_index, (node_id, attrs, order) in enumerate(rows):
            encoded_id = _encode_key(node_id)
            search = _search_properties(node_id, attrs)
            variable = f"node_{local_index}"
            batch = batch.var_as(
                variable,
                self._helix.g().add_n(
                    _NODE_LABEL,
                    {
                        _GENERATION: generation,
                        _STORAGE_KEY: self._storage_key(generation, encoded_id),
                        _EXTERNAL_KEY: _tagged_key(node_id),
                        _ATTRS: attrs,
                        _ORDER: order,
                        _IDENTITY_BUCKET: _identity_bucket(encoded_id),
                        _RECORD_HASH: _record_hash(_node_topology_record(node_id, attrs)),
                        **search,
                    },
                ),
            )
        if rows:
            self._query(batch, await_durability=False)

    def _write_aggregate_edges(
        self,
        generation: str,
        rows: list[tuple[str, str, str, dict[str, Any], str]],
    ) -> None:
        batch = self._helix.write_batch()
        for local_index, (source, target, relation, attrs, order) in enumerate(rows):
            source_var = f"source_{local_index}"
            target_var = f"target_{local_index}"
            edge_var = f"edge_{local_index}"
            source_key = self._storage_key(generation, _encode_key(source))
            target_key = self._storage_key(generation, _encode_key(target))
            stable_identity = _edge_identity(
                directed=False,
                multigraph=False,
                source=_encode_key(source),
                target=_encode_key(target),
                key=_tagged_key(None),
            )
            batch = (
                batch.var_as(
                    source_var,
                    self._helix.g().n_with_label_where(
                        _NODE_LABEL,
                        self._helix.SourcePredicate.eq(_STORAGE_KEY, source_key),
                    ),
                )
                .var_as(
                    target_var,
                    self._helix.g().n_with_label_where(
                        _NODE_LABEL,
                        self._helix.SourcePredicate.eq(_STORAGE_KEY, target_key),
                    ),
                )
                .var_as(
                    edge_var,
                    self._helix.g()
                    .n(self._helix.NodeRef.var(source_var))
                    .add_e(
                        relation,
                        self._helix.NodeRef.var(target_var),
                        {
                            _GENERATION: generation,
                            _EDGE_KEY: _tagged_key(None),
                            _ATTRS: attrs,
                            _ORDER: order,
                            _EDGE_IDENTITY: stable_identity,
                            _IDENTITY_BUCKET: _identity_bucket(stable_identity),
                            _RECORD_HASH: _record_hash(
                                _edge_topology_record(
                                    source,
                                    target,
                                    None,
                                    relation,
                                    attrs,
                                    multigraph=False,
                                )
                            ),
                            **(
                                {_EDGE_CONTEXT: attrs["context"]}
                                if isinstance(attrs.get("context"), str) and attrs["context"]
                                else {}
                            ),
                            **(
                                {_NATIVE_WEIGHT: float(attrs["weight"])}
                                if isinstance(attrs.get("weight"), (int, float))
                                and not isinstance(attrs.get("weight"), bool)
                                and math.isfinite(float(attrs["weight"]))
                                else {}
                            ),
                        },
                    ),
                )
            )
        if rows:
            self._query(batch, await_durability=False)

    def save_aggregate_sources(
        self,
        sources: list[tuple[Path, str, str]],
        state: dict[str, Any],
    ) -> None:
        """Stream project generations into one staged aggregate generation.

        Source topology is read in bounded public-query pages and written
        directly to Helix. No Python graph, adjacency structure, or full ID map
        is constructed.
        """
        if self._read_only:
            raise RuntimeError("cannot write through a read-only embedded Helix store")
        generation = uuid.uuid4().hex
        previous_generation = self._active_generation(required=False)
        checksum = _TopologyStreamChecksum(directed=False, multigraph=False, graph={}, extras={})
        external_ids: set[str] = set()
        node_count = 0
        edge_count = 0
        try:
            for source_path, source_generation, repo in sources:
                if source_path.resolve() == self.path:
                    raise ValueError("aggregate destination cannot also be a source")
                with HelixEmbeddedStore(source_path, read_only=True) as source:
                    source._metadata(source_generation)
                    for page in source._source_node_pages(source_generation):
                        output: list[tuple[str, dict[str, Any], str]] = []
                        for raw in page:
                            row = _properties(raw, "aggregate source node")
                            old_id = _decode_identity(row.get(_EXTERNAL_KEY))
                            attrs = row.get(_ATTRS, {})
                            if not isinstance(attrs, dict):
                                raise RuntimeError("aggregate source node has invalid attributes")
                            node_id = self._global_identity(repo, old_id, attrs)
                            if node_id.startswith("external::"):
                                if node_id in external_ids:
                                    continue
                                external_ids.add(node_id)
                            projected = dict(attrs)
                            projected["repo"] = repo
                            projected.setdefault("local_id", old_id)
                            output.append((node_id, projected, _encode_key(node_id)))
                            checksum.node(_node_topology_record(node_id, projected))
                            node_count += 1
                        self._write_aggregate_nodes(generation, output)
                    for page in source._source_edge_pages(source_generation):
                        output_edges: list[tuple[str, str, str, dict[str, Any], str]] = []
                        for raw in page:
                            row = _properties(raw, "aggregate source edge")
                            source_attrs = row.get("source_attrs")
                            target_attrs = row.get("target_attrs")
                            attrs = row.get(_ATTRS, {})
                            relation = row.get("relation")
                            if (
                                not isinstance(source_attrs, dict)
                                or not isinstance(target_attrs, dict)
                                or not isinstance(attrs, dict)
                                or not isinstance(relation, str)
                            ):
                                raise RuntimeError(
                                    "aggregate source edge has invalid schema fields"
                                )
                            old_source = _decode_identity(row.get("source_external_key"))
                            old_target = _decode_identity(row.get("target_external_key"))
                            source_id = self._global_identity(repo, old_source, source_attrs)
                            target_id = self._global_identity(repo, old_target, target_attrs)
                            if source_id == target_id:
                                continue
                            projected_edge = dict(attrs)
                            weight = row.get(_NATIVE_WEIGHT)
                            if isinstance(weight, (int, float)) and not isinstance(weight, bool):
                                projected_edge.setdefault("weight", float(weight))
                            stable_identity = _edge_identity(
                                directed=False,
                                multigraph=False,
                                source=_encode_key(source_id),
                                target=_encode_key(target_id),
                                key=_tagged_key(None),
                            )
                            output_edges.append(
                                (
                                    source_id,
                                    target_id,
                                    relation,
                                    projected_edge,
                                    stable_identity,
                                )
                            )
                            checksum.edge(
                                _edge_topology_record(
                                    source_id,
                                    target_id,
                                    None,
                                    relation,
                                    projected_edge,
                                    multigraph=False,
                                )
                            )
                            edge_count += 1
                        self._write_aggregate_edges(generation, output_edges)

            encoded_state_value = copy.deepcopy(state)
            build_state = encoded_state_value.setdefault("build", {})
            incremental_state = encoded_state_value.setdefault("incremental", {})
            if not isinstance(build_state, dict) or not isinstance(incremental_state, dict):
                raise TypeError("durable build and incremental state must be mappings")
            build_state["generation"] = generation
            incremental_state["last_successful_generation"] = generation
            encoded_state = _json_value(
                _encode_state_value(encoded_state_value), "durable graph state"
            )
            state_records = self._state_records(encoded_state)
            category_records = {
                kind: [record for record in state_records if record[0] == kind]
                for kind in _STATE_KINDS
            }
            category_checksums = {
                kind: _state_category_checksum(category_records[kind]) for kind in _STATE_KINDS
            }
            state_checksum = _combined_state_checksum(category_checksums)
            topology_checksum = checksum.hexdigest()
            manifest = {
                "schema_version": _SCHEMA_VERSION,
                "directed": False,
                "multigraph": False,
                "graph": {},
                "extras": {},
                "node_count": node_count,
                "edge_count": edge_count,
                "state_record_count": len(state_records),
                "state_checksum": state_checksum,
                _ACTIVE_STATE_REVISION: generation,
                _CHECKSUM_MODE: _STREAM_CHECKSUM_MODE,
                _TOPOLOGY_CHECKSUM: topology_checksum,
                _TOPOLOGY_REVISION: generation,
                _NODE_BUCKET_HASHES: [""] * _IDENTITY_BUCKET_COUNT,
                _EDGE_BUCKET_HASHES: [""] * _IDENTITY_BUCKET_COUNT,
                **{key: generation for key in _STATE_REVISION_KEYS.values()},
                **{_STATE_CHECKSUM_KEYS[kind]: category_checksums[kind] for kind in _STATE_KINDS},
                **{_STATE_COUNT_KEYS[kind]: len(category_records[kind]) for kind in _STATE_KINDS},
                "checksum": _generation_checksum(topology_checksum, state_checksum),
                _GENERATION: generation,
            }
            self._query(
                self._helix.write_batch().var_as(
                    "meta", self._helix.g().add_n(_META_LABEL, manifest)
                ),
                await_durability=False,
            )
            self._write_state_records(
                generation,
                state_records,
                generation,
                await_durability=False,
            )
            self._activate_generation(
                generation,
                create=previous_generation is None,
                previous=previous_generation,
                retain_previous=self._retain_rollback,
            )
        except Exception:
            try:
                self._drop_generation(generation)
            except Exception:
                pass
            raise
        self._fresh = False
        self._cleanup_inactive_generations()

    @contextmanager
    def staged_graph(self, graph: GraphBuildData):
        """Yield a validated native proposal before any full-topology writes."""
        prepared = _prepare_topology(
            graph,
            max_nodes=self._max_nodes,
            max_edges=self._max_edges,
        )
        generation = self._active_generation(required=False)
        if generation is not None and not self._retain_rollback:
            metadata = self._metadata(generation)
            compatible = (
                metadata.get("directed") is prepared.directed
                and metadata.get("multigraph") is prepared.multigraph
                and metadata.get("graph") == prepared.graph_attributes
                and metadata.get("extras") == prepared.extras
            )
            topology_changed = metadata.get(_TOPOLOGY_CHECKSUM) != prepared.checksum
            delta_candidate = (
                self._topology_delta_candidate(generation, metadata, prepared)
                if compatible and topology_changed
                else None
            )
            if compatible and (not topology_changed or delta_candidate is not None):
                staged = _StagedDeltaGraph(
                    generation=generation,
                    state={},
                    metadata=metadata,
                    store_path=self.path,
                    _phase=_StagedProposal(
                        graph=(
                            self._validate_proposed_native_graph(prepared)
                            if topology_changed
                            else self.native_graph(generation, metadata=metadata)
                        ),
                        prepared=prepared,
                    ),
                )
                del prepared
                yield staged
                return

        generation = uuid.uuid4().hex
        staged = _StagedFullGraph(
            generation=generation,
            state={},
            metadata={},
            store_path=self.path,
            _phase=_StagedProposal(
                graph=self._validate_proposed_native_graph(prepared),
                prepared=prepared,
            ),
        )
        del prepared
        yield staged

    def activate_staged(
        self,
        staged: LoadedGraph | _StagedDeltaGraph | _StagedFullGraph,
        state: dict[str, Any],
    ) -> LoadedGraph:
        """Attach durable state, verify, and activate an existing staged topology."""
        if self._read_only:
            raise RuntimeError("cannot activate through a read-only embedded Helix store")
        generation = staged.generation
        if staged.store_path != self.path:
            raise ValueError("staged graph belongs to a different embedded Helix store")
        if isinstance(staged, _StagedDeltaGraph):
            if self._active_generation() != generation:
                raise RuntimeError("active generation changed during native delta analysis")
            native = staged.graph
            prepared = staged.prepared
            if (
                self._try_delta(prepared, state, native_validated=True)
                is not _DeltaAttempt.PUBLISHED
            ):
                raise RuntimeError("native delta became ineligible during analysis")
            topology_checksum = prepared.checksum
            staged.mark_published()
            del prepared
            return self._load_generation_snapshot(
                generation,
                attach_query=True,
                native=native,
                expected_topology_checksum=topology_checksum,
            )
        if isinstance(staged, _StagedFullGraph):
            native = staged.graph
            prepared = staged.prepared
            self._save_prepared_graph(
                prepared,
                state=state,
                activate=True,
                generation=generation,
                native_validated=True,
            )
            topology_checksum = prepared.checksum
            staged.mark_published()
            del prepared
            return self._load_generation_snapshot(
                generation,
                attach_query=True,
                native=native,
                expected_topology_checksum=topology_checksum,
            )
        if self._metadata(generation).get("state_record_count") != 0:
            raise RuntimeError("staged Helix generation has already been finalized")

        encoded = copy.deepcopy(state)
        build_state = encoded.setdefault("build", {})
        incremental_state = encoded.setdefault("incremental", {})
        if not isinstance(build_state, dict) or not isinstance(incremental_state, dict):
            raise TypeError("durable build and incremental state must be mappings")
        build_state["generation"] = generation
        incremental_state["last_successful_generation"] = generation
        encoded_state = _json_value(_encode_state_value(encoded), "durable graph state")
        records = self._state_records(encoded_state)
        category_records = {
            kind: [record for record in records if record[0] == kind] for kind in _STATE_KINDS
        }
        category_checksums = {
            kind: _state_category_checksum(category_records[kind]) for kind in _STATE_KINDS
        }
        previous_generation = self._active_generation(required=False)
        try:
            meta = self._metadata(generation)
            topology_checksum = meta.get(_TOPOLOGY_CHECKSUM)
            if not isinstance(topology_checksum, str):
                raise RuntimeError("embedded Helix metadata has no topology checksum")
            self._write_state_records(
                generation,
                records,
                generation,
                await_durability=False,
            )
            written = self._state_records_from_rows(
                self._read_state_rows(generation, revision=generation)
            )
            state_checksum = _combined_state_checksum(category_checksums)
            if written != records:
                raise RuntimeError("embedded Helix staged state failed checksum verification")
            updates = {
                "state_record_count": len(records),
                "state_checksum": state_checksum,
                "checksum": _generation_checksum(topology_checksum, state_checksum),
                **{_STATE_CHECKSUM_KEYS[kind]: category_checksums[kind] for kind in _STATE_KINDS},
                **{_STATE_COUNT_KEYS[kind]: len(category_records[kind]) for kind in _STATE_KINDS},
            }
            traversal = self._helix.g().n_with_label_where(
                _META_LABEL,
                self._helix.SourcePredicate.eq(_GENERATION, generation),
            )
            for key, value in updates.items():
                traversal = traversal.set_property(key, value)
            self._query(
                self._helix.write_batch().var_as("finalize", traversal),
                await_durability=False,
            )
            self._activate_generation(
                generation,
                create=previous_generation is None,
                previous=previous_generation,
                retain_previous=self._retain_rollback,
            )
        except Exception:
            self._drop_generation(generation)
            raise
        self._cleanup_inactive_generations()
        return self.load_generation(generation)

    def replace_state(
        self,
        state: dict[str, Any],
        *,
        previous_state: dict[str, Any] | None = None,
        snapshot: LoadedGraph | None = None,
    ) -> None:
        """Atomically replace only changed native-state categories."""
        if self._read_only:
            raise RuntimeError("cannot write through a read-only embedded Helix store")
        if snapshot is not None:
            if snapshot.store_path != self.path:
                raise ValueError("native snapshot belongs to a different Helix store")
            generation = snapshot.generation
            meta = dict(snapshot.metadata)
        else:
            generation = self.active_generation
            meta = self._metadata(generation)
        topology_checksum = meta.get(_TOPOLOGY_CHECKSUM)
        if not isinstance(topology_checksum, str):
            raise RuntimeError("embedded Helix metadata has invalid state revision fields")

        current = previous_state if previous_state is not None else self.read_state()
        for value in (current, state):
            if not isinstance(value.get("build", {}), dict) or not isinstance(
                value.get("incremental", {}), dict
            ):
                raise TypeError("durable build and incremental state must be mappings")
        changed_kinds = [
            kind
            for kind in _STATE_KINDS
            if _state_category_value(current, kind, generation)
            != _state_category_value(state, kind, generation)
        ]
        if not changed_kinds:
            return

        revision = uuid.uuid4().hex
        records_by_kind = {
            kind: self._state_records_for_kind(state, generation, kind) for kind in changed_kinds
        }
        changed_records = [record for kind in changed_kinds for record in records_by_kind[kind]]
        category_checksums: dict[str, str] = {}
        category_counts: dict[str, int] = {}
        for kind in _STATE_KINDS:
            if kind in records_by_kind:
                category_checksums[kind] = _state_category_checksum(records_by_kind[kind])
                category_counts[kind] = len(records_by_kind[kind])
                continue
            checksum = meta.get(_STATE_CHECKSUM_KEYS[kind])
            count = meta.get(_STATE_COUNT_KEYS[kind])
            if not isinstance(checksum, str) or not isinstance(count, int):
                raise RuntimeError("embedded Helix metadata has invalid state category fields")
            category_checksums[kind] = checksum
            category_counts[kind] = count
        state_checksum = _combined_state_checksum(category_checksums)
        state_record_count = sum(category_counts.values())
        try:
            traversal = self._helix.g().n_with_label_where(
                _META_LABEL,
                self._helix.SourcePredicate.eq(_GENERATION, generation),
            )
            updates = {
                "state_record_count": state_record_count,
                "state_checksum": state_checksum,
                "checksum": _generation_checksum(topology_checksum, state_checksum),
                **{_STATE_REVISION_KEYS[kind]: revision for kind in changed_kinds},
                **{_STATE_CHECKSUM_KEYS[kind]: category_checksums[kind] for kind in changed_kinds},
                **{_STATE_COUNT_KEYS[kind]: category_counts[kind] for kind in changed_kinds},
            }
            for key, value in updates.items():
                traversal = traversal.set_property(key, value)
            transaction_size = len(changed_records) + len(changed_kinds) + 1
            atomic_write = transaction_size <= _STATE_WRITE_CHUNK_SIZE
            batch = self._helix.write_batch()
            if atomic_write:
                for index, record in enumerate(changed_records):
                    batch = batch.var_as(
                        f"new_state_{index}",
                        self._helix.g().add_n(
                            _STATE_LABEL,
                            self._state_record_properties(generation, revision, record),
                        ),
                    )
            else:
                self._write_state_records(
                    generation,
                    changed_records,
                    revision,
                    await_durability=False,
                )
            batch = batch.var_as("activate_state", traversal)
            for index, kind in enumerate(changed_kinds):
                old_revision = _state_revision(meta, kind)
                if old_revision is None:
                    continue
                variable = f"drop_old_state_{index}"
                predicate = self._helix.SourcePredicate.and_(
                    (
                        self._helix.SourcePredicate.eq(_GENERATION, generation),
                        self._helix.SourcePredicate.eq(_STATE_REVISION, old_revision),
                        self._helix.SourcePredicate.eq(_STATE_KIND, kind),
                    )
                )
                batch = batch.var_as(
                    variable,
                    self._helix.g().n_with_label_where(_STATE_LABEL, predicate).drop(),
                )
            self._query(batch, await_durability=True)
        except Exception:
            for kind in changed_kinds:
                self._drop_state_revision(generation, revision, kind=kind)
            raise

    @staticmethod
    def _storage_key(generation: str, external_key: str) -> str:
        return f"{generation}:{external_key}"

    @staticmethod
    def _state_records(
        state: dict[str, Any] | None,
    ) -> list[tuple[str, str, Any, int]]:
        if state is None:
            return []
        records: list[tuple[str, str, Any, int]] = []
        order = 0
        for section, payload in state.items():
            if section == "communities" and isinstance(payload, list):
                if not payload:
                    records.append(("section", section, [], order))
                    order += 1
                for index, community in enumerate(payload):
                    records.append(("community", str(index), community, order))
                    order += 1
                continue
            if section == "incremental" and isinstance(payload, dict):
                files = payload.get("files", {})
                if not isinstance(files, dict):
                    raise TypeError("incremental durable state files must be a mapping")
                extraction_cache = payload.get("extraction_cache", {})
                if not isinstance(extraction_cache, dict):
                    raise TypeError("incremental durable state extraction cache must be a mapping")
                metadata = {
                    key: value
                    for key, value in payload.items()
                    if key not in {"files", "extraction_cache"}
                }
                if "files" in payload and not files:
                    metadata["files"] = {}
                if "extraction_cache" in payload and not extraction_cache:
                    metadata["extraction_cache"] = {}
                records.append(("section", section, metadata, order))
                order += 1
                for path, file_state in files.items():
                    if not isinstance(path, str):
                        raise TypeError("incremental durable state file paths must be strings")
                    records.append(("file", path, file_state, order))
                    order += 1
                for cache_key, cache_value in extraction_cache.items():
                    if not isinstance(cache_key, str):
                        raise TypeError("incremental durable extraction cache keys must be strings")
                    records.append(("cache", cache_key, cache_value, order))
                    order += 1
                continue
            records.append(("section", section, payload, order))
            order += 1
        kind_order = {kind: 0 for kind in _STATE_KINDS}
        normalized: list[tuple[str, str, Any, int]] = []
        for kind, key, payload, _ in records:
            normalized.append((kind, key, payload, kind_order[kind]))
            kind_order[kind] += 1
        kind_rank = {kind: index for index, kind in enumerate(_STATE_KINDS)}
        normalized.sort(key=lambda item: (kind_rank[item[0]], item[3]))
        return normalized

    def _prepare_state(self, state: dict[str, Any] | None, generation: str) -> _PreparedState:
        encoded_state: dict[str, Any] | None = None
        if state is not None:
            if not isinstance(state, dict):
                raise TypeError("durable graph state must be a mapping")
            durable_state = copy.deepcopy(state)
            build_state = durable_state.setdefault("build", {})
            incremental_state = durable_state.setdefault("incremental", {})
            if not isinstance(build_state, dict) or not isinstance(incremental_state, dict):
                raise TypeError("durable build and incremental state sections must be mappings")
            build_state["generation"] = generation
            incremental_state["last_successful_generation"] = generation
            encoded_state = _json_value(_encode_state_value(durable_state), "durable graph state")
        records = self._state_records(encoded_state)
        category_records = {
            kind: [record for record in records if record[0] == kind] for kind in _STATE_KINDS
        }
        category_checksums = {
            kind: _state_category_checksum(category_records[kind]) for kind in _STATE_KINDS
        }
        return _PreparedState(
            encoded=encoded_state,
            records=records,
            category_records=category_records,
            category_checksums=category_checksums,
            category_counts={kind: len(category_records[kind]) for kind in _STATE_KINDS},
            checksum=_combined_state_checksum(category_checksums),
        )

    def _state_records_for_kind(
        self, state: dict[str, Any], generation: str, kind: str
    ) -> list[tuple[str, str, Any, int]]:
        value = _state_category_value(state, kind, generation)
        if kind == "section":
            partial = value
        elif kind == "community":
            partial = {"communities": value}
        else:
            partial = {"incremental": {"files" if kind == "file" else "extraction_cache": value}}
        encoded = _json_value(_encode_state_value(partial), f"durable {kind} state")
        return [record for record in self._state_records(encoded) if record[0] == kind]

    def _stage_generation(
        self,
        generation: str,
        manifest: dict[str, Any],
        nodes: list[_PreparedNode],
        edges: list[_PreparedEdge],
        state: dict[str, Any] | None,
    ) -> None:
        metadata = {**manifest, _GENERATION: generation}
        multigraph = bool(manifest.get("multigraph"))
        self._query(
            self._helix.write_batch().var_as("meta", self._helix.g().add_n(_META_LABEL, metadata)),
            await_durability=False,
        )

        row_params = self._helix.define_params(
            {"rows": self._helix.param.array(self._helix.param.object())}
        )
        node_body = self._helix.write_batch().var_as(
            "node",
            self._helix.g().add_n(
                _NODE_LABEL,
                {
                    _GENERATION: generation,
                    _STORAGE_KEY: self._helix.PropertyInput.param(_STORAGE_KEY),
                    _EXTERNAL_KEY: self._helix.PropertyInput.param(_EXTERNAL_KEY),
                    _ATTRS: self._helix.PropertyInput.param(_ATTRS),
                    _IDENTITY_BUCKET: self._helix.PropertyInput.param(_IDENTITY_BUCKET),
                    _SEARCH_LABEL: self._helix.PropertyInput.param(_SEARCH_LABEL),
                    _SEARCH_TEXT: self._helix.PropertyInput.param(_SEARCH_TEXT),
                    _RECORD_HASH: self._helix.PropertyInput.param(_RECORD_HASH),
                },
            ),
        )
        node_batch = self._helix.write_batch().for_each_param("rows", node_body)
        node_pages = (
            (
                node_batch,
                row_params,
                {
                    "rows": [
                        {
                            _STORAGE_KEY: self._storage_key(generation, node.encoded_id),
                            _EXTERNAL_KEY: _tagged_key(node.external_id),
                            _ATTRS: dict(node.attributes),
                            _IDENTITY_BUCKET: node.identity_bucket,
                            _RECORD_HASH: node.record_hash,
                            _SEARCH_LABEL: node.search_label,
                            _SEARCH_TEXT: node.search_text,
                        }
                        for node in nodes[offset : offset + _WRITE_CHUNK_SIZE]
                    ]
                },
            )
            for offset in range(0, len(nodes), _WRITE_CHUNK_SIZE)
        )
        self._run_buffered_queries(node_pages)

        node_ids: dict[str, int] = {}
        if nodes:
            predicate = self._helix.SourcePredicate.eq(_GENERATION, generation)
            result = self._query(
                self._helix.read_batch()
                .var_as(
                    "nodes",
                    self._helix.g()
                    .n_with_label_where(_NODE_LABEL, predicate)
                    .value_map(["$id", _STORAGE_KEY]),
                )
                .returning(["nodes"])
            )
            for raw in _rows(result, "nodes"):
                row = _properties(raw, "staged node identity")
                storage_key = row.get(_STORAGE_KEY)
                node_id = row.get("$id")
                if isinstance(storage_key, str) and isinstance(node_id, int):
                    node_ids[storage_key] = node_id

        if len(node_ids) != len(nodes):
            raise RuntimeError("embedded Helix staged node count does not match the input graph")

        groups: dict[tuple[str, bool, bool, bool], list[_PreparedEdge]] = {}
        for edge in edges:
            groups.setdefault(edge.shape, []).append(edge)

        def edge_pages() -> Iterator[tuple[Any, Any, dict[str, Any]]]:
            for (relation, has_context, has_weight, has_attributes), group in groups.items():
                properties = {
                    _GENERATION: generation,
                    _EDGE_IDENTITY: self._helix.PropertyInput.param(_EDGE_IDENTITY),
                    _IDENTITY_BUCKET: self._helix.PropertyInput.param(_IDENTITY_BUCKET),
                    _RECORD_HASH: self._helix.PropertyInput.param(_RECORD_HASH),
                }
                if multigraph:
                    properties[_EDGE_KEY] = self._helix.PropertyInput.param(_EDGE_KEY)
                if has_attributes:
                    properties[_ATTRS] = self._helix.PropertyInput.param(_ATTRS)
                if has_context:
                    properties[_EDGE_CONTEXT] = self._helix.PropertyInput.param(_EDGE_CONTEXT)
                if has_weight:
                    properties[_NATIVE_WEIGHT] = self._helix.PropertyInput.param(_NATIVE_WEIGHT)
                edge_body = self._helix.write_batch().var_as(
                    "edge",
                    self._helix.g()
                    .n(self._helix.NodeRef.param("source"))
                    .add_e(
                        relation,
                        self._helix.NodeRef.param("target"),
                        properties,
                    ),
                )
                edge_batch = self._helix.write_batch().for_each_param("rows", edge_body)
                for offset in range(0, len(group), _STAGED_EDGE_WRITE_CHUNK_SIZE):
                    rows = []
                    for edge in group[offset : offset + _STAGED_EDGE_WRITE_CHUNK_SIZE]:
                        row = {
                            "source": [node_ids[self._storage_key(generation, edge.source)]],
                            "target": [node_ids[self._storage_key(generation, edge.target)]],
                            _EDGE_IDENTITY: edge.stable_identity,
                            _IDENTITY_BUCKET: edge.identity_bucket,
                            _RECORD_HASH: edge.record_hash,
                        }
                        if multigraph:
                            row[_EDGE_KEY] = _tagged_key(edge.key)
                        if has_attributes:
                            row[_ATTRS] = dict(edge.stored_attributes)
                        if has_context:
                            row[_EDGE_CONTEXT] = edge.context
                        if has_weight:
                            row[_NATIVE_WEIGHT] = edge.weight
                        rows.append(row)
                    yield edge_batch, row_params, {"rows": rows}

        self._run_buffered_queries(edge_pages())

        self._write_state_records(
            generation,
            self._state_records(state),
            generation,
            await_durability=False,
        )
        # The publication fence can transiently duplicate SlateDB's pending
        # write buffers. These canonical records have already been staged and
        # are intentionally consumed here so they do not overlap that peak.
        nodes.clear()
        edges.clear()

    def _write_state_records(
        self,
        generation: str,
        state_records: list[tuple[str, str, Any, int]],
        revision: str,
        *,
        await_durability: bool | None = None,
    ) -> None:
        # State rows are independent native records. A fixed planner-safe batch
        # size keeps transaction cost bounded without exception-driven retries.
        for offset in range(0, len(state_records), _STATE_WRITE_CHUNK_SIZE):
            self._write_state_chunk(
                generation,
                state_records[offset : offset + _STATE_WRITE_CHUNK_SIZE],
                revision,
                await_durability=await_durability,
            )

    def _write_state_chunk(
        self,
        generation: str,
        records: list[tuple[str, str, Any, int]],
        revision: str,
        *,
        await_durability: bool | None = None,
    ) -> None:
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for record in records:
            properties = self._state_record_properties(generation, revision, record)
            groups.setdefault(tuple(properties), []).append(properties)
        row_params = self._helix.define_params(
            {"rows": self._helix.param.array(self._helix.param.object())}
        )
        for property_names, rows in groups.items():
            body = self._helix.write_batch().var_as(
                "state",
                self._helix.g().add_n(
                    _STATE_LABEL,
                    {name: self._helix.PropertyInput.param(name) for name in property_names},
                ),
            )
            batch = self._helix.write_batch().for_each_param("rows", body)
            self._query(
                batch,
                params=row_params,
                values={"rows": rows},
                await_durability=await_durability,
            )

    @staticmethod
    def _state_record_properties(
        generation: str,
        revision: str,
        record: tuple[str, str, Any, int],
    ) -> dict[str, Any]:
        kind, key, payload, order = record
        properties = {
            _GENERATION: generation,
            _STATE_REVISION: revision,
            _STATE_KIND: kind,
            _STATE_KEY: key,
            _STATE_PAYLOAD: "json:"
            + json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ),
            _ORDER: order,
        }
        if kind == "community" and isinstance(payload, dict):
            for name in (
                "id",
                "name",
                "naming_source",
                "signature",
                "cohesion",
            ):
                if name in payload and payload[name] is not None:
                    properties[name] = payload[name]
        elif kind == "file" and isinstance(payload, dict):
            properties["relative_path"] = key
            for name in ("content_hash", "semantic_hash"):
                if name in payload:
                    properties[name] = payload[name]
        return properties

    def _active_generation(self, *, required: bool = True, client: Any | None = None) -> str | None:
        batch = (
            self._helix.read_batch()
            .var_as(
                "control",
                self._helix.g()
                .n_with_label_where(
                    _CONTROL_LABEL,
                    self._helix.SourcePredicate.eq(_CONTROL_KEY, "active"),
                )
                .value_map(),
            )
            .returning(["control"])
        )
        rows = _rows(self._snapshot_query(batch, client), "control")
        if not rows:
            if required:
                raise RuntimeError("embedded Helix graph has no active generation")
            return None
        if len(rows) != 1:
            raise RuntimeError("embedded Helix graph has duplicated control rows")
        generation = _properties(rows[0], "control").get(_ACTIVE_GENERATION)
        if not isinstance(generation, str):
            raise RuntimeError("embedded Helix graph control row has no active generation")
        return generation

    def _activate_generation(
        self,
        generation: str,
        *,
        create: bool,
        previous: str | None,
        retain_previous: bool,
    ) -> None:
        if create:
            traversal = self._helix.g().add_n(
                _CONTROL_LABEL,
                {_CONTROL_KEY: "active", _ACTIVE_GENERATION: generation},
            )
        else:
            traversal = (
                self._helix.g()
                .n_with_label_where(
                    _CONTROL_LABEL,
                    self._helix.SourcePredicate.eq(_CONTROL_KEY, "active"),
                )
                .set_property(_ACTIVE_GENERATION, generation)
            )
            if retain_previous and previous is not None:
                traversal = traversal.set_property(_PREVIOUS_GENERATION, previous)
            else:
                traversal = traversal.remove_property(_PREVIOUS_GENERATION)
        batch = self._helix.write_batch().var_as("activate", traversal)
        self._query(batch, await_durability=True)

    def rollback(self) -> LoadedGraph:
        """Activate the explicitly retained previous generation."""
        if self._read_only:
            raise RuntimeError("cannot roll back through a read-only embedded Helix store")
        control = self._control_properties()
        assert control is not None
        active = control.get(_ACTIVE_GENERATION)
        previous = control.get(_PREVIOUS_GENERATION)
        if not isinstance(active, str) or not isinstance(previous, str):
            raise RuntimeError(
                "no rollback generation was retained; rebuild or update with --retain-rollback"
            )
        self.load_generation(previous, attach_query=False)
        self._activate_generation(
            previous,
            create=False,
            previous=active,
            retain_previous=True,
        )
        self._cleanup_inactive_generations()
        return self.load_generation(previous)

    def _drop_generation(self, generation: str) -> None:
        predicate = self._helix.SourcePredicate.eq(_GENERATION, generation)
        batch = (
            self._helix.write_batch()
            .var_as(
                "drop_edges",
                self._helix.g().e_where(predicate).drop(),
            )
            .var_as(
                "drop_nodes",
                self._helix.g().n_with_label_where(_NODE_LABEL, predicate).drop(),
            )
            .var_as(
                "drop_meta",
                self._helix.g().n_with_label_where(_META_LABEL, predicate).drop(),
            )
            .var_as(
                "drop_state",
                self._helix.g().n_with_label_where(_STATE_LABEL, predicate).drop(),
            )
        )
        self._query(batch)

    def _drop_state_revision(
        self, generation: str, revision: str, *, kind: str | None = None
    ) -> None:
        predicates = [
            self._helix.SourcePredicate.eq(_GENERATION, generation),
            self._helix.SourcePredicate.eq(_STATE_REVISION, revision),
        ]
        if kind is not None:
            predicates.append(self._helix.SourcePredicate.eq(_STATE_KIND, kind))
        predicate = self._helix.SourcePredicate.and_(predicates)
        self._query(
            self._helix.write_batch().var_as(
                "drop_state_revision",
                self._helix.g().n_with_label_where(_STATE_LABEL, predicate).drop(),
            )
        )

    def _cleanup_inactive_generations(self) -> None:
        active = self._active_generation(required=False)
        retained = {active} if active is not None else set()
        control = self._control_properties(required=False)
        previous = control.get(_PREVIOUS_GENERATION) if control is not None else None
        if isinstance(previous, str):
            retained.add(previous)
        batch = (
            self._helix.read_batch()
            .var_as("meta", self._helix.g().n_with_label(_META_LABEL).value_map())
            .returning(["meta"])
        )
        generations = {
            generation
            for raw in _rows(self._query(batch), "meta")
            if isinstance(generation := _properties(raw, "metadata").get(_GENERATION), str)
        }
        for generation in generations:
            if generation not in retained:
                self._drop_generation(generation)

    def _cleanup_inactive_state_revisions(self) -> None:
        batch = (
            self._helix.read_batch()
            .var_as("meta", self._helix.g().n_with_label(_META_LABEL).value_map())
            .returning(["meta"])
        )
        for raw in _rows(self._query(batch), "meta"):
            row = _properties(raw, "metadata")
            generation = row.get(_GENERATION)
            if not isinstance(generation, str):
                continue
            for kind in _STATE_KINDS:
                revision = _state_revision(row, kind)
                if revision is None:
                    continue
                predicate = self._helix.SourcePredicate.and_(
                    (
                        self._helix.SourcePredicate.eq(_GENERATION, generation),
                        self._helix.SourcePredicate.eq(_STATE_KIND, kind),
                        self._helix.SourcePredicate.neq(_STATE_REVISION, revision),
                    )
                )
                self._query(
                    self._helix.write_batch().var_as(
                        "drop_inactive_state",
                        self._helix.g().n_with_label_where(_STATE_LABEL, predicate).drop(),
                    )
                )

    def _control_properties(
        self, *, required: bool = True, client: Any | None = None
    ) -> dict[str, Any] | None:
        batch = (
            self._helix.read_batch()
            .var_as(
                "control",
                self._helix.g()
                .n_with_label_where(
                    _CONTROL_LABEL,
                    self._helix.SourcePredicate.eq(_CONTROL_KEY, "active"),
                )
                .value_map(),
            )
            .returning(["control"])
        )
        rows = _rows(self._snapshot_query(batch, client), "control")
        if not rows:
            if required:
                raise RuntimeError("embedded Helix graph has no active generation")
            return None
        if len(rows) != 1:
            raise RuntimeError("embedded Helix graph has duplicated control rows")
        return _properties(rows[0], "control")

    def _read_rows(self, generation: str) -> tuple[dict[str, Any], list[Any], list[Any], list[Any]]:
        predicate = self._helix.SourcePredicate.eq(_GENERATION, generation)
        batch = (
            self._helix.read_batch()
            .var_as(
                "meta",
                self._helix.g().n_with_label_where(_META_LABEL, predicate).value_map(),
            )
            .var_as(
                "nodes",
                self._helix.g().n_with_label_where(_NODE_LABEL, predicate).value_map(),
            )
            .var_as(
                "edges",
                self._helix.g().e_where(predicate).value_map(),
            )
            .var_as(
                "state",
                self._helix.g().n_with_label_where(_STATE_LABEL, predicate).value_map(),
            )
            .returning(["meta", "nodes", "edges", "state"])
        )
        result = self._query(batch)
        meta_rows = _rows(result, "meta")
        if len(meta_rows) != 1:
            raise RuntimeError(
                f"embedded Helix graph must contain exactly one metadata node; "
                f"found {len(meta_rows)}"
            )
        return (
            _properties(meta_rows[0], "metadata"),
            _rows(result, "nodes"),
            _rows(result, "edges"),
            _rows(result, "state"),
        )

    def _read_state_rows(
        self,
        generation: str,
        *,
        metadata: dict[str, Any] | None = None,
        revision: str | None = None,
        client: Any | None = None,
    ) -> list[Any]:
        generation_predicate = self._helix.SourcePredicate.eq(_GENERATION, generation)
        if revision is not None:
            predicate = self._helix.SourcePredicate.and_(
                (
                    generation_predicate,
                    self._helix.SourcePredicate.eq(_STATE_REVISION, revision),
                )
            )
        else:
            meta = metadata or self._metadata(generation, client=client)
            kind_predicates = []
            for kind in _STATE_KINDS:
                selected_revision = _state_revision(meta, kind)
                if selected_revision is None:
                    predicate = generation_predicate
                    break
                kind_predicates.append(
                    self._helix.SourcePredicate.and_(
                        (
                            self._helix.SourcePredicate.eq(_STATE_KIND, kind),
                            self._helix.SourcePredicate.eq(_STATE_REVISION, selected_revision),
                        )
                    )
                )
            else:
                predicate = self._helix.SourcePredicate.and_(
                    (
                        generation_predicate,
                        self._helix.SourcePredicate.or_(kind_predicates),
                    )
                )
        batch = (
            self._helix.read_batch()
            .var_as(
                "state",
                self._helix.g()
                .n_with_label_where(
                    _STATE_LABEL,
                    predicate,
                )
                .value_map((_STATE_KIND, _STATE_KEY, _STATE_PAYLOAD, _ORDER)),
            )
            .returning(["state"])
        )
        return _rows(self._snapshot_query(batch, client), "state")

    @staticmethod
    def _state_records_from_rows(
        rows: list[Any],
    ) -> list[tuple[str, str, Any, int]]:
        ordered: list[tuple[str, str, Any, int]] = []
        seen_orders: set[tuple[str, int]] = set()
        for raw in rows:
            row = _properties(raw, "durable state")
            kind = row.get(_STATE_KIND)
            key = row.get(_STATE_KEY)
            order = row.get(_ORDER)
            if (
                kind not in {"section", "community", "file", "cache"}
                or not isinstance(key, str)
                or not isinstance(order, int)
                or isinstance(order, bool)
                or _STATE_PAYLOAD not in row
            ):
                raise RuntimeError("embedded Helix durable state record is missing schema fields")
            order_key = (kind, order)
            if order_key in seen_orders:
                raise RuntimeError("embedded Helix durable state has duplicate ordering")
            seen_orders.add(order_key)
            payload = row[_STATE_PAYLOAD]
            if isinstance(payload, str) and payload.startswith("json:"):
                try:
                    payload = json.loads(payload[5:])
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        "embedded Helix durable state has invalid encoded payload"
                    ) from exc
            ordered.append((kind, key, payload, order))
        kind_rank = {kind: index for index, kind in enumerate(_STATE_KINDS)}
        ordered.sort(key=lambda item: (kind_rank[item[0]], item[3]))
        return ordered

    @staticmethod
    def _state_from_rows(rows: list[Any], expected_count: Any) -> dict[str, Any]:
        if not isinstance(expected_count, int) or isinstance(expected_count, bool):
            raise RuntimeError("embedded Helix metadata has an invalid state record count")
        if len(rows) != expected_count:
            raise RuntimeError(
                "embedded Helix durable state failed count verification: "
                f"expected {expected_count}, read {len(rows)}"
            )

        ordered = HelixEmbeddedStore._state_records_from_rows(rows)

        state: dict[str, Any] = {}
        community_records: list[Any] = []
        file_records: dict[str, Any] = {}
        cache_records: dict[str, Any] = {}
        for kind, key, payload, _ in ordered:
            if kind == "section":
                if key in state:
                    raise RuntimeError(f"embedded Helix durable state duplicates section {key!r}")
                state[key] = payload
            elif kind == "community":
                community_records.append(payload)
            elif kind == "file":
                if key in file_records:
                    raise RuntimeError(f"embedded Helix durable state duplicates file {key!r}")
                file_records[key] = payload
            else:
                if key in cache_records:
                    raise RuntimeError(f"embedded Helix durable state duplicates cache key {key!r}")
                cache_records[key] = payload

        if community_records:
            if "communities" in state:
                raise RuntimeError(
                    "embedded Helix durable state mixes community section and records"
                )
            state["communities"] = community_records
        if file_records:
            incremental = state.setdefault("incremental", {})
            if not isinstance(incremental, dict) or "files" in incremental:
                raise RuntimeError("embedded Helix durable state has invalid incremental records")
            incremental["files"] = file_records
        if cache_records:
            incremental = state.setdefault("incremental", {})
            if not isinstance(incremental, dict) or "extraction_cache" in incremental:
                raise RuntimeError(
                    "embedded Helix durable state has invalid extraction cache records"
                )
            incremental["extraction_cache"] = cache_records
        return state

    @staticmethod
    def _verified_state_from_rows(rows: list[Any], metadata: dict[str, Any]) -> dict[str, Any]:
        state = HelixEmbeddedStore._state_from_rows(rows, metadata.get("state_record_count"))
        has_category_checksums = all(
            isinstance(metadata.get(_STATE_CHECKSUM_KEYS[kind]), str)
            and isinstance(metadata.get(_STATE_COUNT_KEYS[kind]), int)
            for kind in _STATE_KINDS
        )
        if has_category_checksums:
            records = HelixEmbeddedStore._state_records_from_rows(rows)
            checksums: dict[str, str] = {}
            for kind in _STATE_KINDS:
                category = [record for record in records if record[0] == kind]
                expected_count = metadata[_STATE_COUNT_KEYS[kind]]
                if len(category) != expected_count:
                    raise RuntimeError(
                        "embedded Helix durable state category failed count verification"
                    )
                checksum = _state_category_checksum(category)
                if checksum != metadata[_STATE_CHECKSUM_KEYS[kind]]:
                    raise RuntimeError(
                        "embedded Helix durable state category failed checksum verification"
                    )
                checksums[kind] = checksum
            actual_checksum = _combined_state_checksum(checksums)
        else:
            actual_checksum = _checksum(state)
        if metadata.get("state_checksum") != actual_checksum:
            raise RuntimeError("embedded Helix durable state failed checksum verification")
        return state

    def read_data(self) -> dict[str, Any]:
        generation = self._active_generation()
        assert generation is not None
        return self._read_generation_data(generation)

    @property
    def active_generation(self) -> str:
        generation = self._active_generation()
        assert generation is not None
        return generation

    def read_state(self) -> dict[str, Any]:
        generation = self.active_generation
        meta = self._metadata(generation)
        self._validate_metadata(meta)
        state = self._verified_state_from_rows(
            self._read_state_rows(generation, metadata=meta), meta
        )
        decoded = _decode_state_value(state)
        if not isinstance(decoded, dict):
            raise RuntimeError("embedded Helix generation contains invalid durable state")
        return decoded

    def native_graph(
        self,
        generation: str | None = None,
        *,
        metadata: dict[str, Any] | None = None,
        client: Any | None = None,
        include_storage_identity: bool = False,
    ) -> Any:
        """Load one immutable native snapshot of the active generation."""
        generation = generation or self.active_generation
        meta = metadata or self._metadata(generation, client=client)
        node_count = meta.get("node_count")
        edge_count = meta.get("edge_count")
        if (
            not isinstance(node_count, int)
            or not isinstance(edge_count, int)
            or node_count > self._max_nodes
            or edge_count > self._max_edges
        ):
            raise RuntimeError("embedded Helix generation exceeds configured snapshot bounds")
        predicate = self._helix.SourcePredicate.eq(_GENERATION, generation)
        kind = (
            "multidigraph"
            if bool(meta.get("directed")) and bool(meta.get("multigraph"))
            else "digraph"
            if bool(meta.get("directed"))
            else "multigraph"
            if bool(meta.get("multigraph"))
            else "graph"
        )
        selection = self._helix.GraphSelection(
            node_traversal=self._helix.g().n_with_label_where(_NODE_LABEL, predicate),
            edge_traversal=self._helix.g().e_where(predicate),
            kind=kind,
            metadata=self._helix.GraphMetadataSelection(
                self._helix.g().n_with_label_where(_META_LABEL, predicate),
                (
                    _GENERATION,
                    "schema_version",
                    "directed",
                    "multigraph",
                    "graph",
                    "extras",
                    "node_count",
                    "edge_count",
                    _ACTIVE_STATE_REVISION,
                    *_STATE_REVISION_KEYS.values(),
                    *_STATE_CHECKSUM_KEYS.values(),
                    *_STATE_COUNT_KEYS.values(),
                    _CHECKSUM_MODE,
                    _TOPOLOGY_CHECKSUM,
                    _TOPOLOGY_REVISION,
                    _NODE_BUCKET_HASHES,
                    _EDGE_BUCKET_HASHES,
                    "state_checksum",
                    "checksum",
                ),
            ),
            node_identity=self._helix.IdentitySelection.tagged_property(_EXTERNAL_KEY),
            graphify_edge_key=(
                self._helix.IdentitySelection.tagged_property(_EDGE_KEY)
                if bool(meta.get("multigraph"))
                else None
            ),
            weight_property=_NATIVE_WEIGHT,
            node_properties=(
                (_ATTRS, _STORAGE_KEY) if include_storage_identity else (_ATTRS,)
            ),
            edge_properties=(
                (_ATTRS, _EDGE_IDENTITY) if include_storage_identity else (_ATTRS,)
            ),
            max_nodes=self._max_nodes,
            max_edges=self._max_edges,
            allow_full_scan=True,
        )
        selected = client if client is not None else self._ensure_client()
        graph = selected.graph(selection)
        if graph.node_count != meta.get("node_count") or graph.edge_count != meta.get("edge_count"):
            raise RuntimeError("native Helix snapshot failed generation count verification")
        return graph

    def _read_generation_data(self, generation: str) -> dict[str, Any]:
        meta = self._metadata(generation)
        self._validate_metadata(meta)
        native = self.native_graph(
            generation,
            metadata=meta,
            include_storage_identity=True,
        )

        nodes_with_order: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for record in native.nodes():
            projected = dict(record.attributes)
            attrs, order = projected.get(_ATTRS), projected.get(_STORAGE_KEY)
            if not isinstance(attrs, dict) or not isinstance(order, str):
                raise RuntimeError("native Helix node is missing Graphify schema fields")
            nodes_with_order.append(
                (
                    order,
                    {"id": record.id, **attrs},
                    _node_topology_record(record.id, attrs),
                )
            )

        edges_with_order: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        multigraph = bool(meta.get("multigraph", False))
        for record in native.edges():
            projected = dict(record.attributes)
            attrs, order = projected.get(_ATTRS, {}), projected.get(_EDGE_IDENTITY)
            if not isinstance(attrs, dict) or not isinstance(order, str):
                raise RuntimeError("native Helix edge is missing Graphify schema fields")
            attrs = dict(attrs)
            if record.weight is not None:
                attrs.setdefault("weight", record.weight)
            edge = {
                "source": record.source,
                "target": record.target,
                "relation": record.label,
                **attrs,
            }
            if multigraph:
                edge["key"] = record.graphify_key
            edges_with_order.append(
                (
                    order,
                    edge,
                    _edge_topology_record(
                        record.source,
                        record.target,
                        record.graphify_key,
                        record.label,
                        attrs,
                        multigraph=multigraph,
                    ),
                )
            )

        nodes_with_order.sort(key=lambda item: item[0])
        edges_with_order.sort(key=lambda item: item[0])
        extras = meta.get("extras", {})
        graph_attrs = meta.get("graph", {})
        if not isinstance(extras, dict) or not isinstance(graph_attrs, dict):
            raise RuntimeError("embedded Helix metadata contains invalid graph attributes")
        topology_payload = {
            "directed": bool(meta.get("directed", False)),
            "multigraph": multigraph,
            "graph": graph_attrs,
            "nodes": [row for _, row, _ in nodes_with_order],
            "links": [row for _, row, _ in edges_with_order],
            **extras,
        }
        payload = dict(topology_payload)
        state = self._verified_state_from_rows(
            self._read_state_rows(generation, metadata=meta), meta
        )
        if state:
            payload[_DURABLE_STATE] = state
        expected_nodes = meta.get("node_count")
        expected_edges = meta.get("edge_count")
        expected_checksum = meta.get("checksum")
        if expected_nodes != len(nodes_with_order) or expected_edges != len(edges_with_order):
            raise RuntimeError(
                "embedded Helix graph failed count verification: "
                f"expected {expected_nodes}/{expected_edges}, "
                f"read {len(nodes_with_order)}/{len(edges_with_order)}"
            )
        if meta.get(_CHECKSUM_MODE) in {
            _SPLIT_CHECKSUM_MODE,
            _STREAM_CHECKSUM_MODE,
        }:
            if meta.get(_CHECKSUM_MODE) == _STREAM_CHECKSUM_MODE:
                stream_checksum = _TopologyStreamChecksum(
                    directed=topology_payload["directed"],
                    multigraph=topology_payload["multigraph"],
                    graph=graph_attrs,
                    extras=extras,
                )
                for _, _, node in nodes_with_order:
                    stream_checksum.node(node)
                for _, _, edge in edges_with_order:
                    stream_checksum.edge(edge)
                topology_checksum = stream_checksum.hexdigest()
            else:
                topology_checksum = _checksum(topology_payload)
            expected_topology_checksum = meta.get(_TOPOLOGY_CHECKSUM)
            if expected_topology_checksum != topology_checksum:
                raise RuntimeError(
                    "embedded Helix topology failed checksum verification: "
                    f"expected {expected_topology_checksum!r}, got {topology_checksum!r}"
                )
            state_checksum = meta.get("state_checksum")
            if not isinstance(state_checksum, str):
                raise RuntimeError("embedded Helix metadata has no durable state checksum")
            actual_checksum = _generation_checksum(topology_checksum, state_checksum)
        else:
            actual_checksum = _checksum(payload)
        if expected_checksum != actual_checksum:
            raise RuntimeError(
                "embedded Helix graph failed checksum verification: "
                f"expected {expected_checksum!r}, got {actual_checksum!r}"
            )
        return payload

    def _verify_generation_counts(self, generation: str) -> dict[str, Any]:
        """Verify one staged generation with bounded native count projections."""
        metadata = self._metadata(generation)
        self._validate_metadata(metadata)
        predicate = self._helix.SourcePredicate.eq(_GENERATION, generation)
        counts = self._query(
            self._helix.read_batch()
            .var_as(
                "nodes",
                self._helix.g().n_with_label_where(_NODE_LABEL, predicate).count(),
            )
            .var_as("edges", self._helix.g().e_where(predicate).count())
            .var_as(
                "state_records",
                self._helix.g().n_with_label_where(_STATE_LABEL, predicate).count(),
            )
            .returning(["nodes", "edges", "state_records"])
        )
        if not isinstance(counts, dict):
            raise RuntimeError("embedded Helix count verification returned no result")
        expected = {
            "nodes": metadata.get("node_count"),
            "edges": metadata.get("edge_count"),
            "state_records": metadata.get("state_record_count"),
        }
        if any(
            not isinstance(expected[name], int) or counts.get(name) != expected[name]
            for name in expected
        ):
            raise RuntimeError(
                "embedded Helix generation failed count verification: "
                f"expected {expected!r}, read {counts!r}"
            )
        return {
            "schema_version": _SCHEMA_VERSION,
            **counts,
            "checksum": metadata.get("checksum"),
        }

    @staticmethod
    def _validate_metadata(meta: dict[str, Any]) -> None:
        if meta.get("schema_version") != _SCHEMA_VERSION:
            raise RuntimeError(
                "unsupported embedded Helix graph schema: "
                f"expected {_SCHEMA_VERSION}, got {meta.get('schema_version')!r}"
            )

    def _load_generation_snapshot(
        self,
        generation: str | None,
        *,
        attach_query: bool,
        native: Any | None = None,
        expected_topology_checksum: str | None = None,
    ) -> LoadedGraph:
        attempts = 3 if attach_query else 1
        for attempt in range(attempts):
            snapshot_client = (
                open_embedded_client(
                    self.path,
                    read_only=True,
                    disable_cache=True,
                )
                if attach_query
                else None
            )
            client = snapshot_client if snapshot_client is not None else self._ensure_client()
            try:
                selected_generation = generation
                if selected_generation is None:
                    selected_generation = self._active_generation(client=client)
                    assert selected_generation is not None
                meta = self._metadata(selected_generation, client=client)
                self._validate_metadata(meta)
                if (
                    expected_topology_checksum is not None
                    and meta.get(_TOPOLOGY_CHECKSUM) != expected_topology_checksum
                ):
                    raise RuntimeError(
                        "validated native topology does not match the published generation"
                    )
                loaded_native = native
                if loaded_native is None:
                    loaded_native = self.native_graph(
                        selected_generation,
                        metadata=meta,
                        client=client,
                    )
                elif loaded_native.node_count != meta.get(
                    "node_count"
                ) or loaded_native.edge_count != meta.get("edge_count"):
                    raise RuntimeError(
                        "validated native topology does not match published generation counts"
                    )
                state = self._verified_state_from_rows(
                    self._read_state_rows(
                        selected_generation,
                        metadata=meta,
                        client=client,
                    ),
                    meta,
                )
                decoded = _decode_state_value(state)
                if not isinstance(decoded, dict):
                    raise RuntimeError("embedded Helix generation contains invalid durable state")
                query = (
                    HelixNodeQuery(self.path, selected_generation, client=snapshot_client)
                    if snapshot_client is not None
                    else None
                )
                return LoadedGraph(
                    loaded_native,
                    selected_generation,
                    decoded,
                    meta,
                    self.path,
                    query,
                )
            except Exception as exc:
                if snapshot_client is not None:
                    _close_public_client(snapshot_client)
                if attempt + 1 < attempts and "Request read view changed during execution" in str(
                    exc
                ):
                    continue
                raise
        raise AssertionError("snapshot retry loop must return or raise")

    def load_generation(self, generation: str | None, *, attach_query: bool = True) -> LoadedGraph:
        """Load topology, metadata, state, and query from one reader snapshot."""
        return self._load_generation_snapshot(generation, attach_query=attach_query)

    def load(self) -> LoadedGraph:
        return self.load_generation(None)

    def checkpoint(self) -> None:
        # Durable publications fence earlier buffered writes; close() flushes the handle.
        if self._closed:
            raise RuntimeError("embedded Helix store is closed")

    def _metadata(self, generation: str, *, client: Any | None = None) -> dict[str, Any]:
        batch = (
            self._helix.read_batch()
            .var_as(
                "meta",
                self._helix.g()
                .n_with_label_where(
                    _META_LABEL,
                    self._helix.SourcePredicate.eq(_GENERATION, generation),
                )
                .value_map(),
            )
            .returning(["meta"])
        )
        rows = _rows(self._snapshot_query(batch, client), "meta")
        if len(rows) != 1:
            raise RuntimeError("embedded Helix graph metadata is missing or duplicated")
        return _properties(rows[0], "metadata")

    def verify(self) -> dict[str, Any]:
        """Perform a deep topology/state checksum verification."""
        payload = self.read_data()
        metadata = self._metadata(self.active_generation)
        return {
            "schema_version": _SCHEMA_VERSION,
            "nodes": len(payload["nodes"]),
            "edges": len(payload["links"]),
            "checksum": metadata.get("checksum"),
        }

    def verify_counts(self) -> dict[str, Any]:
        """Perform the lightweight verification used on the write path."""
        return self._verify_generation_counts(self.active_generation)

    def close(self) -> None:
        if not self._closed:
            try:
                _close_public_client(self._ensure_client())
            finally:
                if not self._closed:
                    self._store_lock.release()
                    self._closed = True

    def __enter__(self) -> "HelixEmbeddedStore":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            if hasattr(self, "_closed") and not self._closed:
                self.close()
        except Exception:
            pass


class HelixGraphReader:
    """Retain one native graph while polling immutable embedded snapshots."""

    def __init__(self, path: str | Path = DEFAULT_PROJECT_STORE) -> None:
        self.path = Path(path)
        self._version: tuple[str | None, ...] | None = None
        self._graph: LoadedGraph | None = None
        self._lock = threading.RLock()

    def get(self) -> LoadedGraph:
        with self._lock:
            # Helix embedded readers are immutable database snapshots. Reopen
            # the lightweight handle to observe a writer's atomic pointer flip;
            # retain the expensive native graph while its version is unchanged.
            with HelixEmbeddedStore(self.path, read_only=True) as store:
                generation = store.active_generation
                metadata = store._metadata(generation)
                version = (
                    generation,
                    metadata.get(_TOPOLOGY_REVISION),
                    *(_state_revision(metadata, kind) for kind in _STATE_KINDS),
                )
                if self._graph is None or version != self._version:
                    candidate = store.load()
                    candidate_version = (
                        candidate.generation,
                        candidate.metadata.get(_TOPOLOGY_REVISION),
                        *(_state_revision(dict(candidate.metadata), kind) for kind in _STATE_KINDS),
                    )
                    if candidate_version != self._version:
                        self._graph = candidate
                        self._version = candidate_version
                    elif candidate.query is not None:
                        candidate.query.close()
            graph = self._graph
            assert graph is not None
            return graph

    def close(self) -> None:
        with self._lock:
            if self._graph is not None and self._graph.query is not None:
                self._graph.query.close()
            self._graph = None
            self._version = None

    # Deliberately no __del__; closing the owned query from cyclic GC has the
    # same unsafe b3 re-entrancy as finalizing HelixNodeQuery directly.


def persist_graph(
    graph: GraphBuildData,
    path: str | Path = DEFAULT_PROJECT_STORE,
    *,
    state: dict[str, Any] | None = None,
    retain_rollback: bool = False,
) -> None:
    with HelixEmbeddedStore(path, retain_rollback=retain_rollback) as store:
        store.save(graph, state=state)


def persist_graph_data(
    data: dict[str, Any],
    path: str | Path,
    *,
    retain_rollback: bool = False,
) -> None:
    with HelixEmbeddedStore(path, retain_rollback=retain_rollback) as store:
        store.save_data(data)


def load_graph(path: str | Path = DEFAULT_PROJECT_STORE) -> LoadedGraph:
    with HelixEmbeddedStore(path, read_only=True) as store:
        return store.load()


def graph_storage_exists(path: str | Path = DEFAULT_PROJECT_STORE) -> bool:
    return Path(path).expanduser().is_dir()


__all__ = [
    "HelixEmbeddedStore",
    "HelixGraphReader",
    "HelixNodeQuery",
    "DEFAULT_GLOBAL_STORE",
    "DEFAULT_MAX_EDGES",
    "DEFAULT_MAX_NODES",
    "DEFAULT_PROJECT_STORE",
    "graph_storage_exists",
    "load_graph",
    "persist_graph",
    "persist_graph_data",
]
