"""Actual source-class identities distinguish literal C++ case before allocation."""
from __future__ import annotations

from graphify.extract import extract, extract_cpp
from graphify.extractors.cpp_class_proof import class_fact
from graphify.extractors.cpp_functions import decoded
from graphify.extractors.cpp_member_identity import member_fact


def source(*, out_of_line=False, forwards=False, reverse=False, namespace=""):
    """Each real class owns a field and the same-spelled method, never an alias."""
    names = ["box", "Box"] if reverse else ["Box", "box"]
    prefix = "".join(f"struct {name};\n" for name in names) if forwards else ""
    classes = "".join(f"struct {name}{{int field;void run()" + (";" if out_of_line else "{helper();}") + "};\n" for name in names)
    bodies = "".join(f"void {name}::run(){{helper();}}\n" for name in names) if out_of_line else ""
    content = "void helper(){}\n" + prefix + classes + bodies
    return (f"namespace {namespace}{{\n{content}}}\n" if namespace else content).encode()


def classes(result):
    return {decoded(fact["qualified_name_b64"]): node for node in result["nodes"] if (fact := class_fact(node))}


def produced(root, raw, *, mode="direct", filename="unit.cpp"):
    path = root / filename
    path.write_bytes(raw)
    result = extract_cpp(path) if mode == "direct" else extract([path], root=root, cache_root=root, parallel=False)
    assert not result.get("error") and not result.get("failed_sources") and not result.get("qml_failures")
    assert path.read_bytes() == raw
    return result


def member_calls(result):
    callers = {node["id"] for node in result["nodes"] if member_fact(node)}
    return [edge for edge in result["edges"] if edge.get("relation") == "calls" and edge["source"] in callers]
