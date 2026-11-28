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


def _python_param_shadow_checker(source: bytes):
    """Return ``is_shadowed(call, name)``: does *name* at *call* read a parameter
    of an enclosing function?

    Walks outward the way Python resolves a free name. A function's parameters
    are visible only from its body: a default, annotation or decorator is
    evaluated in the scope around it. A nested ``def``/``class``, an import or
    ``global`` in a nearer scope rebinds the name, so the walk stops there and
    the ordinary lookup decides. A class body is visible only to code directly
    in it, never to its methods.
    """
    scopes: dict[int, tuple[set[str], set[str]]] = {}

    def rebound_names(body) -> set[str]:
        names: set[str] = set()
        pending = list(body.named_children)
        while pending:
            node = pending.pop()
            kind = node.type
            if kind in ("function_definition", "class_definition"):
                name = node.child_by_field_name("name")
                if name is not None:
                    names.add(_read_text(name, source))
            elif kind == "global_statement":
                names.update(_read_text(c, source) for c in node.named_children)
            elif kind in ("import_statement", "import_from_statement"):
                for item in node.children_by_field_name("name"):
                    alias = item.child_by_field_name("alias")
                    text = _read_text(item if alias is None else alias, source)
                    names.add(text.split(".")[0] if kind == "import_statement" else text)
            elif kind != "lambda":
                pending.extend(node.named_children)
        return names

    def facts(scope, body) -> tuple[set[str], set[str]]:
        if scope.id not in scopes:
            params = scope.child_by_field_name("parameters")
            scopes[scope.id] = (
                _python_param_names(params, source), rebound_names(body),
            )
        return scopes[scope.id]

    def is_shadowed(call, name: str) -> bool:
        node = call
        nearest = True
        while (parent := node.parent) is not None:
            if parent.type in ("function_definition", "class_definition"):
                body = parent.child_by_field_name("body")
                if node == body:
                    is_function = parent.type == "function_definition"
                    if is_function or nearest:
                        params, rebound = facts(parent, body)
                        if name in rebound:
                            return False
                        if is_function and name in params:
                            return True
                    nearest = False
            node = parent
        return False

    return is_shadowed
