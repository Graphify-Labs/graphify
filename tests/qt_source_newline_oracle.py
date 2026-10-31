"""INC-QML-103: original-byte proof precedes exact source-graph comparison.

The four existing fixtures deliberately retain C#/C++ source coordinates. Only
validated physical span coordinates are expressed in LF coordinates for this
test oracle; IDs, semantic facts, uncertainty and edge multiplicity stay exact.
No production input or graph is normalized by these helpers.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json


FIXTURE_NAMES = (
    "sample.cs", "sample.cu", "sample.metal",
    "xaml_viewmodel/ViewModels/ToolkitViewModel.cs",
)
SPAN_KEYS = frozenset({"start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column"})


def links(data):
    return data.get("links", data.get("edges", []))


def node(data, source, label, family=None):
    matches = [item for item in data["nodes"] if item.get("source_file") == source
               and item.get("label") == label
               and (family is None or family in item.get("metadata", {}))]
    assert len(matches) == 1, (source, label, family)
    return matches[0]


def _source(root, value):
    path = (root / value).resolve()
    assert path.is_relative_to(root.resolve()) and path.is_file()
    return path.read_bytes()


def _point(raw, offset):
    before = raw[:offset]
    return before.count(b"\n"), len(before.rsplit(b"\n", 1)[-1])


def validated_projection(data, root):
    """Validate every original 6D witness, then transform only its coordinates.

    Recursing through actual producer records also checks the CUDA raw call and
    caller spans at the direct-extractor boundary. Unknown coordinate shapes or
    non-integer values cannot be silently treated as semantic equivalence.
    """
    result = deepcopy(data)
    count = 0

    def visit(value, raw):
        nonlocal count
        if isinstance(value, list):
            for child in value:
                visit(child, raw)
        elif isinstance(value, dict):
            if SPAN_KEYS <= value.keys():
                assert all(type(value[key]) is int for key in SPAN_KEYS)
                start, end = value["start_byte"], value["end_byte"]
                assert 0 <= start < end <= len(raw)
                for prefix, offset in (("start", start), ("end", end)):
                    assert _point(raw, offset) == (value[prefix + "_row"], value[prefix + "_column"])
                fragment = raw[start:end]
                normalized = raw.replace(b"\r\n", b"\n")
                a, b = len(raw[:start].replace(b"\r\n", b"\n")), len(raw[:end].replace(b"\r\n", b"\n"))
                assert fragment.replace(b"\r\n", b"\n") == normalized[a:b]
                value["start_byte"], value["end_byte"] = a, b
                for prefix, offset in (("start", a), ("end", b)):
                    value[prefix + "_row"], value[prefix + "_column"] = _point(normalized, offset)
                count += 1
            for child in value.values():
                visit(child, raw)

    for item in result["nodes"] + links(result) + result.get("raw_calls", []):
        if item.get("source_file"):
            visit(item, _source(root, item["source_file"]))
    return result, count


def _fragment(data, root, source, label, family):
    fact = node(data, source, label, family)["metadata"][family]
    raw = _source(root, source)
    span = fact["span"]
    return fact, raw[span["start_byte"]:span["end_byte"]].replace(b"\r\n", b"\n")


def require_cli_facts(data, root):
    """Independent tokens and mandatory ownership prevent symmetric omissions."""
    assert {item["source_file"] for item in data["nodes"] if item.get("source_file")} == set(FIXTURE_NAMES)
    required = []
    for source, label, token in (
        ("sample.cs", "_client", b"_client"),
        (FIXTURE_NAMES[3], "userName", b'userName = ""'),
        (FIXTURE_NAMES[3], "email", b'email = ""'),
        (FIXTURE_NAMES[3], "ignoredName", b'ignoredName = ""'),
    ):
        fact, fragment = _fragment(data, root, source, label, "csharp_member")
        assert fragment == token and fact["kind"] == "field" and fact["type_status"] == "source_only"
        required.append(node(data, source, label))
    for source in ("sample.cu", "sample.metal"):
        for label in ("x", "y", "z"):
            fact, fragment = _fragment(data, root, source, label, "cpp_declarator")
            assert fragment == label.encode() and fact["kind"] == "field"
            required.append(node(data, source, label))
    for source, label, token in (
        ("sample.cu", "host_norm()", b"float host_norm(const Vec3& v) {\n    return dot(v, v);\n}"),
        ("sample.metal", "dot3()", b"float dot3(Vec3 a, Vec3 b) {\n    return a.x * b.x + a.y * b.y + a.z * b.z;\n}"),
    ):
        fact, fragment = _fragment(data, root, source, label, "cpp_function")
        assert fragment == token and fact["role"] == "definition" and fact["ambiguous"] is False
    for item in required:
        assert not item.get("_callable")
        owners = [edge for edge in links(data) if edge["target"] == item["id"]
                  and edge["relation"] == "defines" and edge.get("context") == "field"]
        assert len(owners) == 1 and owners[0]["confidence"] == "EXTRACTED"
    identities = {item["id"] for item in data["nodes"]}
    assert len(identities) == len(data["nodes"])
    assert all(edge[endpoint] in identities for edge in links(data) for endpoint in ("source", "target"))
    for caller, callee in (("host_norm()", "dot()"), ("main()", "host_norm()")):
        a, b = node(data, "sample.cu", caller), node(data, "sample.cu", callee)
        assert any(edge["source"] == a["id"] and edge["target"] == b["id"]
                   and edge["relation"] == "calls" and edge.get("context") == "call" for edge in links(data))


def equivalent(left, right, left_root, right_root):
    """All semantic attributes, stable IDs and counted directed edges stay exact."""
    require_cli_facts(left, left_root)
    require_cli_facts(right, right_root)
    a, a_count = validated_projection(left, left_root)
    b, b_count = validated_projection(right, right_root)
    assert a_count == b_count == 12
    for key in set(a) | set(b):
        if key not in {"nodes", "links", "edges", "built_at_commit"}:
            assert a.get(key) == b.get(key), key

    def records(items):
        return Counter(json.dumps({key: value for key, value in item.items()
                                   if key not in {"community", "community_name"}}, sort_keys=True) for item in items)

    assert records(a["nodes"]) == records(b["nodes"])
    assert records(links(a)) == records(links(b))
