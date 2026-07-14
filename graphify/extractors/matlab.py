"""MATLAB structural extraction and conservative cross-file resolution.

MATLAB and Objective-C share ``.m``.  Routing is handled in ``extract.py``;
this module assumes that a file has already been classified as MATLAB.  The
grammar intentionally parses both calls and indexing (``A(1)``/``A{1}``) as a
``function_call``, so this extractor emits a call only when lexical or corpus
evidence identifies the target as callable.  Unknown ambiguous expressions are
left unresolved instead of manufacturing graph edges.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id, _read_text

_LANGUAGE = "matlab"
_FAMILY = "matlab"


def _child(node, type_name: str):
    return next((c for c in node.children if c.type == type_name), None)


def _field(node, name: str):
    try:
        return node.child_by_field_name(name)
    except Exception:
        return None


def _identifiers(node, source: bytes) -> list[str]:
    if node is None:
        return []
    out: list[str] = []
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type == "identifier":
            value = _read_text(current, source).strip()
            if value:
                out.append(value)
            continue
        stack.extend(reversed(current.children))
    return out


def _package_name(path: Path) -> str:
    return ".".join(part[1:] for part in path.parent.parts if part.startswith("+") and len(part) > 1)


def _class_folder(path: Path) -> str | None:
    for part in reversed(path.parent.parts):
        if part.startswith("@") and len(part) > 1:
            return part[1:]
    return None


def _in_private_folder(path: Path) -> bool:
    return any(part.lower() == "private" for part in path.parent.parts)


def _qualified(package: str, name: str) -> str:
    return f"{package}.{name}" if package else name


def _function_name(node, source: bytes) -> str | None:
    name_node = _field(node, "name")
    if name_node is None:
        name_node = _child(node, "identifier")
    if name_node is None:
        return None
    name = _read_text(name_node, source).strip()
    raw = _read_text(node, source)
    prefix = raw[: max(0, name_node.start_byte - node.start_byte)]
    if re.search(r"\bget\.\s*$", prefix):
        return f"get.{name}"
    if re.search(r"\bset\.\s*$", prefix):
        return f"set.{name}"
    return name or None


def _function_arguments(node, source: bytes) -> list[str]:
    args = _child(node, "function_arguments")
    if args is None:
        return []
    # Preserve ignored (`~`) arguments so arity stays faithful, while callers
    # can still exclude the placeholder from lexical variable bindings.
    return [
        "~" if c.type == "ignored_argument" else _read_text(c, source).strip()
        for c in args.children
        if c.type in ("identifier", "ignored_argument")
        and (c.type == "ignored_argument" or _read_text(c, source).strip())
    ]


def _function_outputs(node, source: bytes) -> list[str]:
    output = _child(node, "function_output")
    return _identifiers(output, source)


def _call_arity(call_node) -> int:
    args = _child(call_node, "arguments")
    if args is None:
        return 0
    return sum(1 for c in args.children if c.is_named)


def _call_name(call_node, source: bytes) -> str:
    name_node = _field(call_node, "name")
    if name_node is None:
        name_node = next((c for c in call_node.children if c.type == "identifier"), None)
    return _read_text(name_node, source).strip() if name_node is not None else ""


def extract_matlab(path: Path) -> dict:
    """Extract MATLAB scripts, functions, classes, members, imports and calls."""
    try:
        import tree_sitter_matlab as tsmatlab
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-matlab not installed"}

    try:
        source = path.read_bytes()
        parser = Parser(Language(tsmatlab.language()))
        root = parser.parse(source).root_node
    except Exception as exc:  # parser initialization/read failure
        return {"nodes": [], "edges": [], "error": str(exc)}

    str_path = str(path)
    stem = _file_stem(path)
    package = _package_name(path)
    class_folder = _class_folder(path)
    is_private = _in_private_folder(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    raw_calls: list[dict] = []
    seen_nodes: set[str] = set()
    seen_edges: set[tuple[str, str, str, str]] = set()
    functions: list[dict[str, Any]] = []
    class_nodes: dict[str, str] = {}
    scope_variables: dict[str, set[str]] = {}
    scope_handles: dict[str, dict[str, str]] = {}
    scope_types: dict[str, dict[str, str]] = {}
    matlab_imports: list[dict[str, str]] = []
    seen_imports: set[tuple[str, str]] = set()

    def add_node(
        nid: str,
        label: str,
        line: int | None,
        *,
        source_file: str | None = str_path,
        node_type: str | None = None,
        **metadata: Any,
    ) -> None:
        if nid in seen_nodes:
            return
        seen_nodes.add(nid)
        node: dict[str, Any] = {
            "id": nid,
            "label": label,
            "file_type": "code",
            "source_file": source_file or "",
            "source_location": f"L{line}" if line else "",
            "language": _LANGUAGE,
            "language_family": _FAMILY,
        }
        if node_type:
            node["type"] = node_type
        node.update({k: v for k, v in metadata.items() if v not in (None, "", [], {})})
        nodes.append(node)

    def add_edge(
        src: str,
        tgt: str,
        relation: str,
        line: int | None,
        *,
        context: str | None = None,
        confidence: str = "EXTRACTED",
        score: float = 1.0,
    ) -> None:
        key = (src, tgt, relation, context or "")
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge: dict[str, Any] = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "confidence_score": score,
            "source_file": str_path,
            "source_location": f"L{line}" if line else "",
            "weight": 1.0,
            "language": _LANGUAGE,
            "language_family": _FAMILY,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    def ensure_stub(name: str, line: int, *, node_type: str | None = None) -> str:
        raw = name.strip()
        nid = _make_id(raw)
        add_node(
            nid,
            raw.split(".")[-1],
            None,
            source_file=None,
            node_type=node_type,
            qualified_name=raw,
            origin_file=str_path,
        )
        return nid

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1, node_type="file", package=package)

    package_nid: str | None = None
    if package:
        package_nid = _make_id("matlab_package", package)
        add_node(package_nid, package, 1, node_type="module", qualified_name=package)
        add_edge(package_nid, file_nid, "contains", 1, context="package_file")

    def emit_import(node, caller_nid: str = file_nid) -> bool:
        if node.type != "command":
            return False
        cmd = _child(node, "command_name")
        if cmd is None or _read_text(cmd, source).strip() != "import":
            return False
        args = [
            _read_text(c, source).strip()
            for c in node.children
            if c.type == "command_argument"
        ]
        line = node.start_point[0] + 1
        for raw in args:
            imported = raw.rstrip(".*")
            if not imported:
                continue
            module_nid = _make_id("matlab_package", imported)
            add_node(module_nid, imported, line, node_type="module", qualified_name=imported)
            add_edge(caller_nid, module_nid, "imports", line, context="import")
            import_key = (caller_nid, imported)
            if import_key not in seen_imports:
                seen_imports.add(import_key)
                matlab_imports.append({
                    "path": str_path,
                    "caller_nid": caller_nid,
                    "name": imported,
                    "raw": raw,
                })
        return True

    def class_property_type(property_node) -> str | None:
        name_node = _field(property_node, "name")
        passed_name = False
        for child in property_node.children:
            if child is name_node:
                passed_name = True
                continue
            if not passed_name or not child.is_named:
                continue
            if child.type in ("dimensions", "validation_functions", "default_value"):
                continue
            raw = _read_text(child, source).strip()
            if raw and re.match(r"^[A-Za-z]\w*(?:\.\w+)*$", raw):
                return raw
        return None

    def section_access(section) -> str | None:
        header = _read_text(section, source).splitlines()[0]
        match = re.search(r"\bAccess\s*=\s*([A-Za-z]\w*)", header, re.IGNORECASE)
        return match.group(1).lower() if match else None

    def create_function(
        node,
        container_nid: str,
        *,
        owner_class: str | None = None,
        parent_function: str | None = None,
        is_top_level: bool = False,
        is_primary: bool = False,
        declaration_only: bool = False,
        is_static: bool = False,
        visibility: str | None = None,
    ) -> str | None:
        name = _function_name(node, source)
        if not name:
            return None
        args = _function_arguments(node, source)
        outputs = _function_outputs(node, source)
        line = node.start_point[0] + 1
        if parent_function:
            nid = _make_id(parent_function, name)
            relation = "contains"
            label = f"{name}()"
            kind = "nested_function"
        elif owner_class:
            nid = _make_id(container_nid, name)
            relation = "method"
            label = f".{name}()"
            kind = "method"
        else:
            nid = _make_id(stem, name)
            relation = "contains"
            label = f"{name}()"
            kind = "function"
        qualified_name = _qualified(package, f"{owner_class}.{name}" if owner_class else name)
        add_node(
            nid,
            label,
            line,
            node_type=kind,
            symbol_name=name,
            qualified_name=qualified_name,
            owner_class_name=owner_class,
            parent_function_nid=parent_function,
            parameter_names=args,
            output_names=outputs,
            arity=len(args),
            is_primary=is_primary,
            is_exported=bool((is_primary and name == path.stem) or owner_class),
            file_name_matches=bool(not is_primary or name == path.stem),
            declaration_only=declaration_only,
            is_static=is_static,
            visibility=visibility or ("private" if is_private else "public"),
            package=package,
        )
        add_edge(container_nid, nid, relation, line)
        for existing in nodes:
            if existing.get("id") == nid:
                existing["_callable"] = True
                break
        scope_variables[nid] = {arg for arg in args if arg != "~"} | set(outputs)
        scope_handles[nid] = {}
        scope_types[nid] = {}
        for argument_block in (c for c in node.children if c.type == "arguments_statement"):
            for declaration in argument_block.children:
                if declaration.type != "property":
                    continue
                argument_name_node = _field(declaration, "name")
                argument_type = class_property_type(declaration)
                if argument_name_node is not None and argument_type:
                    scope_types[nid][_read_text(argument_name_node, source).strip()] = argument_type
        functions.append({
            "nid": nid,
            "node": node,
            "name": name,
            "owner_class": owner_class,
            "parent_function": parent_function,
            "is_top_level": is_top_level,
            "is_primary": is_primary,
            "is_static": is_static,
        })
        return nid

    def collect_bindings(
        node,
        variables: set[str],
        handles: dict[str, str],
        types: dict[str, str],
    ) -> None:
        if node.type in ("function_definition", "class_definition"):
            return
        if node.type == "assignment":
            left = _field(node, "left")
            right = _field(node, "right")
            if left is not None:
                if left.type in ("identifier", "multioutput_variable"):
                    variables.update(_identifiers(left, source))
            if left is not None and left.type == "identifier" and right is not None and right.type == "handle_operator":
                target_ids = _identifiers(right, source)
                if target_ids:
                    handles[_read_text(left, source).strip()] = ".".join(target_ids)
            if left is not None and left.type == "identifier" and right is not None and right.type == "function_call":
                constructor = _call_name(right, source)
                if constructor[:1].isupper() and constructor not in variables:
                    types[_read_text(left, source).strip()] = constructor
        for child in node.children:
            collect_bindings(child, variables, handles, types)

    def walk_function_children(node, fnid: str, owner_class: str | None) -> None:
        body = _child(node, "block")
        if body is None:
            return
        for child in body.children:
            if child.type == "function_definition":
                nested = create_function(
                    child,
                    fnid,
                    parent_function=fnid,
                    owner_class=owner_class,
                )
                if nested:
                    walk_function_children(child, nested, owner_class)

    # First pass: imports, classes and function definitions.
    top_functions = [c for c in root.children if c.type == "function_definition"]
    first_top_start = top_functions[0].start_byte if top_functions else None
    first_executable = next(
        (c for c in root.children if c.type not in ("comment",)),
        None,
    )
    is_function_file = bool(first_executable is not None and first_executable.type == "function_definition")

    for child in root.children:
        if emit_import(child):
            continue
        if child.type == "class_definition":
            name_node = _field(child, "name")
            if name_node is None:
                continue
            class_name = _read_text(name_node, source).strip()
            line = child.start_point[0] + 1
            # Namespace MATLAB type ids so a sibling Objective-C/C++ `Foo.h` /
            # `Foo.mm` declaration-definition pair can still collapse without a
            # same-stem MATLAB `Foo.m` joining that native collision group.
            class_nid = _make_id(stem, "matlab", class_name)
            class_nodes[class_name] = class_nid
            add_node(
                class_nid,
                class_name,
                line,
                node_type="class",
                symbol_name=class_name,
                qualified_name=_qualified(package, class_name),
                package=package,
            )
            add_edge(file_nid, class_nid, "contains", line)
            if package_nid:
                add_edge(package_nid, class_nid, "contains", line)
            superclasses = _child(child, "superclasses")
            if superclasses is not None:
                for base_node in superclasses.children:
                    if base_node.type != "property_name":
                        continue
                    base = _read_text(base_node, source).strip()
                    if base:
                        add_edge(class_nid, ensure_stub(base, line, node_type="class"), "inherits", line)
            for section in child.children:
                if section.type == "properties":
                    property_access = section_access(section)
                    for prop in section.children:
                        if prop.type != "property":
                            continue
                        pn = _field(prop, "name")
                        if pn is None:
                            continue
                        pname = _read_text(pn, source).strip()
                        ptype = class_property_type(prop)
                        pnid = _make_id(class_nid, "property", pname)
                        add_node(
                            pnid,
                            pname,
                            prop.start_point[0] + 1,
                            node_type="property",
                            symbol_name=pname,
                            owner_class_name=class_name,
                            declared_type=ptype,
                            visibility=property_access or ("private" if is_private else "public"),
                            package=package,
                        )
                        add_edge(class_nid, pnid, "defines", prop.start_point[0] + 1, context="property")
                        if ptype:
                            add_edge(
                                pnid,
                                ensure_stub(ptype, prop.start_point[0] + 1),
                                "references",
                                prop.start_point[0] + 1,
                                context="field",
                            )
                elif section.type == "events":
                    for event in section.children:
                        if event.type != "identifier":
                            continue
                        ename = _read_text(event, source).strip()
                        enid = _make_id(class_nid, "event", ename)
                        add_node(enid, ename, event.start_point[0] + 1, node_type="event", owner_class_name=class_name)
                        add_edge(class_nid, enid, "defines", event.start_point[0] + 1, context="event")
                elif section.type == "enumeration":
                    for enum in section.children:
                        if enum.type != "enum":
                            continue
                        ids = _identifiers(enum, source)
                        if not ids:
                            continue
                        ename = ids[0]
                        enid = _make_id(class_nid, "enum", ename)
                        add_node(
                            enid,
                            ename,
                            enum.start_point[0] + 1,
                            node_type="enum_case",
                            owner_class_name=class_name,
                        )
                        add_edge(class_nid, enid, "defines", enum.start_point[0] + 1, context="enum_case")
                elif section.type == "methods":
                    header = _read_text(section, source).splitlines()[0] if _read_text(section, source) else ""
                    static_section = bool(re.search(r"\bStatic\b", header, re.IGNORECASE))
                    method_access = section_access(section)
                    for method in section.children:
                        if method.type not in ("function_definition", "function_signature"):
                            continue
                        mid = create_function(
                            method,
                            class_nid,
                            owner_class=class_name,
                            declaration_only=method.type == "function_signature",
                            is_static=static_section,
                            visibility=method_access,
                        )
                        if mid and method.type == "function_definition":
                            walk_function_children(method, mid, class_name)
            continue
        if child.type == "function_definition":
            if class_folder:
                class_nid = class_nodes.get(class_folder) or _make_id("matlab", class_folder)
                if class_folder not in class_nodes:
                    add_node(
                        class_nid,
                        class_folder,
                        None,
                        source_file=None,
                        node_type="class",
                        symbol_name=class_folder,
                        qualified_name=_qualified(package, class_folder),
                        # Every method file under one @Class folder refers to the
                        # same old-style class. A folder-stable origin prevents
                        # collision disambiguation from splitting that class into
                        # one absolute-path-derived node per method file.
                        origin_file=str(path.parent),
                    )
                fnid = create_function(child, class_nid, owner_class=class_folder)
            else:
                is_primary = is_function_file and child.start_byte == first_top_start
                fnid = create_function(
                    child,
                    file_nid,
                    is_top_level=True,
                    is_primary=is_primary,
                )
                if fnid and package_nid and is_primary:
                    add_edge(package_nid, fnid, "contains", child.start_point[0] + 1)
            if fnid:
                walk_function_children(child, fnid, class_folder)

    # Script scope lexical bindings.  A function file has no executable script
    # scope before its first top-level function.
    script_variables: set[str] = set()
    script_handles: dict[str, str] = {}
    script_types: dict[str, str] = {}
    for child in root.children:
        if child.type not in ("function_definition", "class_definition"):
            collect_bindings(child, script_variables, script_handles, script_types)

    for fn in functions:
        body = _child(fn["node"], "block")
        if body is not None:
            collect_bindings(
                body,
                scope_variables[fn["nid"]],
                scope_handles[fn["nid"]],
                scope_types[fn["nid"]],
            )

    function_by_nid = {str(fn["nid"]): fn for fn in functions}

    def caller_ancestors(caller: str) -> list[str]:
        ancestors: list[str] = []
        current = caller
        seen: set[str] = set()
        while current and current not in seen:
            seen.add(current)
            ancestors.append(current)
            info = function_by_nid.get(current)
            current = str(info.get("parent_function") or "") if info else ""
        return ancestors

    def local_candidates(caller: str, name: str) -> list[str]:
        matches = [fn for fn in functions if fn.get("name") == name]
        if not matches:
            return []

        ancestors = caller_ancestors(caller)
        ancestor_rank = {nid: rank for rank, nid in enumerate(ancestors)}
        visible_nested = [
            fn for fn in matches
            if fn.get("parent_function") in ancestor_rank
        ]
        if visible_nested:
            nearest = min(ancestor_rank[str(fn["parent_function"])] for fn in visible_nested)
            return [
                str(fn["nid"]) for fn in visible_nested
                if ancestor_rank[str(fn["parent_function"])] == nearest
            ]

        caller_info = function_by_nid.get(caller, {})
        caller_owner = caller_info.get("owner_class")
        if caller_owner:
            owned = [
                fn for fn in matches
                if not fn.get("parent_function") and fn.get("owner_class") == caller_owner
            ]
            if owned:
                return [str(fn["nid"]) for fn in owned]

        # Local/top-level functions are file-scoped. Class methods and nested
        # functions never participate in this bare fallback.
        return [
            str(fn["nid"]) for fn in matches
            if fn.get("is_top_level")
            and not fn.get("owner_class")
            and not fn.get("parent_function")
        ]

    def emit_raw(
        caller: str,
        callee: str,
        node,
        *,
        qualifier: str | None = None,
        receiver_type: str | None = None,
        owner_class: str | None = None,
        indirect: bool = False,
        receiver_is_self: bool = False,
        relation: str | None = None,
    ) -> None:
        raw_calls.append({
            "caller_nid": caller,
            "callee": callee,
            "qualifier": qualifier,
            "receiver": qualifier,
            "receiver_type": receiver_type,
            "is_member_call": bool(qualifier),
            "receiver_is_self": receiver_is_self,
            "owner_class": owner_class,
            "indirect": indirect,
            "requested_relation": relation,
            "argument_count": _call_arity(node) if node.type == "function_call" else None,
            "source_file": str_path,
            "source_location": f"L{node.start_point[0] + 1}",
            "language": _LANGUAGE,
            "language_family": _FAMILY,
            "defer_to_language_resolver": True,
        })

    def split_qualified_target(target: str) -> tuple[str, str | None]:
        parts = [part for part in target.split(".") if part]
        if not parts:
            return "", None
        return parts[-1], ".".join(parts[:-1]) or None

    def walk_calls(
        node,
        caller: str,
        variables: set[str],
        handles: dict[str, str],
        types: dict[str, str],
        owner_class: str | None,
        self_names: set[str],
    ) -> None:
        if node.type in ("function_definition", "class_definition"):
            return
        if node.type == "command":
            if emit_import(node, caller):
                return
            command_node = _child(node, "command_name")
            command_name = (
                _read_text(command_node, source).strip()
                if command_node is not None else ""
            )
            if command_name and command_name not in variables:
                local = local_candidates(caller, command_name)
                if len(local) == 1 and local[0] != caller:
                    add_edge(
                        caller,
                        local[0],
                        "calls",
                        node.start_point[0] + 1,
                        context="command",
                    )
                else:
                    emit_raw(caller, command_name, node, owner_class=owner_class)
            return
        if node.type == "field_expression":
            named_children = [child for child in node.children if child.is_named]
            field_node = next(
                (child for child in reversed(named_children) if child.type == "function_call"),
                None,
            )
            if field_node is not None:
                call_index = named_children.index(field_node)
                qualifier_nodes = named_children[:call_index]
                callee = _call_name(field_node, source)
                qualifier = ".".join(
                    _read_text(part, source).strip()
                    for part in qualifier_nodes
                    if _read_text(part, source).strip()
                )
                if callee:
                    emit_raw(
                        caller,
                        callee,
                        field_node,
                        qualifier=qualifier,
                        receiver_type=types.get(qualifier),
                        owner_class=owner_class,
                        receiver_is_self=qualifier in self_names,
                    )
                # Walk arguments, but not the field call again.
                args = _child(field_node, "arguments")
                if args is not None:
                    for arg in args.children:
                        walk_calls(arg, caller, variables, handles, types, owner_class, self_names)
                for qualifier_node in qualifier_nodes:
                    walk_calls(
                        qualifier_node,
                        caller,
                        variables,
                        handles,
                        types,
                        owner_class,
                        self_names,
                    )
                return
        if node.type == "function_call":
            callee = _call_name(node, source)
            if callee:
                if callee == "feval":
                    args = _child(node, "arguments")
                    first_arg = next((c for c in (args.children if args is not None else []) if c.is_named), None)
                    target = ""
                    if first_arg is not None and first_arg.type == "identifier":
                        handle_name = _read_text(first_arg, source).strip()
                        target = handles.get(handle_name, "")
                    elif first_arg is not None and first_arg.type == "handle_operator":
                        target_ids = _identifiers(first_arg, source)
                        target = ".".join(target_ids)
                    target_name, target_qualifier = split_qualified_target(target)
                    if target_name:
                        local = [] if target_qualifier else local_candidates(caller, target_name)
                        if len(local) == 1:
                            add_edge(
                                caller,
                                local[0],
                                "indirect_call",
                                node.start_point[0] + 1,
                                context="feval",
                                confidence="INFERRED",
                                score=0.8,
                            )
                        else:
                            emit_raw(
                                caller,
                                target_name,
                                node,
                                qualifier=target_qualifier,
                                receiver_type=types.get(target_qualifier or ""),
                                owner_class=owner_class,
                                indirect=True,
                            )
                elif callee in handles:
                    target_name, target_qualifier = split_qualified_target(handles[callee])
                    local = [] if target_qualifier else local_candidates(caller, target_name)
                    if len(local) == 1:
                        add_edge(
                            caller,
                            local[0],
                            "indirect_call",
                            node.start_point[0] + 1,
                            context="function_handle",
                            confidence="INFERRED",
                            score=0.8,
                        )
                    else:
                        emit_raw(
                            caller,
                            target_name,
                            node,
                            qualifier=target_qualifier,
                            receiver_type=types.get(target_qualifier or ""),
                            owner_class=owner_class,
                            indirect=True,
                        )
                elif callee not in variables:
                    local = local_candidates(caller, callee)
                    if len(local) == 1 and local[0] != caller:
                        add_edge(caller, local[0], "calls", node.start_point[0] + 1, context="call")
                    else:
                        emit_raw(caller, callee, node, owner_class=owner_class)
            args = _child(node, "arguments")
            if args is not None:
                for arg in args.children:
                    walk_calls(arg, caller, variables, handles, types, owner_class, self_names)
            return
        if node.type == "handle_operator":
            ids = _identifiers(node, source)
            if ids:
                target_name = ids[-1]
                target_qualifier = ".".join(ids[:-1]) or None
                if target_name not in variables:
                    emit_raw(
                        caller,
                        target_name,
                        node,
                        qualifier=target_qualifier,
                        receiver_type=types.get(target_qualifier or ""),
                        owner_class=owner_class,
                        relation="references",
                    )
            return
        for child in node.children:
            walk_calls(child, caller, variables, handles, types, owner_class, self_names)

    # Calls in script statements belong to the file node.
    for child in root.children:
        if child.type not in ("function_definition", "class_definition"):
            walk_calls(
                child,
                file_nid,
                script_variables,
                script_handles,
                script_types,
                None,
                set(),
            )

    def enclosing_self_names(fn: dict[str, Any]) -> set[str]:
        current = fn
        seen: set[str] = set()
        while current:
            nid = str(current.get("nid") or "")
            if not nid or nid in seen:
                break
            seen.add(nid)
            owner = str(current.get("owner_class") or "")
            if (
                owner
                and not current.get("parent_function")
                and not current.get("is_static")
                and current.get("name") != owner
            ):
                args = _function_arguments(current["node"], source)
                if args and args[0] != "~":
                    return {args[0]}
                return set()
            parent = str(current.get("parent_function") or "")
            current = function_by_nid.get(parent, {}) if parent else {}
        return set()

    for fn in functions:
        body = _child(fn["node"], "block")
        if body is None:
            continue
        walk_calls(
            body,
            fn["nid"],
            scope_variables[fn["nid"]],
            scope_handles[fn["nid"]],
            scope_types[fn["nid"]],
            fn["owner_class"],
            enclosing_self_names(fn),
        )

    return {
        "nodes": nodes,
        "edges": edges,
        "raw_calls": raw_calls,
        "matlab_imports": matlab_imports,
        "language": _LANGUAGE,
        "language_family": _FAMILY,
    }


def _matlab_private_visible(definition_file: str, caller_file: str) -> bool:
    dpath = Path(definition_file)
    if dpath.parent.name.lower() != "private":
        return True
    try:
        # MATLAB private functions are visible only to functions in the folder
        # immediately above `private` (including an @Class folder), not to all
        # descendants of that folder.
        return Path(caller_file).resolve().parent == dpath.parent.parent.resolve()
    except OSError:
        return False


def resolve_matlab_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve MATLAB calls with package, class, lexical and visibility evidence."""
    matlab_results = [r for r in per_file if r.get("language") == _LANGUAGE]
    if not matlab_results:
        return

    node_by_id = {str(n.get("id")): n for n in all_nodes if n.get("id")}
    definitions = [
        n for n in all_nodes
        if n.get("language") == _LANGUAGE and n.get("_callable") and n.get("symbol_name")
    ]
    classes = [
        n for n in all_nodes
        if n.get("language") == _LANGUAGE
        and n.get("type") == "class"
        and (n.get("source_file") or n.get("origin_file"))
    ]
    by_name: dict[str, list[dict]] = {}
    by_qualified: dict[str, list[dict]] = {}
    for definition in definitions:
        by_name.setdefault(str(definition["symbol_name"]), []).append(definition)
        qname = definition.get("qualified_name")
        if qname:
            by_qualified.setdefault(str(qname), []).append(definition)
    classes_by_name: dict[str, list[dict]] = {}
    for cls in classes:
        classes_by_name.setdefault(str(cls.get("symbol_name") or cls.get("label")), []).append(cls)
        if cls.get("qualified_name"):
            classes_by_name.setdefault(str(cls["qualified_name"]), []).append(cls)

    owner_by_method: dict[str, str] = {
        str(e["target"]): str(e["source"])
        for e in all_edges
        if e.get("relation") == "method"
    }
    existing = {(e.get("source"), e.get("target"), e.get("relation")) for e in all_edges}

    imports_by_file: dict[str, set[str]] = {}
    imports_by_caller: dict[str, set[str]] = {}
    for result in matlab_results:
        for item in result.get("matlab_imports", []):
            imported = str(item.get("name", ""))
            scope = str(item.get("caller_nid", ""))
            if node_by_id.get(scope, {}).get("type") == "file":
                imports_by_file.setdefault(str(item.get("path", "")), set()).add(imported)
            elif scope:
                imports_by_caller.setdefault(scope, set()).add(imported)

    def lexical_ancestors(caller: str) -> list[str]:
        ancestors: list[str] = []
        current = caller
        seen: set[str] = set()
        while current and current not in seen:
            seen.add(current)
            ancestors.append(current)
            current = str(node_by_id.get(current, {}).get("parent_function_nid") or "")
        return ancestors

    def bare_visible(candidate: dict, caller: str) -> bool:
        parent = str(candidate.get("parent_function_nid") or "")
        if parent:
            return parent in lexical_ancestors(caller)
        owner = str(candidate.get("owner_class_name") or "")
        if owner:
            caller_owner = str(node_by_id.get(caller, {}).get("owner_class_name") or "")
            return bool(caller_owner and caller_owner == owner)
        return True

    def visible(candidates: list[dict], caller_file: str) -> list[dict]:
        return [
            candidate for candidate in candidates
            if _matlab_private_visible(str(candidate.get("source_file", "")), caller_file)
        ]

    for result in matlab_results:
        for rc in result.get("raw_calls", []):
            if not rc.get("defer_to_language_resolver"):
                continue
            caller = str(rc.get("caller_nid", ""))
            callee = str(rc.get("callee", ""))
            caller_file = str(rc.get("source_file", ""))
            if not caller or not callee:
                continue
            qualifier = str(rc.get("qualifier") or "")
            candidates: list[dict] = []
            confidence = "INFERRED"
            score = 0.8

            if rc.get("receiver_is_self") and rc.get("owner_class"):
                owner = str(rc["owner_class"])
                candidates = [d for d in by_name.get(callee, []) if d.get("owner_class_name") == owner]
                confidence, score = "EXTRACTED", 1.0
            elif rc.get("receiver_type"):
                receiver_type = str(rc["receiver_type"]).split(".")[-1]
                candidates = [
                    d for d in by_name.get(callee, [])
                    if d.get("owner_class_name") == receiver_type
                ]
            elif qualifier:
                # Class-qualified static/member call.
                class_hits = classes_by_name.get(qualifier, [])
                if len({str(c.get("id")) for c in class_hits}) == 1:
                    owner_name = str(class_hits[0].get("symbol_name") or class_hits[0].get("label"))
                    candidates = [d for d in by_name.get(callee, []) if d.get("owner_class_name") == owner_name]
                if not candidates:
                    # Package-qualified free function (pkg.func()).
                    candidates = by_qualified.get(f"{qualifier}.{callee}", [])
                if candidates:
                    confidence, score = "EXTRACTED", 1.0
            else:
                same_file = [
                    d for d in by_name.get(callee, [])
                    if str(d.get("source_file")) == caller_file
                    and bare_visible(d, caller)
                ]
                if same_file:
                    ancestors = lexical_ancestors(caller)
                    nested = [
                        d for d in same_file
                        if str(d.get("parent_function_nid") or "") in ancestors
                    ]
                    if nested:
                        ranks = {
                            str(d["id"]): ancestors.index(str(d["parent_function_nid"]))
                            for d in nested
                        }
                        nearest = min(ranks.values())
                        nested = [d for d in nested if ranks[str(d["id"])] == nearest]
                    candidates = nested or same_file
                    confidence, score = "EXTRACTED", 1.0
                else:
                    caller_node = node_by_id.get(caller, {})
                    caller_package = str(caller_node.get("package") or "")
                    free_functions = [
                        d for d in by_name.get(callee, [])
                        if not d.get("owner_class_name")
                        and not d.get("parent_function_nid")
                    ]
                    package_hits = [
                        d for d in free_functions
                        if d.get("is_exported") and str(d.get("package") or "") == caller_package
                    ]
                    if package_hits:
                        candidates = package_hits
                    else:
                        imported = set(imports_by_file.get(caller_file, set()))
                        for scope in lexical_ancestors(caller):
                            imported.update(imports_by_caller.get(scope, set()))
                        imported_hits = [
                            d for d in free_functions
                            if d.get("is_exported") and any(
                                str(d.get("qualified_name", "")).startswith(name + ".")
                                or str(d.get("qualified_name", "")) == name
                                for name in imported
                            )
                        ]
                        candidates = imported_hits or [d for d in free_functions if d.get("is_exported")]
            candidates = visible(candidates, caller_file)

            # A capitalized bare name may be a class constructor.  This is the
            # only safe interpretation when there is exactly one class and no
            # function candidate; unknown A(1) remains unresolved.
            relation = str(
                rc.get("requested_relation")
                or ("indirect_call" if rc.get("indirect") else "calls")
            )
            if (
                not candidates
                and not qualifier
                and not rc.get("requested_relation")
                and callee[:1].isupper()
            ):
                class_hits = classes_by_name.get(callee, [])
                unique_classes = {str(c.get("id")): c for c in class_hits}
                if len(unique_classes) == 1:
                    target = next(iter(unique_classes.values()))
                    relation = "instantiates"
                    candidates = [target]
                    confidence, score = "EXTRACTED", 1.0

            unique = {str(c.get("id")): c for c in candidates if c.get("id")}
            if len(unique) != 1:
                continue
            target = next(iter(unique.values()))
            target_id = str(target["id"])
            if target_id == caller or (caller, target_id, relation) in existing:
                continue
            existing.add((caller, target_id, relation))
            all_edges.append({
                "source": caller,
                "target": target_id,
                "relation": relation,
                "context": (
                    "function_handle_reference" if relation == "references"
                    else "function_handle" if rc.get("indirect")
                    else "call"
                ),
                "confidence": confidence,
                "confidence_score": score,
                "source_file": caller_file,
                "source_location": rc.get("source_location"),
                "weight": 1.0,
                "language": _LANGUAGE,
                "language_family": _FAMILY,
            })
