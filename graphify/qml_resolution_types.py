"""Portable Qt/QML fact and resolution values; no corpus discovery or execution."""

from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass
from pathlib import Path

from graphify.extractors.qml_facts import encode_metadata, make_qml_id
from graphify.extractors.qml_facts import qml_metadata as literal_qml_metadata


@dataclass(frozen=True)
class Resolution:
    """One scoped answer, including why a concrete endpoint was not selected."""

    status: str
    target_id: str | None = None
    reason: str = ""
    evidence: tuple[str, ...] = ()
    candidates: tuple[str, ...] = ()

    def __post_init__(self):
        if (self.status == "resolved") != (self.target_id is not None):
            raise ValueError("QML_RESOLUTION: target must exist exactly for resolved answers")


def answer(candidates, *, reason="missing", evidence=()) -> Resolution:
    """Deduplicate exact declarations; never choose an arbitrary competing target."""
    ids = tuple(sorted(set(candidates)))
    if len(ids) == 1:
        return Resolution("resolved", ids[0], evidence=tuple(sorted(set(evidence))))
    if ids:
        return Resolution("ambiguous", reason="duplicate_provider", candidates=ids[:50])
    return Resolution("unavailable", reason=reason, evidence=tuple(evidence))


def qml_metadata(node: dict) -> dict:
    value = literal_qml_metadata(node)
    return value if value.get("contract_version") == 1 else {}


def source_path(node: dict, root: Path) -> str | None:
    """Normalize an accepted fact's provenance without reading another source file."""
    raw = str(node.get("source_file") or "").replace("\\", "/")
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute():
        try:
            raw = path.relative_to(root).as_posix()
        except ValueError:
            return None
    raw = posixpath.normpath(raw)
    if raw == ".." or raw.startswith("../") or raw.startswith("/") or ":" in raw:
        return None
    return raw


def relative_reference(source: str, value: str) -> str | None:
    """Resolve only a local literal path; corpus membership is checked separately."""
    value = value.replace("\\", "/")
    if not value or value.startswith("/") or ":" in value:
        return None
    result = posixpath.normpath(posixpath.join(posixpath.dirname(source), value))
    return None if result == ".." or result.startswith("../") else result


def fact_node(source: str, kind: str, key, label: str, line: int, **fields) -> dict:
    """Mint exact-spelling salted IDs before Graphify's casefold normalization."""
    semantic_key = json.dumps(key, ensure_ascii=False, separators=(",", ":"))
    return {
        "id": make_qml_id(source, kind, semantic_key),
        "label": label,
        "file_type": "code",
        "type": "file" if kind == "file" else "namespace",
        "source_file": source,
        "source_location": f"L{line}",
        "_origin": "ast",
        "metadata": {"qml": encode_metadata({"kind": kind, **fields})},
    }


def fact_edge(source: str, target: str, relation: str, owner: dict, context: str,
              *, confidence: str = "EXTRACTED", **metadata) -> dict:
    return {
        "source": source,
        "target": target,
        "_src": source,
        "_tgt": target,
        "relation": relation,
        "confidence": confidence,
        "source_file": owner["source_file"],
        "source_location": owner.get("source_location", "L1"),
        "context": context,
        "metadata": {"qml": encode_metadata(metadata)},
    }
