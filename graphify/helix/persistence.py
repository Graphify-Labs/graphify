"""Persistent Graphify schema implemented on the official embedded Helix SDK."""

from __future__ import annotations

import base64
from contextlib import contextmanager
import copy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
from typing import Any
import uuid

from .model import GraphBuildData, LoadedGraph, import_identity
from .native import load_native_module, open_embedded_client


_SCHEMA_VERSION = 6
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
_INTERNAL_ID = "$id"
_ATTRS = "attrs"
_ORDER = "graphify_order"
_LEGACY_TARGET_KEY = "target_key"
_EDGE_KEY = "edge_key"
_NATIVE_WEIGHT = "graphify_weight"
_WRITER_LOCK_FILE = ".graphify-writer.lock"
_WRITER_LOCK_TIMEOUT_SECONDS = 30.0
_WRITE_CHUNK_SIZE = 1_000
_STATE_WRITE_CHUNK_SIZE = 64
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
_TOPOLOGY_CHECKSUM = "topology_checksum"
_STATE_KINDS = ("section", "community", "file", "cache")
_STATE_REVISION_KEYS = {
    kind: f"active_{kind}_revision" for kind in _STATE_KINDS
}
_STATE_CHECKSUM_KEYS = {
    kind: f"{kind}_state_checksum" for kind in _STATE_KINDS
}
_STATE_COUNT_KEYS = {
    kind: f"{kind}_state_count" for kind in _STATE_KINDS
}


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
            stream.write(f"pid={os.getpid()}\n".encode("ascii"))
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
                [_encode_state_value(key), _encode_state_value(item)]
                for key, item in value.items()
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
    return load_native_module().external_id_to_json(value)


def _encode_key(value: Any) -> str:
    return json.dumps(
        _tagged_key(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_tagged_key(value: dict[str, Any]) -> Any:
    try:
        return load_native_module().external_id_from_json(value)
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


def _checksum(payload: dict[str, Any]) -> str:
    def encode_non_json(value: Any) -> Any:
        if isinstance(value, bytes):
            return {"$graphify_bytes": base64.b64encode(value).decode("ascii")}
        if isinstance(value, frozenset):
            return {"$graphify_frozenset": sorted(_encode_key(item) for item in value)}
        raise TypeError(f"cannot checksum {type(value).__name__}")

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
        default=encode_non_json,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _generation_checksum(topology_checksum: str, state_checksum: str) -> str:
    """Bind independently verified topology and state into one generation hash."""
    return _checksum({
        _TOPOLOGY_CHECKSUM: topology_checksum,
        "state_checksum": state_checksum,
    })


def _state_revision(metadata: dict[str, Any], kind: str) -> str | None:
    revision = metadata.get(_STATE_REVISION_KEYS[kind])
    if not isinstance(revision, str):
        revision = metadata.get(_ACTIVE_STATE_REVISION)
    return revision if isinstance(revision, str) else None


def _state_category_checksum(
    records: list[tuple[str, str, Any, int]],
) -> str:
    return _checksum({
        "records": [
            {"kind": kind, "key": key, "payload": payload, "order": order}
            for kind, key, payload, order in records
        ]
    })


def _combined_state_checksum(checksums: dict[str, str]) -> str:
    return _checksum({"categories": checksums})


def _state_category_value(
    state: dict[str, Any], kind: str, generation: str
) -> Any:
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
    sections.setdefault(
        "incremental", {"last_successful_generation": generation}
    )
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


def _returned_keys(result: Any, name: str) -> list[str]:
    values = _rows(result, name)
    keys: list[str] = []
    for value in values:
        if isinstance(value, str):
            keys.append(value)
        elif isinstance(value, dict):
            props = _properties(value, name)
            key = props.get(_EXTERNAL_KEY)
            if not isinstance(key, str):
                raise RuntimeError(f"embedded Helix {name} result has no external key")
            keys.append(key)
        elif isinstance(value, list) and len(value) == 1 and isinstance(value[0], str):
            keys.append(value[0])
        else:
            raise RuntimeError(f"embedded Helix {name} result has an unexpected value")
    return keys


@dataclass
class HelixEmbeddedStore:
    """Graphify's durable graph schema on an in-process Helix ``Disk`` client."""

    path: Path
    _client: Any
    _helix: Any
    _read_only: bool
    _closed: bool
    _store_lock: _StoreLock
    _max_nodes: int
    _max_edges: int

    def __init__(
        self,
        path: str | Path,
        *,
        read_only: bool = False,
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
        self._helix = load_native_module()
        self._read_only = read_only
        self._max_nodes = max_nodes
        self._max_edges = max_edges
        self._closed = False
        self._store_lock = _StoreLock(
            self.path / _WRITER_LOCK_FILE,
            shared=read_only,
        )
        self._store_lock.acquire()
        try:
            self._client = open_embedded_client(self.path, read_only=read_only)
        except Exception:
            self._store_lock.release()
            raise
        if not read_only:
            try:
                self._ensure_indexes()
                self._validate_active_schema()
                self._cleanup_inactive_generations()
                self._cleanup_inactive_state_revisions()
            except Exception:
                try:
                    self._client.close()
                finally:
                    self._store_lock.release()
                raise

    def _query(self, batch: Any) -> Any:
        if self._closed:
            raise RuntimeError("embedded Helix store is closed")
        return self._client.query(batch.to_query_request())

    def _ensure_indexes(self) -> None:
        batch = (
            self._helix.write_batch()
            .var_as(
                "node_storage_key_index",
                self._helix.g().create_index_if_not_exists(
                    self._helix.IndexSpec.node_unique_equality(_NODE_LABEL, _STORAGE_KEY)
                ),
            )
            .var_as(
                "control_key_index",
                self._helix.g().create_index_if_not_exists(
                    self._helix.IndexSpec.node_unique_equality(_CONTROL_LABEL, _CONTROL_KEY)
                ),
            )
            .returning(["node_storage_key_index", "control_key_index"])
        )
        self._query(batch)

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
        self.save_data(graph.to_node_link(state=state))

    def save_generation(self, graph: GraphBuildData, state: dict[str, Any]) -> None:
        """Atomically stage topology and every durable Graphify record together."""
        self.save(graph, state=state)

    def save_data(self, payload: dict[str, Any]) -> None:
        """Stage, verify, and atomically activate a durable graph generation."""
        self._save_data(payload, activate=True)

    def _save_data(self, payload: dict[str, Any], *, activate: bool) -> str:
        if self._read_only:
            raise RuntimeError("cannot write through a read-only embedded Helix store")
        if not isinstance(payload, dict):
            raise TypeError("node-link graph payload must be a mapping")

        directed = bool(payload.get("directed", False))
        multigraph = bool(payload.get("multigraph", False))
        graph_attrs = _json_value(payload.get("graph", {}), "graph metadata")
        if not isinstance(graph_attrs, dict):
            raise TypeError("node-link graph metadata must be a mapping")

        raw_nodes = payload.get("nodes", [])
        if not isinstance(raw_nodes, list):
            raise TypeError("node-link nodes must be a list")
        nodes: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        node_variables: dict[str, str] = {}
        canonical_nodes: list[dict[str, Any]] = []
        for index, row in enumerate(raw_nodes):
            if not isinstance(row, dict) or "id" not in row:
                raise TypeError(f"node-link nodes[{index}] must be a mapping with an id")
            attrs = dict(row)
            node_id = import_identity(attrs.pop("id"))
            encoded_id = _encode_key(node_id)
            if encoded_id in node_variables:
                raise ValueError(f"duplicate graph node identifier at nodes[{index}]")
            attrs = _json_value(attrs, f"node-link nodes[{index}] attributes")
            variable = f"node_{index}"
            node_variables[encoded_id] = variable
            nodes.append((encoded_id, _tagged_key(node_id), attrs))
            canonical_nodes.append({"id": node_id, **attrs})

        raw_edges = payload.get("links", payload.get("edges", []))
        if not isinstance(raw_edges, list):
            raise TypeError("node-link links must be a list")
        if len(raw_nodes) > self._max_nodes or len(raw_edges) > self._max_edges:
            raise ValueError(
                "graph exceeds configured embedded ingestion bounds: "
                f"{len(raw_nodes)}/{len(raw_edges)} > "
                f"{self._max_nodes}/{self._max_edges}"
            )
        edges: list[
            tuple[str, str, str, dict[str, Any], str, dict[str, Any]]
        ] = []
        canonical_edges: list[dict[str, Any]] = []
        for index, row in enumerate(raw_edges):
            if not isinstance(row, dict) or "source" not in row or "target" not in row:
                raise TypeError(
                    f"node-link links[{index}] must contain source and target"
                )
            attrs = dict(row)
            source = import_identity(attrs.pop("source"))
            target = import_identity(attrs.pop("target"))
            encoded_source = _encode_key(source)
            encoded_target = _encode_key(target)
            if encoded_source not in node_variables or encoded_target not in node_variables:
                raise ValueError(f"node-link links[{index}] references a missing node")
            key = import_identity(attrs.pop("key", None)) if multigraph else None
            attrs = _json_value(attrs, f"node-link links[{index}] attributes")
            encoded_edge_key = _encode_key(key)
            relation = attrs.pop("relation", "related_to")
            if not isinstance(relation, str) or not relation:
                raise TypeError(
                    f"node-link links[{index}] relation must be a non-empty string"
                )
            edges.append((
                encoded_source,
                encoded_target,
                encoded_edge_key,
                _tagged_key(key),
                relation,
                attrs,
            ))
            canonical = {
                "source": source,
                "target": target,
                "relation": relation,
                **attrs,
            }
            if multigraph:
                canonical["key"] = key
            canonical_edges.append(canonical)

        reserved = {"directed", "multigraph", "graph", "nodes", "links", "edges"}
        raw_extras = {key: value for key, value in payload.items() if key not in reserved}
        raw_state = raw_extras.pop(_DURABLE_STATE, None)
        generation = uuid.uuid4().hex
        encoded_state: dict[str, Any] | None = None
        if raw_state is not None:
            if not isinstance(raw_state, dict):
                raise TypeError("durable graph state must be a mapping")
            state = copy.deepcopy(raw_state)
            build_state = state.setdefault("build", {})
            incremental_state = state.setdefault("incremental", {})
            if not isinstance(build_state, dict) or not isinstance(
                incremental_state, dict
            ):
                raise TypeError(
                    "durable build and incremental state sections must be mappings"
                )
            build_state["generation"] = generation
            incremental_state["last_successful_generation"] = generation
            encoded_state = _json_value(
                _encode_state_value(state), "durable graph state"
            )
        extras = _json_value(raw_extras, "node-link top-level metadata")
        canonical_topology = {
            "directed": directed,
            "multigraph": multigraph,
            "graph": graph_attrs,
            "nodes": canonical_nodes,
            "links": canonical_edges,
            **extras,
        }
        topology_checksum = _checksum(canonical_topology)
        state_records = self._state_records(encoded_state)
        category_records = {
            kind: [record for record in state_records if record[0] == kind]
            for kind in _STATE_KINDS
        }
        category_checksums = {
            kind: _state_category_checksum(category_records[kind])
            for kind in _STATE_KINDS
        }
        state_checksum = _combined_state_checksum(category_checksums)
        manifest = {
            "schema_version": _SCHEMA_VERSION,
            "directed": directed,
            "multigraph": multigraph,
            "graph": graph_attrs,
            "extras": extras,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "state_record_count": len(state_records),
            "state_checksum": state_checksum,
            _ACTIVE_STATE_REVISION: generation,
            _CHECKSUM_MODE: _SPLIT_CHECKSUM_MODE,
            _TOPOLOGY_CHECKSUM: topology_checksum,
            **{key: generation for key in _STATE_REVISION_KEYS.values()},
            **{
                _STATE_CHECKSUM_KEYS[kind]: category_checksums[kind]
                for kind in _STATE_KINDS
            },
            **{
                _STATE_COUNT_KEYS[kind]: len(category_records[kind])
                for kind in _STATE_KINDS
            },
            "checksum": _generation_checksum(topology_checksum, state_checksum),
        }

        previous_generation = self._active_generation(required=False)
        try:
            self._stage_generation(
                generation, manifest, nodes, edges, encoded_state
            )
            self._read_generation_data(generation)
            if activate:
                self._activate_generation(
                    generation,
                    create=previous_generation is None,
                    previous=previous_generation,
                )
        except Exception:
            try:
                self._drop_generation(generation)
            except Exception:
                pass
            raise

        if activate:
            self._cleanup_inactive_generations()
        return generation

    @contextmanager
    def staged_graph(self, graph: GraphBuildData):
        """Yield one inactive native snapshot that can be finalized in place."""
        generation = self._save_data(graph.to_node_link(), activate=False)
        staged = self.load_generation(generation)
        try:
            yield staged
        finally:
            if self._active_generation(required=False) != generation:
                self._drop_generation(generation)

    def activate_staged(self, staged: LoadedGraph, state: dict[str, Any]) -> LoadedGraph:
        """Attach durable state, verify, and activate an existing staged topology."""
        if self._read_only:
            raise RuntimeError("cannot activate through a read-only embedded Helix store")
        generation = staged.generation
        if staged.store_path != self.path:
            raise ValueError("staged graph belongs to a different embedded Helix store")
        if self._metadata(generation).get("state_record_count") != 0:
            raise RuntimeError("staged Helix generation has already been finalized")

        encoded = copy.deepcopy(state)
        build_state = encoded.setdefault("build", {})
        incremental_state = encoded.setdefault("incremental", {})
        if not isinstance(build_state, dict) or not isinstance(incremental_state, dict):
            raise TypeError("durable build and incremental state must be mappings")
        build_state["generation"] = generation
        incremental_state["last_successful_generation"] = generation
        encoded_state = _json_value(
            _encode_state_value(encoded), "durable graph state"
        )
        records = self._state_records(encoded_state)
        category_records = {
            kind: [record for record in records if record[0] == kind]
            for kind in _STATE_KINDS
        }
        category_checksums = {
            kind: _state_category_checksum(category_records[kind])
            for kind in _STATE_KINDS
        }
        previous_generation = self._active_generation(required=False)
        try:
            meta = self._metadata(generation)
            topology_checksum = meta.get(_TOPOLOGY_CHECKSUM)
            if not isinstance(topology_checksum, str):
                raise RuntimeError("embedded Helix metadata has no topology checksum")
            self._write_state_records(generation, records, generation)
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
                **{
                    _STATE_CHECKSUM_KEYS[kind]: category_checksums[kind]
                    for kind in _STATE_KINDS
                },
                **{
                    _STATE_COUNT_KEYS[kind]: len(category_records[kind])
                    for kind in _STATE_KINDS
                },
            }
            traversal = self._helix.g().n_with_label_where(
                _META_LABEL,
                self._helix.SourcePredicate.eq(_GENERATION, generation),
            )
            for key, value in updates.items():
                traversal = traversal.set_property(key, value)
            self._query(
                self._helix.write_batch()
                .var_as("finalize", traversal)
                .returning(["finalize"])
            )
            self._read_generation_data(generation)
            self._activate_generation(
                generation,
                create=previous_generation is None,
                previous=previous_generation,
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
            kind: self._state_records_for_kind(state, generation, kind)
            for kind in changed_kinds
        }
        changed_records = [
            record
            for kind in changed_kinds
            for record in records_by_kind[kind]
        ]
        category_checksums: dict[str, str] = {}
        category_counts: dict[str, int] = {}
        for kind in _STATE_KINDS:
            if kind in records_by_kind:
                category_checksums[kind] = _state_category_checksum(
                    records_by_kind[kind]
                )
                category_counts[kind] = len(records_by_kind[kind])
                continue
            checksum = meta.get(_STATE_CHECKSUM_KEYS[kind])
            count = meta.get(_STATE_COUNT_KEYS[kind])
            if not isinstance(checksum, str) or not isinstance(count, int):
                raise RuntimeError(
                    "embedded Helix metadata has invalid state category fields"
                )
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
                **{
                    _STATE_REVISION_KEYS[kind]: revision
                    for kind in changed_kinds
                },
                **{
                    _STATE_CHECKSUM_KEYS[kind]: category_checksums[kind]
                    for kind in changed_kinds
                },
                **{
                    _STATE_COUNT_KEYS[kind]: category_counts[kind]
                    for kind in changed_kinds
                },
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
                            self._state_record_properties(
                                generation, revision, record
                            ),
                        ),
                    )
            else:
                self._write_state_records(generation, changed_records, revision)
            batch = batch.var_as("activate_state", traversal)
            returned = ["activate_state"]
            for index, kind in enumerate(changed_kinds):
                old_revision = _state_revision(meta, kind)
                if old_revision is None:
                    continue
                variable = f"drop_old_state_{index}"
                predicate = self._helix.SourcePredicate.and_((
                    self._helix.SourcePredicate.eq(_GENERATION, generation),
                    self._helix.SourcePredicate.eq(_STATE_REVISION, old_revision),
                    self._helix.SourcePredicate.eq(_STATE_KIND, kind),
                ))
                batch = batch.var_as(
                    variable,
                    self._helix.g()
                    .n_with_label_where(_STATE_LABEL, predicate)
                    .drop(),
                )
                returned.append(variable)
            self._query(
                batch.returning(returned)
            )
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
                    raise TypeError(
                        "incremental durable state extraction cache must be a mapping"
                    )
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
                        raise TypeError(
                            "incremental durable state file paths must be strings"
                        )
                    records.append(("file", path, file_state, order))
                    order += 1
                for cache_key, cache_value in extraction_cache.items():
                    if not isinstance(cache_key, str):
                        raise TypeError(
                            "incremental durable extraction cache keys must be strings"
                        )
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

    def _state_records_for_kind(
        self, state: dict[str, Any], generation: str, kind: str
    ) -> list[tuple[str, str, Any, int]]:
        value = _state_category_value(state, kind, generation)
        if kind == "section":
            partial = value
        elif kind == "community":
            partial = {"communities": value}
        else:
            partial = {"incremental": {
                "files" if kind == "file" else "extraction_cache": value
            }}
        encoded = _json_value(
            _encode_state_value(partial), f"durable {kind} state"
        )
        return [
            record for record in self._state_records(encoded)
            if record[0] == kind
        ]

    def _stage_generation(
        self,
        generation: str,
        manifest: dict[str, Any],
        nodes: list[tuple[str, dict[str, Any], dict[str, Any]]],
        edges: list[
            tuple[str, str, str, dict[str, Any], str, dict[str, Any]]
        ],
        state: dict[str, Any] | None,
    ) -> None:
        metadata = {**manifest, _GENERATION: generation}
        self._query(
            self._helix.write_batch()
            .var_as("meta", self._helix.g().add_n(_META_LABEL, metadata))
            .returning(["meta"])
        )

        for offset in range(0, len(nodes), _WRITE_CHUNK_SIZE):
            batch = self._helix.write_batch()
            returned = ""
            for local_index, (encoded_id, identity, attrs) in enumerate(
                nodes[offset : offset + _WRITE_CHUNK_SIZE]
            ):
                index = offset + local_index
                returned = f"node_{local_index}"
                batch = batch.var_as(
                    returned,
                    self._helix.g().add_n(
                        _NODE_LABEL,
                        {
                            _GENERATION: generation,
                            _STORAGE_KEY: self._storage_key(generation, encoded_id),
                            _EXTERNAL_KEY: identity,
                            _ATTRS: attrs,
                            _ORDER: index,
                        },
                    ),
                )
            self._query(batch.returning([returned]))

        node_ids = self._node_ids_for_generation(generation)
        if len(node_ids) != len(nodes):
            raise RuntimeError(
                "embedded Helix staged node count does not match the input graph"
            )

        for offset in range(0, len(edges), _WRITE_CHUNK_SIZE):
            batch = self._helix.write_batch()
            returned = ""
            for local_index, (source, target, key, identity, relation, attrs) in enumerate(
                edges[offset : offset + _WRITE_CHUNK_SIZE]
            ):
                index = offset + local_index
                returned = f"edge_{local_index}"
                batch = batch.var_as(
                    returned,
                    self._helix.g()
                    .n(self._helix.NodeRef.ids([node_ids[source]]))
                    .add_e(
                        relation,
                        self._helix.NodeRef.ids([node_ids[target]]),
                        {
                            _GENERATION: generation,
                            _EDGE_KEY: identity,
                            _ATTRS: attrs,
                            _ORDER: index,
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
            self._query(batch.returning([returned]))

        self._write_state_records(generation, self._state_records(state), generation)

    def _write_state_records(
        self,
        generation: str,
        state_records: list[tuple[str, str, Any, int]],
        revision: str,
    ) -> None:
        # State rows are independent native records. A fixed planner-safe batch
        # size keeps transaction cost bounded without exception-driven retries.
        for offset in range(0, len(state_records), _STATE_WRITE_CHUNK_SIZE):
            self._write_state_chunk(
                generation,
                state_records[offset : offset + _STATE_WRITE_CHUNK_SIZE],
                revision,
            )

    def _write_state_chunk(
        self,
        generation: str,
        records: list[tuple[str, str, Any, int]],
        revision: str,
    ) -> None:
        batch = self._helix.write_batch()
        returned = ""
        for local_index, record in enumerate(records):
            returned = f"state_{local_index}"
            batch = batch.var_as(
                returned,
                self._helix.g().add_n(
                    _STATE_LABEL,
                    self._state_record_properties(generation, revision, record),
                ),
            )
        self._query(batch.returning([returned]))

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
            _STATE_PAYLOAD: "json:" + json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ),
            _ORDER: order,
        }
        if kind == "community" and isinstance(payload, dict):
            for name in (
                "id", "name", "naming_source", "signature", "cohesion",
            ):
                if name in payload and payload[name] is not None:
                    properties[name] = payload[name]
        elif kind == "file" and isinstance(payload, dict):
            properties["relative_path"] = key
            for name in ("content_hash", "semantic_hash"):
                if name in payload:
                    properties[name] = payload[name]
        return properties

    def _node_ids_for_generation(self, generation: str) -> dict[str, int]:
        batch = (
            self._helix.read_batch()
            .var_as(
                "nodes",
                self._helix.g()
                .n_with_label_where(
                    _NODE_LABEL,
                    self._helix.SourcePredicate.eq(_GENERATION, generation),
                )
                .value_map(),
            )
            .returning(["nodes"])
        )
        node_ids: dict[str, int] = {}
        for raw in _rows(self._query(batch), "nodes"):
            row = _properties(raw, "node")
            storage_key = row.get(_STORAGE_KEY)
            internal_id = row.get(_INTERNAL_ID)
            if (
                not isinstance(storage_key, str)
                or not isinstance(internal_id, int)
                or isinstance(internal_id, bool)
            ):
                raise RuntimeError("embedded Helix staged node has no internal ID")
            prefix = f"{generation}:"
            if not storage_key.startswith(prefix):
                raise RuntimeError("embedded Helix staged node has an invalid storage key")
            node_ids[storage_key[len(prefix):]] = internal_id
        return node_ids

    def _active_generation(self, *, required: bool = True) -> str | None:
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
        rows = _rows(self._query(batch), "control")
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
    ) -> None:
        if create:
            traversal = self._helix.g().add_n(
                _CONTROL_LABEL,
                {_CONTROL_KEY: "active", _ACTIVE_GENERATION: generation},
            )
        else:
            traversal = self._helix.g().n_with_label_where(
                _CONTROL_LABEL,
                self._helix.SourcePredicate.eq(_CONTROL_KEY, "active"),
            ).set_property(_ACTIVE_GENERATION, generation)
            if previous is not None:
                traversal = traversal.set_property(_PREVIOUS_GENERATION, previous)
        batch = self._helix.write_batch().var_as("activate", traversal).returning(["activate"])
        self._query(batch)

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
            .returning(["drop_edges", "drop_nodes", "drop_meta", "drop_state"])
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
            self._helix.write_batch()
            .var_as(
                "drop_state_revision",
                self._helix.g().n_with_label_where(_STATE_LABEL, predicate).drop(),
            )
            .returning(["drop_state_revision"])
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
            if isinstance(
                generation := _properties(raw, "metadata").get(_GENERATION), str
            )
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
                predicate = self._helix.SourcePredicate.and_((
                    self._helix.SourcePredicate.eq(_GENERATION, generation),
                    self._helix.SourcePredicate.eq(_STATE_KIND, kind),
                    self._helix.SourcePredicate.neq(_STATE_REVISION, revision),
                ))
                self._query(
                    self._helix.write_batch()
                    .var_as(
                        "drop_inactive_state",
                        self._helix.g()
                        .n_with_label_where(_STATE_LABEL, predicate)
                        .drop(),
                    )
                    .returning(["drop_inactive_state"])
                )

    def _control_properties(self, *, required: bool = True) -> dict[str, Any] | None:
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
        rows = _rows(self._query(batch), "control")
        if not rows:
            if required:
                raise RuntimeError("embedded Helix graph has no active generation")
            return None
        if len(rows) != 1:
            raise RuntimeError("embedded Helix graph has duplicated control rows")
        return _properties(rows[0], "control")

    def _read_rows(
        self, generation: str
    ) -> tuple[dict[str, Any], list[Any], list[Any], list[Any]]:
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
    ) -> list[Any]:
        generation_predicate = self._helix.SourcePredicate.eq(
            _GENERATION, generation
        )
        if revision is not None:
            predicate = self._helix.SourcePredicate.and_((
                generation_predicate,
                self._helix.SourcePredicate.eq(_STATE_REVISION, revision),
            ))
        else:
            meta = metadata or self._metadata(generation)
            kind_predicates = []
            for kind in _STATE_KINDS:
                selected_revision = _state_revision(meta, kind)
                if selected_revision is None:
                    predicate = generation_predicate
                    break
                kind_predicates.append(self._helix.SourcePredicate.and_((
                    self._helix.SourcePredicate.eq(_STATE_KIND, kind),
                    self._helix.SourcePredicate.eq(
                        _STATE_REVISION, selected_revision
                    ),
                )))
            else:
                predicate = self._helix.SourcePredicate.and_((
                    generation_predicate,
                    self._helix.SourcePredicate.or_(kind_predicates),
                ))
        batch = (
            self._helix.read_batch()
            .var_as(
                "state",
                self._helix.g()
                .n_with_label_where(
                    _STATE_LABEL,
                    predicate,
                )
                .value_map(),
            )
            .returning(["state"])
        )
        return _rows(self._query(batch), "state")

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
                raise RuntimeError(
                    "embedded Helix durable state record is missing schema fields"
                )
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
                    raise RuntimeError(
                        f"embedded Helix durable state duplicates section {key!r}"
                    )
                state[key] = payload
            elif kind == "community":
                community_records.append(payload)
            elif kind == "file":
                if key in file_records:
                    raise RuntimeError(
                        f"embedded Helix durable state duplicates file {key!r}"
                    )
                file_records[key] = payload
            else:
                if key in cache_records:
                    raise RuntimeError(
                        f"embedded Helix durable state duplicates cache key {key!r}"
                    )
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
                raise RuntimeError(
                    "embedded Helix durable state has invalid incremental records"
                )
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
    def _verified_state_from_rows(
        rows: list[Any], metadata: dict[str, Any]
    ) -> dict[str, Any]:
        state = HelixEmbeddedStore._state_from_rows(
            rows, metadata.get("state_record_count")
        )
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
    ) -> Any:
        """Load one immutable native snapshot of the active generation."""
        generation = generation or self.active_generation
        meta = metadata or self._metadata(generation)
        node_count = meta.get("node_count")
        edge_count = meta.get("edge_count")
        if (
            not isinstance(node_count, int)
            or not isinstance(edge_count, int)
            or node_count > self._max_nodes
            or edge_count > self._max_edges
        ):
            raise RuntimeError(
                "embedded Helix generation exceeds configured snapshot bounds"
            )
        predicate = self._helix.SourcePredicate.eq(_GENERATION, generation)
        kind = (
            "multidigraph" if bool(meta.get("directed")) and bool(meta.get("multigraph"))
            else "digraph" if bool(meta.get("directed"))
            else "multigraph" if bool(meta.get("multigraph"))
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
            node_properties=(_ATTRS, _ORDER),
            edge_properties=(_ATTRS, _ORDER),
            max_nodes=self._max_nodes,
            max_edges=self._max_edges,
            allow_full_scan=True,
        )
        graph = self._client.graph(selection)
        if graph.node_count != meta.get("node_count") or graph.edge_count != meta.get("edge_count"):
            raise RuntimeError("native Helix snapshot failed generation count verification")
        return graph

    def _read_generation_data(self, generation: str) -> dict[str, Any]:
        meta = self._metadata(generation)
        self._validate_metadata(meta)
        native = self.native_graph(generation, metadata=meta)

        nodes_with_order: list[tuple[int, dict[str, Any]]] = []
        for record in native.nodes():
            projected = dict(record.attributes)
            attrs, order = projected.get(_ATTRS), projected.get(_ORDER)
            if not isinstance(attrs, dict) or not isinstance(order, int):
                raise RuntimeError("native Helix node is missing Graphify schema fields")
            nodes_with_order.append((order, {"id": record.id, **attrs}))

        edges_with_order: list[tuple[int, dict[str, Any]]] = []
        multigraph = bool(meta.get("multigraph", False))
        for record in native.edges():
            projected = dict(record.attributes)
            attrs, order = projected.get(_ATTRS), projected.get(_ORDER)
            if not isinstance(attrs, dict) or not isinstance(order, int):
                raise RuntimeError("native Helix edge is missing Graphify schema fields")
            edge = {
                "source": record.source,
                "target": record.target,
                "relation": record.label,
                **attrs,
            }
            if multigraph:
                edge["key"] = record.graphify_key
            edges_with_order.append((order, edge))

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
            "nodes": [row for _, row in nodes_with_order],
            "links": [row for _, row in edges_with_order],
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
        if meta.get(_CHECKSUM_MODE) == _SPLIT_CHECKSUM_MODE:
            topology_checksum = _checksum(topology_payload)
            expected_topology_checksum = meta.get(_TOPOLOGY_CHECKSUM)
            if expected_topology_checksum != topology_checksum:
                raise RuntimeError(
                    "embedded Helix topology failed checksum verification: "
                    f"expected {expected_topology_checksum!r}, got {topology_checksum!r}"
                )
            state_checksum = meta.get("state_checksum")
            if not isinstance(state_checksum, str):
                raise RuntimeError(
                    "embedded Helix metadata has no durable state checksum"
                )
            actual_checksum = _generation_checksum(topology_checksum, state_checksum)
        else:
            actual_checksum = _checksum(payload)
        if expected_checksum != actual_checksum:
            raise RuntimeError(
                "embedded Helix graph failed checksum verification: "
                f"expected {expected_checksum!r}, got {actual_checksum!r}"
            )
        return payload

    @staticmethod
    def _validate_metadata(meta: dict[str, Any]) -> None:
        if meta.get("schema_version") != _SCHEMA_VERSION:
            raise RuntimeError(
                "unsupported embedded Helix graph schema: "
                f"expected {_SCHEMA_VERSION}, got {meta.get('schema_version')!r}"
            )

    def load_generation(self, generation: str) -> LoadedGraph:
        meta = self._metadata(generation)
        self._validate_metadata(meta)
        native = self.native_graph(generation, metadata=meta)
        state = self._verified_state_from_rows(
            self._read_state_rows(generation, metadata=meta), meta
        )
        decoded = _decode_state_value(state)
        if not isinstance(decoded, dict):
            raise RuntimeError("embedded Helix generation contains invalid durable state")
        return LoadedGraph(native, generation, decoded, meta, self.path)

    def load(self) -> LoadedGraph:
        return self.load_generation(self.active_generation)

    def checkpoint(self) -> None:
        # Embedded write queries await the storage commit; close() flushes the handle.
        if self._closed:
            raise RuntimeError("embedded Helix store is closed")

    def _metadata(self, generation: str) -> dict[str, Any]:
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
        rows = _rows(self._query(batch), "meta")
        if len(rows) != 1:
            raise RuntimeError("embedded Helix graph metadata is missing or duplicated")
        return _properties(rows[0], "metadata")

    def verify(self) -> dict[str, Any]:
        payload = self.read_data()
        metadata = self._metadata(self.active_generation)
        return {
            "schema_version": _SCHEMA_VERSION,
            "nodes": len(payload["nodes"]),
            "edges": len(payload["links"]),
            "checksum": metadata.get("checksum"),
        }

    def close(self) -> None:
        if not self._closed:
            try:
                self._client.close()
            finally:
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
                    *(
                        _state_revision(metadata, kind)
                        for kind in _STATE_KINDS
                    ),
                )
                if self._graph is None or version != self._version:
                    self._graph = store.load_generation(generation)
                    self._version = version
            return self._graph


def persist_graph(
    graph: GraphBuildData,
    path: str | Path = DEFAULT_PROJECT_STORE,
    *,
    state: dict[str, Any] | None = None,
) -> None:
    with HelixEmbeddedStore(path) as store:
        store.save(graph, state=state)


def persist_graph_data(data: dict[str, Any], path: str | Path) -> None:
    with HelixEmbeddedStore(path) as store:
        store.save_data(data)


def load_graph(path: str | Path = DEFAULT_PROJECT_STORE) -> LoadedGraph:
    with HelixEmbeddedStore(path, read_only=True) as store:
        return store.load()


def graph_storage_exists(path: str | Path = DEFAULT_PROJECT_STORE) -> bool:
    return Path(path).expanduser().is_dir()


def load_graph_payload(path: str | Path = DEFAULT_PROJECT_STORE) -> dict[str, Any]:
    with HelixEmbeddedStore(path, read_only=True) as store:
        return store.read_data()


__all__ = [
    "HelixEmbeddedStore",
    "HelixGraphReader",
    "DEFAULT_GLOBAL_STORE",
    "DEFAULT_MAX_EDGES",
    "DEFAULT_MAX_NODES",
    "DEFAULT_PROJECT_STORE",
    "graph_storage_exists",
    "load_graph",
    "load_graph_payload",
    "persist_graph",
    "persist_graph_data",
]
