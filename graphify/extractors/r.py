"""Structural extraction for R source files."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tree_sitter import Node

from graphify.extractors.base import _file_stem, _make_id, _read_text


_CLASS_CONSTRUCTORS = frozenset({"R6Class", "setRefClass", "ggproto"})
_NON_PROJECT_CALLS = frozenset({
    "R6Class", "c", "get", "ggproto", "library", "list", "print", "require",
    "setClass", "setGeneric", "setMethod", "setRefClass", "source",
})


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def resolve_r_sourced_calls(
    per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]
) -> None:
    """Resolve calls only through an explicit source relationship."""
    file_source_by_id = {
        node["id"]: str(node["source_file"])
        for node in all_nodes
        if node.get("source_file")
        and node.get("label") == Path(str(node["source_file"])).name
    }
    sourced_files: dict[str, set[str]] = {}
    for edge in all_edges:
        if edge.get("relation") != "imports_from":
            continue
        target_id = edge.get("target")
        if not isinstance(target_id, str):
            continue
        target_source = file_source_by_id.get(target_id)
        if target_source:
            sourced_files.setdefault(edge["source"], set()).add(target_source)

    file_id_by_source = {source: nid for nid, source in file_source_by_id.items()}
    callables: dict[tuple[str, str], list[str]] = {}
    for node in all_nodes:
        if not node.get("_callable") or not node.get("source_file"):
            continue
        name = str(node.get("label", "")).strip("()")
        callables.setdefault((str(node["source_file"]), name), []).append(node["id"])

    existing = {
        (edge.get("source"), edge.get("target"))
        for edge in all_edges
        if edge.get("relation") == "calls"
    }
    for result in per_file:
        for call in result.get("raw_calls", []):
            if call.get("language") != "r":
                continue
            caller = call.get("caller_nid")
            caller_file = file_id_by_source.get(str(call.get("source_file", "")))
            if caller_file is None:
                continue
            candidates: list[str] = []
            for source in sourced_files.get(caller_file, set()):
                candidates.extend(callables.get((source, str(call.get("callee", ""))), []))
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
                "context": "sourced_call",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": call.get("source_file", ""),
                "source_location": call.get("source_location"),
                "weight": 1.0,
            })


def extract_r(path: Path) -> dict:
    try:
        from tree_sitter import Parser
        from tree_sitter_language_pack import get_language
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-language-pack not installed"}

    try:
        source = path.read_bytes()
        root = Parser(get_language("r")).parse(source).root_node
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": f"R grammar failed to load: {exc}"}

    source_file = str(path)
    stem = _file_stem(path)
    file_id = _make_id(source_file)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    raw_calls: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()
    definitions: dict[str, dict[str, str]] = {file_id: {}}
    scope_parent: dict[str, str] = {}
    callable_bodies: list[tuple[Node, str]] = []
    classes: dict[str, str] = {}

    def add_node(
        nid: str,
        label: str,
        line: int,
        *,
        kind: str,
        source_backed: bool = True,
        callable_node: bool = False,
    ) -> None:
        if not nid or nid in seen_ids:
            return
        seen_ids.add(nid)
        item: dict[str, Any] = {
            "id": nid,
            "label": label,
            "file_type": "code",
            "source_location": f"L{line}",
            "metadata": {"language": "r", "kind": kind},
        }
        if source_backed:
            item["source_file"] = source_file
        if callable_node:
            item["_callable"] = True
        nodes.append(item)

    def add_edge(
        source_id: str,
        target_id: str,
        relation: str,
        line: int,
        *,
        target_file: str | None = None,
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
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if target_file is not None:
            edge["target_file"] = target_file
        edges.append(edge)

    add_node(file_id, path.name, 1, kind="file")

    def argument_value(argument: Node) -> Node | None:
        name_node = argument.child_by_field_name("name")
        values = [child for child in argument.named_children if child != name_node]
        return values[-1] if values else None

    def call_parts(node: Node) -> tuple[str, Node | None]:
        function = node.child_by_field_name("function")
        arguments = node.child_by_field_name("arguments")
        if function is None:
            return "", arguments
        return _read_text(function, source), arguments

    def string_or_identifier(node: Node | None) -> str:
        if node is None:
            return ""
        return _unquote(_read_text(node, source))

    def declare_function(
        name: str, function: Node, body: Node | None, owner: str, relation: str = "contains"
    ) -> str:
        nid = _make_id(owner, name)
        line = function.start_point[0] + 1
        add_node(nid, f"{name}()", line, kind="function", callable_node=True)
        add_edge(owner, nid, relation, line)
        definitions.setdefault(owner, {})[name] = nid
        definitions.setdefault(nid, {})
        scope_parent[nid] = owner
        if body is not None:
            callable_bodies.append((body, nid))
            scan_declarations(body, nid, top_level=False)
        return nid

    def add_class(name: str, declaration: Node, owner: str = file_id) -> str:
        nid = _make_id(stem, "class", name)
        line = declaration.start_point[0] + 1
        add_node(nid, name, line, kind="class", callable_node=True)
        add_edge(owner, nid, "contains", line)
        definitions.setdefault(nid, {})
        scope_parent[nid] = owner
        classes[name] = nid
        return nid

    def add_class_members(class_id: str, arguments: Node) -> None:
        for argument in arguments.named_children:
            if argument.type != "argument":
                continue
            key_node = argument.child_by_field_name("name")
            value = argument_value(argument)
            key = _read_text(key_node, source) if key_node is not None else ""
            if key == "inherit" and value is not None:
                base_name = string_or_identifier(value).split("$")[-1]
                if base_name:
                    base_id = classes.get(base_name, _make_id("r", "class", base_name))
                    add_node(
                        base_id, base_name, value.start_point[0] + 1,
                        kind="external_class", source_backed=False,
                    )
                    add_edge(class_id, base_id, "inherits", value.start_point[0] + 1)
            if key not in {"public", "private", "active", "methods"} or value is None:
                continue
            if value.type != "call":
                continue
            list_name, list_arguments = call_parts(value)
            if list_name != "list" or list_arguments is None:
                continue
            for member in list_arguments.named_children:
                if member.type != "argument":
                    continue
                member_name_node = member.child_by_field_name("name")
                member_value = argument_value(member)
                if (
                    member_name_node is None
                    or member_value is None
                    or member_value.type != "function_definition"
                ):
                    continue
                member_name = _read_text(member_name_node, source)
                declare_function(
                    member_name,
                    member_value,
                    member_value.child_by_field_name("body"),
                    class_id,
                    relation="method",
                )

    def process_call_declaration(node: Node, owner: str) -> bool:
        call_name, arguments = call_parts(node)
        if arguments is None:
            return False
        args = [child for child in arguments.named_children if child.type == "argument"]
        if call_name in {"library", "require"} and args:
            package = string_or_identifier(argument_value(args[0]))
            if package:
                package_id = _make_id("r", "package", package)
                add_node(
                    package_id, package, node.start_point[0] + 1,
                    kind="package", source_backed=False,
                )
                add_edge(file_id, package_id, "imports", node.start_point[0] + 1)
            return True
        if call_name == "source" and args:
            relative = string_or_identifier(argument_value(args[0]))
            if relative and "$" not in relative and "(" not in relative:
                target = path.parent / relative
                add_edge(
                    file_id,
                    _make_id(str(target)),
                    "imports_from",
                    node.start_point[0] + 1,
                    target_file=str(target),
                )
            return True
        if call_name in {"setClass", "setRefClass"} and args:
            name = string_or_identifier(argument_value(args[0]))
            if name:
                class_id = classes.get(name) or add_class(name, node, owner)
                add_class_members(class_id, arguments)
            return True
        if call_name == "setMethod" and len(args) >= 3:
            method_name = string_or_identifier(argument_value(args[0]))
            class_name = string_or_identifier(argument_value(args[1]))
            implementation = argument_value(args[-1])
            if method_name and class_name and implementation is not None:
                class_id = classes.get(class_name) or add_class(class_name, node, owner)
                if implementation.type == "function_definition":
                    declare_function(
                        method_name,
                        implementation,
                        implementation.child_by_field_name("body"),
                        class_id,
                        relation="method",
                    )
            return True
        if call_name == "setGeneric" and args:
            name = string_or_identifier(argument_value(args[0]))
            if name:
                declare_function(name, node, None, owner)
            return True
        return False

    def binding(node: Node | None) -> tuple[str, Node, Node | None] | None:
        if node is None or node.type != "binary_operator":
            return None
        lhs = node.child_by_field_name("lhs")
        rhs = node.child_by_field_name("rhs")
        operator = node.child_by_field_name("operator")
        if lhs is None or rhs is None or operator is None:
            return None
        op = _read_text(operator, source)
        if op in {"->", "->>"}:
            lhs, rhs = rhs, lhs
        elif op not in {"<-", "<<-", "="}:
            return None
        if lhs.type != "identifier":
            return None
        return _read_text(lhs, source), rhs, lhs

    def scan_declarations(node: Node, owner: str, *, top_level: bool) -> None:
        for child in node.named_children:
            bound = binding(child)
            if bound is not None:
                name, value, name_node = bound
                if value.type == "function_definition":
                    declare_function(name, value, value.child_by_field_name("body"), owner)
                    continue
                if value.type == "call":
                    constructor, arguments = call_parts(value)
                    if constructor in _CLASS_CONSTRUCTORS:
                        class_name = name
                        if arguments is not None:
                            args = [
                                item for item in arguments.named_children if item.type == "argument"
                            ]
                            if args:
                                class_name = string_or_identifier(argument_value(args[0])) or name
                        class_id = add_class(class_name, child, owner)
                        if arguments is not None:
                            add_class_members(class_id, arguments)
                        continue
                if top_level and name_node is not None:
                    nid = _make_id(owner, name)
                    line = name_node.start_point[0] + 1
                    add_node(nid, name, line, kind="variable")
                    add_edge(owner, nid, "contains", line)
                continue
            if child.type == "call" and process_call_declaration(child, owner):
                continue
            # tree-sitter-r associates a right-assignment after a single-expression
            # function body with that body. Recover the actual outer binding.
            if child.type == "function_definition":
                body = child.child_by_field_name("body")
                right = binding(body)
                operator = body.child_by_field_name("operator") if body is not None else None
                if (
                    right is not None
                    and operator is not None
                    and _read_text(operator, source) in {"->", "->>"}
                ):
                    name, value, _ = right
                    declare_function(name, child, value, owner)
                continue
            scan_declarations(child, owner, top_level=top_level)

    scan_declarations(root, file_id, top_level=True)

    def resolve_local(caller_id: str, name: str) -> str | None:
        scope: str | None = caller_id
        while scope is not None:
            target = definitions.get(scope, {}).get(name)
            if target is not None:
                return target
            scope = scope_parent.get(scope)
        return None

    def walk_calls(node: Node, caller_id: str) -> None:
        if node.type == "function_definition":
            return
        if node.type == "call":
            callee_node = node.child_by_field_name("function")
            if callee_node is not None and callee_node.type == "identifier":
                callee = _read_text(callee_node, source)
                target = resolve_local(caller_id, callee)
                line = node.start_point[0] + 1
                if target is not None:
                    add_edge(caller_id, target, "calls", line)
                elif callee not in _NON_PROJECT_CALLS:
                    raw_calls.append({
                        "caller_nid": caller_id,
                        "callee": callee,
                        "is_member_call": True,
                        "language": "r",
                        "source_file": source_file,
                        "source_location": f"L{line}",
                    })
            elif callee_node is not None and callee_node.type == "namespace_operator":
                package_node = callee_node.child_by_field_name("lhs")
                function_node = callee_node.child_by_field_name("rhs")
                if package_node is not None and function_node is not None:
                    package = _read_text(package_node, source)
                    function = _read_text(function_node, source)
                    line = node.start_point[0] + 1
                    package_id = _make_id("r", "package", package)
                    add_node(
                        package_id,
                        package,
                        line,
                        kind="package",
                        source_backed=False,
                    )
                    external_id = _make_id(package_id, "function", function)
                    add_node(
                        external_id,
                        f"{package}::{function}()",
                        line,
                        kind="external_function",
                        source_backed=False,
                        callable_node=True,
                    )
                    add_edge(caller_id, external_id, "calls", line)
        for child in node.named_children:
            walk_calls(child, caller_id)

    for body, caller_id in callable_bodies:
        walk_calls(body, caller_id)

    clean_edges = [
        edge for edge in edges
        if edge["source"] in seen_ids
        and (edge["target"] in seen_ids or edge["relation"] == "imports_from")
    ]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
