# Semantic fragment sanitizer — converts sentence-like rationale nodes into
# attributes on related nodes and removes invalid file_type values.
#
# Called from the skill merge path (see skill-devin.md) and from the in-process
# `graphify merge-chunks` command — both ingest untrusted agent-written chunk
# JSON, and validate_semantic_fragment() rejects malformed/oversized payloads and
# crafted node/edge IDs before they touch the graph. The primary build/load paths
# (build_from_json, load_graph_json) deliberately do NOT run this: they must keep
# loading valid pre-existing graphs whose AST node IDs predate the stricter
# semantic-ID charset.
from __future__ import annotations

import codecs
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

from .build import _normalize_hyperedge_members

# Labels longer than this many characters, or containing >= this many words,
# are candidates for being sentence-like rationale text rather than entity names.
_RATIONALE_MIN_CHARS = 80
_RATIONALE_MIN_WORDS = 8

# Validation limits for untrusted semantic-fragment payloads. See
# validate_semantic_fragment(). Issue #825: returned-JSON normalization for
# OpenCode and Codex agents requires a Python enforcement boundary so a
# malicious or runaway agent response cannot exhaust memory or escape the
# graphify-out chunk directory via crafted node/edge IDs.
MAX_SEMANTIC_FRAGMENT_BYTES = 25 * 1024 * 1024
# Final package-owned cached-plus-new merges may combine more than one valid
# worker fragment, but remain tightly bounded at twice the worker ceiling.
MAX_SEMANTIC_AGGREGATE_BYTES = 2 * MAX_SEMANTIC_FRAGMENT_BYTES
MAX_SEMANTIC_FRAGMENT_NODES = 10_000
MAX_SEMANTIC_FRAGMENT_EDGES = 100_000
MAX_SEMANTIC_FRAGMENT_HYPEREDGES = 10_000
MAX_SEMANTIC_HYPEREDGE_NODES = 256
MAX_SEMANTIC_ID_LENGTH = 256
VALID_SEMANTIC_FILE_TYPES = frozenset({"code", "document", "paper", "image", "rationale", "concept"})
VALID_SEMANTIC_EDGE_RELATIONS = frozenset(
    {
        "calls",
        "implements",
        "references",
        "cites",
        "conceptually_related_to",
        "shares_data_with",
        "semantically_similar_to",
        "rationale_for",
    }
)
VALID_SEMANTIC_HYPEREDGE_RELATIONS = frozenset({"participate_in", "implement", "form"})
SEMANTIC_SOURCE_MANIFEST_SCHEMA_VERSION = 1
_SEMANTIC_SOURCE_MANIFEST_MAX_BYTES = 25 * 1024 * 1024
_SEMANTIC_SOURCE_HASH_FIELD = "source_sha256"
_BINARY_SOURCE_SUFFIXES = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"})
_LINE_SPAN_RE = re.compile(r"^L([1-9]\d{0,11})(?:-L([1-9]\d{0,11}))?$")
_BYTE_SPAN_RE = re.compile(r"^B(0|[1-9]\d{0,11})-B(0|[1-9]\d{0,11})$")
# Unicode word characters are allowed: build's normalize_id preserves CJK /
# Cyrillic / accented-Latin identifiers, so an ASCII-only gate would reject valid
# ids that the loader accepts. The explicit path-separator / ".." check in
# _validate_semantic_id still blocks directory escape (#825); "/", "\\", spaces,
# "@", "#" etc. are not \w and remain rejected.
_SEMANTIC_ID_RE = re.compile(r"^[\w.:-]+$")


@dataclass(frozen=True)
class PreparedSemanticSourceManifest:
    """Validated, immutable source snapshot used across a complete merge.

    Preparing resolves and hashes every source once. Fragment validation and
    digest binding then use only this sealed in-memory copy; a final explicit
    recheck immediately before atomic replacement detects changes made while
    agents or JSON serialization were running.
    """

    root: Path
    sources: Mapping[str, Mapping[str, object]]


def _read_bounded_bytes(path: Path, limit: int) -> bytes:
    """Read at most ``limit`` bytes from one opened descriptor.

    The extra-byte probe keeps the size cap effective even when an untrusted
    path is replaced or grows between metadata checks and the read.
    """
    with path.open("rb") as handle:
        payload = handle.read(limit + 1)
    if len(payload) > limit:
        raise ValueError(f"payload exceeds {limit} bytes")
    return payload


def _stream_source_metadata(path: Path) -> tuple[str, int, str]:
    """Hash one source and derive its addressing extent without loading it whole."""
    digest = hashlib.sha256()
    byte_extent = 0
    binary = path.suffix.lower() in _BINARY_SOURCE_SUFFIXES
    decoder = None if binary else codecs.getincrementaldecoder("utf-8")("strict")
    line_breaks = 0
    saw_text = False
    last_was_break = False
    previous_was_cr = False

    def consume_text(text: str) -> None:
        nonlocal line_breaks, saw_text, last_was_break, previous_was_cr
        if text:
            saw_text = True
        for character in text:
            if character == "\n" and previous_was_cr:
                previous_was_cr = False
                last_was_break = True
                continue
            if character in "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029":
                line_breaks += 1
                last_was_break = True
                previous_was_cr = character == "\r"
            else:
                last_was_break = False
                previous_was_cr = False

    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            byte_extent += len(chunk)
            if decoder is not None:
                try:
                    consume_text(decoder.decode(chunk))
                except UnicodeDecodeError:
                    decoder = None
        if decoder is not None:
            try:
                consume_text(decoder.decode(b"", final=True))
            except UnicodeDecodeError:
                decoder = None

    if decoder is None:
        return "byte", byte_extent, digest.hexdigest()
    line_extent = line_breaks + int(saw_text and not last_was_break)
    return "line", line_extent, digest.hexdigest()


def snapshot_semantic_sources(files: Iterable[str | Path], root: Path) -> dict:
    """Snapshot the exact sources a semantic extraction agent may cite.

    The manifest is created before untrusted extraction starts. It binds each
    verbatim dispatched path to its current resolved file, SHA-256 digest, and
    valid line or byte-span extent. Paths that do not resolve to regular files
    beneath ``root`` fail closed.
    """
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"could not resolve source root {root}: {exc}") from exc
    if not resolved_root.is_dir():
        raise ValueError(f"source root is not a directory: {resolved_root}")

    sources: dict[str, dict] = {}
    for supplied in files:
        source_file = str(supplied)
        if not source_file:
            continue
        candidate = Path(source_file)
        if not candidate.is_absolute():
            candidate = resolved_root / candidate
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(resolved_root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError(
                f"source path does not resolve to a file inside {resolved_root}: {source_file}"
            ) from exc
        if not resolved.is_file():
            raise ValueError(f"source path is not a regular file: {source_file}")
        try:
            span_kind, extent, digest = _stream_source_metadata(resolved)
        except OSError as exc:
            raise ValueError(f"could not read source file {source_file}: {exc}") from exc

        entry = {
            "resolved_path": str(resolved),
            "sha256": digest,
            "span_kind": span_kind,
            "extent": extent,
        }
        previous = sources.get(source_file)
        if previous is not None and previous != entry:
            raise ValueError(f"duplicate source path resolves inconsistently: {source_file}")
        sources[source_file] = entry

    return {
        "schema_version": SEMANTIC_SOURCE_MANIFEST_SCHEMA_VERSION,
        "root": str(resolved_root),
        "sources": sources,
    }


def load_semantic_source_manifest(
    path: Path,
    *,
    expected_sha256: str,
) -> tuple[PreparedSemanticSourceManifest | None, list[str]]:
    """Load and prepare a source snapshot whose parent-held seal must match."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        return None, ["expected manifest SHA-256 must be a lowercase digest"]
    try:
        payload = _read_bounded_bytes(
            path,
            _SEMANTIC_SOURCE_MANIFEST_MAX_BYTES,
        )
        if hashlib.sha256(payload).hexdigest() != expected_sha256:
            return None, ["manifest SHA-256 differs from the parent-held snapshot seal"]
        manifest = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"invalid source manifest JSON: {exc}"]
    except UnicodeDecodeError as exc:
        return None, [f"source manifest is not UTF-8: {exc}"]
    except ValueError as exc:
        return None, [f"source manifest {exc}"]
    except OSError as exc:
        return None, [f"could not read source manifest {path}: {exc}"]
    prepared, errors = prepare_semantic_source_manifest(manifest)
    return (None, errors) if errors else (prepared, [])


def validate_semantic_fragment(
    fragment: object,
    *,
    source_manifest: object | None = None,
    enforce_collection_limits: bool = True,
    max_bytes: int | None = None,
) -> list[str]:
    """Return validation errors for an untrusted semantic extraction fragment.

    Empty list means valid. Called by skill merge code before
    sanitize_semantic_fragment() so malformed or malicious agent JSON is
    rejected before it touches the graph. Parameter is `object` (not `dict`)
    because we may be handed arbitrary deserialized JSON — the first check
    rejects anything that isn't a dict.
    """
    if not isinstance(fragment, dict):
        return ["fragment must be a JSON object"]
    if max_bytes is None:
        max_bytes = MAX_SEMANTIC_FRAGMENT_BYTES

    errors: list[str] = []
    prepared_sources: Mapping[str, Mapping[str, object]] | None = None
    if source_manifest is not None:
        prepared_manifest, manifest_errors = _coerce_prepared_semantic_sources(source_manifest)
        errors.extend(f"source manifest: {error}" for error in manifest_errors)
        if prepared_manifest is not None:
            prepared_sources = prepared_manifest.sources
    try:
        payload = json.dumps(fragment, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        return [f"fragment is not JSON-serializable: {exc}"]

    if len(payload) > max_bytes:
        errors.append(f"payload is {len(payload)} bytes; max is {max_bytes}")

    nodes = fragment.get("nodes", [])
    edges = fragment.get("edges", [])
    if not isinstance(nodes, list):
        errors.append("nodes must be a list")
        nodes = []
    elif enforce_collection_limits and len(nodes) > MAX_SEMANTIC_FRAGMENT_NODES:
        errors.append(f"nodes has {len(nodes)} entries; max is {MAX_SEMANTIC_FRAGMENT_NODES}")

    if not isinstance(edges, list):
        errors.append("edges must be a list")
        edges = []
    elif enforce_collection_limits and len(edges) > MAX_SEMANTIC_FRAGMENT_EDGES:
        errors.append(f"edges has {len(edges)} entries; max is {MAX_SEMANTIC_FRAGMENT_EDGES}")

    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"nodes[{i}] must be an object")
            continue
        _validate_semantic_id(errors, f"nodes[{i}].id", node.get("id"))
        if prepared_sources is not None:
            _validate_semantic_provenance(errors, f"nodes[{i}]", node, prepared_sources)
        # file_type is intentionally NOT rejected here. It carries no security
        # risk (it can't exhaust memory or escape a directory), and
        # build_from_json already coerces every value via _FILE_TYPE_SYNONYMS
        # (unknown -> "concept", #840). Rejecting a whole chunk over a synonym
        # like "markdown"/"tool"/"framework" that the loader would happily map is
        # pure data loss, so leave file_type normalization to build.

    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"edges[{i}] must be an object")
            continue
        _validate_semantic_id(errors, f"edges[{i}].source", edge.get("source"))
        _validate_semantic_id(errors, f"edges[{i}].target", edge.get("target"))
        _validate_semantic_relation(
            errors,
            f"edges[{i}].relation",
            edge.get("relation"),
            VALID_SEMANTIC_EDGE_RELATIONS,
        )
        if prepared_sources is not None:
            _validate_semantic_provenance(errors, f"edges[{i}]", edge, prepared_sources)

    hyperedges = fragment.get("hyperedges", [])
    if hyperedges is None:
        hyperedges = []
    if not isinstance(hyperedges, list):
        errors.append("hyperedges must be a list")
    else:
        if (
            enforce_collection_limits
            and len(hyperedges) > MAX_SEMANTIC_FRAGMENT_HYPEREDGES
        ):
            errors.append(
                f"hyperedges has {len(hyperedges)} entries; "
                f"max is {MAX_SEMANTIC_FRAGMENT_HYPEREDGES}"
            )
        for i, he in enumerate(hyperedges):
            if not isinstance(he, dict):
                errors.append(f"hyperedges[{i}] must be an object")
                continue
            # Fold alias member keys (members/node_ids) onto `nodes` (#1561) so
            # an alias-keyed hyperedge isn't rejected here for "nodes must be a
            # list" before it ever reaches build's normalization.
            _normalize_hyperedge_members(he)
            _validate_semantic_id(errors, f"hyperedges[{i}].id", he.get("id"))
            _validate_semantic_relation(
                errors,
                f"hyperedges[{i}].relation",
                he.get("relation"),
                VALID_SEMANTIC_HYPEREDGE_RELATIONS,
            )
            if prepared_sources is not None:
                _validate_semantic_provenance(errors, f"hyperedges[{i}]", he, prepared_sources)
            he_nodes = he.get("nodes")
            if not isinstance(he_nodes, list):
                errors.append(f"hyperedges[{i}].nodes must be a list")
                continue
            if len(he_nodes) > MAX_SEMANTIC_HYPEREDGE_NODES:
                errors.append(
                    f"hyperedges[{i}].nodes has {len(he_nodes)} entries; "
                    f"max is {MAX_SEMANTIC_HYPEREDGE_NODES}"
                )
            for j, ref in enumerate(he_nodes):
                _validate_semantic_id(errors, f"hyperedges[{i}].nodes[{j}]", ref)

    return errors


def load_validated_semantic_fragment(
    path: Path,
    *,
    source_manifest: object | None = None,
    enforce_collection_limits: bool = True,
    max_bytes: int | None = None,
) -> tuple[dict | None, list[str]]:
    """Load and validate a semantic chunk, rejecting oversize files before parsing."""
    fragment, errors, _ = load_validated_semantic_fragment_with_size(
        path,
        source_manifest=source_manifest,
        enforce_collection_limits=enforce_collection_limits,
        max_bytes=max_bytes,
    )
    return fragment, errors


def load_validated_semantic_fragment_with_size(
    path: Path,
    *,
    source_manifest: object | None = None,
    enforce_collection_limits: bool = True,
    max_bytes: int | None = None,
) -> tuple[dict | None, list[str], int]:
    """Load a validated semantic chunk and report exact descriptor-read bytes.

    A single bounded descriptor read prevents an attacker-supplied multi-gigabyte
    chunk from reaching JSON parsing. The returned byte count lets callers cap a
    collection of otherwise valid inputs without undercounting JSON whitespace.
    JSON decode errors are returned as validation errors rather than raised so
    callers can reject the complete fragment batch before merge or persistence.
    """
    if max_bytes is None:
        max_bytes = MAX_SEMANTIC_FRAGMENT_BYTES
    payload_size = 0
    try:
        payload = _read_bounded_bytes(path, max_bytes)
        payload_size = len(payload)
        fragment = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"invalid JSON: {exc}"], payload_size
    except UnicodeDecodeError as exc:
        return None, [f"invalid UTF-8: {exc}"], payload_size
    except ValueError as exc:
        return None, [str(exc)], payload_size
    except OSError as exc:
        return None, [f"could not read {path}: {exc}"], payload_size
    errors = validate_semantic_fragment(
        fragment,
        source_manifest=source_manifest,
        enforce_collection_limits=enforce_collection_limits,
        max_bytes=max_bytes,
    )
    if not errors and source_manifest is not None:
        bind_semantic_source_hashes(fragment, source_manifest)
    return (None, errors, payload_size) if errors else (fragment, [], payload_size)


def _coerce_prepared_semantic_sources(
    manifest: object,
) -> tuple[PreparedSemanticSourceManifest | None, list[str]]:
    if isinstance(manifest, PreparedSemanticSourceManifest):
        return manifest, []
    return prepare_semantic_source_manifest(manifest)


def prepare_semantic_source_manifest(
    manifest: object,
) -> tuple[PreparedSemanticSourceManifest | None, list[str]]:
    """Validate and resolve a source manifest against current filesystem state."""
    if not isinstance(manifest, dict):
        return None, ["must be a JSON object"]
    if manifest.get("schema_version") != SEMANTIC_SOURCE_MANIFEST_SCHEMA_VERSION:
        return None, [
            "schema_version must be "
            f"{SEMANTIC_SOURCE_MANIFEST_SCHEMA_VERSION}"
        ]
    root_value = manifest.get("root")
    if not isinstance(root_value, str) or not root_value:
        return None, ["root must be a non-empty string"]
    try:
        root = Path(root_value).resolve(strict=True)
    except OSError as exc:
        return None, [f"root does not resolve: {exc}"]
    if not root.is_dir():
        return None, [f"root is not a directory: {root}"]

    raw_sources = manifest.get("sources")
    if not isinstance(raw_sources, dict):
        return None, ["sources must be an object"]

    prepared: dict[str, dict] = {}
    errors: list[str] = []
    for source_file, raw_entry in raw_sources.items():
        field = f"sources[{source_file!r}]"
        if not isinstance(source_file, str) or not source_file:
            errors.append("source keys must be non-empty strings")
            continue
        if not isinstance(raw_entry, dict):
            errors.append(f"{field} must be an object")
            continue
        resolved_value = raw_entry.get("resolved_path")
        digest = raw_entry.get("sha256")
        span_kind = raw_entry.get("span_kind")
        extent = raw_entry.get("extent")
        allowed_spans = raw_entry.get("allowed_spans")
        if not isinstance(resolved_value, str) or not resolved_value:
            errors.append(f"{field}.resolved_path must be a non-empty string")
            continue
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(f"{field}.sha256 must be a lowercase SHA-256 digest")
            continue
        if span_kind not in {"line", "byte"}:
            errors.append(f"{field}.span_kind must be 'line' or 'byte'")
            continue
        if not isinstance(extent, int) or isinstance(extent, bool) or extent < 0:
            errors.append(f"{field}.extent must be a non-negative integer")
            continue
        prepared_spans: tuple[tuple[int, int], ...] | None = None
        if allowed_spans is not None:
            if not isinstance(allowed_spans, list):
                errors.append(f"{field}.allowed_spans must be a list")
                continue
            parsed_spans: list[tuple[int, int]] = []
            for index, allowed_span in enumerate(allowed_spans):
                parsed, span_error = _parse_source_span(
                    allowed_span,
                    span_kind,
                    extent,
                )
                if span_error:
                    errors.append(
                        f"{field}.allowed_spans[{index}] {span_error}"
                    )
                elif parsed is not None:
                    parsed_spans.append(parsed)
            if any(error.startswith(f"{field}.allowed_spans") for error in errors):
                continue
            prepared_spans = tuple(parsed_spans)
        try:
            resolved = Path(resolved_value).resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append(f"{field}.resolved_path no longer resolves inside root: {exc}")
            continue
        if not resolved.is_file():
            errors.append(f"{field}.resolved_path is not a regular file")
            continue
        candidate = Path(source_file)
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            current_from_key = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            errors.append(f"{field} source_file no longer resolves: {exc}")
            continue
        if current_from_key != resolved:
            errors.append(f"{field} source_file resolves to a different file")
            continue
        try:
            current_span_kind, current_extent, current_digest = (
                _stream_source_metadata(resolved)
            )
        except OSError as exc:
            errors.append(f"{field} could not be read: {exc}")
            continue
        if current_digest != digest:
            errors.append(f"{field} is stale: current SHA-256 differs from snapshot")
            continue
        if current_span_kind != span_kind:
            errors.append(f"{field}.span_kind differs from current source")
            continue
        if current_extent != extent:
            errors.append(f"{field}.extent differs from current source")
            continue
        prepared_entry: dict[str, object] = {
            "resolved_path": resolved,
            "sha256": digest,
            "span_kind": span_kind,
            "extent": extent,
        }
        if prepared_spans is not None:
            prepared_entry["allowed_spans"] = prepared_spans
        prepared[source_file] = MappingProxyType(prepared_entry)
    if errors:
        return None, errors
    return PreparedSemanticSourceManifest(
        root=root,
        sources=MappingProxyType(prepared),
    ), []


def revalidate_semantic_sources(
    manifest: PreparedSemanticSourceManifest,
) -> list[str]:
    """Recheck a prepared snapshot immediately before accepting persistence."""
    errors: list[str] = []
    for source_file, source in manifest.sources.items():
        field = f"sources[{source_file!r}]"
        resolved = source["resolved_path"]
        if not isinstance(resolved, Path):
            errors.append(f"{field}.resolved_path is invalid")
            continue
        candidate = Path(source_file)
        if not candidate.is_absolute():
            candidate = manifest.root / candidate
        try:
            current_from_key = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            errors.append(f"{field} source_file no longer resolves: {exc}")
            continue
        if current_from_key != resolved:
            errors.append(f"{field} source_file resolves to a different file")
            continue
        try:
            current_span_kind, current_extent, current_digest = (
                _stream_source_metadata(resolved)
            )
        except OSError as exc:
            errors.append(f"{field} could not be read: {exc}")
            continue
        if current_digest != source["sha256"]:
            errors.append(f"{field} is stale: current SHA-256 differs from snapshot")
            continue
        if (
            current_span_kind != source["span_kind"]
            or current_extent != source["extent"]
        ):
            errors.append(f"{field} addressing metadata differs from snapshot")
    return errors


def _validate_semantic_relation(
    errors: list[str],
    field: str,
    value: object,
    vocabulary: frozenset[str],
) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{field} must be a non-empty string")
        return
    if value not in vocabulary:
        errors.append(
            f"{field} must be one of: {', '.join(sorted(vocabulary))}; got {value!r}"
        )


def _validate_semantic_provenance(
    errors: list[str],
    field: str,
    record: dict,
    sources: Mapping[str, Mapping[str, object]],
) -> None:
    source_file = record.get("source_file")
    if not isinstance(source_file, str) or not source_file:
        errors.append(f"{field}.source_file must be a non-empty string")
        return
    source = sources.get(source_file)
    if source is None:
        errors.append(f"{field}.source_file was not present in the dispatched source snapshot")
        return
    bound_digest = record.get(_SEMANTIC_SOURCE_HASH_FIELD)
    if bound_digest is not None:
        if (
            not isinstance(bound_digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", bound_digest)
        ):
            errors.append(
                f"{field}.{_SEMANTIC_SOURCE_HASH_FIELD} must be a lowercase SHA-256 digest"
            )
            return
        if bound_digest != source["sha256"]:
            errors.append(
                f"{field}.{_SEMANTIC_SOURCE_HASH_FIELD} differs from the current source snapshot"
            )
            return
    location = record.get("source_location")
    if not isinstance(location, str) or not location:
        errors.append(f"{field}.source_location must be a non-empty exact span")
        return

    parsed, span_error = _parse_source_span(
        location,
        str(source["span_kind"]),
        int(source["extent"]),
    )
    if span_error:
        errors.append(f"{field}.source_location {span_error}")
        return
    allowed_spans = source.get("allowed_spans")
    if (
        parsed is not None
        and allowed_spans is not None
        and not any(start <= parsed[0] and parsed[1] <= end for start, end in allowed_spans)
    ):
        errors.append(
            f"{field}.source_location is outside the dispatched source span"
        )


def _parse_source_span(
    location: object,
    span_kind: str,
    extent: int,
) -> tuple[tuple[int, int] | None, str | None]:
    if not isinstance(location, str) or not location:
        return None, "must be a non-empty exact span"
    if span_kind == "line":
        match = _LINE_SPAN_RE.fullmatch(location)
        if match is None:
            return None, "must be L<start> or L<start>-L<end>"
        start = int(match.group(1))
        end = int(match.group(2) or match.group(1))
        if end < start:
            return None, "end precedes start"
        if end > extent:
            return None, f"exceeds {extent} source lines"
        return (start, end), None

    match = _BYTE_SPAN_RE.fullmatch(location)
    if match is None:
        return None, "must be B<start>-B<end>"
    start = int(match.group(1))
    end = int(match.group(2))
    if end <= start:
        return None, "byte end must be greater than start"
    if end > extent:
        return None, f"exceeds {extent} source bytes"
    return (start, end), None


def bind_semantic_source_hashes(fragment: dict, source_manifest: object) -> None:
    """Stamp validated records with the trusted source snapshot digest."""
    prepared, errors = _coerce_prepared_semantic_sources(source_manifest)
    if errors or prepared is None:
        raise ValueError("cannot bind invalid semantic source manifest")
    sources = prepared.sources
    for collection in ("nodes", "edges", "hyperedges"):
        for record in fragment.get(collection, []) or []:
            if isinstance(record, dict):
                source = sources.get(record.get("source_file"))
                if source is not None:
                    record[_SEMANTIC_SOURCE_HASH_FIELD] = source["sha256"]


def prepare_current_semantic_evidence(
    fragment: object,
    root: Path,
) -> tuple[PreparedSemanticSourceManifest | None, list[str]]:
    """Validate one assembled semantic result against current source files.

    Existing ``source_sha256`` values are compared with the new snapshot before
    they are rebound, so a source changed after provider validation or cache
    lookup fails closed instead of being silently blessed as current.
    """
    if not isinstance(fragment, dict):
        return None, ["fragment must be a JSON object"]
    source_files: list[str] = []
    for collection in ("nodes", "edges", "hyperedges"):
        records = fragment.get(collection, [])
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            source_file = record.get("source_file")
            if isinstance(source_file, str) and source_file:
                source_files.append(source_file)
    try:
        manifest = snapshot_semantic_sources(dict.fromkeys(source_files), root)
    except ValueError as exc:
        return None, [str(exc)]
    prepared, manifest_errors = prepare_semantic_source_manifest(manifest)
    if manifest_errors or prepared is None:
        return None, manifest_errors
    validation_errors = validate_semantic_fragment(
        fragment,
        source_manifest=prepared,
    )
    if validation_errors:
        return None, validation_errors
    bind_semantic_source_hashes(fragment, prepared)
    return prepared, []


def _validate_semantic_id(errors: list[str], field: str, value: object) -> None:
    if not isinstance(value, str):
        errors.append(f"{field} must be a string")
        return
    if not value:
        errors.append(f"{field} must not be empty")
        return
    if len(value) > MAX_SEMANTIC_ID_LENGTH:
        errors.append(f"{field} is {len(value)} chars; max is {MAX_SEMANTIC_ID_LENGTH}")
    if "/" in value or "\\" in value or ".." in value:
        errors.append(f"{field} must not contain path separators or '..'")
    if not _SEMANTIC_ID_RE.fullmatch(value):
        errors.append(f"{field} contains unsupported characters")


def _provenance_covers(container: dict, evidence: dict) -> bool:
    """Whether ``container``'s cited span also supports ``evidence``.

    Legacy sanitizer callers without provenance keep their historical behavior.
    Once either record carries provenance, both must name the same source and
    snapshot, and the container's exact span must enclose the evidence span.
    """
    container_location = container.get("source_location")
    evidence_location = evidence.get("source_location")
    if container_location is None and evidence_location is None:
        return True
    if (
        not isinstance(container_location, str)
        or not isinstance(evidence_location, str)
        or container.get("source_file") != evidence.get("source_file")
        or container.get(_SEMANTIC_SOURCE_HASH_FIELD)
        != evidence.get(_SEMANTIC_SOURCE_HASH_FIELD)
    ):
        return False
    if container_location.startswith("L") and evidence_location.startswith("L"):
        pattern = _LINE_SPAN_RE
    elif container_location.startswith("B") and evidence_location.startswith("B"):
        pattern = _BYTE_SPAN_RE
    else:
        return False
    container_match = pattern.fullmatch(container_location)
    evidence_match = pattern.fullmatch(evidence_location)
    if container_match is None or evidence_match is None:
        return False
    container_start = int(container_match.group(1))
    container_end = int(container_match.group(2) or container_match.group(1))
    evidence_start = int(evidence_match.group(1))
    evidence_end = int(evidence_match.group(2) or evidence_match.group(1))
    return container_start <= evidence_start and evidence_end <= container_end


def sanitize_semantic_fragment(fragment: dict) -> dict:
    """Clean up a semantic extraction fragment in-place.

    Operations:
    1. Removes nodes with ``file_type: "rationale"`` or ``file_type: "concept"``
       that were emitted by an LLM (these are not valid semantic entity types).
    2. Detects nodes whose label reads like a sentence / rationale paragraph
       AND that participate in a ``rationale_for`` edge, then converts the
       label into a ``rationale`` attribute on the target node and removes
       the source-node + its edges. The ``rationale_for`` edge signal applies
       regardless of the source node's ``file_type`` — sentence-like nodes
       with allowed types (``document``, ``code``) are still cleaned up when
       they're explicitly marked as rationale.
    3. Strips nodes whose only distinguishing field is the label itself
       (empty id — likely LLM hallucination).
    4. Filters hyperedges so they cannot reference removed or unknown node
       IDs after the cleanup passes above. A hyperedge with fewer than two
       surviving members is dropped.

    Returns the same dict for convenience.
    """
    _invalid_ft = frozenset({"rationale", "concept"})

    nodes: list[dict] = fragment.get("nodes", [])
    edges: list[dict] = fragment.get("edges", [])
    hyperedges: list[dict] = fragment.get("hyperedges", []) or []

    # ---- build lookup maps --------------------------------------------------
    node_by_id: dict[str, dict] = {}
    for n in nodes:
        nid = n.get("id", "")
        if nid:
            node_by_id[nid] = n

    # Pre-collect node IDs that source a `rationale_for` edge — these are
    # candidates for sentence-like cleanup even when file_type is allowed.
    rationale_for_sources: set[str] = set()
    for e in edges:
        if e.get("relation") == "rationale_for":
            src = e.get("source", "")
            if src:
                rationale_for_sources.add(src)

    # ---- pass 1: identify nodes to remove + rationale candidates -----------
    rationale_candidates: list[dict] = []
    remove_ids: set[str] = set()
    keep_nodes: list[dict] = []
    for n in nodes:
        nid = n.get("id", "")
        if not nid:
            # Node without an id cannot be referenced — discard.
            continue
        ft = n.get("file_type", "")
        label = n.get("label", "")
        if ft in _invalid_ft:
            # Explicitly-invalid file_type ("rationale" or "concept"): if
            # the label looks like a sentence we may convert to attribute.
            if _is_sentence_like_rationale_label(label):
                rationale_candidates.append(n)
            remove_ids.add(nid)
            continue
        if nid in rationale_for_sources and _is_sentence_like_rationale_label(label):
            # Allowed file_type, but the node sources a `rationale_for` edge
            # AND its label is sentence-like prose. Treat it as rationale
            # cleanup material rather than a real graph entity.
            rationale_candidates.append(n)
            remove_ids.add(nid)
            continue
        keep_nodes.append(n)

    # ---- pass 2: convert sentence-nodes → rationale attributes --------------
    # Only `rationale_for` edges propagate the rationale text. Other outgoing
    # edges (e.g. references, conceptually_related_to) are NOT used as
    # attribute-propagation paths — that would corrupt unrelated nodes by
    # attaching rationale meant for a different target.
    rationale_attrs: dict[str, list[str]] = {}
    for rn in rationale_candidates:
        rn_id = rn.get("id", "")
        text = rn.get("label", "").strip()
        for e in edges:
            if e.get("relation") != "rationale_for":
                continue
            if e.get("source") != rn_id:
                continue
            target_id = e.get("target")
            if target_id not in node_by_id or target_id in remove_ids:
                continue
            target = node_by_id[target_id]
            if not (
                _provenance_covers(target, rn)
                and _provenance_covers(target, e)
            ):
                continue
            rationale_attrs.setdefault(target_id, []).append(text)

    for target_id, texts in rationale_attrs.items():
        if target_id in node_by_id and target_id not in remove_ids:
            _append_rationale_attr(node_by_id[target_id], texts)

    # ---- pass 3: strip edges referencing removed nodes ----------------------
    keep_edges: list[dict] = []
    for e in edges:
        src = e.get("source", "")
        tgt = e.get("target", "")
        if src in remove_ids or tgt in remove_ids:
            continue
        keep_edges.append(e)

    # ---- pass 4: filter hyperedges to surviving node IDs --------------------
    surviving_ids: set[str] = {n.get("id", "") for n in keep_nodes}
    surviving_ids.discard("")
    keep_hyperedges: list[dict] = []
    for he in hyperedges:
        if not isinstance(he, dict):
            continue
        # Fold alias member keys (members/node_ids) onto `nodes` (#1561) so an
        # alias-keyed hyperedge isn't silently dropped below for a missing
        # `nodes` list before build can canonicalize it.
        _normalize_hyperedge_members(he)
        he_nodes = he.get("nodes")
        if not isinstance(he_nodes, list):
            continue
        filtered = [ref for ref in he_nodes if isinstance(ref, str) and ref in surviving_ids]
        if len(filtered) < 2:
            # A hyperedge needs at least two surviving members to be meaningful.
            continue
        if len(filtered) != len(he_nodes):
            he = dict(he)
            he["nodes"] = filtered
        keep_hyperedges.append(he)

    fragment["nodes"] = keep_nodes
    fragment["edges"] = keep_edges
    fragment["hyperedges"] = keep_hyperedges
    return fragment


def _is_sentence_like_rationale_label(label: str) -> bool:
    """Return True if *label* looks like prose / rationale text rather than an
    entity or concept name.

    Heuristics (no false positives on short-concept-edge-cases):
    - Longer than *_RATIONALE_MIN_CHARS* chars, OR
    - At least *_RATIONALE_MIN_WORDS* whitespace-delimited tokens, AND
    - Contains at least one sentence-ending punctuation mark (``. ! ?``) or a
      colon (common in "Decision: ..." rationales).
    """
    if not label:
        return False
    label = label.strip()
    if len(label) < _RATIONALE_MIN_CHARS:
        word_count = len(label.split())
        if word_count < _RATIONALE_MIN_WORDS:
            return False
    # Must look like actual prose: has sentence-ending punctuation or a colon.
    return bool(re.search(r"[.!?:]", label))


def _append_rationale_attr(node: dict, texts: list[str]) -> None:
    """Append one or more rationale strings to *node*'s ``rationale`` attribute.

    If the attribute already exists the new texts are appended with a
    double-newline separator so downstream consumers can distinguish distinct
    rationale fragments.
    """
    existing = node.get("rationale", "")
    new_text = "\n\n".join(texts).strip()
    if existing:
        node["rationale"] = existing + "\n\n" + new_text
    else:
        node["rationale"] = new_text
