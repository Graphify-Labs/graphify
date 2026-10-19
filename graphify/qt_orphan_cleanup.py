"""Retire stale generic AST placeholders after a complete accepted Qt refresh.

The caller owns discovery, extraction, reconciliation and publication. This pure
step never expands the corpus or mutates a borrowed graph dictionary. It removes
only unreferenced placeholders omitted by the successful fresh extraction.
"""
from __future__ import annotations

from graphify.build import _is_external_stub
from graphify.graph_direction import logical_endpoints


def fresh_import_targets(fresh: dict, prior_nodes: list) -> set[str]:
    """Read only actual fresh producer owners/edges, with old placeholder roles.

    Generic extractors may leave an imported external endpoint undeclared until
    build. Its prior canonical role can supply that endpoint, but no old owner
    or legacy-inferred edge is allowed into fresh source-ownership proof.
    """
    from graphify.build import _EXTERNAL_STUB_RELATIONS
    nodes = list(fresh.get("nodes", []))
    present = {node.get("id") for node in nodes if isinstance(node, dict)
               and isinstance(node.get("id"), str)}
    nodes.extend(node for node in prior_nodes if isinstance(node, dict)
                 and _is_external_stub(node) and node["id"] not in present)
    return previous_import_targets({"nodes": nodes, "links": fresh.get("edges", fresh.get("links", [])),
                                    "directed": bool(fresh.get("directed", False))},
                                   import_relations=_EXTERNAL_STUB_RELATIONS)


def previous_import_targets(prior: dict | None, *, import_relations: frozenset[str]) -> set[str]:
    """Derive exact external candidates from accepted prior source-owned AST imports.

    The caller supplies the builder's canonical import family. Duplicate IDs,
    missing owners and corrupted logical pairs cannot authorize cleanup; labels
    and sourceless semantic edges are never source ownership evidence.
    """
    if not isinstance(prior, dict):
        return set()
    nodes, edges = prior.get("nodes", []), prior.get("links", prior.get("edges", []))
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return set()
    owners, duplicates = {}, set()
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            continue
        identity = node["id"]
        if identity in owners:
            duplicates.add(identity)
        else:
            owners[identity] = node
    targets = set()
    for edge in edges:
        if (not isinstance(edge, dict) or edge.get("_origin") != "ast"
                or not isinstance(edge.get("relation"), str) or edge["relation"] not in import_relations
                or edge.get("context") != "import"
                or edge.get("confidence") != "EXTRACTED"):
            continue
        pair = logical_endpoints(edge.get("source"), edge.get("target"), edge,
                                 directed=bool(prior.get("directed", False)))
        if pair is None or not all(isinstance(value, str) for value in pair):
            continue
        source, target = pair
        if source in duplicates or target in duplicates or target not in owners:
            continue
        owner, source_file = owners.get(source, {}), edge.get("source_file")
        if (isinstance(source_file, str) and source_file and owner.get("source_file") == source_file
                and owner.get("_origin") == "ast" and owner.get("file_type") == "code"):
            targets.add(target)
    return targets


def prune_stale_ast_orphans(result: dict, *, fresh_ids: set[str], complete_refresh: bool,
                            prior_import_ids: set[str] | None = None) -> dict:
    """Return a filtered view; partial refreshes and authoritative facts survive.

    Empty source provenance alone is insufficient. A generic AST placeholder or
    source-owned prior import endpoint must also be absent from fresh output and
    every surviving ordinary/hyperedge reference. Borrowed inputs stay unchanged.
    """
    if not complete_refresh:
        return result
    external_ids = prior_import_ids or set()
    referenced = set()
    for edge in result.get("edges", []):
        referenced.update((edge.get("source"), edge.get("target")))
    for edge in result.get("hyperedges", []):
        members = edge.get("nodes", edge.get("members", edge.get("node_ids", [])))
        if isinstance(members, list):
            referenced.update(value for value in members if isinstance(value, str))

    def stale(node):
        generic_ast = (node.get("_origin") == "ast" and node.get("file_type") == "code"
                       and not node.get("type") and not node.get("external"))
        # Reuse D30's exact minted/legacy convention, including its bounded
        # presentation fields, rather than interpreting external roles again.
        # Prior source-owned AST import identity remains additional authority.
        generic_external = (node.get("id") in external_ids
                            and _is_external_stub(node))
        return (node.get("id") not in fresh_ids and node.get("id") not in referenced
                and (generic_ast or generic_external) and not node.get("source_file")
                and not node.get("source_location") and not node.get("metadata")
                and not any(key.startswith("_callable") for key in node))

    retained = [node for node in result.get("nodes", []) if not stale(node)]
    return {**result, "nodes": retained}
