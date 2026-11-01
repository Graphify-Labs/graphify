"""D34: real CLI native topology with independently checked original-byte spans.

Native source-site identities may change when newline bytes change. Unique
source/role anchors compare topology without a general ID or scope-hash remapper;
the aggregate invariance suite still compares every attribute and ID exactly for
unchanged native inputs. No analyzed Qt project is configured or executed.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import base64
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata

FIXTURE = Path(__file__).parent / "fixtures/qml/project_metadata"
SEMANTIC_FIELDS = (
    "kind", "raw_name", "raw_type", "reference", "literal_value", "roles", "access", "signature",
    "status", "reason", "class_name", "mechanism", "read", "notify", "accessor_role", "bridge_direction",
)


def _metadata(node):
    if "qt" in node.get("metadata", {}):
        return "qt", qt_metadata(node)
    if "qml" in node.get("metadata", {}):
        return "qml", qml_metadata(node)
    return "", {}


def _anchor(node):
    family, metadata = _metadata(node)
    return tuple(node.get(key, "") for key in ("source_file", "label", "type", "source_location")) + (
        family, metadata.get("kind", ""),
    )


def _links(data):
    return data.get("links", data.get("edges", []))


def _validate_coordinates(data, root):
    """Validate coordinates against original bytes before comparing any semantics."""
    spans = 0

    def visit(value, source):
        nonlocal spans
        if isinstance(value, list):
            for child in value:
                visit(child, source)
        elif isinstance(value, dict):
            if {"start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column"} <= value.keys():
                start, end = value["start_byte"], value["end_byte"]
                assert type(start) is int and type(end) is int and 0 <= start <= end <= len(source)
                for prefix, offset in (("start", start), ("end", end)):
                    before = source[:offset]
                    assert value[prefix + "_row"] == before.count(b"\n")
                    assert value[prefix + "_column"] == len(before.rsplit(b"\n", 1)[-1])
                spans += 1
            if "source_size" in value:
                assert value["source_size"] == len(source)
            if "api_type_position" in value:
                assert 0 <= value["api_type_position"] <= len(source)
            for child in value.values():
                visit(child, source)

    for item in data["nodes"] + _links(data):
        metadata = item.get("metadata", {})
        if metadata and item.get("source_file"):
            path = (root / item["source_file"]).resolve()
            assert path.is_relative_to(root.resolve()) and path.is_file()
            visit(metadata, path.read_bytes())
    assert spans > 20, "Native coordinate checks must exercise a real mixed-language graph"


def _semantic_graph(data):
    """Compare exact declared roles and directed serialized endpoints, not guessed IDs."""
    identities = {node["id"]: _anchor(node) for node in data["nodes"]}
    assert len(identities) == len(data["nodes"])
    assert len(set(identities.values())) == len(identities), "Fixture anchors must be independently unique"
    nodes = Counter()
    for node in data["nodes"]:
        _, metadata = _metadata(node)
        record = {key: metadata[key] for key in SEMANTIC_FIELDS if key in metadata}
        record.update({key: node[key] for key in ("file_type", "_origin", "external") if key in node})
        nodes[json.dumps([identities[node["id"]], record], sort_keys=True)] += 1
    edges = Counter()
    for edge in _links(data):
        record = {key: edge[key] for key in ("relation", "confidence", "context", "source_file", "source_location")
                  if key in edge}
        family, metadata = _metadata(edge)
        record["metadata_family"] = family
        record["semantic_metadata"] = {key: metadata[key] for key in SEMANTIC_FIELDS if key in metadata}
        # Concrete endpoint/property references must survive newline changes as
        # the same uniquely anchored declarations, without remapping opaque scopes.
        for key in ("target_id", "property_id", "owner_id", "class_id", "binding_id"):
            if key in metadata:
                record["semantic_metadata"][key] = identities.get(metadata[key], metadata[key])
        for key in ("source", "target", "_src", "_tgt"):
            if key in edge:
                assert edge[key] in identities, "Every endpoint must address an actual declared node"
                record[key] = identities[edge[key]]
        edges[json.dumps(record, sort_keys=True)] += 1
    return nodes, edges


def _required_facts(data, root):
    """Each byte profile independently proves mandatory facts and token ownership."""
    def required(family, kind, name):
        matches = [node for node in data["nodes"] if _metadata(node)[0] == family
                   and _metadata(node)[1].get("kind") == kind
                   and _metadata(node)[1].get("raw_name") == name]
        assert len(matches) == 1, (family, kind, name)
        node = matches[0]
        metadata = _metadata(node)[1]
        source = (root / node["source_file"]).read_bytes()
        span = metadata["span"]
        return node, metadata, source[span["start_byte"]:span["end_byte"]].replace(b"\r\n", b"\n").strip()

    _, backend, fragment = required("qt", "class", "Backend")
    assert backend["is_qobject"] and fragment.startswith(b"class Backend") and fragment.endswith(b"}")
    _, prop, fragment = required("qt", "property", "status")
    assert prop["status"] == "resolved" and prop["read"] == "status" and prop["notify"] == "statusChanged"
    assert fragment == b"Q_PROPERTY(int status READ status NOTIFY statusChanged)"
    signal, metadata, fragment = required("qt", "member", "statusChanged")
    assert metadata["status"] == "resolved" and metadata["roles"] == ["signal"]
    assert fragment == b"void statusChanged();"
    _, _, fragment = required("qml", "binding", "status")
    assert fragment == b"service.status"
    _, read, fragment = required("qml", "read", "service.status")
    assert fragment == b"service.status" and read["reference"] == "service.status"
    # Both literal build descriptors intentionally provide Public.Tools. Preserve
    # the analyzer's uncertainty rather than allowing a convenient global join.
    assert read["status"] == "ambiguous" and read["reason"] == "duplicate_provider"
    identities = {node["id"]: node for node in data["nodes"]}
    assert any(edge.get("relation") == "references" and edge.get("context") == "qt_property_accessor"
               and _metadata(identities[edge["source"]])[1].get("accessor_role") == "read"
               and identities[edge["target"]]["label"] == ".status()" for edge in _links(data))
    assert any(edge.get("relation") == "uses" and edge.get("context") == "qt_signal_emit"
               and _metadata(identities[edge["source"]])[1].get("kind") == "emission"
               and edge["target"] == signal["id"] for edge in _links(data))


def _assert_equivalent(left, right, left_root, right_root):
    _validate_coordinates(left, left_root)
    _validate_coordinates(right, right_root)
    _required_facts(left, left_root)
    _required_facts(right, right_root)
    assert _semantic_graph(left) == _semantic_graph(right)


@pytest.fixture(scope="module")
def native_builds(tmp_path_factory):
    """The real five-file Qt metadata fixture is built once for each byte profile."""
    base = tmp_path_factory.mktemp("native_newlines")
    results = []
    for name, newline in (("lf", b"\n"), ("crlf", b"\r\n")):
        root = base / name / "proj"
        root.mkdir(parents=True)
        files = [path for path in FIXTURE.iterdir() if path.is_file()]
        assert len(files) == 5
        for path in files:
            source = path.read_bytes().replace(b"\r\n", b"\n")
            (root / path.name).write_bytes(source.replace(b"\n", newline))
        completed = subprocess.run(
            [sys.executable, "-m", "graphify", "update", str(root), "--force", "--no-cluster"],
            cwd=root, env=dict(os.environ, PYTHONIOENCODING="utf-8", GRAPHIFY_NO_TIPS="1"),
            capture_output=True, text=True, timeout=120,
        )
        assert completed.returncode == 0, (completed.stdout + completed.stderr)[-4000:]
        results.append((json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8")), root))
    return results


def test_req_qml003_ac04_native_newlines_keep_cli_roles_and_topology(native_builds):
    """Changed bytes change native site IDs, while declarations and directed roles agree."""
    (left, left_root), (right, right_root) = native_builds
    _assert_equivalent(left, right, left_root, right_root)
    left_nodes = {_anchor(node): node for node in left["nodes"]}
    right_nodes = {_anchor(node): node for node in right["nodes"]}
    changed = [key for key in left_nodes if left_nodes[key]["id"] != right_nodes[key]["id"]]
    assert changed and {key[-2] for key in changed} >= {"qml", "qt"}


@pytest.mark.parametrize("corruption", ["span", "consistent_span", "endpoint", "role", "relation",
                                       "edge_role", "binding_omission"])
def test_req_qml014_ac04_native_newline_oracle_rejects_corruption(native_builds, corruption):
    """No comparison allowance may hide bad source coordinates, links or member roles."""
    (accepted, root), _ = native_builds
    reference, changed = deepcopy(accepted), deepcopy(accepted)
    if corruption in {"span", "consistent_span"}:
        node = next(node for node in changed["nodes"] if _metadata(node)[0] == "qt"
                    and _metadata(node)[1].get("kind") == "class")
        node["metadata"]["qt"]["span"]["start_byte"] += 1
        if corruption == "consistent_span":
            node["metadata"]["qt"]["span"]["start_column"] += 1
    elif corruption == "endpoint":
        _links(changed)[0]["target"] = "not_a_declared_endpoint"
    elif corruption == "relation":
        _links(changed)[0]["relation"] = "a_different_relationship"
    elif corruption == "edge_role":
        edge = next(edge for edge in _links(changed) if edge.get("context") == "qt_property_accessor")
        edge["metadata"]["qt"]["accessor_role"] = "invented_role"
        edge["metadata"]["qt"]["raw_values"]["accessor_role"] = base64.b64encode(b"invented_role").decode()
    elif corruption == "binding_omission":
        for data in (reference, changed):
            node = next(node for node in data["nodes"] if _metadata(node)[0] == "qml"
                        and _metadata(node)[1].get("kind") == "binding"
                        and _metadata(node)[1].get("raw_name") == "status")
            data["nodes"].remove(node)
            _links(data)[:] = [edge for edge in _links(data) if node["id"] not in (edge["source"], edge["target"])]
    else:
        node = next(node for node in changed["nodes"]
                    if "roles" in node.get("metadata", {}).get("qt", {}))
        node["metadata"]["qt"]["roles"].append("invented_role")
    with pytest.raises(AssertionError):
        _assert_equivalent(reference, changed, root, root)
