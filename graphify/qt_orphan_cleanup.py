"""Retire stale generic AST placeholders after a complete accepted Qt refresh.

The caller owns discovery, extraction, reconciliation and publication. This pure
step never expands the corpus or mutates a borrowed graph dictionary. It removes
only unreferenced placeholders omitted by the successful fresh extraction.
"""
from __future__ import annotations


def prune_stale_ast_orphans(result: dict, *, fresh_ids: set[str], complete_refresh: bool) -> dict:
    """Return a filtered view; partial refreshes and authoritative facts survive.

    Empty source provenance alone is insufficient. Explicit AST origin, a generic
    code placeholder shape, absence from fresh output and no surviving ordinary
    or hyperedge reference jointly establish that no accepted fact needs it.
    """
    if not complete_refresh:
        return result
    referenced = set()
    for edge in result.get("edges", []):
        referenced.update((edge.get("source"), edge.get("target")))
    for edge in result.get("hyperedges", []):
        members = edge.get("nodes", edge.get("members", edge.get("node_ids", [])))
        if isinstance(members, list):
            referenced.update(value for value in members if isinstance(value, str))

    def stale(node):
        return (node.get("id") not in fresh_ids and node.get("id") not in referenced
                and node.get("_origin") == "ast" and node.get("file_type") == "code"
                and not node.get("source_file") and not node.get("source_location")
                and not node.get("metadata") and not node.get("type")
                and not any(key.startswith("_callable") for key in node))

    retained = [node for node in result.get("nodes", []) if not stale(node)]
    return {**result, "nodes": retained}
