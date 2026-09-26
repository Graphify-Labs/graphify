"""Structural extraction for Solidity source files."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tree_sitter import Node

from graphify.extractors.base import _file_stem, _make_id, _read_text


_TYPE_DECLARATIONS = {
    "contract_declaration": "contract",
    "interface_declaration": "interface",
    "library_declaration": "library",
}


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def resolve_solidity_type_references(
    _per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]
) -> None:
    """Bind inheritance and using references to types in the file or its imports."""
    node_by_id = {node.get("id"): node for node in all_nodes}
    file_id_by_source = {
        str(node["source_file"]): node["id"]
        for node in all_nodes
        if node.get("source_file")
        and node.get("label") == Path(str(node["source_file"])).name
    }
    source_by_file_id = {nid: source for source, nid in file_id_by_source.items()}
    imported_sources: dict[str, set[str]] = {}
    for edge in all_edges:
        if edge.get("relation") != "imports_from":
            continue
        source_file = source_by_file_id.get(edge.get("source"))
        target_file = source_by_file_id.get(edge.get("target"))
        if source_file and target_file:
            imported_sources.setdefault(source_file, set()).add(target_file)

    types: dict[tuple[str, str], list[str]] = {}
    for node in all_nodes:
        metadata = node.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("kind") not in _TYPE_DECLARATIONS.values():
            continue
        source_file = node.get("source_file")
        if source_file:
            types.setdefault((str(source_file), str(node.get("label", ""))), []).append(node["id"])

    for edge in all_edges:
        context = edge.get("context")
        if not isinstance(context, str) or not context.startswith("solidity_type:"):
            continue
        source_node = node_by_id.get(edge.get("source"))
        if not source_node or not source_node.get("source_file"):
            continue
        source_file = str(source_node["source_file"])
        name = context.split(":", 1)[1]
        candidates = list(types.get((source_file, name), []))
        for imported in imported_sources.get(source_file, set()):
            candidates.extend(types.get((imported, name), []))
        if len(candidates) == 1:
            edge["target"] = candidates[0]


def extract_solidity(path: Path) -> dict:
    try:
        import tree_sitter_solidity
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-solidity not installed"}

    try:
        source = path.read_bytes()
        root = Parser(Language(tree_sitter_solidity.language())).parse(source).root_node
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": f"Solidity grammar failed to load: {exc}"}

    source_file = str(path)
    stem = _file_stem(path)
    file_id = _make_id(source_file)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    raw_calls: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    def add_node(
        nid: str,
        label: str,
        node: Node,
        *,
        kind: str,
        source_backed: bool = True,
        callable_node: bool = False,
    ) -> str:
        if nid not in seen_ids:
            seen_ids.add(nid)
            item: dict[str, Any] = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_location": f"L{node.start_point[0] + 1}",
                "metadata": {"language": "solidity", "kind": kind},
            }
            if source_backed:
                item["source_file"] = source_file
            if callable_node:
                item["_callable"] = True
            nodes.append(item)
        return nid

    def add_edge(
        source_id: str,
        target_id: str,
        relation: str,
        node: Node,
        *,
        context: str | None = None,
        target_file: str | None = None,
    ) -> None:
        key = (source_id, target_id, relation)
        if not source_id or not target_id or source_id == target_id or key in seen_edges:
            return
        seen_edges.add(key)
        item: dict[str, Any] = {
            "source": source_id,
            "target": target_id,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": source_file,
            "source_location": f"L{node.start_point[0] + 1}",
            "weight": 1.0,
        }
        if context:
            item["context"] = context
        if target_file:
            item["target_file"] = target_file
        edges.append(item)

    add_node(file_id, path.name, root, kind="file")

    def type_stub(name: str, node: Node) -> str:
        name = name.split(".")[-1]
        nid = _make_id("solidity", "type", name)
        add_node(nid, name, node, kind="external_type", source_backed=False)
        return nid

    for declaration in root.named_children:
        if declaration.type != "import_directive":
            continue
        source_node = declaration.child_by_field_name("source")
        if source_node is None:
            continue
        relative = _unquote(_read_text(source_node, source))
        if not relative or relative.startswith(("http:", "https:")):
            continue
        target = path.parent / relative
        add_edge(
            file_id,
            _make_id(str(target)),
            "imports_from",
            declaration,
            target_file=str(target),
        )

    for declaration in root.named_children:
        type_kind = _TYPE_DECLARATIONS.get(declaration.type)
        if type_kind is None:
            continue
        name_node = declaration.child_by_field_name("name")
        body = declaration.child_by_field_name("body")
        if name_node is None or body is None:
            continue
        type_name = _read_text(name_node, source)
        type_id = add_node(
            _make_id(stem, type_kind, type_name),
            type_name,
            declaration,
            kind=type_kind,
            callable_node=type_kind == "contract",
        )
        add_edge(file_id, type_id, "contains", declaration)

        for child in declaration.named_children:
            if child.type != "inheritance_specifier":
                continue
            ancestor = child.child_by_field_name("ancestor")
            if ancestor is None:
                continue
            base_name = _read_text(ancestor, source).split(".")[-1]
            add_edge(
                type_id,
                type_stub(base_name, child),
                "inherits",
                child,
                context=f"solidity_type:{base_name}",
            )

        functions: dict[tuple[str, int], list[str]] = {}
        modifiers: dict[str, str] = {}
        reference_targets: dict[tuple[str, int], str] = {}
        bodies: list[tuple[Node, str]] = []
        pending_modifiers: list[tuple[str, str, Node]] = []

        def add_member(
            member: Node,
            name: str,
            label: str,
            kind: str,
            *,
            relation: str = "contains",
            signature: str = "",
            callable_node: bool = False,
        ) -> str:
            # Callables carry an arity:types signature (distinguishes overloads).
            # Non-callable members (struct/enum/event/error/state-var) have no
            # signature; discriminate on the name — which is unique per kind
            # within a contract scope — rather than the line number, so a node's
            # id stays stable when the member moves (avoids incremental id churn).
            member_id = _make_id(type_id, kind, name, signature or name)
            add_node(
                member_id,
                label,
                member,
                kind=kind,
                callable_node=callable_node,
            )
            add_edge(type_id, member_id, relation, member)
            return member_id

        for member in body.named_children:
            kind = member.type
            if kind == "using_directive":
                alias = next(
                    (
                        _read_text(child, source)
                        for child in member.named_children
                        if child.type in {"type_alias", "identifier", "user_defined_type"}
                    ),
                    "",
                )
                if alias:
                    name = alias.split(".")[-1]
                    add_edge(
                        type_id,
                        type_stub(name, member),
                        "uses",
                        member,
                        context=f"solidity_type:{name}",
                    )
                continue

            if kind == "struct_declaration":
                member_name_node = member.child_by_field_name("name")
                struct_body = member.child_by_field_name("body")
                if member_name_node is None:
                    continue
                name = _read_text(member_name_node, source)
                struct_id = add_member(member, name, name, "struct")
                if struct_body is not None:
                    for field in struct_body.named_children:
                        if field.type != "struct_member":
                            continue
                        field_name_node = field.child_by_field_name("name")
                        if field_name_node is None:
                            continue
                        field_name = _read_text(field_name_node, source)
                        field_id = _make_id(struct_id, "field", field_name)
                        add_node(field_id, field_name, field, kind="field")
                        add_edge(struct_id, field_id, "contains", field)
                continue

            if kind == "enum_declaration":
                member_name_node = member.child_by_field_name("name")
                enum_body = member.child_by_field_name("body")
                if member_name_node is None:
                    continue
                name = _read_text(member_name_node, source)
                enum_id = add_member(member, name, name, "enum")
                if enum_body is not None:
                    for value in enum_body.named_children:
                        if value.type != "enum_value":
                            continue
                        value_name = _read_text(value, source)
                        value_id = _make_id(enum_id, value_name)
                        add_node(value_id, value_name, value, kind="enum_value")
                        add_edge(enum_id, value_id, "contains", value)
                continue

            simple_kinds = {
                "event_definition": "event",
                "error_declaration": "error",
                "state_variable_declaration": "state_variable",
            }
            if kind in simple_kinds:
                member_name_node = member.child_by_field_name("name")
                if member_name_node is None:
                    continue
                name = _read_text(member_name_node, source)
                member_id = add_member(member, name, name, simple_kinds[kind])
                arity = sum(child.type in {"event_parameter", "parameter"} for child in member.named_children)
                reference_targets[(name, arity)] = member_id
                continue

            if kind not in {
                "function_definition", "constructor_definition", "modifier_definition",
                "fallback_receive_definition",
            }:
                continue

            name_node = member.child_by_field_name("name")
            if kind == "constructor_definition":
                name = "constructor"
                callable_kind = "constructor"
            elif kind == "fallback_receive_definition":
                text = _read_text(member, source).lstrip()
                name = "receive" if text.startswith("receive") else "fallback"
                callable_kind = name
            else:
                if name_node is None:
                    continue
                name = _read_text(name_node, source)
                callable_kind = "modifier" if kind == "modifier_definition" else "function"

            parameters = [
                child for child in member.named_children
                if child.type in {"parameter", "fallback_receive_parameter"}
            ]
            signature = ",".join(
                _read_text(child.child_by_field_name("type"), source)
                for child in parameters
                if child.child_by_field_name("type") is not None
            )
            arity = len(parameters)
            member_id = add_member(
                member,
                name,
                f"{name}()",
                callable_kind,
                relation="method",
                signature=f"{arity}:{signature}",
                callable_node=True,
            )
            if callable_kind == "modifier":
                modifiers[name] = member_id
            else:
                functions.setdefault((name, arity), []).append(member_id)
            member_body = member.child_by_field_name("body")
            if member_body is not None:
                bodies.append((member_body, member_id))
            if callable_kind == "function":
                for child in member.named_children:
                    if child.type != "modifier_invocation":
                        continue
                    modifier_name = next(
                        (
                            _read_text(item, source)
                            for item in child.named_children
                            if item.type == "identifier"
                        ),
                        "",
                    )
                    if modifier_name:
                        pending_modifiers.append((member_id, modifier_name, child))

        for caller_id, modifier_name, modifier_node in pending_modifiers:
            target = modifiers.get(modifier_name)
            if target:
                add_edge(caller_id, target, "uses", modifier_node)

        for function_body, caller_id in bodies:
            stack = [function_body]
            while stack:
                node = stack.pop()
                if node.type == "call_expression":
                    callee_node = node.child_by_field_name("function")
                    if callee_node is not None:
                        written = _read_text(callee_node, source)
                        callee = written.split(".")[-1]
                        arity = sum(child.type == "call_argument" for child in node.named_children)
                        candidates: list[str] = []
                        if "." not in written or written.startswith("this."):
                            candidates = functions.get((callee, arity), [])
                        if len(candidates) == 1:
                            add_edge(caller_id, candidates[0], "calls", node)
                        else:
                            referenced = reference_targets.get((callee, arity))
                            if referenced is not None and "." not in written:
                                add_edge(caller_id, referenced, "references", node)
                            elif callee and "." in written:
                                raw_calls.append({
                                    "caller_nid": caller_id,
                                    "callee": callee,
                                    "is_member_call": True,
                                    "language": "solidity",
                                    "source_file": source_file,
                                    "source_location": f"L{node.start_point[0] + 1}",
                                })
                stack.extend(reversed(node.named_children))

    clean_edges = [
        edge for edge in edges
        if edge["source"] in seen_ids
        and (edge["target"] in seen_ids or edge["relation"] == "imports_from")
    ]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
