"""Source-owned nested C++ fixtures shared by ancestry and update regressions."""
from __future__ import annotations

from graphify.extract import extract, extract_cpp
from graphify.extractors.cpp_class_proof import class_fact
from graphify.extractors.cpp_functions import decoded, free_definition_fact
from graphify.extractors.cpp_member_identity import member_fact


def nested_source(*, shadow="", namespace="", call="helper()", depth=1, inherited=False):
    """Keep the real body and lexical parent classes in the same source cohort."""
    base = "struct Base {static void (*helper)();};\n" if inherited else ""
    inner = "struct Inner {void run();};"
    middle = "::Inner"
    for level in range(depth - 1):
        name = f"Middle{level}"
        inner = f"struct {name} {{{inner}}};"
        middle = "::" + name + middle
    unit = (f"void helper(){{}}\n{base}struct Outer" + (" : Base" if inherited else "")
            + " {" + shadow + inner + "};\n"
            + f"void Outer{middle}::run(){{{call};}}\n")
    return (f"namespace {namespace} {{\n{unit}}}\n" if namespace else unit).encode()


def produce(root, raw, *, mode="direct", filename="nested.cpp"):
    path = root / filename
    path.write_bytes(raw)
    if mode == "direct":
        result = extract_cpp(path)
    else:
        result = extract([path], root=root, cache_root=root, parallel=False)
        assert result == extract([path], root=root, cache_root=root, parallel=False)
    assert not result.get("error") and not result.get("failed_sources") and not result.get("qml_failures")
    assert path.read_bytes() == raw
    return result


def source_call_edges(result):
    """Use source role and exact member identity, never a same-named global label."""
    callers = {node["id"] for node in result["nodes"] if (fact := member_fact(node))
               and decoded(fact["member_b64"]) == "run"}
    targets = {node["id"] for node in result["nodes"] if free_definition_fact(node)}
    return [edge for edge in result["edges"] if edge.get("relation") == "calls"
            and edge.get("source") in callers and edge.get("target") in targets]


def class_by_name(result, name):
    values = [node for node in result["nodes"] if class_fact(node) and node["label"] == name]
    assert len(values) == 1
    return values[0]
