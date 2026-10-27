"""Source-backed MATLAB definitions and conservative same-file lexical calls."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from graphify.extractors.base import (
    _file_stem,
    _make_id,
    _read_source_bytes,
    _read_text,
    active_scan_root,
)


_DECLARATIONS = {"function_definition", "function_signature", "class_definition"}
_WORKSPACE_CHANGES = {"eval", "evalin", "assignin", "load", "clear"}
_MATLAB_IDENTIFIER = re.compile(r"[^\W\d_]\w*", re.UNICODE)
_MATLAB_NAME = re.compile(r"[^\W\d_]\w*(?:\.[^\W\d_]\w*)*", re.UNICODE)


@dataclass
class _Scope:
    syntax: Any
    name: str
    kind: str
    owner: _Scope | None
    record: dict | None = None
    children: list[_Scope] = field(default_factory=list)
    bindings: set[str] = field(default_factory=set)
    unsafe: bool = False
    primary: bool = False


def extract_matlab(path: Path) -> dict:
    """Extract declarations and only statically justified same-file calls."""
    try:
        import tree_sitter_matlab
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-matlab not installed"}

    try:
        source = _read_source_bytes(path)
        root = Parser(Language(tree_sitter_matlab.language())).parse(source).root_node
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    scan_root = active_scan_root()
    relative = path
    if scan_root is not None:
        try:
            relative = path.resolve().relative_to(scan_root.resolve())
        except ValueError:
            pass
    stem = _file_stem(relative)
    namespace_parts: list[str] = []
    for part in reversed(relative.parent.parts):
        if not part.startswith("+") or not _MATLAB_IDENTIFIER.fullmatch(part[1:]):
            break
        namespace_parts.append(part[1:])
    namespace = ".".join(reversed(namespace_parts))
    nodes: list[dict] = []
    edges: list[dict] = []

    def text(node) -> str:
        return _read_text(node, source) if node is not None else ""

    def add_node(nid: str, name: str, syntax, kind: str, chain: list[str]) -> dict:
        metadata = {
            "language": "matlab",
            "kind": f"matlab_{kind}",
            "scope_chain": chain,
            "namespace": namespace,
        }
        record = {
            "id": nid,
            "label": name,
            "file_type": "code",
            "source_file": str(path),
            "source_location": f"L{syntax.start_point.row + 1}",
            "metadata": metadata,
        }
        nodes.append(record)
        return record

    def add_edge(source_id: str, target_id: str, relation: str, syntax) -> None:
        edges.append({
            "source": source_id,
            "target": target_id,
            "relation": relation,
            "confidence": "EXTRACTED",
            "weight": 1.0,
            "source_file": str(path),
            "source_location": f"L{syntax.start_point.row + 1}",
        })

    file_scope = _Scope(root, "", "file", None)
    file_scope.record = add_node(
        _make_id(relative.as_posix()), path.name, root, "file", []
    )
    scopes = [file_scope]

    def exact_superclass_name(value: str) -> bool:
        return bool(_MATLAB_NAME.fullmatch(value))

    def superclass_facts(class_node) -> list[dict[str, str]]:
        facts: list[dict[str, str]] = []
        groups = [child for child in class_node.named_children if child.type == "superclasses"]
        for group in groups:
            bases = [
                base for base in group.named_children
                if base.type not in {"comment", "line_continuation"}
            ]
            if bases:
                for base in bases:
                    spelling = text(base).strip()
                    parsed = (
                        not group.has_error
                        and not base.has_error
                        and not base.is_missing
                        and base.type == "property_name"
                        and exact_superclass_name(spelling)
                    )
                    facts.append({
                        "name" if parsed else "raw": spelling,
                        "source_location": f"L{base.start_point.row + 1}",
                    })
            elif group.has_error:
                raw = text(group).strip().lstrip("<").strip()
                if raw:
                    facts.append({
                        "raw": raw,
                        "source_location": f"L{group.start_point.row + 1}",
                    })
        if not groups:
            for child in class_node.named_children:
                if child.type != "ERROR" or "<" not in text(child):
                    continue
                raw = text(child).split("<", 1)[1].strip()
                if raw:
                    facts.append({
                        "raw": raw,
                        "source_location": f"L{child.start_point.row + 1}",
                    })
        return facts

    def collect(syntax, owner: _Scope, chain: list[str], in_methods: bool = False) -> None:
        for child in syntax.named_children:
            if child.type in _DECLARATIONS:
                name_node = child.child_by_field_name("name")
                name = text(name_node).strip()
                kind = "class" if child.type == "class_definition" else (
                    "method" if in_methods and owner.kind == "class" else "function"
                )
                scope = _Scope(child, name, kind, owner)
                owner.children.append(scope)
                scopes.append(scope)

                header = [
                    part for part in child.named_children
                    if part.type not in {"block", "methods", "properties", "events", "enumeration", "superclasses"}
                ]
                trustworthy_name = (
                    name_node is not None
                    and name_node.type == "identifier"
                    and not name_node.has_error
                    and not name_node.is_missing
                    and bool(name)
                )
                trustworthy_header = kind == "class" or not any(
                    part.has_error or part.is_missing for part in header
                )
                if not trustworthy_name or not trustworthy_header:
                    scope.unsafe = True
                if owner.kind in {"function", "method"} and not (
                    trustworthy_name and trustworthy_header
                ):
                    owner.unsafe = True
                next_chain = [*chain, name] if name else chain
                if trustworthy_name and trustworthy_header:
                    nid = _make_id(
                        stem,
                        "matlab",
                        kind,
                        *chain,
                        name,
                        f"L{child.start_point.row + 1}",
                        f"C{child.start_point.column + 1}",
                    )
                    scope.record = add_node(nid, name, child, kind, chain)
                    if child.type == "function_signature":
                        scope.record["metadata"]["matlab_declaration_only"] = True
                    if kind == "class":
                        scope.record["metadata"]["matlab_superclasses"] = superclass_facts(child)
                    if owner.record is not None:
                        add_edge(
                            owner.record["id"],
                            nid,
                            "method" if kind == "method" else "contains",
                            child,
                        )

                collect(child, scope, next_chain, False)
            elif syntax.type in {"source_file", "function_definition"} and child.type == "block":
                collect(child, owner, chain)
            elif syntax.type == "class_definition" and child.type == "methods":
                collect(child, owner, chain, True)

    collect(root, file_scope, [])
    excluded_callable_names = {
        scope.name for scope in scopes if scope.kind in {"class", "method"} and scope.name
    }

    meaningful = [
        child for child in root.named_children
        if child.type not in {"comment", "line_continuation"}
    ]
    if meaningful:
        first = meaningful[0]
        while first.type == "block":
            nested = next(
                (child for child in first.named_children
                 if child.type not in {"comment", "line_continuation"}),
                None,
            )
            if nested is None:
                break
            first = nested
        primary = next((scope for scope in file_scope.children if scope.syntax == first), None)
        if primary is not None and primary.record is not None:
            primary.primary = True
            file_scope.record["metadata"].update(
                matlab_file_kind=primary.kind,
                matlab_primary_name=primary.name,
            )
        elif first.type not in {"ERROR", *_DECLARATIONS}:
            file_scope.record["metadata"]["matlab_file_kind"] = "script"

    def node_key(node) -> tuple[str, int, int]:
        return node.type, node.start_byte, node.end_byte

    known_scope_keys = {node_key(scope.syntax) for scope in scopes[1:]}

    def lvalue_roots(node) -> set[str]:
        if node is None:
            return set()
        if node.type == "identifier":
            return {text(node)}
        if node.type == "multioutput_variable":
            return set().union(*(lvalue_roots(child) for child in node.named_children))
        if node.type == "function_call":
            return lvalue_roots(node.child_by_field_name("name"))
        if node.type == "field_expression":
            return lvalue_roots(node.child_by_field_name("object"))
        return set()

    def parameter_names(node) -> set[str]:
        names = set()
        stack = list(node.named_children)
        while stack:
            child = stack.pop()
            if child.type == "identifier":
                names.add(text(child))
            else:
                stack.extend(child.named_children)
        return names

    def is_call_site(node, scope_node) -> bool:
        """A direct unqualified call expression, not an index or dynamic callee."""
        if not any(child.type == "(" for child in node.children):
            return False
        if any(child.type in {"{", "superclass"} for child in node.children):
            return False
        parent = node.parent
        while parent is not None and node_key(parent) != node_key(scope_node):
            if parent.type in {"lambda", "handle_operator", "arguments_statement", "field_expression"}:
                return False
            if parent.type == "assignment":
                left = parent.child_by_field_name("left")
                cursor = node
                while cursor is not None and node_key(cursor) != node_key(parent):
                    if left is not None and node_key(cursor) == node_key(left):
                        return False
                    cursor = cursor.parent
            if parent.type == "function_call":
                outer_name = parent.child_by_field_name("name")
                if outer_name is not None and node_key(outer_name) == node_key(node):
                    return False
            parent = parent.parent
        return True

    def inspect_scope(scope: _Scope) -> list[tuple[str, Any]]:
        """Collect whole-scope bindings and uncertainty barriers."""
        calls: list[tuple[str, Any]] = []
        root_key = node_key(scope.syntax)
        for child in scope.syntax.named_children:
            if child.type == "function_output":
                for output in child.named_children:
                    scope.bindings.update(lvalue_roots(output))
            elif child.type == "function_arguments":
                scope.bindings.update(parameter_names(child))

        def mark_uncertain_subtree(node) -> None:
            stack = [node]
            while stack:
                child = stack.pop()
                if child.type == "ERROR" or child.is_missing:
                    scope.unsafe = True
                if child.type in {"command", "import_statement", "import_declaration"}:
                    scope.unsafe = True
                if child.type == "function_call":
                    callee = child.child_by_field_name("name")
                    if (
                        callee is not None
                        and callee.type == "identifier"
                        and text(callee) in _WORKSPACE_CHANGES
                    ):
                        scope.unsafe = True
                if child.type not in _DECLARATIONS:
                    stack.extend(child.children)

        def visit(node) -> None:
            if node_key(node) != root_key and node.type in _DECLARATIONS:
                if node_key(node) not in known_scope_keys:
                    scope.unsafe = True
                return
            if node.type == "ERROR" or node.is_missing:
                scope.unsafe = True
            if node.type in {"command", "import_statement", "import_declaration"}:
                scope.unsafe = True
            if node.type == "arguments_statement" and node.has_error:
                scope.unsafe = True
            if node.type == "arguments_statement":
                for prop in node.named_children:
                    if prop.type != "property":
                        continue
                    name_node = prop.child_by_field_name("name")
                    if name_node is not None and name_node.type == "identifier":
                        scope.bindings.add(text(name_node))
                mark_uncertain_subtree(node)
                return
            if node.type == "assignment":
                scope.bindings.update(lvalue_roots(node.child_by_field_name("left")))
            elif node.type == "iterator":
                first = next((child for child in node.named_children), None)
                if first is not None and first.type == "identifier":
                    scope.bindings.add(text(first))
            elif node.type == "catch_clause":
                identifier = next(
                    (child for child in node.named_children if child.type == "identifier"),
                    None,
                )
                if identifier is not None:
                    scope.bindings.add(text(identifier))
            elif node.type in {"global_operator", "persistent_operator"}:
                scope.bindings.update(
                    text(child) for child in node.named_children if child.type == "identifier"
                )

            if node.type == "lambda":
                mark_uncertain_subtree(node)
                return
            if node.type == "handle_operator":
                return
            if node.type == "function_call":
                name_node = node.child_by_field_name("name")
                if name_node is not None and name_node.type == "identifier":
                    name = text(name_node)
                    if name in _WORKSPACE_CHANGES:
                        scope.unsafe = True
                    if name != "feval" and is_call_site(node, scope.syntax):
                        calls.append((name, node))
            for child in node.children:
                visit(child)

        visit(scope.syntax)
        return calls

    calls_by_scope: list[tuple[_Scope, list[tuple[str, Any]]]] = []
    for scope in scopes[1:]:
        if scope.kind in {"function", "method"}:
            calls_by_scope.append((scope, inspect_scope(scope)))

    def callable_ancestors(scope: _Scope):
        current: _Scope | None = scope
        while current is not None and current.kind not in {"file", "class"}:
            yield current
            current = current.owner

    def caller_is_unsafe(scope: _Scope) -> bool:
        return any(ancestor.unsafe for ancestor in callable_ancestors(scope))

    def lexical_tiers(scope: _Scope):
        current: _Scope | None = scope
        while current is not None:
            yield [child for child in current.children if child.kind == "function"]
            parent = current.owner
            if parent is None or parent.kind in {"file", "class"}:
                return
            current = parent

    def file_target(name: str) -> _Scope | None:
        declarations = [
            child for child in file_scope.children
            if child.kind == "function" and child.name == name
        ]
        if len(declarations) != 1:
            return None
        target = declarations[0]
        if target.record is None or (target.primary and target.name != path.stem):
            return None
        return target

    for caller, sites in calls_by_scope:
        if caller.record is None or caller_is_unsafe(caller):
            continue
        for name, syntax in sites:
            if name in excluded_callable_names:
                continue
            if any(name in ancestor.bindings for ancestor in callable_ancestors(caller)):
                continue
            target = None
            found_nearest = False
            for tier in lexical_tiers(caller):
                declarations = [candidate for candidate in tier if candidate.name == name]
                if declarations:
                    found_nearest = True
                    if len(declarations) == 1 and declarations[0].record is not None:
                        target = declarations[0]
                    break
            if not found_nearest:
                target = file_target(name)
            if target is not None and target.record is not None:
                add_edge(caller.record["id"], target.record["id"], "calls", syntax)

    return {"nodes": nodes, "edges": edges}
