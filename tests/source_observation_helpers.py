"""Neutral real source and readback helpers for complete logical-arc evidence."""
from __future__ import annotations

from copy import deepcopy
import json

from graphify.extract import extract, extract_csharp


def produce(root, *, local=True, mode="facade"):
    """A generic base and field independently refer to the same literal type."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / "Data.cs"
    body = "void Nested() {} Nested();" if local else ""
    path.write_bytes(("class Token {}\nclass Base<T> {}\nclass Panel : Base<Token> {\n"
                      " Token value;\n void Execute() { " + body + " }\n}\n").encode())
    result = (extract_csharp(path) if mode == "direct" else
              extract([path], root=root, cache_root=root, parallel=False))
    assert not result.get("error") and not result.get("failed_sources")
    return result


def reference(graph):
    """Select the actual repeated source arc, without depending on its storage key."""
    return next(data for _, _, data in graph.edges(data=True)
                if data.get("relation") == "references" and data.get("context") in {"field", "generic_arg"})


def observations(attributes):
    """Read complete records; tests do not reproduce production merging or winner choice."""
    return [attributes, *attributes.get("also_seen", [])]


def state(graph):
    return deepcopy((graph.graph, list(graph.nodes(data=True)), list(graph.edges(data=True))))


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True)
