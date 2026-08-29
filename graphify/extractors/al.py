"""Microsoft Dynamics 365 Business Central AL extraction."""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id


_AL_IDENTIFIER = r'(?P<name>"(?:[^"]|"")+"|[A-Za-z_][\w.]*)'
_AL_OBJECT_RE = re.compile(
    rf"(?im)^\s*(?P<kind>codeunit|tableextension|table|pageextension|page|"
    rf"enumextension|enum|interface|reportextension|report|query|xmlport|"
    rf"permissionsetextension|permissionset|controladdin)\s+"
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
    "permissionsetextension_declaration": "permissionsetextension",
    "controladdin_declaration": "controladdin",
}
_AL_CALLABLE_TYPES = {
    "procedure": "procedure",
    "interface_procedure": "procedure",
    "preproc_split_procedure": "procedure",
    "trigger_declaration": "trigger",
    "event_declaration": "event",
}
_AL_MEMBER_SCOPE_TYPES = {
    "field_declaration",
    "page_field",
    "action_declaration",
    "action_group_section",
    "report_dataitem",
    "query_dataitem",
    "request_page",
    "request_page_section",
    "usercontrol_section",
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


def _mask_al_code(chars: list[str], index: int, char: str, following: str) -> tuple[int, str]:
    if char == "/" and following in {"/", "*"}:
        chars[index] = chars[index + 1] = " "
        state = "line_comment" if following == "/" else "block_comment"
        return index + 2, state
    if char == '"':
        return index + 1, "quoted_identifier"
    if char == "'":
        chars[index] = " "
        return index + 1, "string"
    return index + 1, "code"


def _mask_al_line_comment(chars: list[str], index: int, char: str, _following: str) -> tuple[int, str]:
    if char == "\n":
        return index + 1, "code"
    chars[index] = " "
    return index + 1, "line_comment"


def _mask_al_block_comment(
    chars: list[str], index: int, char: str, following: str
) -> tuple[int, str]:
    if char == "*" and following == "/":
        chars[index] = chars[index + 1] = " "
        return index + 2, "code"
    if char != "\n":
        chars[index] = " "
    return index + 1, "block_comment"


def _mask_al_string(chars: list[str], index: int, char: str, following: str) -> tuple[int, str]:
    chars[index] = " " if char != "\n" else "\n"
    if char == "'" and following == "'":
        chars[index + 1] = " "
        return index + 2, "string"
    return index + 1, "code" if char == "'" else "string"


def _mask_al_quoted_identifier(
    _chars: list[str], index: int, char: str, following: str
) -> tuple[int, str]:
    if char == '"' and following == '"':
        return index + 2, "quoted_identifier"
    return index + 1, "code" if char == '"' else "quoted_identifier"


def _mask_al_comments_and_strings(source: str) -> str:
    """Mask comments and string literals without changing offsets or newlines."""
    chars = list(source)
    if chars and chars[0] == "\ufeff":
        chars[0] = " "
    index = 0
    state = "code"
    handlers = {
        "code": _mask_al_code,
        "line_comment": _mask_al_line_comment,
        "block_comment": _mask_al_block_comment,
        "string": _mask_al_string,
        "quoted_identifier": _mask_al_quoted_identifier,
    }
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        index, state = handlers[state](chars, index, char, following)
    return "".join(chars)


def _matching_brace(masked_source: str, opening: int) -> int:
    """Find the closing brace in source with comments and strings already masked."""
    depth = 0
    for index in range(opening, len(masked_source)):
        if masked_source[index] == "{":
            depth += 1
        elif masked_source[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return len(masked_source)


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
    seeds: list[str] = []
    current = member_node.parent
    while current is not None and current.type not in _AL_OBJECT_TYPES:
        if current.type in _AL_MEMBER_SCOPE_TYPES:
            name = _decode_al_identifier(_field_text(current, "name", source))
            identifier = _field_text(current, "id", source)
            reference = _decode_al_identifier(_field_text(current, "source", source))
            if name or identifier or reference:
                seeds.append(f"{current.type}:{identifier}:{name}:{reference}")
        current = current.parent
    return "/".join(reversed(seeds)) or None


class _ALTreeContext:
    def __init__(self, path: Path, source: str, tree) -> None:
        self.path = path
        self.source = source.encode("utf-8")
        self.str_path = str(path)
        self.stem = _file_stem(path)
        self.root = tree.root_node
        self.namespace, usings = _al_namespace_and_usings(self.root, self.source)
        self.file_nid = _make_id(self.str_path)
        self.nodes: list[dict] = [{
            "id": self.file_nid,
            "label": path.name,
            "file_type": "code",
            "source_file": self.str_path,
            "source_location": "L1",
            "language": "al",
            "namespace": self.namespace or None,
            "extraction_tier": "tree_sitter",
        }]
        self.edges: list[dict] = []
        self.seen_ids = {self.file_nid}
        self.facts: dict[str, object] = {
            "namespace": self.namespace,
            "usings": usings,
            "objects": [],
            "members": [],
            "references": [],
            "calls": [],
            "event_subscribers": [],
            "event_publishers": [],
            "enum_mappings": [],
            "test_handlers": [],
            "control_addin_events": [],
        }

    def add_node(self, node: dict) -> None:
        if node["id"] not in self.seen_ids:
            self.seen_ids.add(node["id"])
            self.nodes.append(node)

    def add_edge(self, parent: str, child: str, relation: str, line: int) -> None:
        self.edges.append({
            "source": parent,
            "target": child,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": self.str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        })

    def result(self) -> dict:
        syntax_errors = [
            {"line": node.start_point.row + 1, "type": node.type}
            for node in _walk_al(self.root)
            if node.type == "ERROR" or node.is_missing
        ]
        result = {"nodes": self.nodes, "edges": self.edges, "al_facts": self.facts}
        if syntax_errors:
            result["syntax_errors"] = syntax_errors
        return result


def _al_namespace_and_usings(root, source: bytes) -> tuple[str, list[str]]:
    namespace_node = next(
        (node for node in root.named_children if node.type == "namespace_declaration"), None
    )
    namespace = _field_text(namespace_node, "name", source) if namespace_node else ""
    usings = [
        _field_text(node, "namespace", source)
        for node in root.named_children
        if node.type == "using_statement"
    ]
    return namespace, usings


def _al_object_info(context: _ALTreeContext, object_node) -> dict:
    kind = _AL_OBJECT_TYPES[object_node.type]
    name = _decode_al_identifier(_field_text(object_node, "object_name", context.source))
    qualified_name = f"{context.namespace}.{name}" if context.namespace else name
    interfaces = [
        _decode_al_identifier(_node_text(child, context.source))
        for clause in object_node.named_children
        if clause.type == "implements_clause"
        for index, child in enumerate(clause.children)
        if clause.field_name_for_child(index) == "interface"
    ]
    return {
        "nid": _make_id(context.stem, kind, qualified_name),
        "kind": kind,
        "name": name,
        "qualified_name": qualified_name,
        "lookup_key": _al_lookup_key(qualified_name),
        "object_id": _field_text(object_node, "object_id", context.source) or None,
        "base": _decode_al_identifier(_field_text(object_node, "base_object", context.source)) or None,
        "interfaces": [interface for interface in interfaces if interface],
        "line": object_node.start_point.row + 1,
    }


def _al_emit_object(context: _ALTreeContext, info: dict) -> None:
    context.add_node({
        "id": info["nid"],
        "label": info["name"],
        "file_type": "code",
        "source_file": context.str_path,
        "source_location": f"L{info['line']}",
        "language": "al",
        "object_kind": info["kind"],
        "object_id": info["object_id"],
        "qualified_name": info["qualified_name"],
        "namespace": context.namespace or None,
        "lookup_key": info["lookup_key"],
        "extraction_tier": "tree_sitter",
    })
    context.add_edge(context.file_nid, info["nid"], "contains", info["line"])
    context.facts["objects"].append({
        **info,
        "namespace": context.namespace,
        "source_file": context.str_path,
    })


def _al_object_variables(context: _ALTreeContext, object_node, object_nid: str) -> dict:
    variable_types: dict[str, tuple[str, str]] = {}
    for declaration in (node for node in _walk_al(object_node) if node.type == "variable_declaration"):
        ancestor = declaration.parent
        while ancestor is not None and ancestor is not object_node:
            if ancestor.type in _AL_CALLABLE_TYPES:
                break
            ancestor = ancestor.parent
        if ancestor is not object_node:
            continue
        variable_name = _decode_al_identifier(_field_text(declaration, "name", context.source))
        type_node = declaration.child_by_field_name("type")
        reference = _type_reference(type_node, context.source) if type_node else None
        if variable_name and reference:
            variable_types[_al_lookup_key(variable_name)] = reference
            context.facts["references"].append({
                "source": object_nid,
                "name": reference[1],
                "kind": reference[0],
                "line": declaration.start_point.row + 1,
            })
    return variable_types


def _al_member_nodes(object_node) -> list:
    return [
        node for node in _walk_al(object_node)
        if node.type in _AL_CALLABLE_TYPES
        or node.type in {
            "field_declaration",
            "enum_value_declaration",
            "usercontrol_section",
        }
    ]


def _al_member_name_counts(context: _ALTreeContext, member_nodes: list) -> dict:
    counts: dict[tuple[str, str], int] = {}
    for candidate in member_nodes:
        if candidate.type not in _AL_CALLABLE_TYPES:
            continue
        name = _decode_al_identifier(_field_text(candidate, "name", context.source))
        key = (_AL_CALLABLE_TYPES[candidate.type], _al_lookup_key(name))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _al_member_declaration(context: _ALTreeContext, member_node) -> dict | None:
    if member_node.type in _AL_CALLABLE_TYPES:
        kind, name_field, suffix = _AL_CALLABLE_TYPES[member_node.type], "name", "()"
    elif member_node.type == "field_declaration":
        kind, name_field, suffix = "field", "name", ""
    elif member_node.type == "enum_value_declaration":
        kind, name_field, suffix = "enum_value", "value_name", ""
    else:
        kind, name_field, suffix = "usercontrol", "name", ""
    name = _decode_al_identifier(_field_text(member_node, name_field, context.source))
    if not name:
        return None
    parameters = _parameter_metadata(member_node, context.source)
    return {
        "kind": kind,
        "name": name,
        "suffix": suffix,
        "lookup_key": _al_lookup_key(name),
        "attributes": _attribute_metadata(member_node, context.source),
        "parameters": parameters,
        "signature": ",".join(
            f"{parameter.get('modifier') or ''}:{parameter.get('type') or ''}"
            for parameter in parameters
        ),
        "line": member_node.start_point.row + 1,
    }


def _al_member_nid(
    context: _ALTreeContext, member_node, object_nid: str, info: dict, counts: dict
) -> str:
    scope_seed = _member_scope_seed(member_node, context.source)
    identity_seeds = [scope_seed] if scope_seed else []
    if counts.get((info["kind"], info["lookup_key"]), 0) > 1:
        identity_seeds.append(f"signature:{info['signature']}")
    return _make_id(object_nid, info["kind"], *identity_seeds, info["name"])


def _al_callable_metadata(context: _ALTreeContext, member_node, info: dict) -> dict:
    return_type = member_node.child_by_field_name("return_type")
    if return_type is None and member_node.type == "interface_procedure":
        suffix = _first_descendant(member_node, {"interface_procedure_suffix"})
        return_type = suffix.child_by_field_name("return_type") if suffix else None
    modifier = member_node.child_by_field_name("modifier")
    return {
        "visibility": _node_text(modifier, context.source).strip() if modifier else None,
        "parameters": info["parameters"],
        "return_type": _node_text(return_type, context.source).strip()
        if return_type else None,
        "attributes": info["attributes"],
        "signature": info["signature"],
        "_callable": True,
    }


def _al_data_member_metadata(
    context: _ALTreeContext, member_node, info: dict
) -> dict:
    data_type = member_node.child_by_field_name(
        "source" if info["kind"] == "usercontrol" else "type"
    )
    return {
        "member_id": _field_text(member_node, "id", context.source)
        or _field_text(member_node, "value_id", context.source) or None,
        "data_type": _node_text(data_type, context.source).strip() if data_type else None,
    }


def _al_member_metadata(
    context: _ALTreeContext, member_node, object_nid: str, member_nid: str, info: dict
) -> dict:
    metadata = {
        "id": member_nid,
        "label": f"{info['name']}{info['suffix']}",
        "file_type": "code",
        "source_file": context.str_path,
        "source_location": f"L{info['line']}",
        "language": "al",
        "member_kind": info["kind"],
        "parent_object": object_nid,
        "lookup_key": info["lookup_key"],
        "extraction_tier": "tree_sitter",
    }
    if info["kind"] in _AL_CALLABLE_TYPES.values():
        metadata.update(_al_callable_metadata(context, member_node, info))
    else:
        metadata.update(_al_data_member_metadata(context, member_node, info))
    return metadata


def _al_callable_types(
    context: _ALTreeContext, member_node, member_nid: str, info: dict, object_types: dict
) -> dict:
    callable_types = dict(object_types)
    for declaration in (
        node for node in _walk_al(member_node) if node.type == "variable_declaration"
    ):
        name = _decode_al_identifier(_field_text(declaration, "name", context.source))
        type_node = declaration.child_by_field_name("type")
        reference = _type_reference(type_node, context.source) if type_node else None
        if name and reference:
            callable_types[_al_lookup_key(name)] = reference
            context.facts["references"].append({
                "source": member_nid,
                "name": reference[1],
                "kind": reference[0],
                "line": declaration.start_point.row + 1,
            })
    for parameter, parameter_data in zip(
        (node for node in _walk_al(member_node) if node.type == "parameter"),
        info["parameters"],
    ):
        type_node = parameter.child_by_field_name("type")
        reference = _type_reference(type_node, context.source) if type_node else None
        if parameter_data["name"] and reference:
            callable_types[_al_lookup_key(parameter_data["name"])] = reference
            context.facts["references"].append({
                "source": member_nid,
                "name": reference[1],
                "kind": reference[0],
                "line": parameter.start_point.row + 1,
            })
    return callable_types


def _al_extract_calls(
    context: _ALTreeContext, member_node, member_nid: str, callable_types: dict
) -> None:
    for call in (node for node in _walk_al(member_node) if node.type == "call_expression"):
        function = call.child_by_field_name("function")
        if function is None:
            continue
        if function.type == "member_expression":
            receiver = _decode_al_identifier(_field_text(function, "object", context.source))
            call_name = _decode_al_identifier(_field_text(function, "member", context.source))
        else:
            receiver = ""
            call_name = _decode_al_identifier(_node_text(function, context.source))
        receiver_type = callable_types.get(_al_lookup_key(receiver)) if receiver else None
        arguments = call.child_by_field_name("arguments")
        context.facts["calls"].append({
            "source": member_nid,
            "name": call_name,
            "receiver": receiver or None,
            "receiver_kind": receiver_type[0] if receiver_type else None,
            "receiver_type": receiver_type[1] if receiver_type else None,
            "argument_count": len(arguments.named_children) if arguments else 0,
            "line": call.start_point.row + 1,
        })


def _al_extract_callable_attributes(
    context: _ALTreeContext, member_nid: str, object_nid: str, info: dict
) -> None:
    attributes = {_al_lookup_key(item["name"]): item for item in info["attributes"]}
    if event_attribute := attributes.get("eventsubscriber"):
        context.facts["event_subscribers"].append({
            "source": member_nid,
            "arguments": event_attribute["arguments"],
            "line": info["line"],
        })
    if attributes.keys() & {"integrationevent", "businessevent"}:
        context.facts["event_publishers"].append({
            "nid": member_nid,
            "object": object_nid,
            "name": info["name"],
            "lookup_key": info["lookup_key"],
        })
    if handler_attribute := attributes.get("handlerfunctions"):
        context.facts["test_handlers"].append({
            "source": member_nid,
            "arguments": handler_attribute["arguments"],
            "line": info["line"],
        })


def _al_enum_mapping(context: _ALTreeContext, prop, member_nid: str) -> None:
    comparison = _first_descendant(prop, {"comparison_expression"})
    if comparison is None:
        return
    context.facts["enum_mappings"].append({
        "source": member_nid,
        "interface": _decode_al_identifier(_field_text(comparison, "left", context.source)),
        "implementation": _decode_al_identifier(_field_text(comparison, "right", context.source)),
        "line": prop.start_point.row + 1,
    })


def _al_extract_enum_mappings(context: _ALTreeContext, member_node, member_nid: str) -> None:
    for prop in (node for node in _walk_al(member_node) if node.type == "property"):
        property_name = _node_text(prop.child_by_field_name("name"), context.source)
        if _al_lookup_key(property_name) == "implementation":
            _al_enum_mapping(context, prop, member_nid)


def _al_postprocess_member(
    context: _ALTreeContext, member_node, object_nid: str, member_nid: str,
    info: dict, object_types: dict,
) -> None:
    if info["kind"] in _AL_CALLABLE_TYPES.values():
        callable_types = _al_callable_types(context, member_node, member_nid, info, object_types)
        _al_extract_calls(context, member_node, member_nid, callable_types)
        _al_extract_callable_attributes(context, member_nid, object_nid, info)
    elif info["kind"] == "enum_value":
        _al_extract_enum_mappings(context, member_node, member_nid)


def _al_emit_member(
    context: _ALTreeContext, member_node, object_nid: str, member_nid: str, info: dict
) -> None:
    context.add_node(
        _al_member_metadata(context, member_node, object_nid, member_nid, info)
    )
    context.add_edge(object_nid, member_nid, "contains", info["line"])
    context.facts["members"].append({
        "nid": member_nid,
        "parent": object_nid,
        "name": info["name"],
        "lookup_key": info["lookup_key"],
        "kind": info["kind"],
        "signature": info["signature"],
        "parameter_count": len(info["parameters"]),
        "line": info["line"],
    })


def _al_controladdin_name(context: _ALTreeContext, node) -> str:
    return _decode_al_identifier(_field_text(node, "source", context.source))


def _al_collect_member_control_facts(
    context: _ALTreeContext, member_node, member_nid: str, info: dict
) -> None:
    if info["kind"] == "usercontrol":
        controladdin = _al_controladdin_name(context, member_node)
        if controladdin:
            context.facts["references"].append({
                "source": member_nid,
                "name": controladdin,
                "kind": "controladdin",
                "line": info["line"],
            })
        return
    if info["kind"] != "trigger":
        return
    parent = member_node.parent
    while parent is not None and parent.type not in _AL_OBJECT_TYPES:
        if parent.type == "usercontrol_section":
            controladdin = _al_controladdin_name(context, parent)
            if controladdin:
                context.facts["control_addin_events"].append({
                    "source": member_nid,
                    "controladdin": controladdin,
                    "event": info["name"],
                    "line": info["line"],
                })
            return
        parent = parent.parent


def _al_extract_member(
    context: _ALTreeContext, member_node, object_nid: str, counts: dict, object_types: dict
) -> None:
    info = _al_member_declaration(context, member_node)
    if info is None:
        return
    member_nid = _al_member_nid(context, member_node, object_nid, info, counts)
    _al_emit_member(context, member_node, object_nid, member_nid, info)
    _al_collect_member_control_facts(context, member_node, member_nid, info)
    _al_postprocess_member(context, member_node, object_nid, member_nid, info, object_types)


def _al_register_usercontrol_types(
    context: _ALTreeContext, members: list, object_types: dict
) -> None:
    for usercontrol in (
        node for node in members if node.type == "usercontrol_section"
    ):
        name = _decode_al_identifier(_field_text(usercontrol, "name", context.source))
        controladdin = _al_controladdin_name(context, usercontrol)
        if name and controladdin:
            reference = ("controladdin", controladdin)
            object_types[_al_lookup_key(name)] = reference
            object_types[_al_lookup_key(f"CurrPage.{name}")] = reference


def _al_extract_members(
    context: _ALTreeContext, object_node, object_nid: str, object_types: dict
) -> None:
    members = _al_member_nodes(object_node)
    counts = _al_member_name_counts(context, members)
    _al_register_usercontrol_types(context, members, object_types)
    for member_node in members:
        _al_extract_member(context, member_node, object_nid, counts, object_types)


def _al_extract_object(context: _ALTreeContext, object_node) -> None:
    info = _al_object_info(context, object_node)
    if not info["name"]:
        return
    _al_emit_object(context, info)
    object_types = _al_object_variables(context, object_node, info["nid"])
    _al_extract_members(context, object_node, info["nid"], object_types)


def _extract_al_tree_sitter(path: Path, source: str, tree) -> dict:
    context = _ALTreeContext(path, source, tree)
    for object_node in (node for node in _walk_al(context.root) if node.type in _AL_OBJECT_TYPES):
        _al_extract_object(context, object_node)
    return context.result()


class _ALFallbackExtractor:
    def __init__(self, path: Path, source: str) -> None:
        self.path = path
        self.str_path = str(path)
        self.stem = _file_stem(path)
        self.masked = _mask_al_comments_and_strings(source)
        namespace_match = _AL_NAMESPACE_RE.search(self.masked)
        self.namespace = namespace_match.group(1) if namespace_match else ""
        self.file_nid = _make_id(self.str_path)
        self.nodes: list[dict] = [{
            "id": self.file_nid,
            "label": path.name,
            "file_type": "code",
            "source_file": self.str_path,
            "source_location": "L1",
            "language": "al",
            "extraction_tier": "fallback",
        }]
        self.edges: list[dict] = []
        self.seen_ids = {self.file_nid}

    def extract(self) -> dict:
        self._extract_objects()
        return {"nodes": self.nodes, "edges": self.edges}

    def _add_node(self, node: dict) -> None:
        if node["id"] not in self.seen_ids:
            self.seen_ids.add(node["id"])
            self.nodes.append(node)

    def _add_contains(self, parent: str, child: str, line: int) -> None:
        self.edges.append({
            "source": parent,
            "target": child,
            "relation": "contains",
            "confidence": "EXTRACTED",
            "source_file": self.str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        })

    def _extract_objects(self) -> None:
        for match in _AL_OBJECT_RE.finditer(self.masked):
            info = self._object_info(match)
            self._emit_object(info)
            self._extract_callables(match, info["nid"])

    def _object_info(self, match) -> dict:
        kind = match.group("kind").casefold()
        name = _decode_al_identifier(match.group("name"))
        qualified_name = f"{self.namespace}.{name}" if self.namespace else name
        return {
            "nid": _make_id(self.stem, kind, qualified_name),
            "kind": kind,
            "name": name,
            "qualified_name": qualified_name,
            "object_id": match.group("object_id"),
            "line": _line_number(self.masked, match.start()),
            "lookup_key": _al_lookup_key(qualified_name),
        }

    def _emit_object(self, info: dict) -> None:
        self._add_node({
            "id": info["nid"],
            "label": info["name"],
            "file_type": "code",
            "source_file": self.str_path,
            "source_location": f"L{info['line']}",
            "language": "al",
            "object_kind": info["kind"],
            "object_id": info["object_id"],
            "qualified_name": info["qualified_name"],
            "namespace": self.namespace or None,
            "lookup_key": info["lookup_key"],
            "extraction_tier": "fallback",
        })
        self._add_contains(self.file_nid, info["nid"], info["line"])

    def _extract_callables(self, match, object_nid: str) -> None:
        opening = match.end() - 1
        closing = _matching_brace(self.masked, opening)
        body = self.masked[opening + 1:closing]
        body_offset = opening + 1
        occurrences: dict[tuple[str, str], int] = {}
        for callable_match in _AL_CALLABLE_RE.finditer(body):
            kind = callable_match.group("callable_kind").casefold()
            name = _decode_al_identifier(callable_match.group("name"))
            key = (kind, _al_lookup_key(name))
            occurrences[key] = occurrences.get(key, 0) + 1
            info = self._callable_info(
                callable_match, object_nid, body_offset, occurrences[key]
            )
            self._emit_callable(info)

    def _callable_info(
        self, match, object_nid: str, body_offset: int, occurrence: int
    ) -> dict:
        name = _decode_al_identifier(match.group("name"))
        kind = match.group("callable_kind").casefold()
        identity = (name,) if occurrence == 1 else (name, str(occurrence))
        return {
            "nid": _make_id(object_nid, kind, *identity),
            "parent": object_nid,
            "name": name,
            "kind": kind,
            "line": _line_number(self.masked, body_offset + match.start()),
            "visibility": match.group("visibility"),
            "parameters": match.group("parameters").strip(),
            "return_type": (match.group("return_type") or "").strip() or None,
            "lookup_key": _al_lookup_key(name),
        }

    def _emit_callable(self, info: dict) -> None:
        self._add_node({
            "id": info["nid"],
            "label": f"{info['name']}()",
            "file_type": "code",
            "source_file": self.str_path,
            "source_location": f"L{info['line']}",
            "language": "al",
            "member_kind": info["kind"],
            "visibility": info["visibility"],
            "parameters": info["parameters"],
            "return_type": info["return_type"],
            "lookup_key": info["lookup_key"],
            "extraction_tier": "fallback",
            "_callable": True,
        })
        self._add_contains(info["parent"], info["nid"], info["line"])


def _extract_al_fallback(path: Path, source: str) -> dict:
    return _ALFallbackExtractor(path, source).extract()


def _al_fallback_result(path: Path, source: str, warning: str) -> dict:
    result = _extract_al_fallback(path, source)
    result["dependency_warning"] = warning
    return result


def extract_al(path: Path, source_override: str | None = None) -> dict:
    """Extract Business Central AL, falling back to structural regex parsing."""
    try:
        source = source_override if source_override is not None else path.read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    try:
        from tree_sitter import Language, Parser
    except ImportError as exc:
        return _al_fallback_result(path, source, f"tree_sitter failed to load: {exc}")
    try:
        import tree_sitter_al
    except ImportError as exc:
        import importlib.util

        if importlib.util.find_spec("tree_sitter_al") is None:
            return _al_fallback_result(
                path, source,
                "tree_sitter_al not installed. Run: pip install tree-sitter-al",
            )
        return _al_fallback_result(
            path, source, f"tree_sitter_al failed to load: {exc}"
        )
    try:
        language = Language(tree_sitter_al.language())
        parser = Parser(language)
        tree = parser.parse(source.encode("utf-8"))
    except Exception as exc:
        return _al_fallback_result(
            path, source, f"tree_sitter_al failed to initialize: {exc}"
        )
    return _extract_al_tree_sitter(path, source, tree)