"""Neutral actual-source fixtures for uniquely owned C++ member occurrences."""
from __future__ import annotations

import base64

from graphify.extract import extract
from graphify.extractors.cpp_class_proof import class_fact
from graphify.extractors.cpp_member_identity import member_fact
from graphify.extractors.qml_facts import qml_metadata


def source(*, marker="Q_INVOKABLE", owner="Panel", namespace="", prefix="", declarations="", definition=None):
    """Keep the prototype and qualified body distinct in one accepted source file."""
    definition = f"void {owner}::run() {{ helper(); }}" if definition is None else definition
    unit = (f"{prefix}class {owner} : public QObject {{\nQ_OBJECT\nQML_NAMED_ELEMENT(Panel)\n"
            f"public:\n{marker} void run();\n{declarations}\n}};\n{definition}\n")
    if namespace:
        unit = f"namespace {namespace} {{\n" + unit + "}\n"
    return "#include <QObject>\nvoid helper() {}\n" + unit


def project(root, *, marker="Q_INVOKABLE", owner="Panel", namespace="", raw=None):
    path = root / "panel.cpp"
    path.write_bytes(raw if raw is not None else source(marker=marker, owner=owner, namespace=namespace).encode())
    (root / "Main.qml").write_bytes(b"import Public.SameUnit 1.0\nPanel { function invoke() { run() } }\n")
    (root / "CMakeLists.txt").write_bytes(b"qt_add_qml_module(app URI Public.SameUnit VERSION 1.0 QML_FILES Main.qml SOURCES panel.cpp)\n")
    (root / "keep.py").write_bytes(b"def helper():return 1\n\ndef retained():return helper()\n")
    return path


def members(result):
    return [(node, fact) for node in result["nodes"] if (fact := member_fact(node))]


def class_node(result):
    values = [node for node in result["nodes"] if (fact := class_fact(node)) and fact["is_definition"]]
    assert len(values) == 1
    return values[0]


def decoded(fact, key):
    return base64.b64decode(fact[key]).decode()


def validate_span(raw, fact):
    span = fact["span"]
    assert 0 <= span["start_byte"] < span["end_byte"] <= len(raw)
    for end in ("start", "end"):
        before = raw[:span[end + "_byte"]]
        assert (span[end + "_row"], span[end + "_column"]) == (before.count(b"\n"), len(before.rsplit(b"\n", 1)[-1]))
    return raw[span["start_byte"]:span["end_byte"]]


def facade(root):
    paths = sorted(path for path in root.iterdir() if path.is_file())
    cold = extract(paths, root=root, cache_root=root, parallel=False)
    warm = extract(paths, root=root, cache_root=root, parallel=False)
    assert cold == warm and not cold.get("qml_failures") and not cold.get("failed_sources")
    return cold


def native_calls(result):
    return [edge for edge in result["edges"] if edge.get("context") == "qml_js_call"]


def call_sites(result):
    return [qml_metadata(node) for node in result["nodes"] if qml_metadata(node).get("kind") == "call"]
