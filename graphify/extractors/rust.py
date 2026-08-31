"""Rust extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations


from pathlib import Path
from graphify.extractors.base import _LANGUAGE_BUILTIN_GLOBALS, _file_stem, _make_id, _read_text


def _rust_collect_type_refs(node, source: bytes, generic: bool, out: list[tuple[str, str]]) -> None:
    """Walk a Rust type expression; append (name, role) tuples."""
    if node is None:
        return
    t = node.type
    if t == "primitive_type":
        return
    if t == "type_identifier":
        text = _read_text(node, source)
        if text:
            out.append((text, "generic_arg" if generic else "type"))
        return
    if t == "scoped_type_identifier":
        text = _read_text(node, source).rsplit("::", 1)[-1]
        if text:
            out.append((text, "generic_arg" if generic else "type"))
        return
    if t == "generic_type":
        name_node = node.child_by_field_name("type")
        if name_node is None:
            for c in node.children:
                if c.type in ("type_identifier", "scoped_type_identifier"):
                    name_node = c
                    break
        if name_node is not None:
            text = _read_text(name_node, source).rsplit("::", 1)[-1]
            if text:
                out.append((text, "generic_arg" if generic else "type"))
        for c in node.children:
            if c.type == "type_arguments":
                for arg in c.children:
                    if arg.is_named:
                        _rust_collect_type_refs(arg, source, True, out)
        return
    if t in ("reference_type", "pointer_type", "array_type", "tuple_type", "slice_type"):
        for c in node.children:
            if c.is_named:
                _rust_collect_type_refs(c, source, generic, out)
        return
    if node.is_named:
        for c in node.children:
            if c.is_named:
                _rust_collect_type_refs(c, source, generic, out)

_RUST_TRAIT_METHOD_BLOCKLIST: frozenset[str] = frozenset({
    "new", "default", "parse", "from_str", "now", "clone", "into", "from",
    "to_string", "to_owned", "len", "is_empty", "iter", "next", "build",
    "start", "run", "init", "app", "get", "set", "push", "pop", "insert",
    "remove", "contains", "collect", "map", "filter", "unwrap", "expect",
    "ok", "err", "some", "none", "send", "recv", "lock", "read", "write",
})

def extract_rust(path: Path) -> dict:
    """Extract functions, structs, enums, traits, impl methods, and use declarations from a .rs file."""
    try:
        import tree_sitter_rust as tsrust
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-rust not installed"}

    try:
        language = Language(tsrust.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    function_bodies: list[tuple[str, object]] = []

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
        nid = _make_id(stem, name)
        if nid in seen_ids:
            return nid
        nid = _make_id(name)
        if nid not in seen_ids:
            # The name isn't defined in this file, so this is a cross-file reference
            # (e.g. a `Thing` type annotation imported from another module). Emit a
            # SOURCELESS stub — like the inheritance-base path below — so the
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

    def emit_param_return_refs(func_node, func_nid: str, line: int) -> None:
        params = func_node.child_by_field_name("parameters")
        if params is not None:
            for p in params.children:
                if p.type != "parameter":
                    continue
                type_node = p.child_by_field_name("type")
                refs: list[tuple[str, str]] = []
                _rust_collect_type_refs(type_node, source, False, refs)
                for ref_name, role in refs:
                    ctx = "generic_arg" if role == "generic_arg" else "parameter_type"
                    tgt = ensure_named_node(ref_name, line)
                    if tgt != func_nid:
                        add_edge(func_nid, tgt, "references", line, context=ctx)
        return_type = func_node.child_by_field_name("return_type")
        if return_type is not None:
            refs = []
            _rust_collect_type_refs(return_type, source, False, refs)
            for ref_name, role in refs:
                ctx = "generic_arg" if role == "generic_arg" else "return_type"
                tgt = ensure_named_node(ref_name, line)
                if tgt != func_nid:
                    add_edge(func_nid, tgt, "references", line, context=ctx)

    def walk(node, parent_impl_nid: str | None = None) -> None:
        t = node.type

        if t == "function_item":
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                if parent_impl_nid:
                    func_nid = _make_id(parent_impl_nid, func_name)
                    add_node(func_nid, f".{func_name}()", line)
                    add_edge(parent_impl_nid, func_nid, "method", line)
                else:
                    func_nid = _make_id(stem, func_name)
                    add_node(func_nid, f"{func_name}()", line)
                    add_edge(file_nid, func_nid, "contains", line)
                emit_param_return_refs(node, func_nid, line)
                body = node.child_by_field_name("body")
                if body:
                    function_bodies.append((func_nid, body))
            return

        if t in ("struct_item", "enum_item", "trait_item"):
            name_node = node.child_by_field_name("name")
            if name_node:
                item_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                item_nid = _make_id(stem, item_name)
                add_node(item_nid, item_name, line)
                add_edge(file_nid, item_nid, "contains", line)
                if t == "trait_item":
                    for c in node.children:
                        if c.type != "trait_bounds":
                            continue
                        for sub in c.children:
                            if not sub.is_named:
                                continue
                            refs: list[tuple[str, str]] = []
                            _rust_collect_type_refs(sub, source, False, refs)
                            for idx, (ref_name, _role) in enumerate(refs):
                                tgt = ensure_named_node(ref_name, line)
                                if tgt == item_nid:
                                    continue
                                rel = "inherits" if idx == 0 else "references"
                                if rel == "inherits":
                                    add_edge(item_nid, tgt, "inherits", line)
                                else:
                                    add_edge(item_nid, tgt, "references", line,
                                             context="generic_arg")
                if t == "struct_item":
                    for c in node.children:
                        if c.type != "field_declaration_list":
                            continue
                        for field in c.children:
                            if field.type != "field_declaration":
                                continue
                            type_node = field.child_by_field_name("type")
                            if type_node is None:
                                for fc in field.children:
                                    if fc.type in ("type_identifier", "generic_type",
                                                    "scoped_type_identifier",
                                                    "reference_type", "primitive_type"):
                                        type_node = fc
                                        break
                            refs = []
                            _rust_collect_type_refs(type_node, source, False, refs)
                            for ref_name, role in refs:
                                ctx = "generic_arg" if role == "generic_arg" else "field"
                                tgt = ensure_named_node(ref_name, field.start_point[0] + 1)
                                if tgt != item_nid:
                                    add_edge(item_nid, tgt, "references",
                                             field.start_point[0] + 1, context=ctx)
                    # Tuple structs (`struct Wrapper(pub Logger, Config);`) nest their
                    # positional field types directly under ordered_field_declaration_list
                    # with no field_declaration wrapper -- the same shape handled for tuple
                    # enum variants below. Without this branch these field type references
                    # are silently dropped.
                    for c in node.children:
                        if c.type != "ordered_field_declaration_list":
                            continue
                        fline = c.start_point[0] + 1
                        for tc in c.children:
                            if tc.type not in ("type_identifier", "generic_type",
                                               "scoped_type_identifier", "reference_type",
                                               "primitive_type", "tuple_type", "array_type"):
                                continue
                            refs = []
                            _rust_collect_type_refs(tc, source, False, refs)
                            for ref_name, role in refs:
                                ctx = "generic_arg" if role == "generic_arg" else "field"
                                tgt = ensure_named_node(ref_name, fline)
                                if tgt != item_nid:
                                    add_edge(item_nid, tgt, "references", fline, context=ctx)
                if t == "enum_item":
                    # Variant payload types nest under enum_variant_list ->
                    # enum_variant -> ordered_field_declaration_list (tuple variant,
                    # `Click(Logger)`) | field_declaration_list (struct variant,
                    # `Resize { size: Dim }`). Neither was traversed, so every
                    # enum-variant type reference was silently dropped.
                    _TYPE_NODES = ("type_identifier", "generic_type",
                                   "scoped_type_identifier", "reference_type",
                                   "primitive_type", "tuple_type", "array_type")

                    def _emit_enum_type(type_node, at_line):
                        if type_node is None:
                            return
                        refs2: list[tuple[str, str]] = []
                        _rust_collect_type_refs(type_node, source, False, refs2)
                        for ref_name, role in refs2:
                            ctx = "generic_arg" if role == "generic_arg" else "field"
                            tgt = ensure_named_node(ref_name, at_line)
                            if tgt != item_nid:
                                add_edge(item_nid, tgt, "references", at_line, context=ctx)

                    for c in node.children:
                        if c.type != "enum_variant_list":
                            continue
                        for variant in c.children:
                            if variant.type != "enum_variant":
                                continue
                            vline = variant.start_point[0] + 1
                            for vc in variant.children:
                                if vc.type == "ordered_field_declaration_list":
                                    for tc in vc.children:
                                        if tc.type in _TYPE_NODES:
                                            _emit_enum_type(tc, vline)
                                elif vc.type == "field_declaration_list":
                                    for field in vc.children:
                                        if field.type != "field_declaration":
                                            continue
                                        type_node = field.child_by_field_name("type")
                                        _emit_enum_type(type_node, field.start_point[0] + 1)
            return

        if t == "impl_item":
            type_node = node.child_by_field_name("type")
            trait_node = node.child_by_field_name("trait")
            impl_nid: str | None = None
            if type_node:
                type_name = _read_text(type_node, source).strip()
                impl_nid = _make_id(stem, type_name)
                add_node(impl_nid, type_name, node.start_point[0] + 1)
            if trait_node is not None and impl_nid is not None:
                refs: list[tuple[str, str]] = []
                _rust_collect_type_refs(trait_node, source, False, refs)
                for idx, (ref_name, _role) in enumerate(refs):
                    tgt = ensure_named_node(ref_name, node.start_point[0] + 1)
                    if tgt == impl_nid:
                        continue
                    if idx == 0:
                        add_edge(impl_nid, tgt, "implements", node.start_point[0] + 1)
                    else:
                        add_edge(impl_nid, tgt, "references", node.start_point[0] + 1,
                                 context="generic_arg")
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    walk(child, parent_impl_nid=impl_nid)
            return

        if t == "use_declaration":
            arg = node.child_by_field_name("argument")
            if arg:
                raw = _read_text(arg, source)
                clean = raw.split("{")[0].rstrip(":").rstrip("*").rstrip(":")
                module_name = clean.split("::")[-1].strip()
                if module_name:
                    tgt_nid = _make_id(module_name)
                    add_edge(file_nid, tgt_nid, "imports_from", node.start_point[0] + 1, context="import")
            return

        for child in node.children:
            walk(child, parent_impl_nid=None)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []

    def walk_calls(node, caller_nid: str) -> None:
        if node.type == "function_item":
            return
        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            callee_name: str | None = None
            is_member_call: bool = False
            is_scoped_call: bool = False
            if func_node:
                if func_node.type == "identifier":
                    callee_name = _read_text(func_node, source)
                elif func_node.type == "field_expression":
                    is_member_call = True
                    field = func_node.child_by_field_name("field")
                    if field:
                        callee_name = _read_text(field, source)
                elif func_node.type == "scoped_identifier":
                    # Type::method() — still allow in-file EXTRACTED match, but
                    # skip cross-file resolution: bare last-segment lookup ignores
                    # crate boundaries and produces spurious INFERRED edges (#908).
                    is_scoped_call = True
                    name = func_node.child_by_field_name("name")
                    if name:
                        callee_name = _read_text(name, source)
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
                elif not is_scoped_call and callee_name.lower() not in _RUST_TRAIT_METHOD_BLOCKLIST:
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
