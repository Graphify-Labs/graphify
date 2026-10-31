"""Accepted generic file roles shared by Qt membership and source containment."""
from __future__ import annotations

from pathlib import PurePosixPath

from graphify.extractors.cpp_constructor_type_authority import valid_source_transport


def generic_file_role(node, path, fresh_ast_ids=()):
    """Transport augments source proof without becoming callable/type authority.

    C++ file records now carry bounded constructor include/shadow evidence. Only
    that exact producer contract is accepted alongside the legacy empty record;
    unrelated metadata cannot turn a semantic node into a file. The caller owns
    source-path normalization and uniqueness; this predicate never reads source.
    """
    origin = node.get("_origin")
    if (not path or not (origin == "ast" or origin is None and node.get("id") in fresh_ast_ids)
            or node.get("file_type") != "code" or node.get("source_location") != "L1"
            or node.get("label") != PurePosixPath(path).name
            or node.get("type") not in {None, "file"}
            or node.get("_callable") or node.get("_callable_class")):
        return False
    metadata = node.get("metadata")
    if metadata is None or metadata == {}:
        return True
    if not isinstance(metadata, dict) or set(metadata) != {"cpp_constructor_types"}:
        return False
    record = metadata["cpp_constructor_types"]
    return (isinstance(record, dict)
            and set(record) == {"contract_version", "complete", "source_size", "includes", "shadows"}
            and valid_source_transport(record))
