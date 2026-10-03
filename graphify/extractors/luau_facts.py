"""Luau AST facts for the Rojo require resolver (#2520).

:func:`luau_module_facts` runs inside the per-file Luau extractor and records,
as JSON-safe lists that ride on the per-file result (and so on the AST cache),
every ``require`` argument, every ``local`` binding with the byte range where
it is visible, and the fields of a top-level ``return { ... }`` table. Each
expression is reduced to an instance-path *chain*: ``game:GetService("X")``,
``script``, ``.Parent``, ``.X``, ``["X"]``, ``:WaitForChild("X")``,
``:FindFirstChild("X")``, ``:FindFirstAncestor("X")``. Casts, parentheses and
comments are dropped; the values of ``if``/``and``/``or`` are kept as
alternatives, the rightmost first. :mod:`graphify.rojo_resolution` evaluates
the chains against a project file.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

LUAU_FACTS_KEY = "luau_module"

# The module name the Lua require handler (`_import_lua`) reads after
# `require(`: an optional quote, then up to a quote, `)` or whitespace.
_LUA_TOKEN_RE = re.compile(r"""\s*['"]?([^'")\s]+)""")

_CHILD_METHODS = frozenset({"WaitForChild", "FindFirstChild"})
_PROPERTY_FIELDS = frozenset({"Name", "ClassName"})
_FUNCTION_TYPES = frozenset({"function_declaration", "function_definition"})
_WRAPPER_TYPES = frozenset({"parenthesized_expression", "cast_expression"})


def _text(node: Any, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _named(node: Any) -> list[Any]:
    return [c for c in node.named_children if c.type != "comment"]


def _unwrap(node: Any) -> Any:
    """Strip parentheses and ``:: T`` casts around an expression."""
    while node is not None and node.type in _WRAPPER_TYPES:
        inner = _named(node)
        node = inner[0] if inner else None
    return node


def _string_literal(node: Any, source: bytes) -> str | None:
    """The value of a plain string literal, or None for anything else."""
    if node is None or node.type != "string":
        return None
    if any(c.type == "interpolation" for c in node.children):
        return None
    content = node.child_by_field_name("content")
    value = _text(content, source) if content is not None else ""
    return None if "\\" in value else value


def _is_require(call: Any, source: bytes) -> bool:
    """True for ``require(...)`` and ``(require :: any)(...)``."""
    callee = _unwrap(call.child_by_field_name("name"))
    return (
        callee is not None and callee.type == "identifier" and _text(callee, source) == "require"
    )


def _call_arguments(call: Any) -> list[Any]:
    args = call.child_by_field_name("arguments")
    if args is None:
        return []
    if args.type == "string":
        return [args]
    return _named(args)


def _step(base: list | None, step: list) -> list | None:
    if base is None:
        return None
    if base[0] == "path":
        return ["path", base[1], base[2] + [step]]
    if base[0] == "require":
        return ["path", base, [step]]
    return None


def _alternatives(nodes: list[Any], source: bytes) -> list | None:
    """Candidate values of an ``if``/``and``/``or`` expression, rightmost first."""
    options: list = []
    for node in reversed(nodes):
        chain = _chain(node, source)
        if chain is None:
            continue
        options.extend(chain[1] if chain[0] == "any" else [chain])
    if not options:
        return None
    return options[0] if len(options) == 1 else ["any", options]


def _chain(node: Any, source: bytes) -> list | None:
    """Reduce an expression to a chain, or None when it is not one.

    ``["path", head, steps]`` starts at an identifier (or at a ``require``
    chain, for ``require(Ref).Systems``) and applies steps
    (``["child", name]``, ``["parent", ""]``, ``["service", name]``,
    ``["ancestor", name]``); ``["str", text]`` is a string literal;
    ``["require", chain]`` is a nested require; ``["any", chains]`` lists
    alternatives in the order they are tried.
    """
    node = _unwrap(node)
    if node is None:
        return None
    kind = node.type
    if kind == "identifier":
        return ["path", _text(node, source), []]
    if kind == "string":
        value = _string_literal(node, source)
        return None if value is None else ["str", value]
    if kind == "dot_index_expression":
        name_node = node.child_by_field_name("field")
        name = _text(name_node, source) if name_node is not None else ""
        if not name or name in _PROPERTY_FIELDS:
            return None
        step = ["parent", ""] if name == "Parent" else ["child", name]
        return _step(_chain(node.child_by_field_name("table"), source), step)
    if kind == "bracket_index_expression":
        name = _string_literal(_unwrap(node.child_by_field_name("field")), source)
        if not name:
            return None
        return _step(_chain(node.child_by_field_name("table"), source), ["child", name])
    if kind == "function_call":
        return _call_chain(node, source)
    if kind == "if_expression":
        values = [node.child_by_field_name("consequence")]
        for clause in node.children:
            if clause.type in ("elseif_clause", "else_clause"):
                values.append(clause.child_by_field_name("consequence"))
        return _alternatives([v for v in values if v is not None], source)
    if kind == "binary_expression":
        if not any(c.type in ("and", "or") for c in node.children if not c.is_named):
            return None
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        return _alternatives([v for v in (left, right) if v is not None], source)
    return None


def _call_chain(call: Any, source: bytes) -> list | None:
    args = _call_arguments(call)
    if _is_require(call, source):
        inner = _chain(args[0], source) if len(args) == 1 else None
        return None if inner is None else ["require", inner]
    callee = call.child_by_field_name("name")
    if callee is None or callee.type != "method_index_expression" or not args:
        return None
    method_node = callee.child_by_field_name("method")
    method = _text(method_node, source) if method_node is not None else ""
    name = _string_literal(_unwrap(args[0]), source)
    if not name:
        return None
    base = _chain(callee.child_by_field_name("table"), source)
    if method == "GetService":
        return _step(base, ["service", name])
    if method in _CHILD_METHODS:
        # FindFirstChild(name, true) searches every descendant: no fixed path.
        if method == "FindFirstChild" and len(args) > 1 and args[1].type != "false":
            return None
        return _step(base, ["child", name])
    if method == "FindFirstAncestor":
        return _step(base, ["ancestor", name])
    return None


def _child_of_type(node: Any, kind: str) -> Any:
    return next((c for c in node.children if c.type == kind), None)


def _local_bindings(decl: Any, source: bytes) -> list[list]:
    """``[name, chain, start, visible_from, scope_end]`` for each ``local`` name."""
    assignment = _child_of_type(decl, "assignment_statement")
    holder = decl if assignment is None else assignment
    names_node = _child_of_type(holder, "variable_list")
    if names_node is None:
        return []
    values_node = _child_of_type(holder, "expression_list")
    values = values_node.children_by_field_name("value") if values_node is not None else []
    scope_end = decl.parent.end_byte if decl.parent is not None else decl.end_byte
    out: list[list] = []
    for i, name_node in enumerate(names_node.children_by_field_name("name")):
        chain = _chain(values[i], source) if i < len(values) else None
        out.append([_text(name_node, source), chain, decl.start_byte, decl.end_byte, scope_end])
    return out


def _shadowing_bindings(
    names: list[Any], visible_from: int, scope_end: int, source: bytes
) -> list[list]:
    """Parameters and loop variables: names that hide an outer local."""
    return [
        [_text(n, source), None, visible_from, visible_from, scope_end]
        for n in names
        if n.type == "identifier"
    ]


def _parameter_bindings(function: Any, source: bytes) -> list[list]:
    params = _child_of_type(function, "parameters")
    if params is None:
        return []
    names = [next(iter(_named(p)), None) for p in _named(params)]
    return _shadowing_bindings(
        [n for n in names if n is not None], params.end_byte, function.end_byte, source
    )


def _loop_bindings(loop: Any, source: bytes) -> list[list]:
    out: list[list] = []
    for clause in loop.children:
        if clause.type == "for_generic_clause":
            names_node = _child_of_type(clause, "variable_list")
            names = _named(names_node) if names_node is not None else []
        elif clause.type == "for_numeric_clause":
            names = _named(clause)[:1]
        else:
            continue
        out.extend(_shadowing_bindings(names, clause.end_byte, loop.end_byte, source))
    return out


def _chain_heads(chain: list | None, out: set[str]) -> None:
    if not chain:
        return
    if chain[0] == "path":
        if isinstance(chain[1], str):
            out.add(chain[1])
        else:
            _chain_heads(chain[1], out)
    elif chain[0] == "require":
        _chain_heads(chain[1], out)
    elif chain[0] == "any":
        for option in chain[1]:
            _chain_heads(option, out)


def _returned_fields(root: Any, source: bytes) -> list:
    """``[position, [[key, chain], ...]]`` of a top-level ``return { ... }``."""
    ret = next((c for c in reversed(root.children) if c.type == "return_statement"), None)
    if ret is None:
        return []
    exprs = _child_of_type(ret, "expression_list")
    values = _named(exprs) if exprs is not None else _named(ret)
    if len(values) != 1 or values[0].type != "table_constructor":
        return []
    fields: list[list] = []
    for entry in values[0].children:
        if entry.type != "field":
            continue
        key = entry.child_by_field_name("name")
        value = entry.child_by_field_name("value")
        if key is None or value is None:
            continue
        name = _text(key, source) if key.type == "identifier" else _string_literal(key, source)
        chain = _chain(value, source)
        if name and chain is not None:
            fields.append([name, chain])
    return [ret.start_byte, fields] if fields else []


def luau_module_facts(root: Any, source: bytes) -> dict[str, list]:
    """Requires, local bindings and returned table of one parsed Luau file.

    ``requires`` holds ``[line, position, chain, token]`` for every require
    call, wherever it sits (the import walk never enters function bodies);
    ``token`` is what the Lua handler would read from the same call, kept as
    the fallback target. ``bindings`` keeps only names some chain starts
    from. Empty when the file neither requires a module nor returns a table
    of chains.
    """
    requires: list[list] = []
    bindings: list[list] = []
    cursor = root.walk()
    while True:
        node = cursor.node
        if node is None:
            break
        kind = node.type
        if kind == "function_call" and _is_require(node, source):
            args = _call_arguments(node)
            if len(args) == 1:
                token = _LUA_TOKEN_RE.match(_text(args[0], source))
                requires.append([
                    node.start_point[0] + 1, node.start_byte, _chain(args[0], source),
                    token.group(1) if token else "",
                ])
        elif kind == "variable_declaration":
            bindings.extend(_local_bindings(node, source))
        elif kind in _FUNCTION_TYPES:
            bindings.extend(_parameter_bindings(node, source))
        elif kind == "for_statement":
            bindings.extend(_loop_bindings(node, source))
        if cursor.goto_first_child():
            continue
        while not cursor.goto_next_sibling():
            if not cursor.goto_parent():
                break
        else:
            continue
        break
    returns = _returned_fields(root, source)
    if not requires and not returns:
        return {}
    heads: set[str] = set()
    for chain in [r[2] for r in requires] + [b[1] for b in bindings] + [
        f[1] for f in (returns[1] if returns else [])
    ]:
        _chain_heads(chain, heads)
    bindings = [b for b in bindings if b[0] in heads]
    return {"requires": requires, "bindings": bindings, "returns": returns}


def parse_luau_facts(path: str) -> dict:
    """Facts of a Luau file read from disk, or ``{}`` if it cannot be parsed.

    For a module outside the extraction batch (an unchanged file on an
    incremental rebuild) whose returned table a requiring file needs.
    """
    try:
        import tree_sitter_luau
        from tree_sitter import Language, Parser

        source = Path(path).read_bytes()
        tree = Parser(Language(tree_sitter_luau.language())).parse(source)
        return luau_module_facts(tree.root_node, source)
    except Exception:
        return {}
