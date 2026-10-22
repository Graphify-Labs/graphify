"""Qt/QML integration preserves upstream C++ byte facts outside QML fixtures.

The real CLI admits a header, quoted include, constructor and receiver call in
each newline profile. Explicit source tokens validate byte coordinates before
unique declaration anchors compare semantics. No Qt runtime or corpus code runs.
"""
from __future__ import annotations

import base64
from collections import Counter
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


FILES = {
    "include/worker.h": "// Unicode α marker\nclass Worker {\npublic:\n"
                        "    explicit Worker(int initial);\n    void run();\n};\n",
    "src/worker.cpp": '#include "../include/worker.h"\n// Unicode α marker\n'
                      "Worker::Worker(int initial) {}\nvoid Worker::run() {}\n"
                      "void useWorker() {\n    Worker worker(1);\n    worker.run();\n}\n",
}


def _links(data):
    return data.get("links", data.get("edges", []))


def _node(data, source, label, family=None):
    matches = [node for node in data["nodes"]
               if node.get("source_file") == source and node.get("label") == label
               and (family is None or family in node.get("metadata", {}))]
    assert len(matches) == 1, (source, label, family)
    return matches[0]


def _span(source, span, expected):
    """Token identity catches a consistently shifted byte/column pair as well."""
    start, end = span["start_byte"], span["end_byte"]
    assert type(start) is int and type(end) is int and 0 <= start < end <= len(source)
    for prefix, offset in (("start", start), ("end", end)):
        before = source[:offset]
        assert span[prefix + "_row"] == before.count(b"\n")
        assert span[prefix + "_column"] == len(before.rsplit(b"\n", 1)[-1])
    assert source[start:end].replace(b"\r\n", b"\n").strip() == expected


def _validate(data, root):
    """Every profile independently proves native facts and directed ownership."""
    sources = {name: (root / name).read_bytes() for name in FILES}
    assert {node.get("source_file") for node in data["nodes"]} == set(FILES)
    assert all(not ({"qt", "qml"} & node.get("metadata", {}).keys()) for node in data["nodes"])
    header = _node(data, "include/worker.h", "worker.h", "cpp_constructor_types")
    implementation = _node(data, "src/worker.cpp", "worker.cpp", "cpp_constructor_types")
    for node in (header, implementation):
        fact = node["metadata"]["cpp_constructor_types"]
        assert fact["complete"] is True and fact["source_size"] == len(sources[node["source_file"]])
    assert header["metadata"]["cpp_constructor_types"]["includes"] == []
    (include,) = implementation["metadata"]["cpp_constructor_types"]["includes"]
    assert include["kind"] == "quoted"
    assert base64.b64decode(include["literal_b64"]) == b"../include/worker.h"
    assert include["end_byte"] == include["span"]["end_byte"]
    _span(sources["src/worker.cpp"], include["span"], b'#include "../include/worker.h"')

    owner = _node(data, "include/worker.h", "Worker", "cpp_class")
    fact = owner["metadata"]["cpp_class"]
    assert fact["is_definition"] is True and fact["ambiguous"] is False
    assert base64.b64decode(fact["qualified_name_b64"]) == b"Worker"
    _span(sources["include/worker.h"], fact["span"],
          b"class Worker {\npublic:\n    explicit Worker(int initial);\n    void run();\n}")
    members = []
    for source, label, family, role, token in (
        ("include/worker.h", ".run()", "cpp_member", "declaration", b"void run();"),
        ("src/worker.cpp", "Worker::run()", "cpp_member", "definition", b"void Worker::run() {}"),
        ("include/worker.h", ".Worker()", "cpp_constructor", "declaration", b"explicit Worker(int initial);"),
        ("src/worker.cpp", "Worker::Worker()", "cpp_constructor", "definition", b"Worker::Worker(int initial) {}"),
    ):
        node = _node(data, source, label, family)
        metadata = node["metadata"][family]
        assert metadata["role"] == role and metadata["ambiguous"] is False
        assert base64.b64decode(metadata["owner_b64"]) == b"Worker"
        _span(sources[source], metadata["span"], token)
        members.append(node)
    declaration, definition = (node["metadata"]["cpp_constructor"] for node in members[2:])
    assert definition["owner_bound"] is True and definition["type_authorized"] is True
    assert declaration["signature"] == definition["signature"]
    # The cross-file declaration's copied definition span belongs to the proven
    # definition, not the header; validate it against that source-owned fact.
    assert declaration["definition_span"] == definition["span"]
    caller = _node(data, "src/worker.cpp", "useWorker()")
    endpoints = {(edge["source"], edge["target"], edge["relation"], edge.get("context", ""))
                 for edge in _links(data)}
    assert (implementation["id"], header["id"], "imports", "import") in endpoints
    assert (owner["id"], members[0]["id"], "method", "") in endpoints
    assert (owner["id"], members[3]["id"], "method", "cpp_constructor_owner") in endpoints
    assert (caller["id"], members[0]["id"], "calls", "call") in endpoints


def _semantic(data):
    """Remove only already-validated physical coordinates from known C++ facts."""
    anchors = {node["id"]: tuple(node.get(key, "") for key in
               ("source_file", "label", "source_location")) for node in data["nodes"]}
    assert len(anchors) == len(data["nodes"]) and len(set(anchors.values())) == len(anchors)
    nodes = Counter()
    for node in data["nodes"]:
        record = deepcopy(node)
        record["id"] = anchors[node["id"]]
        for family, fact in record.get("metadata", {}).items():
            assert family in {"cpp_class", "cpp_member", "cpp_constructor", "cpp_constructor_types"}
            for field in ("span", "definition_span", "source_size"):
                fact.pop(field, None)
            if family == "cpp_constructor_types":
                for include in fact["includes"]:
                    include.pop("span")
                    include.pop("end_byte")
        nodes[json.dumps(record, sort_keys=True)] += 1
    edges = Counter()
    for edge in _links(data):
        record = deepcopy(edge)
        for field in ("source", "target", "_src", "_tgt"):
            if field in record:
                assert record[field] in anchors
                record[field] = anchors[record[field]]
        edges[json.dumps(record, sort_keys=True)] += 1
    return nodes, edges


def _equivalent(left, right, left_root, right_root):
    _validate(left, left_root)
    _validate(right, right_root)
    # This generic C++ profile has stable declaration IDs. Unlike Qt source-site
    # IDs, they must not be reassigned while an anchor projection hides it.
    def identities(data):
        result = {tuple(node.get(key, "") for key in ("source_file", "label", "source_location")):
                  node["id"] for node in data["nodes"]}
        assert len(result) == len(data["nodes"]) == len(set(result.values()))
        return result

    assert identities(left) == identities(right)
    assert _semantic(left) == _semantic(right)


@pytest.fixture(scope="module")
def cpp_builds(tmp_path_factory):
    """Force both byte profiles independently of Git's host checkout conversion."""
    base = tmp_path_factory.mktemp("non_qt_cpp_newlines")
    results = []
    for name, newline in (("lf", b"\n"), ("crlf", b"\r\n")):
        root = base / name
        for relative, text in FILES.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8").replace(b"\n", newline))
        result = subprocess.run(
            [sys.executable, "-m", "graphify", "update", str(root), "--force", "--no-cluster"],
            cwd=root, env=dict(os.environ, PYTHONIOENCODING="utf-8", GRAPHIFY_NO_TIPS="1",
                               GRAPHIFY_NO_AUTO_REFRESH="1"),
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, (result.stdout + result.stderr)[-4000:]
        results.append((json.loads((root / "graphify-out/graph.json").read_text(encoding="utf-8")), root))
    return results


def test_req_qml003_ac04_non_qt_cpp_cli_newlines_keep_source_ownership_and_topology(cpp_builds):
    """Native byte metadata changes while proven declarations and graph roles agree."""
    (left, left_root), (right, right_root) = cpp_builds
    _equivalent(left, right, left_root, right_root)
    assert {node["id"] for node in left["nodes"]} == {node["id"] for node in right["nodes"]}
    for source, label in (("include/worker.h", "worker.h"), ("src/worker.cpp", "worker.cpp")):
        left_fact = _node(left, source, label)["metadata"]["cpp_constructor_types"]
        right_fact = _node(right, source, label)["metadata"]["cpp_constructor_types"]
        assert left_fact["source_size"] < right_fact["source_size"]


@pytest.mark.parametrize("corruption", ["span", "consistent_span", "source_size", "include",
                                       "definition_span", "endpoint", "role", "member_omission",
                                       "identity_permutation"])
def test_req_qml014_ac04_non_qt_cpp_newline_oracle_rejects_corruption(cpp_builds, corruption):
    """Physical-coordinate allowances cannot hide absent facts or changed ownership."""
    (accepted, root), _ = cpp_builds
    reference, changed = deepcopy(accepted), deepcopy(accepted)
    if corruption in {"span", "consistent_span"}:
        span = _node(changed, "include/worker.h", "Worker")["metadata"]["cpp_class"]["span"]
        span["start_byte"] += 1
        if corruption == "consistent_span":
            span["start_column"] += 1
    elif corruption in {"source_size", "include"}:
        fact = _node(changed, "src/worker.cpp", "worker.cpp")["metadata"]["cpp_constructor_types"]
        if corruption == "source_size":
            fact["source_size"] += 1
        else:
            fact["includes"][0]["literal_b64"] = base64.b64encode(b"other.h").decode()
    elif corruption == "definition_span":
        _node(changed, "include/worker.h", ".Worker()")["metadata"]["cpp_constructor"]["definition_span"]["start_byte"] += 1
    elif corruption == "endpoint":
        edge = next(edge for edge in _links(changed) if edge["relation"] == "imports")
        edge["target"] = _node(changed, "src/worker.cpp", "useWorker()")["id"]
    elif corruption == "role":
        _node(changed, "include/worker.h", ".run()")["metadata"]["cpp_member"]["role"] = "definition"
    elif corruption == "identity_permutation":
        first = _node(changed, "include/worker.h", "worker.h")["id"]
        second = _node(changed, "include/worker.h", "Worker")["id"]
        replacements = {first: second, second: first}

        def swap(value):
            if isinstance(value, dict):
                return {key: swap(child) for key, child in value.items()}
            if isinstance(value, list):
                return [swap(child) for child in value]
            return replacements.get(value, value) if isinstance(value, str) else value

        # Reassign identities consistently through every serialized reference;
        # neither an endpoint-existence check nor an unchanged ID set detects it.
        changed = swap(changed)
    else:
        for data in (reference, changed):
            node = _node(data, "include/worker.h", ".run()")
            data["nodes"].remove(node)
            _links(data)[:] = [edge for edge in _links(data) if node["id"] not in (edge["source"], edge["target"])]
    with pytest.raises(AssertionError):
        _equivalent(reference, changed, root, root)
