"""Go extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations


from pathlib import Path
from graphify.extractors.base import _LANGUAGE_BUILTIN_GLOBALS, _file_stem, _make_id, _read_text


_GO_PREDECLARED_TYPES = frozenset({
    "bool", "byte", "complex64", "complex128", "error", "float32", "float64",
    "int", "int8", "int16", "int32", "int64", "rune", "string",
    "uint", "uint8", "uint16", "uint32", "uint64", "uintptr", "any", "comparable",
})

def _go_collect_type_refs(node, source: bytes, generic: bool, out: list[tuple[str, str]]) -> None:
    """Walk a Go type expression; append (name, role) tuples."""
    if node is None:
        return
    t = node.type
    if t == "type_identifier":
        text = _read_text(node, source)
        if text and text not in _GO_PREDECLARED_TYPES:
            out.append((text, "generic_arg" if generic else "type"))
        return
    if t == "qualified_type":
        text = _read_text(node, source).rsplit(".", 1)[-1]
        if text and text not in _GO_PREDECLARED_TYPES:
            out.append((text, "generic_arg" if generic else "type"))
        return
    if t == "generic_type":
        type_field = node.child_by_field_name("type")
        if type_field is not None:
            sub: list[tuple[str, str]] = []
            _go_collect_type_refs(type_field, source, generic, sub)
            out.extend(sub)
        for c in node.children:
            if c.type == "type_arguments":
                for arg in c.children:
                    if arg.is_named:
                        _go_collect_type_refs(arg, source, True, out)
        return
    if t in ("pointer_type", "slice_type", "array_type", "map_type",
             "channel_type", "parenthesized_type"):
        for c in node.children:
            if c.is_named:
                _go_collect_type_refs(c, source, generic, out)
        return
    if node.is_named:
        for c in node.children:
            if c.is_named:
                _go_collect_type_refs(c, source, generic, out)

def extract_go(path: Path) -> dict:
    """Extract functions, methods, type declarations, and imports from a .go file."""
    try:
        import tree_sitter_go as tsgo
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-go not installed"}

    try:
        language = Language(tsgo.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    # Use directory name as package scope so methods on the same type across
    # multiple files in a package share one canonical type node.
    pkg_scope = path.parent.name or stem
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    function_bodies: list[tuple[str, object]] = []
    go_imported_pkgs: set[str] = set()  # local names of imported packages

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            })

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None) -> None:
        edge = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def ensure_named_node(name: str, line: int) -> str:
        nid = _make_id(pkg_scope, name)
        if nid in seen_ids:
            return nid
        nid = _make_id(name)
        if nid not in seen_ids:
            # The name isn't declared in this file, so this is a cross-file reference
            # (e.g. a type defined in another file of the package). Emit a SOURCELESS
            # stub — like the inheritance-base path in the other extractors — so the
            # corpus-level rewire can collapse it onto the real definition. A sourced
            # stub here makes _disambiguate_colliding_node_ids bake the referencing
            # file's path (with extension) into the id and blocks the rewire, which is
            # the phantom-duplicate-node bug (#1402).
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": name,
                "file_type": "code",
                "source_file": "",
                "source_location": "",
                "origin_file": str_path,
            })
        return nid

    def emit_go_method_refs(func_node, func_nid: str, line: int) -> None:
        params = func_node.child_by_field_name("parameters")
        if params is not None:
            for p in params.children:
                if p.type != "parameter_declaration":
                    continue
                type_node = p.child_by_field_name("type")
                refs: list[tuple[str, str]] = []
                _go_collect_type_refs(type_node, source, False, refs)
                for ref_name, role in refs:
                    ctx = "generic_arg" if role == "generic_arg" else "parameter_type"
                    tgt = ensure_named_node(ref_name, line)
                    if tgt != func_nid:
                        add_edge(func_nid, tgt, "references", line, context=ctx)
        result = func_node.child_by_field_name("result")
        if result is not None:
            if result.type == "parameter_list":
                for p in result.children:
                    if p.type != "parameter_declaration":
                        continue
                    type_node = p.child_by_field_name("type")
                    if type_node is None:
                        for c in p.children:
                            if c.is_named:
                                type_node = c
                                break
                    refs = []
                    _go_collect_type_refs(type_node, source, False, refs)
                    for ref_name, role in refs:
                        ctx = "generic_arg" if role == "generic_arg" else "return_type"
                        tgt = ensure_named_node(ref_name, line)
                        if tgt != func_nid:
                            add_edge(func_nid, tgt, "references", line, context=ctx)
            else:
                refs = []
                _go_collect_type_refs(result, source, False, refs)
                for ref_name, role in refs:
                    ctx = "generic_arg" if role == "generic_arg" else "return_type"
                    tgt = ensure_named_node(ref_name, line)
                    if tgt != func_nid:
                        add_edge(func_nid, tgt, "references", line, context=ctx)

    def walk(node) -> None:
        t = node.type

        if t == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                func_nid = _make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge(file_nid, func_nid, "contains", line)
                emit_go_method_refs(node, func_nid, line)
                body = node.child_by_field_name("body")
                if body:
                    function_bodies.append((func_nid, body))
            return

        if t == "method_declaration":
            receiver = node.child_by_field_name("receiver")
            receiver_type: str | None = None
            if receiver:
                for param in receiver.children:
                    if param.type == "parameter_declaration":
                        type_node = param.child_by_field_name("type")
                        if type_node:
                            receiver_type = _read_text(type_node, source).lstrip("*").strip()
                        break
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            method_name = _read_text(name_node, source)
            line = node.start_point[0] + 1

            if receiver_type:
                parent_nid = _make_id(pkg_scope, receiver_type)
                add_node(parent_nid, receiver_type, line)
                method_nid = _make_id(parent_nid, method_name)
                add_node(method_nid, f".{method_name}()", line)
                add_edge(parent_nid, method_nid, "method", line)
            else:
                method_nid = _make_id(stem, method_name)
                add_node(method_nid, f"{method_name}()", line)
                add_edge(file_nid, method_nid, "contains", line)

            emit_go_method_refs(node, method_nid, line)
            body = node.child_by_field_name("body")
            if body:
                function_bodies.append((method_nid, body))
            return

        if t == "type_declaration":
            for child in node.children:
                if child.type != "type_spec":
                    continue
                name_node = child.child_by_field_name("name")
                if not name_node:
                    continue
                type_name = _read_text(name_node, source)
                line = child.start_point[0] + 1
                type_nid = _make_id(pkg_scope, type_name)
                add_node(type_nid, type_name, line)
                add_edge(file_nid, type_nid, "contains", line)
                # Type body: struct fields (with embeds) or interface embedding.
                type_body = None
                for tc in child.children:
                    if tc.type in ("struct_type", "interface_type"):
                        type_body = tc
                        break
                if type_body is None:
                    continue
                if type_body.type == "struct_type":
                    for fdl in type_body.children:
                        if fdl.type != "field_declaration_list":
                            continue
                        for field in fdl.children:
                            if field.type != "field_declaration":
                                continue
                            has_name = any(
                                fc.type == "field_identifier" for fc in field.children
                            )
                            type_node = field.child_by_field_name("type")
                            if type_node is None:
                                for fc in field.children:
                                    if fc.is_named and fc.type != "field_identifier":
                                        type_node = fc
                                        break
                            refs: list[tuple[str, str]] = []
                            _go_collect_type_refs(type_node, source, False, refs)
                            for ref_name, role in refs:
                                tgt = ensure_named_node(ref_name, field.start_point[0] + 1)
                                if tgt == type_nid:
                                    continue
                                if not has_name and role == "type":
                                    add_edge(type_nid, tgt, "embeds",
                                             field.start_point[0] + 1)
                                else:
                                    ctx = "generic_arg" if role == "generic_arg" else "field"
                                    add_edge(type_nid, tgt, "references",
                                             field.start_point[0] + 1, context=ctx)
                elif type_body.type == "interface_type":
                    for elem in type_body.children:
                        if elem.type != "type_elem":
                            continue
                        refs = []
                        for sub in elem.children:
                            if sub.is_named:
                                _go_collect_type_refs(sub, source, False, refs)
                        for ref_name, role in refs:
                            tgt = ensure_named_node(ref_name, elem.start_point[0] + 1)
                            if tgt == type_nid:
                                continue
                            if role == "type":
                                add_edge(type_nid, tgt, "embeds",
                                         elem.start_point[0] + 1)
                            else:
                                add_edge(type_nid, tgt, "references",
                                         elem.start_point[0] + 1, context="generic_arg")
            return

        if t == "import_declaration":
            for child in node.children:
                if child.type == "import_spec_list":
                    for spec in child.children:
                        if spec.type == "import_spec":
                            path_node = spec.child_by_field_name("path")
                            if path_node:
                                raw = _read_text(path_node, source).strip('"')
                                # Prefix with go_pkg_ so stdlib names (e.g. "context")
                                # don't collide with local files of the same basename.
                                tgt_nid = _make_id("go", "pkg", raw)
                                add_edge(file_nid, tgt_nid, "imports_from", spec.start_point[0] + 1, context="import")
                                # Track local name (alias or last path segment)
                                alias = spec.child_by_field_name("name")
                                local_name = _read_text(alias, source) if alias else raw.split("/")[-1]
                                if local_name and local_name != "_" and local_name != ".":
                                    go_imported_pkgs.add(local_name)
                elif child.type == "import_spec":
                    path_node = child.child_by_field_name("path")
                    if path_node:
                        raw = _read_text(path_node, source).strip('"')
                        tgt_nid = _make_id("go", "pkg", raw)
                        add_edge(file_nid, tgt_nid, "imports_from", child.start_point[0] + 1, context="import")
                        alias = child.child_by_field_name("name")
                        local_name = _read_text(alias, source) if alias else raw.split("/")[-1]
                        if local_name and local_name != "_" and local_name != ".":
                            go_imported_pkgs.add(local_name)
            return

        for child in node.children:
            walk(child)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []

    def walk_calls(node, caller_nid: str) -> None:
        if node.type in ("function_declaration", "method_declaration"):
            return
        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            callee_name: str | None = None
            is_member_call: bool = False
            if func_node:
                if func_node.type == "identifier":
                    callee_name = _read_text(func_node, source)
                elif func_node.type == "selector_expression":
                    field = func_node.child_by_field_name("field")
                    operand = func_node.child_by_field_name("operand")
                    receiver_name = _read_text(operand, source) if operand else ""
                    # Package-qualified call (e.g. fmt.Println) → allow cross-file resolution.
                    # Receiver method call (e.g. s.logger.Log) → skip, no import evidence.
                    is_member_call = receiver_name not in go_imported_pkgs
                    if field:
                        callee_name = _read_text(field, source)
            if callee_name and callee_name not in _LANGUAGE_BUILTIN_GLOBALS:
                tgt_nid = label_to_nid.get(callee_name)
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "calls",
                            "context": "call",
                            "confidence": "EXTRACTED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 1.0,
                        })
                elif callee_name:
                    raw_calls.append({
                        "caller_nid": caller_nid,
                        "callee": callee_name,
                        "is_member_call": is_member_call,
                        "source_file": str_path,
                        "source_location": f"L{node.start_point[0] + 1}",
                    })
        for child in node.children:
            walk_calls(child, caller_nid)

    for caller_nid, body_node in function_bodies:
        walk_calls(body_node, caller_nid)

    valid_ids = seen_ids
    clean_edges = []
    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        if src in valid_ids and (tgt in valid_ids or edge["relation"] in ("imports", "imports_from")):
            clean_edges.append(edge)

    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
