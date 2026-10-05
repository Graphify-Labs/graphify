"""Immutable accepted-fact URL lookups; no runtime URL base or source expansion."""
from __future__ import annotations

import posixpath
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from graphify.extractors.qml_resources import resource_url
from graphify.qml_resolution_types import Resolution, answer, qml_metadata, source_path


def normalize_url(literal_url: str, base_url: str | None = None) -> str | Resolution:
    """Normalize only supported explicit URL syntax, including the runtime base."""
    if not isinstance(literal_url, str) or not literal_url or len(literal_url) > 384:
        return Resolution("unsupported", reason="invalid_url_literal")
    if literal_url.startswith(":/"):
        literal_url = "qrc" + literal_url
    try:
        parsed = urlsplit(literal_url)
        path = unquote(parsed.path, errors="strict")
    except (ValueError, UnicodeError):
        return Resolution("unsupported", reason="invalid_url_encoding_or_syntax")
    if parsed.query or parsed.fragment or parsed.netloc:
        return Resolution("unsupported", reason="url_query_fragment_or_authority")
    if "\x00" in path or "\\" in path or any(part in {".", ".."} for part in path.split("/")):
        return Resolution("unavailable", reason="url_path_escape")
    if parsed.scheme == "qrc":
        logical = resource_url("/", path.lstrip("/")) if path.startswith("/") else None
        return logical or Resolution("unsupported", reason="invalid_resource_url")
    if parsed.scheme == "file":
        return "file:" + parsed.path
    if parsed.scheme:
        return Resolution("unsupported", reason="unsupported_url_scheme")
    if not base_url:
        return Resolution("unavailable", reason="runtime_url_base_unavailable")
    base = normalize_url(base_url)
    if isinstance(base, Resolution):
        return base
    parsed_base = urlsplit(base)
    if parsed_base.scheme == "qrc":
        combined = "qrc:" + posixpath.join(posixpath.dirname(parsed_base.path), parsed.path)
    elif parsed_base.scheme == "file":
        combined = urljoin(base, literal_url)
    else:
        return Resolution("unsupported", reason="unsupported_url_base")
    return normalize_url(combined)


class QtResourceIndex:
    def __init__(self, nodes, *, root: Path):
        self.root = Path(root).resolve()
        self.nodes, self.by_file, self.components, self.aliases = {}, {}, {}, {}
        for node in nodes:
            path = source_path(node, self.root)
            if path is None or not node.get("id"):
                continue
            nid, md = node["id"], qml_metadata(node)
            self.nodes[nid] = node
            self.by_file.setdefault(path, []).append(nid)
            if md.get("kind") == "component":
                self.components.setdefault(path, []).append(nid)
            elif md.get("kind") == "resource_alias":
                self.aliases.setdefault(md.get("logical_url"), []).append(nid)

    def _file(self, path: str, *, evidence=()) -> Resolution:
        ids = self.components.get(path)
        if ids is None:
            ids = [nid for nid in self.by_file.get(path, []) if self.nodes[nid].get("type") == "file"]
        return answer(ids, reason="resource_target_outside_corpus", evidence=evidence)

    def _resource(self, literal: str) -> Resolution:
        ids = self.aliases.get(literal, [])
        if not ids:
            return Resolution("unavailable", reason="resource_alias_unavailable")
        if any(qml_metadata(self.nodes[nid]).get("locale") for nid in ids):
            return Resolution("unsupported", reason="resource_locale_dependent", evidence=tuple(ids[:50]))
        results = [self._file(qml_metadata(self.nodes[nid]).get("target_path", ""), evidence=(nid,))
                   for nid in ids]
        if any(result.target_id is None for result in results):
            return Resolution("unavailable", reason="resource_target_outside_corpus", evidence=tuple(ids[:50]))
        # Duplicate mappings remain ambiguous even when their targets coincide.
        if len(ids) != 1:
            return Resolution("ambiguous", reason="duplicate_resource_alias",
                              candidates=tuple(sorted({result.target_id for result in results
                                                       if result.target_id is not None})[:50]),
                              evidence=tuple(ids[:50]))
        return results[0]

    def resolve_url(self, literal_url: str, base_url: str | None = None) -> Resolution:
        """Resolve explicit qrc/file URLs or relative URLs with an explicit URL base."""
        normalized = normalize_url(literal_url, base_url)
        if isinstance(normalized, Resolution):
            return normalized
        parsed = urlsplit(normalized)
        path = unquote(parsed.path)
        if parsed.scheme == "qrc":
            return self._resource(normalized)
        if parsed.scheme == "file":
            local = Path(path[1:] if len(path) > 3 and path[0] == "/" and path[2] == ":" else path)
            if not local.is_absolute():
                return Resolution("unsupported", reason="file_url_not_absolute")
            try:
                accepted = local.resolve().relative_to(self.root).as_posix()
            except ValueError:
                return Resolution("unavailable", reason="file_url_outside_root")
            return self._file(accepted)
        return Resolution("unsupported", reason="unsupported_url_scheme")
