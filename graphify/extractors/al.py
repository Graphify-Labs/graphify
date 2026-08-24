"""Microsoft Dynamics 365 Business Central AL extraction."""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id


_AL_IDENTIFIER = r'(?P<name>"(?:[^"]|"")+"|[A-Za-z_][\w.]*)'
_AL_OBJECT_RE = re.compile(
    rf"(?im)^\s*(?P<kind>codeunit|tableextension|table|pageextension|page|"
    rf"enumextension|enum|interface|reportextension|report|query|xmlport)\s+"
    rf"(?:(?P<object_id>\d+)\s+)?{_AL_IDENTIFIER}\s*"
    rf"(?:extends\s+(?P<base>\"(?:[^\"]|\"\")+\"|[A-Za-z_][\w.]*))?"
    rf"(?:implements\s+(?P<interfaces>[^{{]+))?\s*{{"
)
_AL_CALLABLE_RE = re.compile(
    rf"(?im)^\s*(?:(?P<visibility>local|internal|protected|public)\s+)?"
    rf"(?P<callable_kind>procedure|trigger)\s+{_AL_IDENTIFIER}\s*"
    rf"\((?P<parameters>[^)]*)\)\s*(?::\s*(?P<return_type>[^;\r\n]+))?"
)
_AL_NAMESPACE_RE = re.compile(r"(?im)^\s*namespace\s+([A-Za-z_][\w.]*)\s*;")
_AL_OBJECT_TYPES = {
    "codeunit_declaration": "codeunit",
    "table_declaration": "table",
    "tableextension_declaration": "tableextension",
    "page_declaration": "page",
    "pageextension_declaration": "pageextension",
    "enum_declaration": "enum",
    "enumextension_declaration": "enumextension",
    "interface_declaration": "interface",
    "report_declaration": "report",
    "reportextension_declaration": "reportextension",
    "query_declaration": "query",
    "xmlport_declaration": "xmlport",
    "permissionset_declaration": "permissionset",
}
_AL_CALLABLE_TYPES = {
    "procedure": "procedure",
    "interface_procedure": "procedure",
    "preproc_split_procedure": "procedure",
    "trigger_declaration": "trigger",
    "event_declaration": "event",
}


def _decode_al_identifier(value: str | None) -> str:
    """Return an AL identifier without delimiters while preserving its spelling."""
    if not value:
        return ""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1].replace('""', '"')
    return value


def _al_lookup_key(value: str) -> str:
    return _decode_al_identifier(value).casefold()


def _mask_al_comments_and_strings(source: str) -> str:
    """Mask comments and string literals without changing offsets or newlines."""
    chars = list(source)
    index = 0
    state = "code"
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if char == "/" and following == "/":
                chars[index] = chars[index + 1] = " "
                index += 2
                state = "line_comment"
                continue
            if char == "/" and following == "*":
                chars[index] = chars[index + 1] = " "
                index += 2
                state = "block_comment"
                continue
            if char == "'":
                chars[index] = " "
                index += 1
                state = "string"
                continue
        elif state == "line_comment":
            if char == "\n":
                state = "code"
            else:
                chars[index] = " "
        elif state == "block_comment":
            if char == "*" and following == "/":
                chars[index] = chars[index + 1] = " "
                index += 2
                state = "code"
                continue
            if char != "\n":
                chars[index] = " "
        else:
            chars[index] = " " if char != "\n" else "\n"
            if char == "'" and following == "'":
                chars[index + 1] = " "
                index += 2
                continue
            if char == "'":
                state = "code"
        index += 1
    return "".join(chars)


def _matching_brace(source: str, opening: int) -> int:
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return len(source)


def _line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def _walk_al(node):
    yield node
    for child in node.named_children:
        yield from _walk_al(child)


def _node_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _field_text(node, field: str, source: bytes) -> str:
    child = node.child_by_field_name(field)
    return _node_text(child, source) if child else ""


def _first_descendant(node, types: set[str]):
    return next((child for child in _walk_al(node) if child.type in types), None)


def _attribute_metadata(node, source: bytes) -> list[dict]:
    attributes: list[dict] = []
    sibling = node.prev_named_sibling
    while sibling is not None and sibling.type == "attribute_item":
        content = sibling.child_by_field_name("attribute")
        if content is not None:
            name = _field_text(content, "name", source)
            arguments = content.child_by_field_name("arguments")
            argument_list = _first_descendant(arguments, {"attribute_argument_list"}) if arguments else None
            attributes.append({
                "name": _decode_al_identifier(name),
                "arguments": [
                    _node_text(child, source).strip()
                    for child in (argument_list.named_children if argument_list else [])
                ],
            })
        sibling = sibling.prev_named_sibling
    attributes.reverse()
    return attributes


def _parameter_metadata(node, source: bytes) -> list[dict]:
    parameters = node.child_by_field_name("parameters")
    if parameters is None:
        return []
    result: list[dict] = []
    for parameter in parameters.named_children:
        if parameter.type != "parameter":
            continue
        type_node = parameter.child_by_field_name("type")
        result.append({
            "name": _decode_al_identifier(_field_text(parameter, "name", source)),
            "type": _node_text(type_node, source).strip() if type_node else "",
            "modifier": _field_text(parameter, "modifier", source).strip() or None,
        })
    return result


def _type_reference(type_node, source: bytes) -> tuple[str, str] | None:
    reference_node = _first_descendant(type_node, {"object_reference_type", "record_type"})
    if reference_node is None:
        return None
    reference = _decode_al_identifier(_field_text(reference_node, "reference", source))
    if not reference:
        return None
    object_type = _field_text(reference_node, "object_type", source).casefold()
    if not object_type:
        object_type = "record" if reference_node.type == "record_type" else "object"
    return object_type, reference


def _member_scope_seed(member_node, source: bytes) -> str | None:
    current = member_node.parent
    while current is not None and current.type not in _AL_OBJECT_TYPES:
        if current.type in {"field_declaration", "page_field", "action_declaration"}:
            name = _decode_al_identifier(_field_text(current, "name", source))
            identifier = _field_text(current, "id", source)
            if name or identifier:
                return f"{current.type}:{identifier}:{name}"
        current = current.parent
    return None


def _extract_al_tree_sitter(path: Path, source: str, tree) -> dict:
    source_bytes = source.encode("utf-8")
    str_path = str(path)
    stem = _file_stem(path)
    root = tree.root_node
    namespace_node = next((node for node in root.named_children if node.type == "namespace_declaration"), None)
    namespace = _field_text(namespace_node, "name", source_bytes) if namespace_node else ""
    usings = [
        _field_text(node, "namespace", source_bytes)
        for node in root.named_children
        if node.type == "using_statement"
    ]
    file_nid = _make_id(str_path)
    nodes: list[dict] = [{
        "id": file_nid,
        "label": path.name,
        "file_type": "code",
        "source_file": str_path,
        "source_location": "L1",
        "language": "al",
        "namespace": namespace or None,
        "extraction_tier": "tree_sitter",
    }]
    edges: list[dict] = []
    seen_ids = {file_nid}
    facts: dict[str, object] = {
        "namespace": namespace,
        "usings": usings,
        "objects": [],
        "members": [],
        "references": [],
        "calls": [],
        "event_subscribers": [],
        "event_publishers": [],
        "enum_mappings": [],
        "test_handlers": [],
    }

    def add_node(node: dict) -> None:
        if node["id"] not in seen_ids:
            seen_ids.add(node["id"])
            nodes.append(node)

    def add_edge(parent: str, child: str, relation: str, line: int, context: str | None = None) -> None:
        edge = {
            "source": parent,
            "target": child,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    for object_node in (node for node in _walk_al(root) if node.type in _AL_OBJECT_TYPES):
        kind = _AL_OBJECT_TYPES[object_node.type]
        name = _decode_al_identifier(_field_text(object_node, "object_name", source_bytes))
        if not name:
            continue
        qualified_name = f"{namespace}.{name}" if namespace else name
        object_id = _field_text(object_node, "object_id", source_bytes) or None
        line = object_node.start_point.row + 1
        object_nid = _make_id(stem, kind, qualified_name)
        add_node({
            "id": object_nid,
            "label": name,
            "file_type": "code",
            "source_file": str_path,
            "source_location": f"L{line}",
            "language": "al",
            "object_kind": kind,
            "object_id": object_id,
            "qualified_name": qualified_name,
            "namespace": namespace or None,
            "lookup_key": _al_lookup_key(qualified_name),
            "extraction_tier": "tree_sitter",
        })
        add_edge(file_nid, object_nid, "contains", line)

        base = _decode_al_identifier(_field_text(object_node, "base_object", source_bytes))
        interfaces = [
            _decode_al_identifier(_field_text(clause, "interface", source_bytes))
            for clause in object_node.named_children
            if clause.type == "implements_clause"
        ]
        object_fact = {
            "nid": object_nid,
            "name": name,
            "qualified_name": qualified_name,
            "lookup_key": _al_lookup_key(qualified_name),
            "kind": kind,
            "object_id": object_id,
            "namespace": namespace,
            "base": base or None,
            "interfaces": [interface for interface in interfaces if interface],
            "line": line,
            "source_file": str_path,
        }
        facts["objects"].append(object_fact)

        variable_types: dict[str, tuple[str, str]] = {}
        for declaration in (node for node in _walk_al(object_node) if node.type == "variable_declaration"):
            ancestor = declaration.parent
            while ancestor is not None and ancestor is not object_node:
                if ancestor.type in _AL_CALLABLE_TYPES:
                    break
                ancestor = ancestor.parent
            if ancestor is not object_node:
                continue
            variable_name = _decode_al_identifier(_field_text(declaration, "name", source_bytes))
            type_node = declaration.child_by_field_name("type")
            reference = _type_reference(type_node, source_bytes) if type_node else None
            if variable_name and reference:
                variable_types[_al_lookup_key(variable_name)] = reference
                facts["references"].append({
                    "source": object_nid,
                    "name": reference[1],
                    "kind": reference[0],
                    "line": declaration.start_point.row + 1,
                })

        member_nodes = [
            node for node in _walk_al(object_node)
            if node.type in _AL_CALLABLE_TYPES or node.type in {"field_declaration", "enum_value_declaration"}
        ]
        member_name_counts: dict[tuple[str, str], int] = {}
        for candidate in member_nodes:
            if candidate.type not in _AL_CALLABLE_TYPES:
                continue
            candidate_name = _decode_al_identifier(_field_text(candidate, "name", source_bytes))
            key = (_AL_CALLABLE_TYPES[candidate.type], _al_lookup_key(candidate_name))
            member_name_counts[key] = member_name_counts.get(key, 0) + 1
        for member_node in member_nodes:
            if member_node.type in _AL_CALLABLE_TYPES:
                member_kind = _AL_CALLABLE_TYPES[member_node.type]
                name_field = "name"
                label_suffix = "()"
            elif member_node.type == "field_declaration":
                member_kind = "field"
                name_field = "name"
                label_suffix = ""
            else:
                member_kind = "enum_value"
                name_field = "value_name"
                label_suffix = ""
            member_name = _decode_al_identifier(_field_text(member_node, name_field, source_bytes))
            if not member_name:
                continue
            member_line = member_node.start_point.row + 1
            attributes = _attribute_metadata(member_node, source_bytes)
            parameters = _parameter_metadata(member_node, source_bytes)
            signature = ",".join(
                f"{parameter.get('modifier') or ''}:{parameter.get('type') or ''}"
                for parameter in parameters
            )
            scope_seed = _member_scope_seed(member_node, source_bytes)
            identity_seeds = [scope_seed] if scope_seed else []
            if member_name_counts.get((member_kind, _al_lookup_key(member_name)), 0) > 1:
                identity_seeds.append(f"signature:{signature}")
            member_nid = _make_id(object_nid, member_kind, *identity_seeds, member_name)
            return_type_node = member_node.child_by_field_name("return_type")
            if return_type_node is None and member_node.type == "interface_procedure":
                suffix = _first_descendant(member_node, {"interface_procedure_suffix"})
                return_type_node = suffix.child_by_field_name("return_type") if suffix else None
            modifier = member_node.child_by_field_name("modifier")
            data_type_node = member_node.child_by_field_name("type")
            metadata = {
                "id": member_nid,
                "label": f"{member_name}{label_suffix}",
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{member_line}",
                "language": "al",
                "member_kind": member_kind,
                "parent_object": object_nid,
                "lookup_key": _al_lookup_key(member_name),
                "extraction_tier": "tree_sitter",
            }
            if member_kind in _AL_CALLABLE_TYPES.values():
                metadata.update({
                    "visibility": _node_text(modifier, source_bytes).strip() if modifier else None,
                    "parameters": parameters,
                    "return_type": _node_text(return_type_node, source_bytes).strip() if return_type_node else None,
                    "attributes": attributes,
                    "signature": signature,
                    "_callable": True,
                })
            else:
                metadata.update({
                    "member_id": _field_text(member_node, "id", source_bytes)
                    or _field_text(member_node, "value_id", source_bytes) or None,
                    "data_type": _node_text(data_type_node, source_bytes).strip() if data_type_node else None,
                })
            add_node(metadata)
            add_edge(object_nid, member_nid, "contains", member_line)
            facts["members"].append({
                "nid": member_nid,
                "parent": object_nid,
                "name": member_name,
                "lookup_key": _al_lookup_key(member_name),
                "kind": member_kind,
                "signature": signature,
                "parameter_count": len(parameters),
                "line": member_line,
            })

            if member_kind in _AL_CALLABLE_TYPES.values():
                callable_types = dict(variable_types)
                for declaration in (
                    node for node in _walk_al(member_node) if node.type == "variable_declaration"
                ):
                    variable_name = _decode_al_identifier(_field_text(declaration, "name", source_bytes))
                    type_node = declaration.child_by_field_name("type")
                    reference = _type_reference(type_node, source_bytes) if type_node else None
                    if variable_name and reference:
                        callable_types[_al_lookup_key(variable_name)] = reference
                        facts["references"].append({
                            "source": member_nid,
                            "name": reference[1],
                            "kind": reference[0],
                            "line": declaration.start_point.row + 1,
                        })
                for parameter, parameter_data in zip(
                    (node for node in _walk_al(member_node) if node.type == "parameter"),
                    parameters,
                ):
                    type_node = parameter.child_by_field_name("type")
                    reference = _type_reference(type_node, source_bytes) if type_node else None
                    if parameter_data["name"] and reference:
                        callable_types[_al_lookup_key(parameter_data["name"])] = reference
                        facts["references"].append({
                            "source": member_nid,
                            "name": reference[1],
                            "kind": reference[0],
                            "line": parameter.start_point.row + 1,
                        })
                for call in (node for node in _walk_al(member_node) if node.type == "call_expression"):
                    function = call.child_by_field_name("function")
                    if function is None:
                        continue
                    receiver = ""
                    call_name = ""
                    if function.type == "member_expression":
                        receiver = _decode_al_identifier(_field_text(function, "object", source_bytes))
                        call_name = _decode_al_identifier(_field_text(function, "member", source_bytes))
                    else:
                        call_name = _decode_al_identifier(_node_text(function, source_bytes))
                    receiver_type = callable_types.get(_al_lookup_key(receiver)) if receiver else None
                    facts["calls"].append({
                        "source": member_nid,
                        "name": call_name,
                        "receiver": receiver or None,
                        "receiver_kind": receiver_type[0] if receiver_type else None,
                        "receiver_type": receiver_type[1] if receiver_type else None,
                        "argument_count": len(
                            call.child_by_field_name("arguments").named_children
                        ) if call.child_by_field_name("arguments") else 0,
                        "line": call.start_point.row + 1,
                    })

                attribute_names = {_al_lookup_key(item["name"]) for item in attributes}
                if "eventsubscriber" in attribute_names:
                    event_attribute = next(
                        item for item in attributes if _al_lookup_key(item["name"]) == "eventsubscriber"
                    )
                    facts["event_subscribers"].append({
                        "source": member_nid,
                        "arguments": event_attribute["arguments"],
                        "line": member_line,
                    })
                if attribute_names & {"integrationevent", "businessevent"}:
                    facts["event_publishers"].append({
                        "nid": member_nid,
                        "object": object_nid,
                        "name": member_name,
                        "lookup_key": _al_lookup_key(member_name),
                    })
                if "handlerfunctions" in attribute_names:
                    handler_attribute = next(
                        item for item in attributes if _al_lookup_key(item["name"]) == "handlerfunctions"
                    )
                    facts["test_handlers"].append({
                        "source": member_nid,
                        "arguments": handler_attribute["arguments"],
                        "line": member_line,
                    })

            if member_kind == "enum_value":
                for prop in (node for node in _walk_al(member_node) if node.type == "property"):
                    property_name = _node_text(prop.child_by_field_name("name"), source_bytes)
                    if _al_lookup_key(property_name) != "implementation":
                        continue
                    comparison = _first_descendant(prop, {"comparison_expression"})
                    if comparison is not None:
                        facts["enum_mappings"].append({
                            "source": member_nid,
                            "interface": _decode_al_identifier(_field_text(comparison, "left", source_bytes)),
                            "implementation": _decode_al_identifier(_field_text(comparison, "right", source_bytes)),
                            "line": prop.start_point.row + 1,
                        })

    syntax_errors = [
        {"line": node.start_point.row + 1, "type": node.type}
        for node in _walk_al(root)
        if node.type == "ERROR" or node.is_missing
    ]
    result = {"nodes": nodes, "edges": edges, "al_facts": facts}
    if syntax_errors:
        result["syntax_errors"] = syntax_errors
    return result


def _extract_al_fallback(path: Path, source: str) -> dict:
    str_path = str(path)
    stem = _file_stem(path)
    masked = _mask_al_comments_and_strings(source)
    namespace_match = _AL_NAMESPACE_RE.search(masked)
    namespace = namespace_match.group(1) if namespace_match else ""
    file_nid = _make_id(str_path)
    nodes: list[dict] = [{
        "id": file_nid,
        "label": path.name,
        "file_type": "code",
        "source_file": str_path,
        "source_location": "L1",
        "language": "al",
        "extraction_tier": "fallback",
    }]
    edges: list[dict] = []
    seen_ids = {file_nid}

    def add_node(node: dict) -> None:
        if node["id"] not in seen_ids:
            seen_ids.add(node["id"])
            nodes.append(node)

    def add_contains(parent: str, child: str, line: int) -> None:
        edges.append({
            "source": parent,
            "target": child,
            "relation": "contains",
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        })

    for match in _AL_OBJECT_RE.finditer(masked):
        kind = match.group("kind").casefold()
        name = _decode_al_identifier(match.group("name"))
        qualified_name = f"{namespace}.{name}" if namespace else name
        object_id = match.group("object_id")
        line = _line_number(masked, match.start())
        object_nid = _make_id(stem, kind, qualified_name)
        add_node({
            "id": object_nid,
            "label": name,
            "file_type": "code",
            "source_file": str_path,
            "source_location": f"L{line}",
            "language": "al",
            "object_kind": kind,
            "object_id": object_id,
            "qualified_name": qualified_name,
            "namespace": namespace or None,
            "lookup_key": _al_lookup_key(qualified_name),
            "extraction_tier": "fallback",
        })
        add_contains(file_nid, object_nid, line)

        opening = masked.find("{", match.start(), match.end())
        closing = _matching_brace(masked, opening)
        body = masked[opening + 1:closing]
        body_offset = opening + 1
        for callable_match in _AL_CALLABLE_RE.finditer(body):
            callable_name = _decode_al_identifier(callable_match.group("name"))
            callable_kind = callable_match.group("callable_kind").casefold()
            callable_line = _line_number(masked, body_offset + callable_match.start())
            callable_nid = _make_id(object_nid, callable_kind, callable_name)
            add_node({
                "id": callable_nid,
                "label": f"{callable_name}()",
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{callable_line}",
                "language": "al",
                "member_kind": callable_kind,
                "visibility": callable_match.group("visibility"),
                "parameters": callable_match.group("parameters").strip(),
                "return_type": (callable_match.group("return_type") or "").strip() or None,
                "lookup_key": _al_lookup_key(callable_name),
                "extraction_tier": "fallback",
                "_callable": True,
            })
            add_contains(object_nid, callable_nid, callable_line)

    return {"nodes": nodes, "edges": edges}


def extract_al(path: Path, source_override: str | None = None) -> dict:
    """Extract Business Central AL, falling back to structural regex parsing."""
    try:
        source = source_override if source_override is not None else path.read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    try:
        import tree_sitter_al
        from tree_sitter import Language, Parser
    except ImportError as exc:
        import importlib.util

        if importlib.util.find_spec("tree_sitter_al") is None:
            result = _extract_al_fallback(path, source)
            result["dependency_warning"] = (
                "tree_sitter_al not installed. Run: pip install tree-sitter-al"
            )
            return result
        return {
            "nodes": [],
            "edges": [],
            "error": f"tree_sitter_al is installed but failed to load: {exc}",
        }
    try:
        language = Language(tree_sitter_al.language())
        parser = Parser(language)
        tree = parser.parse(source.encode("utf-8"))
    except Exception as exc:
        return {
            "nodes": [],
            "edges": [],
            "error": f"tree_sitter_al is installed but failed to load: {exc}",
        }
    return _extract_al_tree_sitter(path, source, tree)