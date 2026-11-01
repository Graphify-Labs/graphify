"""Neutral source inputs and real entry points for scoped type rejection."""
from __future__ import annotations

from graphify.extract import extract, extract_cpp


def source(kind="alias", *, qualified=False, spelling=None, newline="\n"):
    """A rejected field and a legitimate parameter may share one bare stub."""
    name = "Count" if kind == "alias" else "Thing"
    declaration = "using Count=int;" if kind == "alias" else "class Thing {};"
    written = spelling or ("::Left::" + name if qualified else name)
    text = (f"namespace Left {{{declaration}}}\n"
            f"namespace Right {{class Holder {{{written} *value;}};}}\n"
            f"using namespace Left;void allowed({name} *arg){{}}\n")
    if newline == "\r\n":
        text = "\ufeff// π source bytes\n" + text
    return text.replace("\n", newline).encode()


def produce(root, raw, mode="facade"):
    path = root / "types.cpp"
    path.write_bytes(raw)
    result = (extract_cpp(path) if mode == "direct" else
              extract([path], root=root, cache_root=root, parallel=False))
    assert not result.get("error") and not result.get("failed_sources") and not result.get("qml_failures")
    assert path.read_bytes() == raw
    return result


def uses(result, label="Holder"):
    nodes = {node["id"]: node for node in result["nodes"]}
    return [(edge, nodes[edge["target"]]) for edge in result["edges"]
            if edge.get("relation") in {"references", "inherits"}
            and nodes.get(edge.get("source"), {}).get("label") == label]


def unavailable(result):
    return [edge for edge in result["edges"] if "cpp_type_reference_version" in edge]
