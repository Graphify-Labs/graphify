"""Structural extraction for Perl source files."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from graphify.extractors.base import _make_id, _read_text

if TYPE_CHECKING:
    from tree_sitter import Node


# Pragmas that take a `use NAME ...;` shape but name no real project/CPAN
# module worth a graph node (they configure the compiler/parser itself).
# `base`/`parent` are handled separately as inheritance, not a generic import.
_PERL_PRAGMAS = frozenset({
    "strict", "warnings", "utf8", "feature", "if", "vars", "lib", "constant",
    "overload", "v5", "experimental",
})

_PERL_INHERITANCE_PRAGMAS = frozenset({"base", "parent"})


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _string_literals(node: Node, source: bytes) -> list[str]:
    """Every quoted string literal's content under ``node``, in source order.

    ``qw(a b c)`` parses as a ``quoted_word_list`` whose single content node
    holds all words; those split into separate entries so the canonical
    ``use base qw(...)`` / ``our @ISA = qw(...)`` inheritance forms yield one
    base per word instead of nothing.
    """
    out: list[str] = []
    if node.type == "quoted_word_list":
        content = next(
            (child for child in node.named_children if child.type == "string_content"),
            None,
        )
        if content is not None:
            out.extend(_read_text(content, source).split())
        return out
    if node.type in {"string_literal", "interpolated_string_literal"}:
        content = next(
            (child for child in node.named_children if child.type == "string_content"),
            None,
        )
        out.append(_read_text(content, source) if content is not None else "")
        return out
    for child in node.named_children:
        out.extend(_string_literals(child, source))
    return out


def _normalize_package(name: str | None) -> str:
    """Canonical Perl package name for call resolution.

    Subs outside any ``package`` statement live in ``main``, and ``::foo()``,
    ``main::foo()``, ``main::Foo::bar()`` and ``Foo::->bar()`` all spell a
    package without its optional ``main::`` prefix or trailing ``::``.
    """
    name = (name or "").strip(":")
    while name.startswith("main::"):
        name = name[len("main::"):]
    return name or "main"


def resolve_perl_calls(
    per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]
) -> None:
    """Resolve package-qualified sub calls and unqualified method calls.

    Both shapes only ever reach ``raw_calls`` here (same-package bareword
    calls are resolved directly during extraction), and both are safe to
    treat with a single uniqueness rule: a qualified call
    (``Pkg::func()`` / ``Pkg->method()``) must match that exact package and
    name; an unqualified method call (``$obj->method()``) must match exactly
    one sub of that name anywhere in the corpus, mirroring the arity-free
    version of ``resolve_erlang_remote_calls``.
    """
    by_package_name: dict[tuple[str, str], list[str]] = {}
    by_name: dict[str, list[str]] = {}
    for node in all_nodes:
        metadata = node.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("language") != "perl":
            continue
        if metadata.get("kind") != "function":
            continue
        package = metadata.get("package")
        name = metadata.get("name")
        if not isinstance(name, str):
            continue
        by_name.setdefault(name, []).append(node["id"])
        if package is None or isinstance(package, str):
            key = (_normalize_package(package), name)
            by_package_name.setdefault(key, []).append(node["id"])

    existing = {
        (edge.get("source"), edge.get("target"))
        for edge in all_edges
        if edge.get("relation") == "calls"
    }
    for result in per_file:
        for call in result.get("raw_calls", []):
            if call.get("language") != "perl":
                continue
            caller = call.get("caller_nid")
            name = str(call.get("callee", ""))
            remote_package = call.get("remote_module")
            if remote_package is not None:
                key = (_normalize_package(str(remote_package)), name)
                candidates = by_package_name.get(key, [])
            else:
                candidates = by_name.get(name, [])
            if len(candidates) != 1 or candidates[0] == caller:
                continue
            pair = (caller, candidates[0])
            if pair in existing:
                continue
            existing.add(pair)
            all_edges.append({
                "source": caller,
                "target": candidates[0],
                "relation": "calls",
                "context": "remote_call" if remote_package is not None else "method_call",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": call.get("source_file", ""),
                "source_location": call.get("source_location"),
                "weight": 1.0,
            })


def extract_perl(path: Path) -> dict:
    try:
        from tree_sitter import Parser
        from tree_sitter_language_pack import get_language
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-language-pack not installed"}

    try:
        source = path.read_bytes()
        root = Parser(get_language("perl")).parse(source).root_node
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": f"Perl grammar failed to load: {exc}"}

    source_file = str(path)
    file_id = _make_id(source_file)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    raw_calls: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    node_by_id: dict[str, dict[str, Any]] = {}
    seen_edges: set[tuple[str, str, str]] = set()
    # (package name) -> {sub name: function nid}, scoped per package for the
    # same-file direct call resolution pass below.
    package_functions: dict[str, dict[str, str]] = {}
    bodies: list[tuple[Node, str, str | None]] = []

    def add_node(
        nid: str,
        label: str,
        node: Node,
        *,
        kind: str,
        source_backed: bool = True,
        callable_node: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if nid not in seen_ids:
            seen_ids.add(nid)
            details: dict[str, Any] = {"language": "perl", "kind": kind}
            if metadata:
                details.update(metadata)
            item: dict[str, Any] = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_location": f"L{node.start_point[0] + 1}",
                "metadata": details,
            }
            if source_backed:
                item["source_file"] = source_file
            if callable_node:
                item["_callable"] = True
            nodes.append(item)
            node_by_id[nid] = item
        return nid

    def add_edge(
        source_id: str, target_id: str, relation: str, node: Node,
        *, target_file: str | None = None,
    ) -> None:
        key = (source_id, target_id, relation)
        if not source_id or not target_id or source_id == target_id or key in seen_edges:
            return
        seen_edges.add(key)
        edge: dict[str, Any] = {
            "source": source_id,
            "target": target_id,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": source_file,
            "source_location": f"L{node.start_point[0] + 1}",
            "weight": 1.0,
        }
        if target_file is not None:
            edge["target_file"] = target_file
        edges.append(edge)

    add_node(file_id, path.name, root, kind="file")

    def external_package(name: str, node: Node) -> str:
        return add_node(
            _make_id("perl", "package", name), name, node,
            kind="package", source_backed=False,
        )

    def add_package(name: str, node: Node) -> str:
        package_id = _make_id("perl", "package", name)
        stub = node_by_id.get(package_id)
        if stub is not None and "source_file" not in stub:
            # Referenced (use/parent/@ISA/require) before its definition in
            # this file: upgrade the external stub to the real definition.
            stub["source_file"] = source_file
            stub["source_location"] = f"L{node.start_point[0] + 1}"
            stub["metadata"]["package"] = name
        add_node(
            package_id, name, node,
            kind="package", metadata={"package": name},
        )
        package_functions.setdefault(name, {})
        return package_id

    def add_sub(name: str, node: Node, package_id: str, package_name: str | None) -> str:
        function_id = add_node(
            _make_id(package_id, "function", name), f"{name}()", node,
            kind="function", callable_node=True,
            metadata={"package": package_name, "name": name},
        )
        add_edge(package_id, function_id, "contains", node)
        package_functions.setdefault(package_name or "", {})[name] = function_id
        return function_id

    def add_inherits(child_package_id: str, base_name: str, node: Node) -> None:
        base_id = external_package(base_name, node)
        add_edge(child_package_id, base_id, "inherits", node)

    def handle_use_or_require(
        pragma_name: str, args_node: Node | None, node: Node, owner: str,
    ) -> None:
        if pragma_name in _PERL_PRAGMAS:
            return
        if pragma_name in _PERL_INHERITANCE_PRAGMAS:
            if args_node is None:
                return
            for base in _string_literals(args_node, source):
                if base:
                    add_inherits(owner, base, node)
            return
        target_id = external_package(pragma_name, node)
        add_edge(owner, target_id, "imports", node)

    def handle_require_path(literal: str, node: Node, owner: str) -> None:
        target = path.parent / literal
        target_id = _make_id(str(target))
        add_edge(owner, target_id, "imports_from", node, target_file=str(target))

    def handle_statements(
        statements: list[Node], current_package: str, current_package_name: str | None,
    ) -> None:
        # A statement-form ``package Foo;`` switches the package until the end
        # of the enclosing block (or file), so the state is local to this scope.
        for child in statements:
            switched = handle_statement(child, current_package, current_package_name)
            if switched is not None:
                current_package, current_package_name = switched

    def handle_package(node: Node) -> tuple[str, str] | None:
        name_node = node.child_by_field_name("name") or next(
            (c for c in node.named_children if c.type == "package"), None
        )
        if name_node is None:
            return None
        name = _read_text(name_node, source)
        package_id = add_package(name, node)
        add_edge(file_id, package_id, "contains", node)
        block = next((c for c in node.named_children if c.type == "block"), None)
        if block is not None:
            handle_statements(block.named_children, package_id, name)
            return None
        return package_id, name

    def handle_statement(
        node: Node, current_package: str, current_package_name: str | None,
    ) -> tuple[str, str] | None:
        """Handle one statement; return the new package if it switches scope."""
        if node.type == "package_statement":
            return handle_package(node)

        if node.type == "subroutine_declaration_statement":
            name_node = next(
                (c for c in node.named_children if c.type == "bareword"), None
            )
            body = node.child_by_field_name("body")
            if name_node is None:
                return None
            name = _unquote(_read_text(name_node, source))
            function_id = add_sub(name, node, current_package, current_package_name)
            if body is not None:
                bodies.append((body, function_id, current_package_name))
            return None

        if node.type == "use_statement":
            name_node = node.child_by_field_name("package") or next(
                (c for c in node.named_children if c.type == "package"), None
            )
            if name_node is None:
                return None
            args = next(
                (c for c in node.named_children if c is not name_node), None
            )
            handle_use_or_require(
                _read_text(name_node, source), args, node, current_package,
            )
            return None

        if node.type == "expression_statement":
            inner = node.named_children[0] if node.named_children else None
            if inner is not None and inner.type == "require_expression":
                handle_require(inner, node, current_package)
            elif inner is not None and inner.type == "assignment_expression":
                handle_isa_assignment(inner, current_package)
            return None

        if node.type == "assignment_expression":
            handle_isa_assignment(node, current_package)
        return None

    def handle_require(inner: Node, node: Node, current_package: str) -> None:
        target = next(iter(inner.named_children), None)
        if target is None:
            return
        if target.type == "bareword":
            handle_use_or_require(
                _read_text(target, source), None, node, current_package,
            )
        elif target.type in {"string_literal", "interpolated_string_literal"}:
            literals = _string_literals(target, source)
            if literals and literals[0]:
                handle_require_path(literals[0], node, current_package)

    def handle_isa_assignment(node: Node, current_package: str) -> None:
        children = node.named_children
        if len(children) < 2:
            return
        lhs, rhs = children[0], children[-1]
        array = None
        if lhs.type == "variable_declaration":
            array = next((c for c in lhs.named_children if c.type == "array"), None)
        elif lhs.type == "array":
            array = lhs
        if array is None:
            return
        varname = next((c for c in array.named_children if c.type == "varname"), None)
        if varname is None or _read_text(varname, source) != "ISA":
            return
        for base in _string_literals(rhs, source):
            if base:
                add_inherits(current_package, base, node)

    handle_statements(root.named_children, file_id, None)

    def resolve_bareword_call(callee: str, current_package_name: str | None) -> str | None:
        if current_package_name is not None:
            return package_functions.get(current_package_name, {}).get(callee)
        return package_functions.get("", {}).get(callee)

    def add_raw_call(caller_id: str, name: str, module: str | None, node: Node) -> None:
        raw_calls.append({
            "caller_nid": caller_id,
            "callee": name,
            "remote_module": module,
            "is_member_call": True,
            "language": "perl",
            "source_file": source_file,
            "source_location": f"L{node.start_point[0] + 1}",
        })

    def method_call_target(invocant: Node, method_text: str) -> tuple[str | None, str]:
        """(package, method) for ``invocant->method``; package None if dynamic."""
        if "::" in method_text:
            # ``$obj->Pkg::method()`` names the package explicitly.
            module, _, name = method_text.rpartition("::")
            return module, name
        if invocant.type == "bareword":
            return _read_text(invocant, source), method_text
        if invocant.type == "string_literal":
            literals = _string_literals(invocant, source)
            if literals and literals[0]:
                return literals[0], method_text
        return None, method_text

    def walk_calls(node: Node, caller_id: str, package_name: str | None) -> None:
        if node.type == "subroutine_declaration_statement":
            return
        if node.type in {"function_call_expression", "ambiguous_function_call_expression"}:
            function_node = node.child_by_field_name("function")
            if function_node is not None:
                text = _read_text(function_node, source)
                if "::" in text:
                    module, _, name = text.rpartition("::")
                    add_raw_call(caller_id, name, module, node)
                else:
                    target = resolve_bareword_call(text, package_name)
                    if target is not None:
                        add_edge(caller_id, target, "calls", node)
        elif node.type == "method_call_expression":
            invocant = node.child_by_field_name("invocant")
            method_node = node.child_by_field_name("method")
            if invocant is not None and method_node is not None:
                module, name = method_call_target(
                    invocant, _read_text(method_node, source),
                )
                add_raw_call(caller_id, name, module, node)
        for child in node.named_children:
            walk_calls(child, caller_id, package_name)

    for body, caller_id, package_name in bodies:
        walk_calls(body, caller_id, package_name)

    clean_edges = [
        edge for edge in edges
        if edge["source"] in seen_ids
        and (edge["target"] in seen_ids or edge["relation"] == "imports_from")
    ]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
