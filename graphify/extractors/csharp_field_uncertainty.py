"""Prevent source field alternatives from choosing a concrete receiver type.

Actual declaration nodes/edges retain every type and location. The derived
receiver table uses an empty value as an explicit unavailable binding so an
inherited or later shard cannot supply a convenient replacement type.
"""
from __future__ import annotations


def _name(value):
    return str(value).split("[", 1)[0].split("{", 1)[0].removeprefix("@")


def invalidate_field_receiver_types(nodes, edges, tables):
    """Apply declaration uncertainty after the source walk, before call typing."""
    candidates = {}
    for node in nodes:
        metadata = node.get("metadata", {})
        fact = metadata.get("csharp_member", {})
        if fact.get("contract_version") == 1 and fact.get("kind") == "field":
            candidates[node["id"]] = node
    groups = {}
    for edge in edges:
        node = candidates.get(edge.get("target"))
        if (node is None or edge.get("relation") != "defines" or edge.get("context") != "field"
                or edge.get("confidence") != "EXTRACTED" or edge.get("source_file") != node.get("source_file")):
            continue
        groups.setdefault((edge["source"], _name(node["label"])), []).append(node)
    for (owner, name), declarations in groups.items():
        fields = tables.setdefault(owner, {})
        facts = [node["metadata"]["csharp_member"] for node in declarations]
        unavailable = (len(declarations) > 1 or any(fact.get("conditional") or fact.get("duplicate_declaration")
                       or fact.get("type_status") == "unsupported" for fact in facts)
                       or not any(node["label"] in fields for node in declarations))
        if not unavailable:
            continue
        # A declaration shadows all element/foreach projections of that name,
        # including a previously recorded alternative and inherited projections.
        for key in list(fields):
            if _name(key) == name:
                del fields[key]
        fields[name] = ""
        for node in declarations:
            fields[node["label"]] = ""
