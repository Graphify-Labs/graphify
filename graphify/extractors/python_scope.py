"""Python parameter scoping shared by the AST extractor and the import resolver."""
from __future__ import annotations

from graphify.extractors.base import _read_text


def _python_param_names(params_node, source: bytes) -> set[str]:
    """Plain parameter identifiers declared on a Python `parameters` node.

    Covers positional/keyword params plus `*args` / `**kwargs` and typed or
    default forms — anything that binds a local name the function body can shadow
    a module-level definition with.
    """
    out: set[str] = set()
    if params_node is None:
        return out
    for child in params_node.children:
        if child.type == "identifier":
            out.add(_read_text(child, source))
        elif child.type in (
            "typed_parameter",
            "default_parameter",
            "typed_default_parameter",
            "list_splat_pattern",
            "dictionary_splat_pattern",
        ):
            # The bound name is the first identifier child (the rest is type/default).
            name_n = child.child_by_field_name("name")
            if name_n is None:
                name_n = next(
                    (c for c in child.children if c.type == "identifier"), None
                )
            if name_n is not None:
                out.add(_read_text(name_n, source))
    return out
