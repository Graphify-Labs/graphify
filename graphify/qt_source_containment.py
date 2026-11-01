"""Connect observed Qt sites to accepted source files without inventing owners."""
from __future__ import annotations

from graphify.extractors.qt_cpp_facts import encode_qt, qt_metadata
from graphify.qml_resolution_types import source_path
from graphify.qt_source_file_role import generic_file_role


def attach_qt_file_sites(results, nodes, edges, *, root, fresh_ast_ids=()):
    """Use existing canonical file IDs; borrowed semantic metadata stays unchanged.

    The generic producer's file role is its AST origin, code type, L1 location,
    exact filename label and absence of callable/semantic roles. Bounded C++ file
    transport is accepted without granting constructor/type authority. Containment
    is independent of an unavailable callable, class or runtime target. Duplicate
    or foreign file evidence cannot authorize a guessed container.
    """
    # Fresh canonical AST nodes precede the facade's final provenance tagging.
    # Borrowed context needs its persisted marker; absence alone is no authority.
    fresh_ast_ids = set(fresh_ast_ids)
    files = {}
    for node in nodes:
        path = source_path(node, root)
        if generic_file_role(node, path, fresh_ast_ids):
            files.setdefault(path, []).append(node["id"])
    existing = {(edge.get("source"), edge.get("target"), edge.get("context")) for edge in edges}
    added = []
    for result in results.values():
        for site in result.get("nodes", []):
            metadata = qt_metadata(site)
            if not metadata or metadata.get("owner_id"):
                continue
            owners = set(files.get(source_path(site, root), []))
            if len(owners) != 1:
                continue
            owner = next(iter(owners))
            key = (owner, site["id"], "qt_source_file")
            if key in existing:
                continue
            # Preserve the occurrence's original bytes and endpoint direction;
            # owner_id remains unavailable rather than being changed to a file.
            edge = {"source": owner, "target": site["id"], "_src": owner, "_tgt": site["id"],
                    "relation": "contains", "context": "qt_source_file", "confidence": "EXTRACTED",
                    "source_file": site["source_file"], "source_location": site["source_location"],
                    "metadata": {"qt": encode_qt({"span": metadata.get("span", {}), "target_id": site["id"]})}}
            result.setdefault("edges", []).append(edge)
            added.append(edge)
            existing.add(key)
    return added
