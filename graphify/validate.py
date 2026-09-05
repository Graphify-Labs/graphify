# validate extraction JSON against the graphify schema before graph assembly
from __future__ import annotations

VALID_FILE_TYPES = {"code", "document", "paper", "image", "rationale", "concept"}
VALID_CONFIDENCES = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}
REQUIRED_NODE_FIELDS = {"id", "label", "file_type", "source_file"}
REQUIRED_EDGE_FIELDS = {"source", "target", "relation", "confidence", "source_file"}
# build.py's hyperedge handling (member normalization, G.graph["hyperedges"])
# only ever reads id/label/nodes - relation/confidence/source_file are part of
# the LLM extraction contract (extraction-spec.md) but not load-bearing at
# build time, so they stay optional-but-validated-if-present below rather than
# required, matching what a hand-constructed or non-LLM-produced hyperedge
# (e.g. build_from_json's own alias-normalization tests) actually needs.
REQUIRED_HYPEREDGE_FIELDS = {"id", "label", "nodes"}
# extraction-spec.md: "if 3 or more nodes clearly participate together" - a
# hyperedge under 3 members is a plain edge that should have been modeled as
# one, not a schema-valid hyperedge.
MIN_HYPEREDGE_NODES = 3


def validate_extraction(data: dict) -> list[str]:
    """
    Validate an extraction JSON dict against the graphify schema.
    Returns a list of error strings - empty list means valid.
    """
    if not isinstance(data, dict):
        return ["Extraction must be a JSON object"]

    errors: list[str] = []

    # Collected during the node pass so the edge pass can reuse it. Only
    # hashable ids land here; a non-hashable id (e.g. a list emitted by a
    # malformed LLM extraction) is reported as an error rather than crashing
    # the validator on set construction.
    node_ids: set = set()

    # Nodes
    if "nodes" not in data:
        errors.append("Missing required key 'nodes'")
    elif not isinstance(data["nodes"], list):
        errors.append("'nodes' must be a list")
    else:
        for i, node in enumerate(data["nodes"]):
            if not isinstance(node, dict):
                errors.append(f"Node {i} must be an object")
                continue
            for field in REQUIRED_NODE_FIELDS:
                if field not in node:
                    errors.append(f"Node {i} (id={node.get('id', '?')!r}) missing required field '{field}'")
            if "id" in node:
                try:
                    hash(node["id"])
                except TypeError:
                    errors.append(
                        f"Node {i} has non-hashable id {node['id']!r} - id must be a string"
                    )
                else:
                    node_ids.add(node["id"])
            if "file_type" in node and node["file_type"] not in VALID_FILE_TYPES:
                errors.append(
                    f"Node {i} (id={node.get('id', '?')!r}) has invalid file_type "
                    f"'{node['file_type']}' - must be one of {sorted(VALID_FILE_TYPES)}"
                )

    # Edges - accept "links" (NetworkX <= 3.1) as fallback for "edges"
    edge_list = data.get("edges") if "edges" in data else data.get("links")
    if edge_list is None:
        errors.append("Missing required key 'edges'")
    elif not isinstance(edge_list, list):
        errors.append("'edges' must be a list")
    else:
        for i, edge in enumerate(edge_list):
            if not isinstance(edge, dict):
                errors.append(f"Edge {i} must be an object")
                continue
            for field in REQUIRED_EDGE_FIELDS:
                if field not in edge:
                    errors.append(f"Edge {i} missing required field '{field}'")
            if "confidence" in edge and edge["confidence"] not in VALID_CONFIDENCES:
                errors.append(
                    f"Edge {i} has invalid confidence '{edge['confidence']}' "
                    f"- must be one of {sorted(VALID_CONFIDENCES)}"
                )
            for endpoint in ("source", "target"):
                if endpoint not in edge:
                    continue
                val = edge[endpoint]
                try:
                    unmatched = bool(node_ids) and val not in node_ids
                except TypeError:
                    errors.append(
                        f"Edge {i} {endpoint} {val!r} is non-hashable - must be a string"
                    )
                    continue
                if unmatched:
                    errors.append(f"Edge {i} {endpoint} '{val}' does not match any node id")

    # Hyperedges - optional (older extractions predate them), but a "hyperedges"
    # key that IS present must be schema-valid; nothing checked this before.
    if "hyperedges" in data:
        hyperedge_list = data["hyperedges"]
        if not isinstance(hyperedge_list, list):
            errors.append("'hyperedges' must be a list")
        else:
            for i, hyperedge in enumerate(hyperedge_list):
                if not isinstance(hyperedge, dict):
                    errors.append(f"Hyperedge {i} must be an object")
                    continue
                for field in REQUIRED_HYPEREDGE_FIELDS:
                    if field not in hyperedge:
                        errors.append(
                            f"Hyperedge {i} (id={hyperedge.get('id', '?')!r}) "
                            f"missing required field '{field}'"
                        )
                if "confidence" in hyperedge and hyperedge["confidence"] not in VALID_CONFIDENCES:
                    errors.append(
                        f"Hyperedge {i} has invalid confidence '{hyperedge['confidence']}' "
                        f"- must be one of {sorted(VALID_CONFIDENCES)}"
                    )
                member_ids = hyperedge.get("nodes")
                if member_ids is None:
                    continue
                if not isinstance(member_ids, list):
                    errors.append(f"Hyperedge {i} 'nodes' must be a list")
                    continue
                if len(member_ids) < MIN_HYPEREDGE_NODES:
                    errors.append(
                        f"Hyperedge {i} (id={hyperedge.get('id', '?')!r}) has "
                        f"{len(member_ids)} member node(s) - hyperedges require at least "
                        f"{MIN_HYPEREDGE_NODES} (a 2-node group is a plain edge)"
                    )
                for member in member_ids:
                    try:
                        unmatched = bool(node_ids) and member not in node_ids
                    except TypeError:
                        errors.append(
                            f"Hyperedge {i} member {member!r} is non-hashable - must be a string"
                        )
                        continue
                    if unmatched:
                        errors.append(
                            f"Hyperedge {i} member '{member}' does not match any node id"
                        )

    return errors


def assert_valid(data: dict) -> None:
    """Raise ValueError with all errors if extraction is invalid."""
    errors = validate_extraction(data)
    if errors:
        msg = f"Extraction JSON has {len(errors)} error(s):\n" + "\n".join(f"  • {e}" for e in errors)
        raise ValueError(msg)
