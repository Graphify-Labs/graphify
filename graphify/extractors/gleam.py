"""Deterministic Gleam extraction and import-backed cross-file resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id, _read_text

_GLEAM_PRELUDE_TYPES = frozenset(
    {
        "BitArray",
        "Bool",
        "Dynamic",
        "Float",
        "Int",
        "List",
        "Nil",
        "Result",
        "String",
        "UtfCodepoint",
    }
)
_GLEAM_TYPE_KINDS = frozenset({"type_definition", "type_alias", "external_type"})
_GLEAM_VALUE_KINDS = frozenset({"function", "external_function", "constant"})
_GLEAM_CALLABLE_KINDS = frozenset({"function", "external_function", "data_constructor"})
_GLEAM_STUB_TYPES = frozenset({"module", "symbol"})


def _gleam_package_root(path: Path) -> Path | None:
    """Return the nearest ancestor containing a gleam.toml package manifest."""
    current = path.parent
    while True:
        if (current / "gleam.toml").is_file():
            return current
        if current.parent == current:
            return None
        current = current.parent


def _gleam_module_name(path: Path) -> str:
    """Derive a module path from the nearest Gleam source-root segment."""
    without_suffix = path.with_suffix("")
    parts = without_suffix.parts
    source_root_index = None
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] in {"src", "test", "dev"}:
            source_root_index = index
            break
    if source_root_index is None:
        return without_suffix.name
    return "/".join(parts[source_root_index + 1 :])


def _line(node: Any) -> int:
    return node.start_point[0] + 1


def extract_gleam(path: Path) -> dict:
    """Extract declarations, imports, type references, and calls from Gleam source."""
    try:
        from tree_sitter import Parser
        from tree_sitter_language_pack import get_language

        parser = Parser(get_language("gleam"))
    except Exception as exc:
        return {
            "nodes": [],
            "edges": [],
            "error": (
                f"tree_sitter_language_pack not installed or Gleam parser unavailable: {exc}"
            ),
        }

    try:
        source = path.read_bytes()
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}: {exc}"}

    try:
        root = parser.parse(source).root_node
    except Exception as exc:
        return {
            "nodes": [],
            "edges": [],
            "error": (
                f"tree_sitter_language_pack not installed or Gleam parser unavailable: {exc}"
            ),
        }

    str_path = str(path)
    stem = _file_stem(path)
    module_name = _gleam_module_name(path)
    package_root = _gleam_package_root(path)
    file_nid = _make_id(str_path)
    nodes: list[dict] = []
    edges: list[dict] = []
    raw_calls: list[dict] = []
    imports: list[dict] = []
    seen_node_ids: set[str] = set()
    seen_call_pairs: set[tuple[str, str]] = set()
    seen_raw_calls: set[tuple[str, str, str | None]] = set()

    def add_node(
        node_id: str,
        label: str,
        line: int | None,
        *,
        node_type: str | None = None,
        source_file: str = str_path,
    ) -> None:
        if node_id in seen_node_ids:
            return
        seen_node_ids.add(node_id)
        node = {
            "id": node_id,
            "label": label,
            "file_type": "code",
            "source_file": source_file,
            "source_location": f"L{line}" if line is not None else "",
        }
        if node_type is not None:
            node["type"] = node_type
        nodes.append(node)

    def add_edge(
        source_id: str,
        target_id: str,
        relation: str,
        line: int,
        *,
        context: str | None = None,
        hints: dict[str, object] | None = None,
    ) -> dict:
        edge = {
            "source": source_id,
            "target": target_id,
            "relation": relation,
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if context is not None:
            edge["context"] = context
        if hints:
            edge.update(hints)
        edges.append(edge)
        return edge

    add_node(file_nid, path.name, 1)

    module_aliases: dict[str, str] = {}
    unqualified_imports: dict[str, dict] = {}

    for child in root.named_children:
        if child.type != "import":
            continue
        module_node = child.child_by_field_name("module")
        if module_node is None:
            module_node = next(
                (candidate for candidate in child.named_children if candidate.type == "module"),
                None,
            )
        if module_node is None:
            continue
        imported_module = _read_text(module_node, source)
        explicit_alias = None
        imports_node = child.child_by_field_name("imports")
        for candidate in child.named_children:
            if candidate is module_node or candidate is imports_node:
                continue
            if candidate.type == "identifier":
                explicit_alias = _read_text(candidate, source)
                break
        module_alias = explicit_alias or imported_module.rsplit("/", 1)[-1]
        module_aliases[module_alias] = imported_module
        symbols: list[dict] = []
        if imports_node is not None:
            for symbol_node in imports_node.named_children:
                if symbol_node.type != "unqualified_import":
                    continue
                name_node = symbol_node.child_by_field_name("name")
                alias_node = symbol_node.child_by_field_name("alias")
                if name_node is None:
                    continue
                symbol_name = _read_text(name_node, source)
                local_name = (
                    _read_text(alias_node, source) if alias_node is not None else symbol_name
                )
                if name_node.type == "type_identifier":
                    symbol_kind = "type"
                elif name_node.type == "constructor_name":
                    symbol_kind = "constructor"
                else:
                    symbol_kind = "value"
                symbol = {
                    "name": symbol_name,
                    "local_name": local_name,
                    "kind": symbol_kind,
                }
                symbols.append(symbol)
                unqualified_imports[local_name] = {
                    "module": imported_module,
                    **symbol,
                }

        import_info = {
            "module": imported_module,
            "module_alias": module_alias,
            "line": _line(child),
            "symbols": symbols,
        }
        imports.append(import_info)
        module_stub_id = _make_id("gleam_module", imported_module)
        add_node(
            module_stub_id,
            imported_module,
            None,
            node_type="module",
            source_file="",
        )
        add_edge(
            file_nid,
            module_stub_id,
            "imports",
            _line(child),
            context="module",
            hints={
                "gleam_module": imported_module,
                "gleam_module_alias": module_alias,
            },
        )
        for symbol in symbols:
            symbol_stub_id = _make_id("gleam_symbol", imported_module, symbol["name"])
            add_node(
                symbol_stub_id,
                symbol["name"],
                None,
                node_type="symbol",
                source_file="",
            )
            add_edge(
                file_nid,
                symbol_stub_id,
                "imports",
                _line(child),
                context="symbol",
                hints={
                    "gleam_module": imported_module,
                    "gleam_import_name": symbol["name"],
                    "gleam_local_name": symbol["local_name"],
                    "gleam_symbol_kind": symbol["kind"],
                    "gleam_module_alias": module_alias,
                },
            )

    declarations: list[tuple[Any, str, str]] = []
    functions: list[tuple[Any, str, str, Any | None]] = []
    type_nodes_by_name: dict[str, str] = {}
    callable_nodes_by_name: dict[str, str] = {}
    pending_external_attribute = False

    for child in root.named_children:
        if child.type == "attribute":
            attribute_name = child.child_by_field_name("name")
            pending_external_attribute = (
                attribute_name is not None and _read_text(attribute_name, source) == "external"
            )
            continue
        if child.type == "comment":
            continue

        if child.type == "function":
            name_node = child.child_by_field_name("name")
            body_node = child.child_by_field_name("body")
            if name_node is not None:
                name = _read_text(name_node, source)
                node_type = (
                    "external_function"
                    if pending_external_attribute or body_node is None
                    else "function"
                )
                node_id = _make_id(stem, name)
                add_node(node_id, f"{name}()", _line(child), node_type=node_type)
                add_edge(file_nid, node_id, "contains", _line(child))
                callable_nodes_by_name[name] = node_id
                declarations.append((child, node_id, node_type))
                functions.append((child, node_id, name, body_node))
            pending_external_attribute = False
            continue

        pending_external_attribute = False
        if child.type == "constant":
            name_node = child.child_by_field_name("name")
            if name_node is None:
                continue
            name = _read_text(name_node, source)
            node_id = _make_id(stem, name)
            add_node(node_id, name, _line(child), node_type="constant")
            add_edge(file_nid, node_id, "contains", _line(child))
            declarations.append((child, node_id, "constant"))
            continue

        if child.type in _GLEAM_TYPE_KINDS:
            type_name_node = next(
                (candidate for candidate in child.named_children if candidate.type == "type_name"),
                None,
            )
            if type_name_node is None:
                continue
            name_node = type_name_node.child_by_field_name("name")
            if name_node is None:
                name_node = next(iter(type_name_node.named_children), None)
            if name_node is None:
                continue
            name = _read_text(name_node, source)
            node_id = _make_id(stem, name)
            add_node(node_id, name, _line(child), node_type=child.type)
            add_edge(file_nid, node_id, "contains", _line(child))
            type_nodes_by_name[name] = node_id
            declarations.append((child, node_id, child.type))

            if child.type == "type_definition":
                for constructors in child.named_children:
                    if constructors.type != "data_constructors":
                        continue
                    for constructor in constructors.named_children:
                        if constructor.type != "data_constructor":
                            continue
                        constructor_name_node = constructor.child_by_field_name("name")
                        if constructor_name_node is None:
                            continue
                        constructor_name = _read_text(constructor_name_node, source)
                        constructor_id = _make_id(node_id, constructor_name)
                        add_node(
                            constructor_id,
                            constructor_name,
                            _line(constructor),
                            node_type="data_constructor",
                        )
                        add_edge(node_id, constructor_id, "case_of", _line(constructor))
                        callable_nodes_by_name[constructor_name] = constructor_id
                        declarations.append((constructor, constructor_id, "data_constructor"))

    def add_type_references(owner_id: str, type_node: Any, context: str) -> None:
        references: list[tuple[str | None, str, int]] = []

        def collect(node: Any) -> None:
            if node.type == "remote_type_identifier":
                module_node = node.child_by_field_name("module")
                name_node = node.child_by_field_name("name")
                if module_node is not None and name_node is not None:
                    references.append(
                        (
                            _read_text(module_node, source),
                            _read_text(name_node, source),
                            _line(node),
                        )
                    )
                return
            if node.type == "type_identifier":
                references.append((None, _read_text(node, source), _line(node)))
                return
            if node.type == "type_var":
                return
            for nested in node.named_children:
                collect(nested)

        collect(type_node)
        seen_references: set[tuple[str | None, str, int]] = set()
        for receiver, name, reference_line in references:
            key = (receiver, name, reference_line)
            if key in seen_references or name in _GLEAM_PRELUDE_TYPES:
                continue
            seen_references.add(key)
            if receiver is None and name in type_nodes_by_name:
                add_edge(
                    owner_id,
                    type_nodes_by_name[name],
                    "references",
                    reference_line,
                    context=context,
                )
                continue

            if receiver is not None:
                imported_module = module_aliases.get(receiver, receiver)
                import_name = name
                local_name = name
                module_alias = receiver
            else:
                imported = unqualified_imports.get(name)
                imported_module = imported["module"] if imported is not None else module_name
                import_name = imported["name"] if imported is not None else name
                local_name = name
                module_alias = None
            stub_id = _make_id("gleam_symbol", imported_module, import_name)
            add_node(stub_id, import_name, None, node_type="symbol", source_file="")
            hints: dict[str, object] = {
                "gleam_module": imported_module,
                "gleam_import_name": import_name,
                "gleam_local_name": local_name,
                "gleam_symbol_kind": "type",
            }
            if module_alias is not None:
                hints["gleam_module_alias"] = module_alias
            add_edge(
                owner_id,
                stub_id,
                "references",
                reference_line,
                context=context,
                hints=hints,
            )

    for declaration, owner_id, declaration_kind in declarations:
        if declaration_kind in {"function", "external_function"}:
            parameters = declaration.child_by_field_name("parameters")
            if parameters is not None:
                for parameter in parameters.named_children:
                    if parameter.type != "function_parameter":
                        continue
                    parameter_type = parameter.child_by_field_name("type")
                    if parameter_type is not None:
                        add_type_references(owner_id, parameter_type, "parameter_type")
            return_type = declaration.child_by_field_name("return_type")
            if return_type is not None:
                add_type_references(owner_id, return_type, "return_type")
        elif declaration_kind == "constant":
            annotation = next(
                (candidate for candidate in declaration.named_children if candidate.type == "type"),
                None,
            )
            if annotation is not None:
                add_type_references(owner_id, annotation, "type")
        elif declaration_kind == "type_alias":
            alias_body = next(
                (
                    candidate
                    for candidate in reversed(declaration.named_children)
                    if candidate.type == "type"
                ),
                None,
            )
            if alias_body is not None:
                add_type_references(owner_id, alias_body, "type")
        elif declaration_kind == "data_constructor":
            arguments = declaration.child_by_field_name("arguments")
            if arguments is not None:
                for argument in arguments.named_children:
                    if argument.type != "data_constructor_argument":
                        continue
                    field_type = argument.child_by_field_name("value")
                    if field_type is None:
                        field_type = next(
                            (
                                candidate
                                for candidate in argument.named_children
                                if candidate.type == "type"
                            ),
                            None,
                        )
                    if field_type is not None:
                        add_type_references(owner_id, field_type, "field")

    def record_call(
        caller_id: str,
        callee: str,
        receiver: str | None,
        member_call: bool,
        call_line: int,
    ) -> None:
        if not callee:
            return
        if receiver is None:
            target_id = callable_nodes_by_name.get(callee)
            if target_id is not None:
                if target_id != caller_id and (caller_id, target_id) not in seen_call_pairs:
                    seen_call_pairs.add((caller_id, target_id))
                    add_edge(
                        caller_id,
                        target_id,
                        "calls",
                        call_line,
                        context="call",
                    )
                return
        raw_key = (caller_id, callee, receiver)
        if raw_key in seen_raw_calls:
            return
        seen_raw_calls.add(raw_key)
        raw_calls.append(
            {
                "caller_nid": caller_id,
                "callee": callee,
                "receiver": receiver,
                "is_member_call": member_call,
                "language": "gleam",
                "source_file": str_path,
                "source_location": f"L{call_line}",
            }
        )

    def call_target(node: Any) -> tuple[str, str | None, bool] | None:
        if node.type in {"identifier", "constructor_name"}:
            return _read_text(node, source), None, False
        if node.type != "field_access":
            return None
        receiver_node = node.child_by_field_name("record")
        field_node = node.child_by_field_name("field")
        if receiver_node is None or field_node is None or receiver_node.type != "identifier":
            return None
        receiver = _read_text(receiver_node, source)
        if receiver not in module_aliases:
            return None
        return _read_text(field_node, source), receiver, True

    def walk_calls(node: Any, caller_id: str) -> None:
        if node.type == "function_call":
            function_node = node.child_by_field_name("function")
            if function_node is not None:
                target = call_target(function_node)
                if target is not None:
                    record_call(caller_id, *target, _line(node))
        elif node.type == "binary_expression":
            operator = node.child_by_field_name("operator")
            right = node.child_by_field_name("right")
            if operator is not None and _read_text(operator, source) == "|>" and right is not None:
                target = call_target(right)
                if target is not None:
                    record_call(caller_id, *target, _line(right))
        for nested in node.named_children:
            walk_calls(nested, caller_id)

    for _, function_id, _, body in functions:
        if body is not None:
            walk_calls(body, function_id)

    return {
        "nodes": nodes,
        "edges": edges,
        "raw_calls": raw_calls,
        "gleam_module": {
            "name": module_name,
            "package_root": str(package_root) if package_root is not None else None,
        },
        "gleam_imports": imports,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def resolve_gleam_symbols(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Resolve Gleam imports, types, and calls only through explicit module evidence."""
    file_records: list[dict] = []
    record_by_source: dict[str, dict] = {}
    modules: dict[str, list[dict]] = {}

    for result in per_file:
        module_metadata = result.get("gleam_module")
        if not isinstance(module_metadata, dict):
            continue
        file_node = next(
            (
                node
                for node in result.get("nodes", [])
                if node.get("source_file") and str(node.get("label", "")).endswith(".gleam")
            ),
            None,
        )
        if file_node is None:
            continue
        source_file = str(file_node["source_file"])
        record = {
            "result": result,
            "file_node": file_node,
            "source_file": source_file,
            "module": str(module_metadata.get("name", "")),
            "package_root": module_metadata.get("package_root"),
            "imports": result.get("gleam_imports", []),
            "symbols": {},
        }
        for node in result.get("nodes", []):
            node_type = node.get("type")
            if node_type not in (_GLEAM_TYPE_KINDS | _GLEAM_VALUE_KINDS | _GLEAM_CALLABLE_KINDS):
                continue
            label = str(node.get("label", ""))
            name = label[:-2] if label.endswith("()") else label
            record["symbols"].setdefault(name, []).append(node)
        file_records.append(record)
        record_by_source[source_file] = record
        modules.setdefault(record["module"], []).append(record)

    if not file_records:
        return

    def select_module(importer: dict, module_name: str) -> tuple[str, dict | None]:
        candidates = modules.get(module_name, [])
        if not candidates:
            return "external", None
        if len(candidates) == 1:
            return "resolved", candidates[0]
        importer_root = importer.get("package_root")
        if importer_root is not None:
            same_package = [
                candidate
                for candidate in candidates
                if candidate.get("package_root") == importer_root
            ]
            if len(same_package) == 1:
                return "resolved", same_package[0]
        return "ambiguous", None

    def symbol_candidates(module: dict, name: str, symbol_kind: str) -> list[dict]:
        candidates = module["symbols"].get(name, [])
        if symbol_kind == "type":
            allowed = _GLEAM_TYPE_KINDS
        elif symbol_kind == "constructor":
            allowed = frozenset({"data_constructor"})
        elif symbol_kind == "callable":
            allowed = _GLEAM_CALLABLE_KINDS
        else:
            allowed = _GLEAM_VALUE_KINDS
        return [candidate for candidate in candidates if candidate.get("type") in allowed]

    def importer_for_edge(edge: dict) -> dict | None:
        source_file = str(edge.get("source_file", ""))
        return record_by_source.get(source_file)

    edges_to_drop: set[int] = set()
    for edge in all_edges:
        module_name = edge.get("gleam_module")
        if not isinstance(module_name, str):
            continue
        importer = importer_for_edge(edge)
        if importer is None:
            continue
        resolution, target_module = select_module(importer, module_name)
        symbol_kind = edge.get("gleam_symbol_kind")

        if edge.get("relation") == "imports" and symbol_kind is None:
            if resolution == "resolved" and target_module is not None:
                edge["target"] = target_module["file_node"]["id"]
            continue

        if symbol_kind is not None:
            if resolution == "ambiguous":
                if edge.get("relation") == "references":
                    edges_to_drop.add(id(edge))
                continue
            if resolution != "resolved" or target_module is None:
                continue
            import_name = str(edge.get("gleam_import_name", ""))
            candidates = symbol_candidates(target_module, import_name, str(symbol_kind))
            if len(candidates) == 1:
                edge["target"] = candidates[0]["id"]

    if edges_to_drop:
        all_edges[:] = [edge for edge in all_edges if id(edge) not in edges_to_drop]

    existing_call_pairs = {
        (edge.get("source"), edge.get("target"))
        for edge in all_edges
        if edge.get("relation") == "calls"
    }

    for importer in file_records:
        imports_by_alias: dict[str, list[dict]] = {}
        symbols_by_local_name: dict[str, list[tuple[dict, dict]]] = {}
        for import_info in importer["imports"]:
            if not isinstance(import_info, dict):
                continue
            alias = import_info.get("module_alias")
            if isinstance(alias, str):
                imports_by_alias.setdefault(alias, []).append(import_info)
            for symbol in import_info.get("symbols", []):
                if not isinstance(symbol, dict):
                    continue
                local_name = symbol.get("local_name")
                if isinstance(local_name, str):
                    symbols_by_local_name.setdefault(local_name, []).append((import_info, symbol))

        for raw_call in importer["result"].get("raw_calls", []):
            if raw_call.get("language") != "gleam":
                continue
            callee = raw_call.get("callee")
            receiver = raw_call.get("receiver")
            target_node = None

            if isinstance(receiver, str):
                matched_imports = imports_by_alias.get(receiver, [])
                if len(matched_imports) != 1:
                    continue
                import_info = matched_imports[0]
                resolution, target_module = select_module(importer, import_info["module"])
                if resolution != "resolved" or target_module is None:
                    continue
                candidates = symbol_candidates(target_module, str(callee), "callable")
                if len(candidates) == 1:
                    target_node = candidates[0]
            else:
                bindings = symbols_by_local_name.get(str(callee), [])
                if len(bindings) != 1:
                    continue
                import_info, symbol = bindings[0]
                resolution, target_module = select_module(importer, import_info["module"])
                if resolution != "resolved" or target_module is None:
                    continue
                symbol_kind = str(symbol.get("kind", "value"))
                if symbol_kind not in {"value", "constructor"}:
                    continue
                requested_kind = "constructor" if symbol_kind == "constructor" else "callable"
                candidates = symbol_candidates(
                    target_module,
                    str(symbol.get("name", callee)),
                    requested_kind,
                )
                if len(candidates) == 1:
                    target_node = candidates[0]

            if target_node is None:
                continue
            caller_id = raw_call.get("caller_nid")
            target_id = target_node["id"]
            pair = (caller_id, target_id)
            if caller_id == target_id or pair in existing_call_pairs:
                continue
            existing_call_pairs.add(pair)
            all_edges.append(
                {
                    "source": caller_id,
                    "target": target_id,
                    "relation": "calls",
                    "context": "call",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": raw_call.get("source_file", ""),
                    "source_location": raw_call.get("source_location"),
                    "weight": 1.0,
                }
            )

    for edge in all_edges:
        for key in list(edge):
            if key.startswith("gleam_"):
                edge.pop(key, None)

    referenced_node_ids = {
        endpoint
        for edge in all_edges
        for endpoint in (edge.get("source"), edge.get("target"))
        if isinstance(endpoint, str)
    }
    seen_stub_ids: set[str] = set()
    cleaned_nodes: list[dict] = []
    for node in all_nodes:
        is_stub = not node.get("source_file") and node.get("type") in _GLEAM_STUB_TYPES
        if not is_stub:
            cleaned_nodes.append(node)
            continue
        node_id = node.get("id")
        if node_id not in referenced_node_ids or node_id in seen_stub_ids:
            continue
        seen_stub_ids.add(node_id)
        cleaned_nodes.append(node)
    all_nodes[:] = cleaned_nodes
