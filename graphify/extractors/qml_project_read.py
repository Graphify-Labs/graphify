"""Bounded original-byte Qt metadata input and source-owned fact construction."""
from __future__ import annotations

import hashlib
import posixpath
from bisect import bisect_left
from pathlib import Path

from graphify.qml_resolution_types import fact_edge, fact_node
from graphify.extractors.qml_source_identity import relative_qml_source

MAX_PROJECT_BYTES = 1_048_576
MAX_PROJECT_FACTS = 10_000


class MetadataError(ValueError):
    def __init__(self, code: str, reason: str):
        self.code, self.reason = code, reason
        super().__init__(f"{code}: {reason}")


def literal_path(source_file: str, value: str) -> str | None:
    """Normalize a literal within the corpus without reading its target."""
    value = value.replace("\\", "/")
    if not value or value.startswith("/") or ":" in value or "\x00" in value:
        return None
    path = posixpath.normpath(posixpath.join(posixpath.dirname(source_file), value))
    return None if path == ".." or path.startswith("../") else path


class ProjectFacts:
    """One accepted metadata file owns records; no mutable project context exists."""
    def __init__(self, source: bytes | str, relative_file: str, metadata_format: str):
        self.raw = source.encode("utf-8") if isinstance(source, str) else source
        if len(self.raw) > MAX_PROJECT_BYTES:
            raise MetadataError("QML_PROJECT_LIMIT", "metadata_size_limit")
        self.text = self.raw.decode("utf-8")
        self.file = relative_file
        self.format = metadata_format
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self.diagnostics: list[dict] = []
        self.counts: dict[tuple, int] = {}
        self.newlines = [pos for pos, char in enumerate(self.raw) if char == 10]
        self.byte_offsets = [0]
        for char in self.text:
            self.byte_offsets.append(self.byte_offsets[-1] + len(char.encode("utf-8")))
        self.file_node = self.add("file", metadata_format, Path(relative_file).name,
                                  0, len(self.raw), metadata_format=metadata_format)

    def span(self, start: int, end: int) -> dict:
        def point(offset):
            row = bisect_left(self.newlines, offset)
            return row, offset - (self.newlines[row - 1] + 1 if row else 0)
        sr, sc = point(start)
        er, ec = point(end)
        return {"start_byte": start, "end_byte": end, "start_row": sr,
                "start_column": sc, "end_row": er, "end_column": ec}

    def add(self, kind: str, key, label: str, start: int, end: int, *, owner=None,
            **fields) -> dict:
        if len(self.nodes) >= MAX_PROJECT_FACTS:
            raise MetadataError("QML_PROJECT_LIMIT", "metadata_fact_limit")
        digest = hashlib.sha256(repr((kind, key)).encode("utf-8")).hexdigest()
        occurrence = self.counts.get((kind, digest), 0)
        self.counts[kind, digest] = occurrence + 1
        location = self.span(start, end)
        node = fact_node(self.file, kind, (digest, occurrence), label,
                         location["start_row"] + 1, span=location, **fields)
        self.nodes.append(node)
        parent = owner or getattr(self, "file_node", None)
        if parent:
            self.edges.append(fact_edge(parent["id"], node["id"], "contains", node,
                                        "qt_metadata_declaration", span=location))
        return node

    def add_chars(self, kind, key, label, start, end, **fields):
        return self.add(kind, key, label, self.byte_offsets[start], self.byte_offsets[end], **fields)

    def reject(self, reason: str, start=0, end=None, *, code="QML_PROJECT_UNSUPPORTED"):
        if len(self.diagnostics) < 50:
            self.diagnostics.append({"code": code, "reason": reason, "severity": "error",
                                     "owner": self.format, "source_file": self.file,
                                     "span": self.span(start, len(self.raw) if end is None else end),
                                     "message": "Qt metadata coverage is incomplete",
                                     "recovery": "Use the documented literal subset and retry."})

    def result(self) -> dict:
        result: dict = {"nodes": self.nodes, "edges": self.edges, "diagnostics": self.diagnostics}
        if self.diagnostics:
            result.update(error="QML_PROJECT_UNSUPPORTED: incomplete metadata coverage", partial=True,
                          qml_failures=[{"code": d["code"], "source_file": self.file,
                                         "reason": d["reason"]} for d in self.diagnostics])
        return result


def failure(relative_file: str, metadata_format: str, error: Exception) -> dict:
    code = getattr(error, "code", "QML_PROJECT_READ")
    reason = getattr(error, "reason", "metadata_unreadable_or_outside_root")
    identity_failed = code == "SOURCE_INPUT_IDENTITY_FAILED"
    # Native admission failed before a source label was established. Match the
    # other typed readers' explicit unavailable context, without a raw basename.
    if identity_failed:
        relative_file = ""
    return {"nodes": [], "edges": [], "error": f"{code}: metadata rejected",
            "diagnostics": [{"code": code, "reason": reason, "severity": "error",
                             "owner": metadata_format, "source_file": relative_file,
                             "message": "Source input identity unavailable" if identity_failed else
                                        "Qt metadata rejected before source expansion",
                             "recovery": "Repair filesystem access and retry." if identity_failed else
                                         "Use accepted UTF-8 metadata within documented bounds."}],
            "qml_failures": [{"code": code, "source_file": relative_file, "reason": reason}]}


def extract_project(path: Path, root: Path | None, metadata_format: str, parser) -> dict:
    """Read original bytes with stat/read bounds and an explicit source-root gate."""
    path = Path(path)
    relative = path.name
    try:
        # Resolve authority before retaining a lexical source owner. Literal
        # targets remain relative to that declaration; no new file is admitted.
        relative = relative_qml_source(path, root)
        if path.stat().st_size > MAX_PROJECT_BYTES:
            raise MetadataError("QML_PROJECT_LIMIT", "metadata_size_limit")
        with path.open("rb") as stream:
            raw = stream.read(MAX_PROJECT_BYTES + 1)
        if len(raw) > MAX_PROJECT_BYTES:
            raise MetadataError("QML_PROJECT_LIMIT", "metadata_size_limit")
        return parser(raw, relative_file=relative)
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        return failure(relative, metadata_format, exc)
