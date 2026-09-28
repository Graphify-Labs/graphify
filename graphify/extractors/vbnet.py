"""Structural extraction for Visual Basic .NET source files."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tree_sitter import Node

from graphify.extractors.base import _file_stem, _make_id, _read_text


_TYPE_BLOCKS = {
    "class_block": "class",
    "module_block": "module",
    "interface_block": "interface",
    "structure_block": "structure",
    "enum_block": "enum",
}


def resolve_vbnet_partial_calls(
    per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]
) -> None:
    """Resolve calls across files that declare the same partial VB type."""
    methods: dict[tuple[str, str, int], list[str]] = {}
    for node in all_nodes:
        metadata = node.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("language") != "vbnet":
            continue
        if metadata.get("kind") not in {"method", "constructor"}:
            continue
        owner = metadata.get("owner")
        name = metadata.get("name")
        accepted_arities = metadata.get("accepted_arities")
        if (
            isinstance(owner, str)
            and isinstance(name, str)
            and isinstance(accepted_arities, list)
        ):
            for arity in accepted_arities:
                if isinstance(arity, int):
                    methods.setdefault(
                        (owner.casefold(), name.casefold(), arity), []
                    ).append(node["id"])

    existing = {
        (edge.get("source"), edge.get("target"))
        for edge in all_edges
        if edge.get("relation") == "calls"
    }
    for result in per_file:
        for call in result.get("raw_calls", []):
            if call.get("language") != "vbnet" or not call.get("owner"):
                continue
            key = (
                str(call["owner"]).casefold(),
                str(call.get("callee", "")).casefold(),
                int(call.get("arity", -1)),
            )
            candidates = methods.get(key, [])
            caller = call.get("caller_nid")
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
                "context": "partial_type_call",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": call.get("source_file", ""),
                "source_location": call.get("source_location"),
                "weight": 1.0,
            })


def extract_vbnet(path: Path) -> dict:
    try:
        import tree_sitter_vb_dotnet
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-vb-dotnet not installed"}

    try:
        source = path.read_bytes()
        root = Parser(Language(tree_sitter_vb_dotnet.language())).parse(source).root_node
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": f"VB.NET grammar failed to load: {exc}"}

    source_file = str(path)
    stem = _file_stem(path)
    file_id = _make_id(source_file)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    raw_calls: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()
    types_by_name: dict[str, str] = {}
    methods: dict[tuple[str, str, int], list[str]] = {}
    events: dict[tuple[str, str], str] = {}
    bodies: list[tuple[Node, str, str, str]] = []
    pending_handles: list[tuple[str, str, str, Node]] = []

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
            details: dict[str, Any] = {"language": "vbnet", "kind": kind}
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
        return nid

    def add_edge(source_id: str, target_id: str, relation: str, node: Node) -> None:
        key = (source_id, target_id, relation)
        if not source_id or not target_id or source_id == target_id or key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({
            "source": source_id,
            "target": target_id,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": source_file,
            "source_location": f"L{node.start_point[0] + 1}",
            "weight": 1.0,
        })

    add_node(file_id, path.name, root, kind="file")

    for statement in (node for node in root.named_children if node.type == "imports_statement"):
        namespace_node = next(
            (child for child in statement.named_children if child.type == "namespace_name"),
            None,
        )
        if namespace_node is None:
            continue
        namespace = _read_text(namespace_node, source)
        target = add_node(
            _make_id("vbnet", "namespace", namespace.casefold()),
            namespace,
            namespace_node,
            kind="external_namespace",
            source_backed=False,
        )
        add_edge(file_id, target, "imports", statement)

    def type_reference(name: str, node: Node) -> str:
        short_name = name.split(".")[-1]
        target = types_by_name.get(short_name.casefold())
        if target is not None:
            return target
        return add_node(
            _make_id("vbnet", "type", name.casefold()),
            short_name,
            node,
            kind="external_type",
            source_backed=False,
        )

    def add_data_member(type_id: str, member: Node, name: str, kind: str) -> str:
        member_id = add_node(
            _make_id(type_id, kind, name.casefold(), str(member.start_point[0])),
            name,
            member,
            kind=kind,
        )
        add_edge(type_id, member_id, "contains", member)
        return member_id

    def process_type(block: Node, parent_id: str, namespace: str) -> None:
        kind = _TYPE_BLOCKS[block.type]
        name_node = block.child_by_field_name("name")
        if name_node is None:
            return
        name = _read_text(name_node, source)
        full_name = f"{namespace}.{name}" if namespace else name
        owner_key = full_name.casefold()
        type_id = add_node(
            _make_id(stem, "type", owner_key),
            name,
            block,
            kind=kind,
            callable_node=kind in {"class", "structure"},
            metadata={"name": name, "full_name": full_name},
        )
        add_edge(parent_id, type_id, "contains", block)
        types_by_name[name.casefold()] = type_id

        for clause in block.named_children:
            if clause.type not in {"inherits_clause", "implements_clause"}:
                continue
            relation = "inherits" if clause.type == "inherits_clause" else "implements"
            for type_node in (child for child in clause.named_children if child.type == "type"):
                referenced = _read_text(type_node, source)
                add_edge(type_id, type_reference(referenced, type_node), relation, clause)

        for member in block.named_children:
            if member.type == "enum_member":
                member_name = member.child_by_field_name("name")
                if member_name is not None:
                    add_data_member(
                        type_id, member, _read_text(member_name, source), "enum_member"
                    )
                continue
            if member.type == "field_declaration":
                for declarator in (
                    child for child in member.named_children
                    if child.type == "variable_declarator"
                ):
                    member_name = declarator.child_by_field_name("name")
                    if member_name is not None:
                        add_data_member(
                            type_id,
                            declarator,
                            _read_text(member_name, source),
                            "field",
                        )
                continue
            if member.type in {"property_declaration", "event_declaration"}:
                member_name = member.child_by_field_name("name")
                if member_name is not None:
                    data_name = _read_text(member_name, source)
                    member_id = add_data_member(
                        type_id,
                        member,
                        data_name,
                        "property" if member.type == "property_declaration" else "event",
                    )
                    if member.type == "event_declaration":
                        events[(owner_key, data_name.casefold())] = member_id
                continue
            if member.type not in {"method_declaration", "constructor_declaration"}:
                continue

            if member.type == "constructor_declaration":
                method_name = "New"
                method_kind = "constructor"
            else:
                method_name_node = member.child_by_field_name("name")
                if method_name_node is None:
                    continue
                method_name = _read_text(method_name_node, source)
                method_kind = "method"
            parameters = member.child_by_field_name("parameters")
            parameter_nodes = (
                [child for child in parameters.named_children if child.type == "parameter"]
                if parameters is not None
                else []
            )
            arity = len(parameter_nodes)
            required_arity = sum(
                not _read_text(parameter, source).lstrip().casefold().startswith("optional ")
                for parameter in parameter_nodes
            )
            accepted_arities = list(range(required_arity, arity + 1))
            method_id = add_node(
                _make_id(
                    type_id,
                    method_kind,
                    method_name.casefold(),
                    str(arity),
                    str(member.start_point[0]),
                ),
                f"{method_name}()",
                member,
                kind=method_kind,
                callable_node=True,
                metadata={
                    "owner": owner_key,
                    "name": method_name,
                    "arity": arity,
                    "accepted_arities": accepted_arities,
                },
            )
            add_edge(type_id, method_id, "method", member)
            for accepted_arity in accepted_arities:
                methods.setdefault(
                    (owner_key, method_name.casefold(), accepted_arity), []
                ).append(method_id)
            for clause in (
                child for child in member.named_children if child.type == "handles_clause"
            ):
                for handled in (
                    child for child in clause.named_children if child.type == "namespace_name"
                ):
                    pending_handles.append((
                        method_id,
                        owner_key,
                        _read_text(handled, source),
                        handled,
                    ))
            bodies.append((member, method_id, owner_key, name))

    def scan(node: Node, parent_id: str, namespace: str) -> None:
        if node.type == "imports_statement":
            return
        if node.type == "namespace_block":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            local_name = _read_text(name_node, source)
            full_namespace = f"{namespace}.{local_name}" if namespace else local_name
            namespace_id = add_node(
                _make_id(stem, "namespace", full_namespace.casefold()),
                local_name,
                node,
                kind="namespace",
                metadata={"full_name": full_namespace},
            )
            add_edge(parent_id, namespace_id, "contains", node)
            for child in node.named_children:
                if child != name_node:
                    scan(child, namespace_id, full_namespace)
            return
        if node.type in _TYPE_BLOCKS:
            process_type(node, parent_id, namespace)
            # Nested type declarations are the only child containers that still
            # need recursion after processing this type's own members.
            for child in node.named_children:
                if child.type == "type_declaration":
                    scan(child, parent_id, namespace)
            return
        for child in node.named_children:
            scan(child, parent_id, namespace)

    scan(root, file_id, "")

    for method_id, owner_key, written, handled_node in pending_handles:
        event_name = written.split(".")[-1]
        target = events.get((owner_key, event_name.casefold()))
        if target is None:
            target = add_node(
                _make_id("vbnet", "event", written.casefold()),
                written,
                handled_node,
                kind="external_event",
                source_backed=False,
            )
        add_edge(method_id, target, "handles", handled_node)

    for body, caller_id, owner_key, type_name in bodies:
        stack = [body]
        while stack:
            node = stack.pop()
            if node != body and node.type in {
                "method_declaration", "constructor_declaration", "property_declaration"
            }:
                continue
            if node.type == "invocation":
                target_node = node.child_by_field_name("target")
                arguments = node.child_by_field_name("arguments")
                if target_node is not None:
                    written = _read_text(target_node, source)
                    parts = written.split(".")
                    receiver = ".".join(parts[:-1]).casefold()
                    callee = parts[-1]
                    known_receiver = (
                        not receiver
                        or receiver in {"me", "myclass", type_name.casefold()}
                    )
                    if known_receiver:
                        arity = len(arguments.named_children) if arguments is not None else 0
                        candidates = methods.get(
                            (owner_key, callee.casefold(), arity), []
                        )
                        if len(candidates) == 1:
                            add_edge(caller_id, candidates[0], "calls", node)
                        else:
                            raw_calls.append({
                                "caller_nid": caller_id,
                                "callee": callee,
                                "arity": arity,
                                "owner": owner_key,
                                "is_member_call": True,
                                "language": "vbnet",
                                "source_file": source_file,
                                "source_location": f"L{node.start_point[0] + 1}",
                            })
            stack.extend(reversed(node.named_children))

    clean_edges = [
        edge for edge in edges
        if edge["source"] in seen_ids and edge["target"] in seen_ids
    ]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
