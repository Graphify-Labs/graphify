"""Neutral literal alias declarations with separately owned reference sites."""
from __future__ import annotations

from graphify.extract import extract, extract_cpp


def source(form="using", scope="", names=("Alias", "alias")):
    statements = [(f"using {name} = {target};" if form == "using" else f"typedef {target} {name};")
                  for name, target in zip(names, ("First", "Second"))]
    if scope == "separate":
        declarations = f"namespace Left {{{statements[0]}}}\nnamespace Right {{{statements[1]}}}"
        refs = (f"Left::{names[0]}", f"Right::{names[1]}")
    elif scope:
        declarations = f"namespace Outer {{namespace Inner {{\n{statements[0]}\n{statements[1]}\n}}}}"
        refs = (f"Outer::Inner::{names[0]}", f"Outer::Inner::{names[1]}")
    else:
        declarations, refs = "\n".join(statements), names
    return ("struct First {};\nstruct Second {};\n" + declarations + "\n"
            + f"struct UsesUpper {{{refs[0]} value;}};\nstruct UsesLower {{{refs[1]} value;}};\n").encode()


def produce(root, raw, *, mode="direct"):
    path = root / "types.cpp"
    path.write_bytes(raw)
    result = (extract_cpp(path) if mode == "direct" else
              extract([path], root=root, cache_root=root, parallel=False))
    assert not result.get("error") and not result.get("failed_sources") and not result.get("qml_failures")
    assert path.read_bytes() == raw
    return result


def declarations(result, names=("Alias", "alias")):
    return [node for node in result["nodes"] if node.get("label") in names and node.get("source_file")]


def references(result):
    nodes = {node["id"]: node for node in result["nodes"]}
    return {nodes[edge["source"]]["label"]: nodes[edge["target"]]
            for edge in result["edges"] if edge.get("relation") == "references"
            and nodes.get(edge.get("source"), {}).get("label") in {"UsesUpper", "UsesLower"}}
