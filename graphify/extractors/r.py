"""R extractor.

R has no named-function syntax: every definition is an assignment whose
right-hand side is an anonymous ``function_definition`` (``f <- function(x)``,
``f = \\(x)``, ``f <<- function()``). The name lives on the assignment's ``lhs``,
so the generic config-driven walker — which reads a ``name`` field off the
function node — cannot see it. Hence a bespoke extractor.

Calls are deliberately NOT resolved here. A bare ``paste0(...)`` is base R and a
bare ``compute_moments(...)`` is a sibling file in the same package namespace,
and nothing in the file distinguishes them. Same-file callees resolve here (they
are certain); everything else is emitted as a ``raw_call`` and resolved corpus-
wide by ``graphify.r_resolution``, which drops what nothing defines. That keeps
base R out of the graph without hardcoding ~1,300 base names, and keeps package
calls in.

The grammar comes from tree-sitter-language-pack (r-lib/tree-sitter-r); there is
no standalone ``tree-sitter-r`` wheel on PyPI.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id, _read_text

# `name <- function()`, `name = function()`, `name <<- function()`. The
# right-assign forms (`function() -> name`) are handled separately: they invert
# lhs/rhs, so folding them in here would read the operator as the name.
_R_ASSIGN_OPS = frozenset({"<-", "=", "<<-"})
_R_RIGHT_ASSIGN_OPS = frozenset({"->", "->>"})

# Calls that source another R file, as opposed to merely naming one. Everything
# else that carries an R path literal becomes a `references` edge, since a helper
# like `test_file("x.R")` or a project-local `source_once(path("x.R"))` wrapper
# names the file without necessarily being an import.
_R_SOURCE_FNS = frozenset({"source", "sys.source"})

# `library(x)` / `require(x)` take a bare symbol; `requireNamespace("x")` and
# `loadNamespace("x")` take a string. Both shapes are read below.
_R_LIBRARY_FNS = frozenset({"library", "require", "requireNamespace", "loadNamespace"})


def _r_string_value(node, source: bytes) -> str | None:
    """Text of a `string` node with its quotes stripped, else None."""
    if node is None or node.type != "string":
        return None
    content = next((c for c in node.children if c.type == "string_content"), None)
    return _read_text(content, source) if content is not None else ""


def _r_arg_values(call_node) -> list:
    """The `value` child of each `argument` under a call's `arguments` node."""
    args = call_node.child_by_field_name("arguments")
    if args is None:
        return []
    return [v for c in args.children if c.type == "argument"
            for v in (c.child_by_field_name("value"),) if v is not None]


def _r_path_literal(node, source: bytes) -> str | None:
    """Resolve an argument to an R file path, or None.

    Two shapes carry one in practice: a bare string literal (``source("x.R")``)
    and a path-joining call over string literals (``source(file.path("a",
    "b.R"))``, and project-local equivalents). The join is by "/" regardless of
    the helper's name — the segments are matched by suffix later, so a wrong
    separator guess cannot invent an edge.
    """
    literal = _r_string_value(node, source)
    if literal is not None:
        return literal if literal.lower().endswith((".r",)) else None
    if node is None or node.type != "call":
        return None
    segments = [_r_string_value(v, source) for v in _r_arg_values(node)]
    if not segments or any(s is None for s in segments):
        return None
    joined = "/".join(segments)
    return joined if joined.lower().endswith((".r",)) else None


def extract_r(path: Path) -> dict:
    """Extract functions, calls, package imports, and sourced files from a .R file."""
    try:
        from tree_sitter import Parser
        from tree_sitter_language_pack import get_language
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-language-pack not installed"}

    try:
        # get_language returns a ready tree_sitter.Language, unlike the
        # per-grammar modules whose language() hands back a raw pointer.
        parser = Parser(get_language("r"))
        source = path.read_bytes()
        root = parser.parse(source).root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    raw_calls: list[dict] = []
    seen_ids: set[str] = set()
    defined_here: set[str] = set()
    # Bodies of named functions, walked for calls after every definition in the
    # file is known — R resolves at call time, so a function may call one
    # defined further down the file.
    function_bodies: list[tuple[str, object]] = []
    named_fn_nodes: set[int] = set()

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            })

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None) -> None:
        edge = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def add_raw_call(caller_nid: str, callee: str, line: int, **extra) -> None:
        raw_calls.append({
            "lang": "r",
            "caller_nid": caller_nid,
            "callee": callee,
            "source_file": str_path,
            "source_location": f"L{line}",
            **extra,
        })

    def _unwrap(node):
        """Strip redundant parens: `(function(x) x) -> f` binds a function too."""
        while node is not None and node.type == "parenthesized_expression":
            node = next((c for c in node.children
                         if c.type not in ("(", ")", "comment")), None)
        return node

    def _assignment_parts(node):
        """(name_node, function_node) for an assignment binding a function, else None."""
        op = node.child_by_field_name("operator")
        lhs = _unwrap(node.child_by_field_name("lhs"))
        rhs = _unwrap(node.child_by_field_name("rhs"))
        if op is None or lhs is None or rhs is None:
            return None
        if op.type in _R_ASSIGN_OPS and rhs.type == "function_definition":
            return lhs, rhs
        if op.type in _R_RIGHT_ASSIGN_OPS and lhs.type == "function_definition":
            return rhs, lhs
        return None

    def collect_definitions(node, scope_nid: str) -> None:
        if node.type == "binary_operator":
            parts = _assignment_parts(node)
            if parts is not None:
                name_node, fn_node = parts
                # `"quoted" <- function()` is legal and binds a string literal.
                name = (_r_string_value(name_node, source)
                        if name_node.type == "string" else
                        _read_text(name_node, source) if name_node.type == "identifier" else None)
                if name:
                    line = node.start_point[0] + 1
                    func_nid = _make_id(stem, name)
                    add_node(func_nid, f"{name}()", line)
                    add_edge(scope_nid, func_nid, "defines", line)
                    defined_here.add(name)
                    named_fn_nodes.add(fn_node.id)
                    function_bodies.append((func_nid, fn_node))
                    body = fn_node.child_by_field_name("body")
                    if body is not None:
                        collect_definitions(body, func_nid)
                    return
        for child in node.children:
            collect_definitions(child, scope_nid)

    def emit_import(scope_nid: str, name: str, line: int) -> None:
        imp_nid = _make_id(name)
        add_node(imp_nid, name, line)
        add_edge(scope_nid, imp_nid, "imports", line, context="import")

    def walk_calls(node, caller_nid: str) -> None:
        # A named function has its own caller identity and is walked separately.
        # Anonymous ones (a callback passed to lapply) are transparent: their
        # calls belong to whatever scope encloses them.
        if node.type == "function_definition" and node.id in named_fn_nodes:
            return

        if node.type == "call":
            fn = node.child_by_field_name("function")
            line = node.start_point[0] + 1
            callee = None
            if fn is not None and fn.type == "identifier":
                callee = _read_text(fn, source)
            elif fn is not None and fn.type == "namespace_operator":
                # pkg::fn(...) — the package is an import, the function a call.
                pkg_node = fn.child_by_field_name("lhs")
                fn_node = fn.child_by_field_name("rhs")
                if pkg_node is not None:
                    emit_import(caller_nid, _read_text(pkg_node, source), line)
                if fn_node is not None:
                    callee = _read_text(fn_node, source)
            elif fn is not None and fn.type == "extract_operator":
                # obj$method(...) — the method name is the best available target.
                method = fn.child_by_field_name("rhs")
                if method is not None and method.type == "identifier":
                    callee = _read_text(method, source)

            if callee:
                if callee in _R_LIBRARY_FNS:
                    for value in _r_arg_values(node):
                        pkg = (_read_text(value, source) if value.type == "identifier"
                               else _r_string_value(value, source))
                        if pkg:
                            emit_import(caller_nid, pkg, line)
                elif callee in defined_here:
                    add_edge(caller_nid, _make_id(stem, callee), "calls", line, context="call")
                else:
                    add_raw_call(caller_nid, callee, line)

                # Any call may name an R file: source(), sys.source(), or a
                # project-local wrapper. Resolution keeps only paths that match a
                # file actually in the corpus.
                for value in _r_arg_values(node):
                    target = _r_path_literal(value, source)
                    if target:
                        add_raw_call(
                            caller_nid, callee, line,
                            kind="file_ref",
                            file_path=target,
                            relation="imports" if callee in _R_SOURCE_FNS else "references",
                        )

        for child in node.children:
            walk_calls(child, caller_nid)

    collect_definitions(root, file_nid)
    # Top-level statements are the bulk of an analysis script, so the file node
    # is a caller in its own right, not just a container.
    walk_calls(root, file_nid)
    for func_nid, fn_node in function_bodies:
        body = fn_node.child_by_field_name("body")
        if body is not None:
            walk_calls(body, func_nid)

    return {"nodes": nodes, "edges": edges, "raw_calls": raw_calls}
