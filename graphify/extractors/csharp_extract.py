"""C# per-file extractor helpers, split out of graphify/extract.py."""
from __future__ import annotations

import hashlib

from graphify.extractors.base import _make_id, _read_text, LanguageConfig
from graphify.extractors.csharp import _csharp_base_identifier
from graphify.security import sanitize_metadata


def _csharp_namespace_id(dotted_name: str) -> str:
    digest = hashlib.sha1(dotted_name.encode("utf-8")).hexdigest()[:16]
    return f"csharp_namespace:{digest}"


_CSHARP_SCOPE_NODES = frozenset({
    "block",
    "checked_statement",
    "compilation_unit",
    "constructor_declaration",
    "class_declaration",
    "conversion_operator_declaration",
    "delegate_declaration",
    "destructor_declaration",
    "do_statement",
    "enum_declaration",
    "event_declaration",
    "file_scoped_namespace_declaration",
    "fixed_statement",
    "finally_clause",
    "for_statement",
    "foreach_statement",
    "if_statement",
    "indexer_declaration",
    "interface_declaration",
    "lambda_expression",
    "lock_statement",
    "local_function_statement",
    "method_declaration",
    "namespace_declaration",
    "operator_declaration",
    "property_declaration",
    "query_expression",
    "record_declaration",
    "struct_declaration",
    "switch_expression",
    "switch_expression_arm",
    "switch_section",
    "switch_statement",
    "try_statement",
    "unsafe_statement",
    "using_statement",
    "while_statement",
    "anonymous_method_expression",
    "accessor_declaration",
    "catch_clause",
})


_CSHARP_TYPE_DECLARATION_NODES = frozenset({
    "class_declaration",
    "enum_declaration",
    "interface_declaration",
    "record_declaration",
    "struct_declaration",
})


_CSHARP_PARAMETER_LIST_NODES = frozenset({
    "bracketed_parameter_list",
    "parameter_list",
})


_CSHARP_CALLABLE_PARAMETER_OWNER_NODES = frozenset({
    "accessor_declaration",
    "anonymous_method_expression",
    "constructor_declaration",
    "conversion_operator_declaration",
    "delegate_declaration",
    "indexer_declaration",
    "lambda_expression",
    "local_function_statement",
    "method_declaration",
    "operator_declaration",
})


def _csharp_scope_chain(node) -> list[str]:
    """Innermost-first lexical scope ids (f"s{start_byte}") from `node` up."""
    chain, cur = [], node
    while cur is not None:
        if cur.type in _CSHARP_SCOPE_NODES:
            chain.append(f"s{cur.start_byte}")
        cur = cur.parent
    return chain


def _csharp_scope_id(node) -> str:
    ch = _csharp_scope_chain(node)
    return ch[0] if ch else "s0"


_CSHARP_BINDING_PATTERN_NODES = frozenset({
    "declaration_expression",
    "declaration_pattern",
    "list_pattern",
    "parenthesized_pattern",
    "parenthesized_variable_designation",
    "positional_pattern_clause",
    "property_pattern_clause",
    "recursive_pattern",
    "subpattern",
    "tuple_pattern",
    "var_pattern",
})


def _csharp_designator_names(node, source: bytes) -> list[str]:
    """Collect local value names from C# binding designators/patterns.

    The installed grammar has `parenthesized_variable_designation` but no
    `single_variable_designation` node; concrete single-name designators are
    `identifier` leaves in binding positions. This collector is deliberately
    pattern-recursive, but it only treats direct designator/name-field
    identifiers as bindings, so recursive-pattern property names (`P:`) and
    type identifiers (`Actual`) are not collected.
    """
    if node is None:
        return []

    out: list[str] = []

    def _add(name: str) -> None:
        if name and name != "_" and name not in out:
            out.append(name)

    def _collect(cur, direct_identifier: bool = False) -> None:
        if cur is None:
            return
        if cur.type == "identifier":
            if direct_identifier:
                _add(_read_text(cur, source))
            return
        if cur.type == "implicit_parameter":
            _add(_read_text(cur, source))
            return

        name_node = cur.child_by_field_name("name")
        if name_node is not None:
            _collect(name_node, direct_identifier=True)

        if cur.type in ("tuple_pattern", "parenthesized_variable_designation"):
            for i, child in enumerate(cur.children):
                if child.type == "identifier" and (
                    cur.type == "parenthesized_variable_designation"
                    or cur.field_name_for_child(i) == "name"
                ):
                    _collect(child, direct_identifier=True)
                elif child.is_named:
                    _collect(child)
            return

        if cur.type in _CSHARP_BINDING_PATTERN_NODES:
            for i, child in enumerate(cur.children):
                if cur.field_name_for_child(i) in ("type", "expression", "qualifier"):
                    continue
                if cur.type == "var_pattern" and child.type == "identifier":
                    _collect(child, direct_identifier=True)
                elif child.type in _CSHARP_BINDING_PATTERN_NODES:
                    _collect(child)

    _collect(node, direct_identifier=node.type in ("identifier", "implicit_parameter"))
    return out


def _bare_type_node(type_node, source: bytes) -> str | None:
    if type_node is None or type_node.type != "identifier":
        return None
    text = _read_text(type_node, source).strip()
    return text if text and text != "var" else None


def _csharp_declared_bare_type(type_node, decl_node, source: bytes) -> str | None:
    bare = _bare_type_node(type_node, source)
    if bare is None:
        return None
    return None if bare in _csharp_type_parameters_in_scope(decl_node, source) else bare


def _csharp_parameter_scope_owner(node):
    cur = node.parent
    while cur is not None and cur.type in _CSHARP_PARAMETER_LIST_NODES:
        cur = cur.parent
    return cur


def _csharp_parameter_is_callable_scoped(node) -> bool:
    owner = _csharp_parameter_scope_owner(node)
    if owner is None or owner.type in _CSHARP_TYPE_DECLARATION_NODES:
        return False
    return owner.type in _CSHARP_CALLABLE_PARAMETER_OWNER_NODES


def _build_csharp_type_table(root, source: bytes) -> dict[str, list[tuple[str, str | None, int]]]:
    """Per-lexical-scope C# value binders:
    Entries have the shape `(var_name, bare_unqualified_type_or_None, decl_start_byte)`.

    The table records every non-member value binder collected by
    `_build_csharp_shadow_names`, minus type-scoped binders. Bare declared types
    are accepted only when they are identifiers and not visible type parameters.
    Unknown/unaccepted types are recorded as None so the resolver can poison
    shadowed receiver names instead of falling through to fields/properties.
    """
    table: dict[str, list[tuple[str, str | None, int]]] = {}

    def _put(scope_id: str, name: str, type_name: str | None, decl_start_byte: int) -> None:
        if name and name != "_":
            table.setdefault(scope_id, []).append((name, type_name, decl_start_byte))

    def _first_tuple_pattern(node):
        return next((c for c in node.children if c.type == "tuple_pattern"), None)

    def _put_explicit_designators(scope_node, designator_node, type_name: str | None, decl_start_byte: int) -> None:
        for name in _csharp_designator_names(designator_node, source):
            _put(_csharp_scope_id(scope_node), name, type_name, decl_start_byte)

    def _put_query_name(scope_node, name_node) -> None:
        if name_node is not None and name_node.type == "identifier":
            _put(_csharp_scope_id(scope_node), _read_text(name_node, source), None, name_node.start_byte)

    def _walk(node) -> None:
        if node.type == "parameter":
            if _csharp_parameter_is_callable_scoped(node):
                type_name = _csharp_declared_bare_type(node.child_by_field_name("type"), node, source)
                _put_explicit_designators(node, node, type_name, node.start_byte)
        elif node.type == "implicit_parameter":
            if _csharp_parameter_is_callable_scoped(node):
                _put_explicit_designators(node, node, None, node.start_byte)
        elif node.type == "variable_declaration":
            is_type_member_decl = node.parent is not None and node.parent.type in (
                "field_declaration",
                "event_field_declaration",
            )
            if not is_type_member_decl:
                type_node = node.child_by_field_name("type")
                is_var = type_node is not None and type_node.type == "implicit_type"
                declared = _csharp_declared_bare_type(type_node, node, source)
                for child in node.children:
                    if child.type != "variable_declarator":
                        continue
                    name_node = child.child_by_field_name("name") or _first_tuple_pattern(child)
                    if name_node is None:
                        continue
                    if name_node.type == "tuple_pattern":
                        for var_name in _csharp_designator_names(name_node, source):
                            _put(_csharp_scope_id(child), var_name, None, child.start_byte)
                        continue
                    names = _csharp_designator_names(name_node, source)
                    if not names:
                        continue
                    type_name = declared
                    if declared is None and is_var:
                        # var f = new Bar(args): in tree_sitter_c_sharp, the
                        # variable_declarator has only a `name` field; the RHS
                        # object_creation_expression is a named child after `=`.
                        creation = next(
                            (c for c in child.named_children if c.type == "object_creation_expression"),
                            None,
                        )
                        if creation is not None:
                            ctype = creation.child_by_field_name("type")
                            type_name = _csharp_declared_bare_type(ctype, child, source)
                        else:
                            type_name = None
                    for var_name in names:
                        _put(_csharp_scope_id(child), var_name, type_name, child.start_byte)
        elif node.type == "foreach_statement":
            type_name = _csharp_declared_bare_type(node.child_by_field_name("type"), node, source)
            _put_explicit_designators(node, node.child_by_field_name("left"), type_name, node.start_byte)
        elif node.type in ("catch_declaration", "declaration_pattern", "declaration_expression"):
            type_name = _csharp_declared_bare_type(node.child_by_field_name("type"), node, source)
            _put_explicit_designators(node, node, type_name, node.start_byte)
        elif node.type == "var_pattern":
            for name in _csharp_designator_names(node, source):
                _put(_csharp_scope_id(node), name, None, node.start_byte)
        elif node.type == "from_clause":
            _put_query_name(node, node.child_by_field_name("name"))
        elif node.type in ("let_clause", "join_clause", "join_into_clause"):
            _put_query_name(node, _csharp_first_identifier_child(node))
        elif node.type == "query_continuation":
            _put_query_name(node, _csharp_first_identifier_child(node))
        elif node.type == "query_expression":
            for index, child in enumerate(node.children):
                if child.type != "into":
                    continue
                for next_child in node.children[index + 1:]:
                    if next_child.type == "identifier":
                        _put_query_name(node, next_child)
                        break
                    if next_child.is_named:
                        break

        for child in node.children:
            _walk(child)

    _walk(root)
    return table


def _csharp_direct_invocation_initializer(declarator):
    seen_equals = False
    for child in declarator.children:
        if child.type == "=":
            seen_equals = True
            continue
        if seen_equals and child.is_named:
            return child if child.type == "invocation_expression" else None
    return None


def _build_csharp_var_call_inits(root, source: bytes) -> dict[str, list[dict[str, object]]]:
    """Structural facts for `var x = <invocation>();` locals.

    Facts are keyed by the same lexical binding identity as `csharp_type_table`:
    `(scope_id, name, decl_start_byte)`. Poison markers are scope/name pairs;
    the resolver skips every init for a poisoned pair.
    """
    inits: list[dict[str, object]] = []
    decl_counts: dict[tuple[str, str], int] = {}
    assignments: list[dict[str, object]] = []

    def _record_decl(scope_id: str, name: str) -> None:
        if name and name != "_":
            key = (scope_id, name)
            decl_counts[key] = decl_counts.get(key, 0) + 1

    def _walk(node) -> None:
        if node.type == "variable_declaration":
            is_type_member_decl = node.parent is not None and node.parent.type in (
                "field_declaration",
                "event_field_declaration",
            )
            if not is_type_member_decl:
                type_node = node.child_by_field_name("type")
                is_var = type_node is not None and type_node.type == "implicit_type"
                for child in node.children:
                    if child.type != "variable_declarator":
                        continue
                    scope_id = _csharp_scope_id(child)
                    name_node = child.child_by_field_name("name") or _csharp_first_child(child, "tuple_pattern")
                    names = _csharp_designator_names(name_node, source)
                    for name in names:
                        _record_decl(scope_id, name)
                    if not (is_var and len(names) == 1):
                        continue
                    init_call = _csharp_direct_invocation_initializer(child)
                    if init_call is None:
                        continue
                    inits.append({
                        "scope_id": scope_id,
                        "name": names[0],
                        "decl_start_byte": child.start_byte,
                        "call_byte": init_call.start_byte,
                    })
        elif node.type == "assignment_expression":
            left = node.child_by_field_name("left")
            if left is None:
                left = next((child for child in node.children if child.is_named), None)
            if left is not None and left.type == "identifier":
                assignments.append({
                    "name": _read_text(left, source),
                    "scope_chain": _csharp_scope_chain(node),
                    "assignment_byte": node.start_byte,
                })

        for child in node.children:
            _walk(child)

    _walk(root)

    poisoned: dict[tuple[str, str], set[str]] = {}
    for key, count in decl_counts.items():
        if count > 1:
            poisoned.setdefault(key, set()).add("redeclaration")

    for assignment in assignments:
        name = assignment.get("name")
        scope_chain = assignment.get("scope_chain")
        assignment_byte = assignment.get("assignment_byte")
        if not (isinstance(name, str) and isinstance(scope_chain, list) and isinstance(assignment_byte, int)):
            continue
        for fact in inits:
            scope_id = fact.get("scope_id")
            decl_start_byte = fact.get("decl_start_byte")
            if (
                fact.get("name") == name
                and isinstance(scope_id, str)
                and scope_id in scope_chain
                and isinstance(decl_start_byte, int)
                and decl_start_byte < assignment_byte
            ):
                poisoned.setdefault((scope_id, name), set()).add("assignment")

    poisoned_facts = [
        {"scope_id": scope_id, "name": name, "reason": reason}
        for (scope_id, name), reasons in sorted(poisoned.items())
        for reason in sorted(reasons)
    ]
    return {"inits": inits, "poisoned": poisoned_facts}


def _csharp_unique_sorted(values: list[str] | set[str]) -> list[str]:
    return sorted({v for v in values if isinstance(v, str) and v and v != "_"})


def _csharp_shadow_bucket() -> dict[str, list[str]]:
    return {
        "values": [],
        "namespaces": [],
        "methods": [],
        "typeparams": [],
        "nested_types": [],
    }


def _csharp_add_shadow(
    scopes: dict[str, dict[str, list[str]]],
    scope_id: str,
    bucket: str,
    name: str | None,
) -> None:
    if not name or name == "_":
        return
    entry = scopes.setdefault(scope_id, _csharp_shadow_bucket())
    if name not in entry[bucket]:
        entry[bucket].append(name)


def _csharp_first_child(node, node_type: str):
    return next((child for child in node.children if child.type == node_type), None)


def _csharp_enclosing_scope_id(node) -> str:
    cur = node.parent
    while cur is not None:
        if cur.type in _CSHARP_SCOPE_NODES and cur.type != node.type:
            return f"s{cur.start_byte}"
        cur = cur.parent
    return "s0"


def _csharp_first_identifier_child(node):
    return next((child for child in node.children if child.type == "identifier"), None)


def _csharp_names_from_variable_declaration(node, source: bytes) -> list[str]:
    names: list[str] = []
    for child in node.children:
        if child.type != "variable_declarator":
            continue
        name_node = child.child_by_field_name("name") or _csharp_first_child(child, "tuple_pattern")
        names.extend(_csharp_designator_names(name_node, source))
    return _csharp_unique_sorted(names)


def _csharp_direct_member_names(type_node, source: bytes) -> dict[str, list[str]]:
    """Direct C# member names needed for inherited shadow checks.

    Values are fields, properties, events, enum members, and record positional
    parameters. Methods are regular method declarations. Nested types are direct
    type declarations inside this type. The resolver later walks resolved
    internal base chains and treats an unresolved base as "cannot prove absence".
    """
    members: dict[str, set[str]] = {
        "values": set(),
        "methods": set(),
        "nested_types": set(),
    }
    if type_node.type == "record_declaration":
        for child in type_node.children:
            if child.type != "parameter_list":
                continue
            for param in child.children:
                if param.type != "parameter":
                    continue
                name_node = param.child_by_field_name("name")
                if name_node is not None:
                    members["values"].add(_read_text(name_node, source))

    body = type_node.child_by_field_name("body")
    if body is not None:
        for child in body.children:
            if child.type in ("field_declaration", "event_field_declaration"):
                decl = child.child_by_field_name("declaration") or _csharp_first_child(child, "variable_declaration")
                if decl is not None:
                    members["values"].update(_csharp_names_from_variable_declaration(decl, source))
            elif child.type in ("property_declaration", "event_declaration"):
                name_node = child.child_by_field_name("name")
                if name_node is not None:
                    members["values"].add(_read_text(name_node, source))
            elif child.type == "enum_member_declaration":
                name_node = child.child_by_field_name("name")
                if name_node is not None:
                    members["values"].add(_read_text(name_node, source))
            elif child.type == "method_declaration":
                name_node = child.child_by_field_name("name")
                if name_node is not None:
                    members["methods"].add(_csharp_base_identifier(_read_text(name_node, source)))
            elif child.type in _CSHARP_CONFIG.class_types:
                name_node = child.child_by_field_name("name")
                if name_node is not None:
                    members["nested_types"].add(_read_text(name_node, source))
    return {key: _csharp_unique_sorted(values) for key, values in members.items()}


def _csharp_direct_member_types(type_node, source: bytes) -> dict[str, str | None]:
    """Direct C# member receiver types for fields, properties, and record positional properties."""
    members: dict[str, str | None] = {}

    def _put(name_node, type_name: str | None) -> None:
        if name_node is None:
            return
        name = _read_text(name_node, source)
        if name and name != "_":
            members[name] = type_name

    if type_node.type == "record_declaration":
        for child in type_node.children:
            if child.type != "parameter_list":
                continue
            for param in child.children:
                if param.type != "parameter":
                    continue
                _put(
                    param.child_by_field_name("name"),
                    _csharp_declared_bare_type(param.child_by_field_name("type"), param, source),
                )

    body = type_node.child_by_field_name("body")
    if body is not None:
        for child in body.children:
            if child.type == "field_declaration":
                decl = child.child_by_field_name("declaration") or _csharp_first_child(child, "variable_declaration")
                if decl is None:
                    continue
                type_name = _csharp_declared_bare_type(decl.child_by_field_name("type"), decl, source)
                for decl_child in decl.children:
                    if decl_child.type != "variable_declarator":
                        continue
                    name_node = decl_child.child_by_field_name("name") or _csharp_first_child(decl_child, "tuple_pattern")
                    for name in _csharp_designator_names(name_node, source):
                        if name and name != "_":
                            members[name] = type_name
            elif child.type == "property_declaration":
                _put(
                    child.child_by_field_name("name"),
                    _csharp_declared_bare_type(child.child_by_field_name("type"), child, source),
                )

    return dict(sorted(members.items()))


def _build_csharp_shadow_names(root, source: bytes) -> dict[str, dict[str, list[str]]]:
    """Collect C# simple-name lookup shadow facts by lexical scope id.

    The result is keyed by `_csharp_scope_id`, with buckets:
    values, namespaces, methods, typeparams, nested_types. This mirrors the
    binder coverage used by `_build_csharp_type_table` and adds type members
    that are not local variable declarations.
    """
    scopes: dict[str, dict[str, list[str]]] = {}

    def _add_designators(scope_node, designator_node, bucket: str = "values") -> None:
        for name in _csharp_designator_names(designator_node, source):
            _csharp_add_shadow(scopes, _csharp_scope_id(scope_node), bucket, name)

    def _add_type_parameters(scope_node) -> None:
        for child in scope_node.children:
            if child.type != "type_parameter_list":
                continue
            for param in child.children:
                if param.type == "type_parameter":
                    name_node = param.child_by_field_name("name") or _csharp_first_child(param, "identifier")
                    if name_node is not None:
                        _csharp_add_shadow(scopes, _csharp_scope_id(scope_node), "typeparams", _read_text(name_node, source))
                elif param.type == "identifier":
                    _csharp_add_shadow(scopes, _csharp_scope_id(scope_node), "typeparams", _read_text(param, source))

    def _add_query_name(scope_node, name_node) -> None:
        if name_node is not None and name_node.type == "identifier":
            _csharp_add_shadow(scopes, _csharp_scope_id(scope_node), "values", _read_text(name_node, source))

    def _walk(node) -> None:
        if node.type in ("namespace_declaration", "file_scoped_namespace_declaration"):
            ns_name = _csharp_namespace_name(node, source)
            if ns_name:
                first = ns_name.split(".", 1)[0]
                _csharp_add_shadow(scopes, _csharp_scope_id(node), "namespaces", first)

        if node.type in _CSHARP_TYPE_PARAMETER_SCOPE_DECLARATIONS:
            _add_type_parameters(node)

        if node.type == "parameter":
            _add_designators(node, node)
        elif node.type == "implicit_parameter":
            _add_designators(node, node)
        elif node.type == "variable_declaration":
            if node.parent is not None and node.parent.type in ("field_declaration", "event_field_declaration"):
                bucket_scope = node.parent.parent if node.parent.parent is not None else node.parent
                for name in _csharp_names_from_variable_declaration(node, source):
                    _csharp_add_shadow(scopes, _csharp_scope_id(bucket_scope), "values", name)
            else:
                for child in node.children:
                    if child.type == "variable_declarator":
                        name_node = child.child_by_field_name("name") or _csharp_first_child(child, "tuple_pattern")
                        _add_designators(child, name_node)
        elif node.type == "foreach_statement":
            _add_designators(node, node.child_by_field_name("left"))
        elif node.type in ("catch_declaration", "declaration_pattern", "declaration_expression", "var_pattern"):
            _add_designators(node, node)
        elif node.type == "local_function_statement":
            _add_type_parameters(node)
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                _csharp_add_shadow(scopes, _csharp_enclosing_scope_id(node), "methods", _read_text(name_node, source))
        elif node.type == "from_clause":
            _add_query_name(node, node.child_by_field_name("name"))
        elif node.type in ("let_clause", "join_clause", "join_into_clause"):
            _add_query_name(node, _csharp_first_identifier_child(node))
        elif node.type == "query_continuation":
            _add_query_name(node, _csharp_first_identifier_child(node))
        elif node.type == "query_expression":
            for index, child in enumerate(node.children):
                if child.type != "into":
                    continue
                for next_child in node.children[index + 1:]:
                    if next_child.type == "identifier":
                        _add_query_name(node, next_child)
                        break
                    if next_child.is_named:
                        break
        elif node.type == "property_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None and node.parent is not None:
                _csharp_add_shadow(scopes, _csharp_scope_id(node.parent), "values", _read_text(name_node, source))
        elif node.type == "event_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None and node.parent is not None:
                _csharp_add_shadow(scopes, _csharp_scope_id(node.parent), "values", _read_text(name_node, source))
        elif node.type == "enum_member_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                _csharp_add_shadow(scopes, _csharp_scope_id(node), "values", _read_text(name_node, source))
        elif node.type in _CSHARP_CONFIG.class_types and node.parent is not None and node.parent.type == "declaration_list":
            name_node = node.child_by_field_name("name")
            parent = node.parent.parent
            if parent is not None and parent.type in _CSHARP_CONFIG.class_types and name_node is not None:
                _csharp_add_shadow(scopes, _csharp_scope_id(parent), "nested_types", _read_text(name_node, source))

        for child in node.children:
            _walk(child)

    _walk(root)
    return {
        scope_id: {bucket: _csharp_unique_sorted(names) for bucket, names in buckets.items()}
        for scope_id, buckets in scopes.items()
    }


def _csharp_pre_scan_interfaces(root_node, source: bytes) -> set[str]:
    """Return names declared as `interface` in this C# compilation unit."""
    out: set[str] = set()
    stack = [root_node]
    while stack:
        n = stack.pop()
        if n.type == "interface_declaration":
            name_node = n.child_by_field_name("name")
            if name_node is not None:
                text = _read_text(name_node, source)
                if text:
                    out.add(text)
        stack.extend(n.children)
    return out


def _csharp_classify_base(name: str, interface_names: set[str]) -> str:
    """`implements` if the base name is an interface (declared or by I-prefix convention), else `inherits`."""
    if name in interface_names:
        return "implements"
    if len(name) >= 2 and name[0] == "I" and name[1].isupper():
        return "implements"
    return "inherits"


_CSHARP_TYPE_PARAMETER_SCOPE_DECLARATIONS = _CSHARP_TYPE_DECLARATION_NODES | frozenset({
    "delegate_declaration",
    "local_function_statement",
    "method_declaration",
})


def _csharp_type_parameters_in_scope(node, source: bytes) -> frozenset[str]:
    """Return C# type-parameter names visible from ``node``."""
    names: set[str] = set()
    scope = node
    while scope is not None:
        if scope.type in _CSHARP_TYPE_PARAMETER_SCOPE_DECLARATIONS:
            for child in scope.children:
                if child.type != "type_parameter_list":
                    continue
                for param in child.children:
                    if param.type == "type_parameter":
                        name_node = next(
                            (sub for sub in param.children if sub.type == "identifier"),
                            None,
                        )
                        if name_node is not None:
                            name = _read_text(name_node, source)
                            if name:
                                names.add(name)
                    elif param.type == "identifier":
                        name = _read_text(param, source)
                        if name:
                            names.add(name)
        scope = scope.parent
    return frozenset(names)


def _csharp_collect_type_refs(
    node,
    source: bytes,
    generic: bool,
    out: list[tuple[str, str, bool, str]],
    skip: frozenset[str] | None = None,
) -> None:
    """Walk a C# type expression; append (name, role, qualified, qualifier) tuples."""
    if node is None:
        return
    if skip is None:
        skip = _csharp_type_parameters_in_scope(node, source)
    t = node.type
    if t == "predefined_type":
        return
    if t == "identifier":
        name = _read_text(node, source)
        if name and name not in skip:
            out.append((name, "generic_arg" if generic else "type", False, ""))
        return
    if t == "qualified_name":
        prefix, _, text = _read_text(node, source).rpartition(".")
        text = text.split("<", 1)[0]
        if text and text not in skip:
            out.append((text, "generic_arg" if generic else "type", True, prefix))
        return
    if t == "generic_name":
        name_child = node.child_by_field_name("name")
        if name_child is None:
            for sub in node.children:
                if sub.type == "identifier":
                    name_child = sub
                    break
        if name_child is not None:
            qualified = name_child.type == "qualified_name"
            prefix, _, name = _read_text(name_child, source).rpartition(".")
            if name and name not in skip:
                out.append((name, "generic_arg" if generic else "type", qualified, prefix if qualified else ""))
        for sub in node.children:
            if sub.type == "type_argument_list":
                for arg in sub.children:
                    if arg.is_named:
                        _csharp_collect_type_refs(arg, source, True, out, skip)
        return
    if t in ("nullable_type", "array_type", "pointer_type", "ref_type"):
        for c in node.children:
            if c.is_named:
                _csharp_collect_type_refs(c, source, generic, out, skip)
        return
    if node.is_named:
        for c in node.children:
            if c.is_named:
                _csharp_collect_type_refs(c, source, generic, out, skip)


def _csharp_attribute_names(method_node, source: bytes) -> list[tuple[str, bool, str]]:
    """Collect attribute names from a C# method/declaration's attribute_list children."""
    names: list[tuple[str, bool, str]] = []
    skip = _csharp_type_parameters_in_scope(method_node, source)
    for child in method_node.children:
        if child.type != "attribute_list":
            continue
        for attr in child.children:
            if attr.type != "attribute":
                continue
            name_node = attr.child_by_field_name("name")
            if name_node is None:
                for sub in attr.children:
                    if sub.type in ("identifier", "qualified_name"):
                        name_node = sub
                        break
            if name_node is not None:
                qualified = name_node.type == "qualified_name"
                prefix, _, text = _read_text(name_node, source).rpartition(".")
                if text and text not in skip:
                    names.append((text, qualified, prefix if qualified else ""))
    return names


def _csharp_import_target_kind(using_kind: str, target_fqn: str) -> str:
    if using_kind == "namespace":
        return "namespace"
    if using_kind == "static":
        return "type"
    if "<" in target_fqn or target_fqn.endswith("]"):
        return "type"
    tail = target_fqn.rsplit(".", 1)[-1].strip()
    return "type" if tail[:1].isupper() else "namespace"


def _import_csharp(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str, scope_stack: list[str] | None = None) -> None:
    text = _read_text(node, source).strip().rstrip(";")
    if node.type == "extern_alias_directive":
        alias_node = node.child_by_field_name("name")
        alias = _read_text(alias_node, source).strip() if alias_node is not None else ""
        if not alias:
            return
        edges.append({
            "source": file_nid,
            "target": _make_id(alias),
            "relation": "imports",
            "context": "import",
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{node.start_point[0] + 1}",
            "weight": 1.0,
            "metadata": sanitize_metadata({
                "using_kind": "extern_alias",
                "alias": alias,
                "target_fqn": alias,
                "target_kind": "namespace",
                "scope_kind": "global",
            }),
        })
        return

    is_global = text.startswith("global ")
    if is_global:
        text = text[len("global "):].strip()
    if not text.startswith("using"):
        return
    body = text[len("using"):].strip()
    using_kind, alias, target_fqn = "namespace", None, body
    if body.startswith("static "):
        using_kind, target_fqn = "static", body[len("static "):].strip()
    elif "=" in body:
        lhs, rhs = body.split("=", 1)
        using_kind, alias, target_fqn = "alias", lhs.strip(), rhs.strip()
    if not target_fqn:
        return
    scope_kind = "global" if is_global else ("namespace" if scope_stack else "file")
    metadata = {
        "using_kind": using_kind,
        "target_fqn": target_fqn,
        "target_kind": _csharp_import_target_kind(using_kind, target_fqn),
        "scope_kind": scope_kind,
        "is_global": is_global,
    }
    if alias:
        metadata["alias"] = alias
    if scope_stack and not is_global:
        metadata["scope_id"] = scope_stack[-1]
    edges.append({
        "source": file_nid,
        "target": _make_id(target_fqn),
        "relation": "imports",
        "context": "import",
        "confidence": "EXTRACTED",
        "source_file": str_path,
        "source_location": f"L{node.start_point[0] + 1}",
        "weight": 1.0,
        "metadata": sanitize_metadata(metadata),
    })


def _csharp_namespace_name(node, source: bytes) -> str:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return _read_text(name_node, source).strip()
    for child in node.children:
        if child.type in ("identifier", "qualified_name"):
            return _read_text(child, source).strip()
    return ""


def _csharp_extra_walk(node, source: bytes, file_nid: str, stem: str, str_path: str,
                       nodes: list, edges: list, seen_ids: set, function_bodies: list,
                       parent_class_nid: str | None, add_node_fn, add_edge_fn,
                       walk_fn, namespace_stack: list[str], scope_stack: list[str]) -> bool:
    """Handle namespace declarations for C#. Returns True if handled."""
    if node.type == "namespace_declaration":
        ns_name = _csharp_namespace_name(node, source)
        pushed = False
        if ns_name:
            namespace_stack.append(ns_name)
            scope_stack.append(f"s{node.start_byte}")
            pushed = True
            ns_label = ".".join(namespace_stack)
            ns_nid = _csharp_namespace_id(ns_label)
            line = node.start_point[0] + 1
            add_node_fn(ns_nid, ns_label, line, node_type="namespace", metadata={"kind": "csharp_namespace"})
            add_edge_fn(file_nid, ns_nid, "contains", line)
        body = node.child_by_field_name("body")
        if body:
            try:
                for child in body.children:
                    walk_fn(child, parent_class_nid)
            finally:
                if pushed:
                    namespace_stack.pop()
                    scope_stack.pop()
        elif pushed:
            namespace_stack.pop()
            scope_stack.pop()
        return True
    if node.type == "file_scoped_namespace_declaration":
        ns_name = _csharp_namespace_name(node, source)
        if ns_name:
            namespace_stack.append(ns_name)
            scope_stack.append(f"s{node.start_byte}")
            ns_label = ".".join(namespace_stack)
            ns_nid = _csharp_namespace_id(ns_label)
            line = node.start_point[0] + 1
            add_node_fn(ns_nid, ns_label, line, node_type="namespace", metadata={"kind": "csharp_namespace"})
            add_edge_fn(file_nid, ns_nid, "contains", line)
        return True
    return False


_CSHARP_CONFIG = LanguageConfig(
    ts_module="tree_sitter_c_sharp",
    class_types=frozenset({
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "struct_declaration",
        "record_declaration",
    }),
    function_types=frozenset({"method_declaration"}),
    import_types=frozenset({"using_directive", "extern_alias_directive"}),
    call_types=frozenset({"invocation_expression"}),
    call_function_field="function",
    call_accessor_node_types=frozenset({"member_access_expression"}),
    call_accessor_field="name",
    body_fallback_child_types=("declaration_list",),
    function_boundary_types=frozenset({"method_declaration"}),
    import_handler=_import_csharp,
)


def _read_csharp_type_name(node, source: bytes) -> tuple[str, bool, str] | None:
    """Resolve a C# type name, whether it was qualified, and its qualifier prefix."""
    if node is None:
        return None
    if node.type in ("identifier", "predefined_type"):
        return (_read_text(node, source), False, "")
    if node.type == "qualified_name":
        prefix, _, tail = _read_text(node, source).rpartition(".")
        tail = tail.split("<", 1)[0]
        return (tail, True, prefix)
    if node.type == "generic_name":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            qualified = name_node.type == "qualified_name"
            prefix, _, tail = _read_text(name_node, source).rpartition(".")
            return (tail, qualified, prefix if qualified else "")
    for child in node.children:
        if not child.is_named:
            continue
        result = _read_csharp_type_name(child, source)
        if result:
            return result
    return None


CsharpTypeRefFact = tuple[str, str, bool, str]
CsharpBaseListFact = tuple[str, bool, str, str, list[tuple[str, bool, str]]]
_CSHARP_NEW_RECEIVER_PREFIX = "__csharp_new__:"


def csharp_class_member_metadata(type_node, source: bytes, parent_class_nid: str | None) -> dict:
    """Return C# type metadata collected from the declaration node."""
    metadata = {
        "csharp_member_names": _csharp_direct_member_names(type_node, source),
        "csharp_member_types": _csharp_direct_member_types(type_node, source),
    }
    if parent_class_nid:
        metadata["is_nested_type"] = True
        metadata["parent_class_nid"] = parent_class_nid
    return metadata


def csharp_base_list_facts(
    type_node,
    source: bytes,
    csharp_interface_names: set[str],
    csharp_type_params: frozenset[str],
) -> list[CsharpBaseListFact]:
    """Return ordered base-list facts for C# class/interface emission."""
    facts: list[CsharpBaseListFact] = []
    for child in type_node.children:
        if child.type != "base_list":
            continue
        for sub in child.children:
            base_type_node = sub
            if sub.type == "primary_constructor_base_type":
                base_type_node = sub.child_by_field_name("type")
            if base_type_node is None or base_type_node.type not in (
                "identifier",
                "generic_name",
                "qualified_name",
            ):
                continue
            base_info = _read_csharp_type_name(base_type_node, source)
            if base_info is None:
                continue
            base, qualified, qualifier = base_info
            if not base or base in csharp_type_params:
                continue
            generic_refs: list[tuple[str, bool, str]] = []
            if base_type_node.type == "generic_name":
                for tal in base_type_node.children:
                    if tal.type != "type_argument_list":
                        continue
                    for arg in tal.children:
                        if not arg.is_named:
                            continue
                        refs: list[tuple[str, str, bool, str]] = []
                        _csharp_collect_type_refs(arg, source, True, refs, csharp_type_params)
                        for ref_name, _role, ref_qualified, ref_qualifier in refs:
                            generic_refs.append((ref_name, ref_qualified, ref_qualifier))
            facts.append((
                base,
                qualified,
                qualifier,
                _csharp_classify_base(base, csharp_interface_names),
                generic_refs,
            ))
    return facts


def csharp_field_type_ref_facts(field_node, source: bytes) -> list[CsharpTypeRefFact]:
    """Return C# field type reference facts in emission order."""
    type_node = field_node.child_by_field_name("type")
    if type_node is None:
        for child in field_node.children:
            if child.type == "variable_declaration":
                type_node = child.child_by_field_name("type")
                if type_node is not None:
                    break
    type_info = _read_csharp_type_name(type_node, source)
    if not type_info:
        return []
    type_name, qualified, qualifier = type_info
    csharp_type_params = _csharp_type_parameters_in_scope(
        type_node if type_node is not None else field_node, source
    )
    if not type_name or type_name in csharp_type_params:
        return []
    return [(type_name, "field", qualified, qualifier)]


def csharp_property_type_ref_facts(property_node, source: bytes) -> list[CsharpTypeRefFact]:
    """Return C# property type reference facts in emission order."""
    type_node = property_node.child_by_field_name("type")
    if type_node is None:
        return []
    refs: list[tuple[str, str, bool, str]] = []
    _csharp_collect_type_refs(type_node, source, False, refs)
    return [
        (ref_name, "generic_arg" if role == "generic_arg" else "field", qualified, qualifier)
        for ref_name, role, qualified, qualifier in refs
    ]


def csharp_method_reference_facts(method_node, source: bytes) -> list[CsharpTypeRefFact]:
    """Return ordered C# parameter, return, and attribute reference facts."""
    csharp_type_params = _csharp_type_parameters_in_scope(method_node, source)
    facts: list[CsharpTypeRefFact] = []
    params_node = method_node.child_by_field_name("parameters")
    if params_node is not None:
        for param in params_node.children:
            if param.type != "parameter":
                continue
            refs: list[tuple[str, str, bool, str]] = []
            _csharp_collect_type_refs(
                param.child_by_field_name("type"), source, False, refs, csharp_type_params
            )
            for ref_name, role, qualified, qualifier in refs:
                facts.append((
                    ref_name,
                    "generic_arg" if role == "generic_arg" else "parameter_type",
                    qualified,
                    qualifier,
                ))
    return_node = method_node.child_by_field_name("returns")
    if return_node is not None:
        refs = []
        _csharp_collect_type_refs(return_node, source, False, refs, csharp_type_params)
        for ref_name, role, qualified, qualifier in refs:
            facts.append((
                ref_name,
                "generic_arg" if role == "generic_arg" else "return_type",
                qualified,
                qualifier,
            ))
    for attr_name, qualified, qualifier in _csharp_attribute_names(method_node, source):
        facts.append((attr_name, "attribute", qualified, qualifier))
    return facts


def csharp_invocation_callee(node, source: bytes) -> tuple[str | None, bool, str | None]:
    """Parse a C# invocation node into `(callee_name, is_member_call, member_receiver)`."""
    callee_name: str | None = None
    is_member_call = False
    member_receiver: str | None = None

    def _receiver_text(recv_node) -> str:
        if recv_node.type in ("object_creation_expression", "implicit_object_creation_expression"):
            type_node = recv_node.child_by_field_name("type")
            if type_node is None:
                type_node = next(
                    (
                        child
                        for child in recv_node.named_children
                        if child.type in ("identifier", "qualified_name", "generic_name")
                    ),
                    None,
                )
            info = _read_csharp_type_name(type_node, source)
            if info:
                return f"{_CSHARP_NEW_RECEIVER_PREFIX}{info[0]}"
        return _read_text(recv_node, source)

    def _member_access_parts(access_node) -> tuple[str | None, str | None]:
        recv_node = access_node.child_by_field_name("expression")
        name_node = access_node.child_by_field_name("name")
        if recv_node is None or name_node is None:
            named = [child for child in access_node.named_children if child.is_named]
            if len(named) >= 2:
                recv_node = named[-2]
                name_node = named[-1]
        if recv_node is None or name_node is None:
            return None, None
        return _csharp_base_identifier(_read_text(name_node, source)), _receiver_text(recv_node)

    func_node = node.child_by_field_name("function")
    if func_node is not None and func_node.type == "conditional_access_expression":
        is_member_call = True
        recv_node = func_node.child_by_field_name("condition")
        if recv_node is not None:
            member_receiver = _receiver_text(recv_node)
        binding_node = next(
            (child for child in func_node.named_children if child.type == "member_binding_expression"),
            None,
        )
        name_node = binding_node.child_by_field_name("name") if binding_node is not None else None
        if name_node is not None:
            callee_name = _csharp_base_identifier(_read_text(name_node, source))
    elif func_node is not None and func_node.type == "member_access_expression":
        is_member_call = True
        callee_name, member_receiver = _member_access_parts(func_node)
    else:
        if func_node is not None and func_node.type in ("identifier", "generic_name"):
            callee_name = _csharp_base_identifier(_read_text(func_node, source))
            is_member_call = True
            member_receiver = ""
        else:
            name_node = node.child_by_field_name("name")
            if name_node:
                callee_name = _read_text(name_node, source)
            else:
                for child in node.children:
                    if child.is_named:
                        if child.type == "member_access_expression":
                            callee_name, member_receiver = _member_access_parts(child)
                            is_member_call = bool(callee_name)
                            break
                        raw = _read_text(child, source)
                        if "." in raw:
                            callee_name = _csharp_base_identifier(raw.split(".")[-1])
                            is_member_call = True
                            member_receiver = raw.rsplit(".", 1)[0]
                        else:
                            callee_name = _csharp_base_identifier(raw)
                        break
    return callee_name, is_member_call, member_receiver


def csharp_file_facts(root, source: bytes, str_path: str) -> dict[str, dict]:
    """Return per-file C# fact tables for the shared extraction result."""
    csharp_var_call_inits = _build_csharp_var_call_inits(root, source)
    return {
        "csharp_type_table": {
            "path": str_path,
            "scopes": _build_csharp_type_table(root, source),
        },
        "csharp_shadow_names": {
            "path": str_path,
            "scopes": _build_csharp_shadow_names(root, source),
        },
        "csharp_var_call_inits": {
            "path": str_path,
            "inits": csharp_var_call_inits["inits"],
            "poisoned": csharp_var_call_inits["poisoned"],
        },
    }
