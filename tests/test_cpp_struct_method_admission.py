"""INC-QML-113: actual struct callables choose C++, while C data stays C."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.cpp_header import is_cpp_header
from graphify.export import to_json
from graphify.extract import _get_extractor, extract, extract_c, extract_cpp
from graphify.paths import load_node_link_graph


@pytest.mark.parametrize("prefix,newline", [(b"", b"\n"), (b"\xef\xbb\xbf", b"\r\n")])
@pytest.mark.parametrize("kind,member,label", [
    ("struct", "void run();", ".run()"),
    ("struct", "unsigned long run();", ".run()"),
    ("struct", "const Value *run();", ".run()"),
    ("struct", "int read(int value) const &;", ".read()"),
    ("struct", "void run() {}", ".run()"),
    ("struct", "Panel();", ".Panel()"),
    ("struct", "Panel(int value) {}", ".Panel()"),
    ("struct", "Panel() : value(0) {} int value;", ".Panel()"),
    ("struct", "~Panel();", ".~Panel()"),
    ("struct", "Panel() = default;", ".Panel()"),
    ("struct", "virtual void run() = 0;", ".run()"),
    ("union", "void run();", ".run()"),
])
def test_req_qml022_ac02_struct_callable_selects_cpp_and_retains_actual_facts(
        tmp_path, prefix, newline, kind, member, label):
    """Cue-free .h declarations reach the real C++ producer and durable graph."""
    path = tmp_path / "panel.h"
    raw = prefix + (kind + " Panel { " + member + " };\n").encode().replace(b"\n", newline)
    path.write_bytes(raw)
    assert is_cpp_header(path) and _get_extractor(path) is extract_cpp
    direct = extract_cpp(path)
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result["failed_sources"]
    for facts in (direct, result):
        owner, = [node for node in facts["nodes"] if node["label"] == "Panel"]
        method, = [node for node in facts["nodes"] if node["label"] == label]
        assert method.get("_callable")
        assert any(edge["source"] == owner["id"] and edge["target"] == method["id"]
                   and edge["relation"] == "method" for edge in facts["edges"])
        metadata = method.get("metadata", {})
        proof = metadata.get("cpp_declarator") or metadata.get("cpp_constructor") or metadata.get("cpp_member")
        assert proof
        span = proof["span"]
        fragment = raw[span["start_byte"]:span["end_byte"]]
        assert fragment and fragment.rstrip(b";") in member.encode()
        for endpoint in ("start", "end"):
            before = raw[:span[endpoint + "_byte"]]
            assert span[endpoint + "_row"] == before.count(b"\n")
            assert span[endpoint + "_column"] == len(before) - before.rfind(b"\n") - 1
    assert result == extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    graph = build_from_json(result, root=tmp_path)
    output = tmp_path / "saved.json"
    assert to_json(graph, {}, str(output))
    saved = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    assert set(saved) == set(graph)
    assert path.read_bytes() == raw


@pytest.mark.parametrize("source", [
    "struct Panel { void (*run)(int); };",
    "struct Panel { int (value); };",
    "struct Panel { unsigned width:(1); };",
    "struct Panel { unsigned width:(1+2); };",
    "struct Panel { int value __attribute__((aligned(8))); };",
    "struct Panel { int value __attribute__((packed, aligned(8))); };",
    "struct Panel { int value __declspec(align(8)); };",
    "#define ATTR(x) __attribute__((aligned(x)))\nstruct Panel { int value ATTR(8); };",
    "#define ATTR(x) __declspec(align(x))\nstruct Panel { int value ATTR(8); };",
    "struct Panel { int value ATTR(8); };",
    "#define TYPE int\nstruct Panel { TYPE value ATTR(8); };",
    "struct Panel { int values[1 == 1]; };",
    "struct Panel { int value; }; struct Panel item = {.value = 1};",
    "void run();",
    "void run() { int Panel(int); }",
    'const char *text = "struct Panel { void run(); };";',
    'const char *text = R"tag(struct Panel { Panel(); };)tag";',
    "/* struct Panel { void run(); }; */ int value;",
    "// struct Panel { Panel(); };\nint value;",
    "#define MAKE struct Panel { void run(); };\nint value;",
    "#define MAKE \\\nstruct Panel { Panel(); };\nint value;",
    "\ufeff#define MAKE struct Panel { void run(); };\nint value;",
])
def test_req_qml022_ac06_struct_callable_hint_cannot_relabel_c_data_or_inert_text(tmp_path, source):
    """Callbacks, bitfields and hidden/executable lookalikes supply no new hint."""
    path = tmp_path / "panel.h"
    path.write_bytes(source.encode())
    assert not is_cpp_header(path)
    assert _get_extractor(path) is extract_c


# Explicit bounded IDs keep pytest's current-test environment value portable;
# the oversized source remains unchanged and is still exercised in full.
@pytest.mark.parametrize("raw", [b"struct Panel { void run(", b"}",
                                  b"struct Panel { void (*run)(int); }; }",
                                  b" " * (256 * 1024) + b"struct Panel { void run(); };"],
                         ids=["partial-parameters", "orphan-close", "extra-close", "beyond-read-bound"])
def test_req_qml022_ac06_partial_or_outside_read_bound_source_cannot_supply_member_hint(tmp_path, raw):
    """Incomplete scopes and declarations outside the existing read limit gain no hint."""
    path = tmp_path / "panel.h"
    path.write_bytes(raw)
    assert not is_cpp_header(path) and path.read_bytes() == raw
